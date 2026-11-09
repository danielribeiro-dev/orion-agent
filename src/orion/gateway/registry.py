"""
O.R.I.O.N — Model Registry (v0.3.0 Sprint 1)

Catálogo tipado de modelos suportados com metadados de preço,
janela de contexto e capacidades.

Referência de custos (USD/1M tokens — OpenRouter, Out. 2026):
  https://openrouter.ai/models
"""

from __future__ import annotations

from orion.gateway.models import ComplexityTier, ModelSpec, ProviderName

# ---------------------------------------------------------------------------
# Catálogo Oficial de Modelos
# ---------------------------------------------------------------------------

_CATALOG: list[ModelSpec] = [
    # ── CLAUDE 5 NATIVO (API Anthropic — ADR-020) ───────────────────────────
    # Preços: tabela da Anthropic (cache de 06/10/2026). Escrita no cache = 1,25x input.
    # Haiku 5.5: preço vale para prompts até 100K tokens ($0.50/$2.50 acima).
    ModelSpec(
        id="claude-fable-5-1",
        supports_prompt_cache=True,
        name="Claude Fable 5.1",
        provider=ProviderName.ANTHROPIC,
        context_window=1_000_000,
        cost_input_m=10.0,
        cost_output_m=50.0,
        supports_thinking=True,
        default_tier=ComplexityTier.HEAVY,
        openrouter_id="anthropic/claude-fable-5-1",
        cache_read_cost_m=0.25,
    ),
    ModelSpec(
        id="claude-opus-5-5",
        supports_prompt_cache=True,
        name="Claude Opus 5.5",
        provider=ProviderName.ANTHROPIC,
        context_window=1_000_000,
        cost_input_m=4.0,
        cost_output_m=20.0,
        supports_thinking=True,
        default_tier=ComplexityTier.HEAVY,
        openrouter_id="anthropic/claude-opus-5-5",
        cache_read_cost_m=0.2,
    ),
    ModelSpec(
        id="claude-sonnet-5-5",
        supports_prompt_cache=True,
        name="Claude Sonnet 5.5",
        provider=ProviderName.ANTHROPIC,
        context_window=1_000_000,
        cost_input_m=2.0,
        cost_output_m=10.0,
        supports_thinking=True,
        default_tier=ComplexityTier.BALANCED,
        openrouter_id="anthropic/claude-sonnet-5-5",
        cache_read_cost_m=0.2,
    ),
    ModelSpec(
        id="claude-haiku-5-5",
        supports_prompt_cache=True,
        name="Claude Haiku 5.5",
        provider=ProviderName.ANTHROPIC,
        context_window=1_000_000,
        cost_input_m=0.1,
        cost_output_m=0.5,
        supports_thinking=True,
        default_tier=ComplexityTier.FAST,
        openrouter_id="anthropic/claude-haiku-5-5",
        cache_read_cost_m=None,
    ),
    # ── HEAVY FRONTIER ──────────────────────────────────────────────────────
    ModelSpec(
        id="anthropic/claude-opus-4-5",
        name="Claude Opus 4.5",
        provider=ProviderName.OPENROUTER,
        context_window=200_000,
        cost_input_m=15.0,
        cost_output_m=75.0,
        supports_thinking=True,
        default_tier=ComplexityTier.HEAVY,
    ),
    ModelSpec(
        id="anthropic/claude-sonnet-4-5",
        name="Claude Sonnet 4.5",
        provider=ProviderName.OPENROUTER,
        context_window=200_000,
        cost_input_m=3.0,
        cost_output_m=15.0,
        supports_thinking=True,
        default_tier=ComplexityTier.HEAVY,
    ),
    ModelSpec(
        id="google/gemini-2.5-pro",
        name="Gemini 2.5 Pro",
        provider=ProviderName.OPENROUTER,
        context_window=1_000_000,
        cost_input_m=3.5,
        cost_output_m=10.5,
        supports_thinking=True,
        default_tier=ComplexityTier.HEAVY,
    ),
    ModelSpec(
        id="openai/gpt-4o",
        name="GPT-4o",
        provider=ProviderName.OPENROUTER,
        context_window=128_000,
        cost_input_m=5.0,
        cost_output_m=15.0,
        supports_thinking=False,
        default_tier=ComplexityTier.HEAVY,
    ),
    ModelSpec(
        id="deepseek/deepseek-r1",
        name="DeepSeek R1",
        provider=ProviderName.OPENROUTER,
        context_window=128_000,
        cost_input_m=0.55,
        cost_output_m=2.19,
        supports_thinking=True,
        default_tier=ComplexityTier.HEAVY,
    ),
    # ── BALANCED ────────────────────────────────────────────────────────────
    ModelSpec(
        id="anthropic/claude-haiku-3-5",
        name="Claude Haiku 3.5",
        provider=ProviderName.OPENROUTER,
        context_window=200_000,
        cost_input_m=0.8,
        cost_output_m=4.0,
        supports_thinking=False,
        default_tier=ComplexityTier.BALANCED,
    ),
    ModelSpec(
        id="google/gemini-2.0-flash",
        name="Gemini 2.0 Flash",
        provider=ProviderName.OPENROUTER,
        context_window=1_000_000,
        cost_input_m=0.1,
        cost_output_m=0.4,
        supports_thinking=False,
        default_tier=ComplexityTier.BALANCED,
    ),
    ModelSpec(
        id="mistralai/mistral-small-3.1",
        name="Mistral Small 3.1",
        provider=ProviderName.OPENROUTER,
        context_window=128_000,
        cost_input_m=0.1,
        cost_output_m=0.3,
        supports_thinking=False,
        default_tier=ComplexityTier.BALANCED,
    ),
    ModelSpec(
        id="qwen/qwen-2.5-72b-instruct",
        name="Qwen 2.5 72B Instruct",
        provider=ProviderName.OPENROUTER,
        context_window=131_072,
        cost_input_m=0.35,
        cost_output_m=0.4,
        supports_thinking=False,
        default_tier=ComplexityTier.BALANCED,
    ),
    # ── FAST / LITE ─────────────────────────────────────────────────────────
    ModelSpec(
        id="google/gemini-2.0-flash-lite",
        name="Gemini 2.0 Flash Lite",
        provider=ProviderName.OPENROUTER,
        context_window=1_000_000,
        cost_input_m=0.075,
        cost_output_m=0.3,
        supports_thinking=False,
        default_tier=ComplexityTier.FAST,
    ),
    ModelSpec(
        id="anthropic/claude-3-haiku",
        name="Claude 3 Haiku",
        provider=ProviderName.OPENROUTER,
        context_window=200_000,
        cost_input_m=0.25,
        cost_output_m=1.25,
        supports_thinking=False,
        default_tier=ComplexityTier.FAST,
    ),
    # ── LOCAL (OLLAMA — ORION Imortal / Failover) ────────────────────────────
    ModelSpec(
        id="qwen2.5-coder:1.5b",
        name="Qwen2.5 Coder 1.5B (Local)",
        provider=ProviderName.OLLAMA,
        context_window=32_768,
        cost_input_m=0.0,
        cost_output_m=0.0,
        supports_thinking=False,
        default_tier=ComplexityTier.FAST,
        is_local=True,
    ),
    ModelSpec(
        id="qwen2.5-coder:3b",
        name="Qwen2.5 Coder 3B (Local)",
        provider=ProviderName.OLLAMA,
        context_window=32_768,
        cost_input_m=0.0,
        cost_output_m=0.0,
        supports_thinking=False,
        default_tier=ComplexityTier.BALANCED,
        is_local=True,
    ),
    ModelSpec(
        id="qwen2.5-coder:7b",
        name="Qwen2.5 Coder 7B (Local)",
        provider=ProviderName.OLLAMA,
        context_window=32_768,
        cost_input_m=0.0,
        cost_output_m=0.0,
        supports_thinking=False,
        default_tier=ComplexityTier.BALANCED,
        is_local=True,
    ),
]


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------


class ModelRegistry:
    """Catálogo imutável de modelos suportados pelo ORION Gateway.

    Permite consulta por ID, tier, provedor e capacidades.
    O catálogo é um singleton de dados; não persiste estado externo.
    """

    def __init__(self, catalog: list[ModelSpec] | None = None) -> None:
        self._catalog: dict[str, ModelSpec] = {
            m.id: m for m in (catalog or _CATALOG)
        }

    # ── Consultas ─────────────────────────────────────────────────────────

    def get(self, model_id: str) -> ModelSpec | None:
        """Retorna a ``ModelSpec`` pelo ID canônico, ou ``None`` se não encontrado."""
        return self._catalog.get(model_id)

    def require(self, model_id: str) -> ModelSpec:
        """Retorna a ``ModelSpec`` pelo ID ou levanta ``KeyError``."""
        spec = self.get(model_id)
        if spec is None:
            raise KeyError(
                f"Model {model_id!r} not found in registry. "
                f"Available: {list(self._catalog.keys())}"
            )
        return spec

    def all_models(self) -> list[ModelSpec]:
        """Retorna todos os modelos do catálogo."""
        return list(self._catalog.values())

    def by_tier(self, tier: ComplexityTier) -> list[ModelSpec]:
        """Retorna modelos do tier especificado, em ordem de custo crescente."""
        models = [m for m in self._catalog.values() if m.default_tier == tier]
        return sorted(models, key=lambda m: m.cost_output_m)

    def by_provider(self, provider: ProviderName) -> list[ModelSpec]:
        """Retorna modelos de um provedor específico."""
        return [m for m in self._catalog.values() if m.provider == provider]

    def local_models(self) -> list[ModelSpec]:
        """Retorna modelos locais (Ollama) — usados no failover ORION Imortal."""
        return [m for m in self._catalog.values() if m.is_local]

    def cloud_models(self) -> list[ModelSpec]:
        """Retorna modelos em nuvem (não-locais)."""
        return [m for m in self._catalog.values() if not m.is_local]

    def supports_thinking(self) -> list[ModelSpec]:
        """Retorna modelos com suporte a extended thinking / raciocínio interno."""
        return [m for m in self._catalog.values() if m.supports_thinking]

    def ids(self) -> list[str]:
        """Retorna todos os IDs do catálogo."""
        return list(self._catalog.keys())

    def __len__(self) -> int:
        return len(self._catalog)

    def __contains__(self, model_id: str) -> bool:
        return model_id in self._catalog

    def __repr__(self) -> str:
        return f"ModelRegistry({len(self._catalog)} models)"
