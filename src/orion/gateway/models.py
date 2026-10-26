"""
O.R.I.O.N — Gateway Data Models (v0.3.0 Sprint 1)

Contratos Pydantic v2 imutáveis para requisições, respostas, chunks de
streaming e especificações de modelos no Model Registry.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerações
# ---------------------------------------------------------------------------


class MessageRole(str, Enum):
    """Papéis válidos de mensagem no contexto de inferência."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ProviderName(str, Enum):
    """Provedores de inferência suportados pelo Gateway."""

    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"


class ComplexityTier(str, Enum):
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

    prompt_tokens: int = Field(default=0, ge=0, description="Tokens de entrada (prompt)")
    completion_tokens: int = Field(default=0, ge=0, description="Tokens gerados (completion)")
    cached_tokens: int = Field(default=0, ge=0, description="Tokens lidos do cache (prompt caching)")
    reasoning_tokens: int = Field(default=0, ge=0, description="Tokens de raciocínio interno (thinking)")
    total_tokens: int = Field(default=0, ge=0, description="Total: prompt + completion")

    def model_post_init(self, __context: object) -> None:
        """Garante que total_tokens seja consistente se não fornecido."""
        # total_tokens é calculado externamente; este model é frozen (imutável)


# ---------------------------------------------------------------------------
# Mensagens
# ---------------------------------------------------------------------------


class LLMMessage(BaseModel):
    """Mensagem individual no histórico de contexto para inferência."""

    model_config = {"frozen": True}

    role: MessageRole = Field(description="Papel da mensagem no diálogo")
    content: str = Field(description="Conteúdo textual da mensagem")
    reasoning_content: Optional[str] = Field(
        default=None,
        description="Conteúdo de raciocínio interno (apenas em mensagens do assistant com thinking)",
    )
    name: Optional[str] = Field(
        default=None,
        description="Nome opcional do participante (útil para tool calls)",
    )


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
    extra_params: dict = Field(
        default_factory=dict,
        description="Parâmetros extras passados diretamente ao provedor (ex: top_p, seed)",
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
    reasoning_delta: Optional[str] = Field(
        default=None,
        description="Fragmento de raciocínio interno (thinking), se suportado",
    )
    is_final: bool = Field(default=False, description="Indica o último chunk do stream")
    usage: Optional[TokenUsage] = Field(
        default=None,
        description="Métricas de uso — presentes apenas no chunk final",
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
    reasoning_content: Optional[str] = Field(
        default=None,
        description="Raciocínio interno completo (thinking), se disponível",
    )
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
