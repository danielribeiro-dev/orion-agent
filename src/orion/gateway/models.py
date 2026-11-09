"""
O.R.I.O.N — Gateway Data Models (v0.3.0 Sprint 1)

Contratos Pydantic v2 imutáveis para requisições, respostas, chunks de
streaming e especificações de modelos no Model Registry.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ---------------------------------------------------------------------------
# Enumerações
# ---------------------------------------------------------------------------


class MessageRole(StrEnum):
    """Papéis válidos de mensagem no contexto de inferência."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ProviderName(StrEnum):
    """Provedores de inferência suportados pelo Gateway."""

    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


class ComplexityTier(StrEnum):
    """Tiers de complexidade de turno para Dynamic Auto-Routing (Sprint 2)."""

    FAST = "fast"       # Comandos rotineiros, busca, resposta curta
    BALANCED = "balanced"  # Raciocínio médio, código padrão
    HEAVY = "heavy"     # Arquitetura, refactoring, raciocínio profundo


# ---------------------------------------------------------------------------
# Tokens & Uso
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    """Contagem detalhada de tokens de uma chamada de inferência."""

    model_config = {"frozen": True}

    prompt_tokens: int = Field(
        default=0,
        ge=0,
        description="Tokens de entrada TOTAIS (inclui cache lido e escrito)",
    )
    completion_tokens: int = Field(default=0, ge=0, description="Tokens gerados (completion)")
    cached_tokens: int = Field(default=0, ge=0, description="Tokens lidos do cache (prompt caching)")
    reasoning_tokens: int = Field(default=0, ge=0, description="Tokens de raciocínio interno (thinking)")
    cache_write_tokens: int = Field(
        default=0,
        ge=0,
        description="Tokens escritos no cache de prompt (cobrança maior; já contidos em prompt_tokens)",
    )
    total_tokens: int = Field(default=0, ge=0, description="Total: prompt + completion")

    def model_post_init(self, __context: object) -> None:
        """Garante que total_tokens seja consistente se não fornecido."""
        # total_tokens é calculado externamente; este model é frozen (imutável)



# ---------------------------------------------------------------------------
# Content Blocks (ADR-021)
# ---------------------------------------------------------------------------


class CacheControl(BaseModel):
    """Ponto de cache de prompt (``cache_control`` da Messages API)."""

    model_config = {"frozen": True}

    type: Literal["ephemeral"] = "ephemeral"
    ttl: Literal["5m", "1h"] | None = Field(default=None, description="TTL; None = padrão do provedor (5m)")


class ContentBlock(BaseModel):
    """Bloco tipado de conteúdo de mensagem (formato neutro, espelha a Messages API).

    Campos por tipo:
      - ``text``: ``text``
      - ``thinking``: ``thinking`` + ``signature`` (deve voltar intacto em turnos seguintes)
      - ``redacted_thinking``: ``data``
      - ``tool_use``: ``id``, ``name``, ``input``
      - ``tool_result``: ``tool_use_id``, ``content``, ``is_error``
      - ``image``: ``source`` (``{"type": "base64", "media_type": ..., "data": ...}``)
    """

    model_config = {"frozen": True}

    type: Literal["text", "thinking", "redacted_thinking", "tool_use", "tool_result", "image"]
    text: str | None = None
    thinking: str | None = None
    signature: str | None = None
    data: str | None = None
    id: str | None = None
    name: str | None = None
    input: dict[str, Any] | None = None
    tool_use_id: str | None = None
    content: str | list[ContentBlock] | None = None
    is_error: bool = False
    source: dict[str, Any] | None = None
    cache_control: CacheControl | None = None

    @model_validator(mode="after")
    def _check_required(self) -> ContentBlock:
        required: dict[str, tuple[str, ...]] = {
            "text": ("text",),
            "thinking": ("thinking",),
            "redacted_thinking": ("data",),
            "tool_use": ("id", "name", "input"),
            "tool_result": ("tool_use_id",),
            "image": ("source",),
        }
        missing = [f for f in required[self.type] if getattr(self, f) is None]
        if missing:
            raise ValueError(f"ContentBlock '{self.type}' exige: {', '.join(missing)}")
        return self

    # ── Fábricas ──
    @classmethod
    def of_text(cls, text: str, cache_control: CacheControl | None = None) -> ContentBlock:
        return cls(type="text", text=text, cache_control=cache_control)

    @classmethod
    def of_tool_use(cls, id: str, name: str, input: dict[str, Any]) -> ContentBlock:
        return cls(type="tool_use", id=id, name=name, input=input)

    @classmethod
    def of_tool_result(
        cls, tool_use_id: str, content: str | list[ContentBlock], is_error: bool = False
    ) -> ContentBlock:
        return cls(type="tool_result", tool_use_id=tool_use_id, content=content, is_error=is_error)


ContentBlock.model_rebuild()


def flatten_content(content: str | list[ContentBlock]) -> str:
    """Adaptador de compatibilidade: reduz blocos a texto para providers legados.

    ``thinking`` é descartado; ``tool_use``/``tool_result`` viram texto marcado
    (os providers legados não têm tool use estruturado — vide Sprint 2).
    """
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for b in content:
        if b.type == "text":
            parts.append(b.text or "")
        elif b.type == "tool_use":
            parts.append(f"[tool_use {b.name} {b.input}]")
        elif b.type == "tool_result":
            inner = b.content if isinstance(b.content, str) else flatten_content(b.content or [])
            parts.append(f"[tool_result {b.tool_use_id}{' error' if b.is_error else ''}] {inner}")
        elif b.type == "image":
            parts.append("[image]")
    return "\n".join(p for p in parts if p)


def to_blocks(content: str | list[ContentBlock]) -> list[ContentBlock]:
    """Adaptador de compatibilidade: string legada -> lista de blocos."""
    if isinstance(content, str):
        return [ContentBlock.of_text(content)] if content else []
    return list(content)


class ToolSpec(BaseModel):
    """Definição de tool exposta ao modelo (schema JSON validado)."""

    model_config = {"frozen": True}

    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    strict: bool = False
    cache_control: CacheControl | None = None


class ToolChoice(BaseModel):
    """Política de escolha de tool. ``any``/``tool`` forçados são recusados por alguns modelos Claude 5."""

    model_config = {"frozen": True}

    type: Literal["auto", "any", "tool", "none"] = "auto"
    name: str | None = None
    disable_parallel_tool_use: bool = False

    @model_validator(mode="after")
    def _check_name(self) -> ToolChoice:
        if self.type == "tool" and not self.name:
            raise ValueError("ToolChoice 'tool' exige name")
        return self


class ThinkingConfig(BaseModel):
    """Configuração de thinking/esforço.

    Modelos Claude 5: ``adaptive`` (+ ``effort``); ``enabled``/``budget_tokens``
    só existe para modelos legados e é rejeitado (400) pela API nos novos.
    """

    model_config = {"frozen": True}

    type: Literal["adaptive", "enabled", "disabled"] = "adaptive"
    budget_tokens: int | None = Field(default=None, ge=1024)
    display: Literal["summarized", "omitted"] | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None


# ---------------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------------


class LLMMessage(BaseModel):
    """Mensagem individual no histórico de contexto para inferência."""

    model_config = {"frozen": True}

    role: MessageRole = Field(description="Papel da mensagem no diálogo")
    content: str | list[ContentBlock] = Field(
        description="Texto (legado) ou lista de ContentBlock (ADR-021)"
    )
    reasoning_content: str | None = Field(
        default=None,
        description="Conteúdo de raciocínio interno (apenas em mensagens do assistant com thinking)",
    )
    name: str | None = Field(
        default=None,
        description="Nome opcional do participante (útil para tool calls)",
    )

    @property
    def text(self) -> str:
        """Conteúdo reduzido a texto (adaptador para providers/estimadores legados)."""
        return flatten_content(self.content)

    @property
    def blocks(self) -> list[ContentBlock]:
        """Conteúdo como lista de blocos."""
        return to_blocks(self.content)


# ---------------------------------------------------------------------------
# Requisição
# ---------------------------------------------------------------------------


class LLMRequest(BaseModel):
    """Requisição normalizada para qualquer provedor de inferência.

    Agnóstica de provedor: cada ``BaseLLMProvider`` traduz este contrato
    para o formato de API específico do seu backend.
    """

    model_config = {"frozen": True}

    model: str = Field(description="ID canônico do modelo no registry (ex: 'anthropic/claude-3-5-sonnet')")
    messages: list[LLMMessage] = Field(description="Histórico de mensagens do turno")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperatura de amostragem")
    max_tokens: int = Field(default=4096, ge=1, le=200_000, description="Teto de tokens gerados")
    stream: bool = Field(default=True, description="Usar streaming SSE se suportado pelo provedor")
    complexity_tier: ComplexityTier = Field(
        default=ComplexityTier.BALANCED,
        description="Tier de complexidade para registro e roteamento",
    )
    extra_params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parâmetros extras passados diretamente ao provedor (ex: top_p, seed)",
    )
    system: str | list[ContentBlock] | None = Field(
        default=None, description="System prompt estruturado (blocos podem levar cache_control)"
    )
    tools: list[ToolSpec] = Field(default_factory=list, description="Tools expostas ao modelo")
    tool_choice: ToolChoice | None = None
    thinking: ThinkingConfig | None = None
    cache_control: CacheControl | None = Field(
        default=None, description="Cache automático do prefixo (nível de requisição)"
    )


# ---------------------------------------------------------------------------
# Chunk de Streaming
# ---------------------------------------------------------------------------


class LLMResponseChunk(BaseModel):
    """Delta incremental recebido durante streaming SSE.

    Emitido pelo ``BaseLLMProvider.stream()`` a cada evento SSE recebido.
    O chunk final (``is_final=True``) carrega o ``usage`` completo.
    """

    model_config = {"frozen": True}

    delta: str = Field(default="", description="Fragmento de texto do completion")
    reasoning_delta: str | None = Field(
        default=None,
        description="Fragmento de raciocínio interno (thinking), se suportado",
    )
    block: ContentBlock | None = Field(
        default=None,
        description=(
            "Bloco COMPLETO finalizado (text/thinking/tool_use), na ordem do modelo. "
            "Os deltas servem à renderização ao vivo; os blocos, à montagem da mensagem."
        ),
    )
    stop_reason: str | None = Field(
        default=None, description="end_turn, tool_use, max_tokens, refusal... (chunk final)"
    )
    is_final: bool = Field(default=False, description="Indica o último chunk do stream")
    usage: TokenUsage | None = Field(
        default=None,
        description="Métricas de uso — presentes apenas no chunk final",
    )
    notice: str | None = Field(
        default=None,
        description="Aviso do provider ao usuário (ex.: modelo local sem suporte a tools)",
    )


# ---------------------------------------------------------------------------
# Resposta Completa
# ---------------------------------------------------------------------------


class LLMResponse(BaseModel):
    """Resposta completa de uma chamada de inferência (modo não-streaming).

    Também é o objeto agregado ao final de um stream completo.
    """

    model_config = {"frozen": True}

    content: str = Field(description="Conteúdo completo gerado pelo modelo")
    reasoning_content: str | None = Field(
        default=None,
        description="Raciocínio interno completo (thinking), se disponível",
    )
    blocks: list[ContentBlock] = Field(default_factory=list, description="Blocos completos, em ordem")
    stop_reason: str | None = None
    model: str = Field(description="ID do modelo que gerou a resposta")
    provider: ProviderName = Field(description="Provedor que atendeu a requisição")
    usage: TokenUsage = Field(description="Contagem detalhada de tokens")
    latency_ms: float = Field(ge=0.0, description="Latência total da chamada em milissegundos")
    complexity_tier: ComplexityTier = Field(
        default=ComplexityTier.BALANCED,
        description="Tier de complexidade do turno associado",
    )


# ---------------------------------------------------------------------------
# Especificação de Modelo (Model Registry)
# ---------------------------------------------------------------------------


class ModelSpec(BaseModel):
    """Metadados e custos de um modelo no catálogo do Model Registry."""

    model_config = {"frozen": True}

    id: str = Field(description="ID canônico do modelo (ex: 'anthropic/claude-3-5-sonnet')")
    name: str = Field(description="Nome legível por humanos (ex: 'Claude 3.5 Sonnet')")
    provider: ProviderName = Field(description="Provedor primário do modelo")
    context_window: int = Field(ge=1024, description="Janela de contexto máxima em tokens")
    cost_input_m: float = Field(
        ge=0.0,
        description="Custo por 1 milhão de tokens de entrada (USD)",
    )
    cost_output_m: float = Field(
        ge=0.0,
        description="Custo por 1 milhão de tokens de saída (USD)",
    )
    supports_thinking: bool = Field(
        default=False,
        description="Suporta raciocínio interno estendido (extended thinking / CoT nativo)",
    )
    default_tier: ComplexityTier = Field(
        default=ComplexityTier.BALANCED,
        description="Tier de complexidade padrão para roteamento automático",
    )
    is_local: bool = Field(
        default=False,
        description="Modelo local (Ollama). Custo zero; não requer internet.",
    )
    openrouter_id: str | None = Field(
        default=None,
        description="Slug equivalente no OpenRouter (failover do mesmo modelo, sem downgrade)",
    )
    supports_prompt_cache: bool = Field(
        default=False,
        description="O provedor aplica cache de prefixo do prompt (ADR-031: capability flag)",
    )
    supports_tool_use: bool = Field(
        default=True,
        description="Aceita tool use estruturado; sem isso o modelo não serve a subagents",
    )
    cache_read_cost_m: float | None = Field(
        default=None,
        ge=0.0,
        description="Custo absoluto/1M de tokens lidos do cache; None = input * desconto padrão",
    )
