"""
O.R.I.O.N — Model Router (v0.3.0 Sprint 2)

Motor de Dynamic Auto-Routing para seleção autônoma do modelo de
inferência com base no tier de complexidade cognitiva do turno.

Suporta dois modos de operação:
  - AUTO: Classifica o prompt e roteia para o modelo ótimo do tier.
  - FIXED: Respeita estritamente o modelo escolhido pelo usuário.

Integra o ComplexityClassifier (Sprint 2) e o ModelRegistry (Sprint 1)
para compor a decisão de roteamento de forma determinística e auditável.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from orion.gateway.classifier import ClassificationResult, ComplexityClassifier
from orion.gateway.models import ComplexityTier, LLMMessage
from orion.gateway.registry import ModelRegistry


# ---------------------------------------------------------------------------
# Enumerações e Contratos de Roteamento
# ---------------------------------------------------------------------------


class RoutingMode(str, Enum):
    """Modo de operação do roteador.

    AUTO: O roteador classifica automaticamente a complexidade e escolhe
          o modelo ideal. O usuário pode alterar via linguagem natural.
    FIXED: O roteador usa o modelo configurado pelo usuário, ignorando
           a classificação de complexidade.
    """

    AUTO = "auto"
    FIXED = "fixed"


@dataclass(frozen=True)
class RoutingDecision:
    """Decisão de roteamento produzida pelo ModelRouter.

    Attributes:
        selected_model: ID canônico do modelo escolhido (ex: 'anthropic/claude-haiku-3-5').
        complexity: Tier de complexidade determinado para o turno.
        mode: Modo de operação (AUTO ou FIXED) que gerou esta decisão.
        reason: Justificativa legível por humanos da seleção.
        confidence: Confiança da classificação de complexidade (0.0–1.0).
    """

    selected_model: str
    complexity: ComplexityTier
    mode: RoutingMode
    reason: str
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if not self.selected_model:
            raise ValueError("selected_model cannot be empty")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")


# ---------------------------------------------------------------------------
# Mapeamentos Padrão de Tier → Modelo
# ---------------------------------------------------------------------------

# Modelo padrão para cada tier — pode ser sobrescrito na configuração do router.
# Escolhas priorizando custo-benefício e latência por tier.
DEFAULT_TIER_MODELS: dict[ComplexityTier, str] = {
    ComplexityTier.FAST: "google/gemini-2.0-flash-lite",
    ComplexityTier.BALANCED: "google/gemini-2.0-flash",
    ComplexityTier.HEAVY: "anthropic/claude-sonnet-4-5",
}


# ---------------------------------------------------------------------------
# Padrões de Linguagem Natural para Alternância de Modo
# ---------------------------------------------------------------------------

# Padrões que ativam o modo AUTO via linguagem natural
_PATTERN_SET_AUTO = re.compile(
    r"""
    \b(
        switch\s+to\s+(auto|automatic|auto\s+mode)
        | use\s+auto\s+routing
        | enable\s+auto\s*(routing|mode)?
        | modo\s+autom[aá]tico
        | altern[ea]\s+para\s+o?\s*modo\s+autom[aá]tico
        | ativar?\s+roteamento\s+autom[aá]tico
        | voltar?\s+(ao?|para\s+o?)\s+auto
        | set\s+mode\s+to\s+auto
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Padrões que ativam o modo FIXED e capturam o modelo alvo
_PATTERN_SET_FIXED = re.compile(
    r"""
    \b(
        fix\s*(e|o)?\s+(on|in|to|no|em|ao?)\s+(?P<model1>[\w\-./]+)
        | use\s+(?P<model2>[\w\-./]+)\s+(model|modelo)?
        | switch\s+to\s+(?P<model3>[\w\-./]+)
        | altern[ea]\s+para\s+(?P<model4>[\w\-./]+)
        | fixar?\s+(n[oa]|em|ao?)\s+(?P<model5>[\w\-./]+)
        | set\s+model\s+to\s+(?P<model6>[\w\-./]+)
        | force\s+(?P<model7>[\w\-./]+)
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Atalhos de linguagem natural para nomes canônicos de modelo
_MODEL_ALIASES: dict[str, str] = {
    # Claude
    "claude opus": "anthropic/claude-opus-4-5",
    "claude sonnet": "anthropic/claude-sonnet-4-5",
    "claude haiku": "anthropic/claude-haiku-3-5",
    "opus": "anthropic/claude-opus-4-5",
    "sonnet": "anthropic/claude-sonnet-4-5",
    "haiku": "anthropic/claude-haiku-3-5",
    # Gemini
    "gemini pro": "google/gemini-2.5-pro",
    "gemini flash": "google/gemini-2.0-flash",
    "gemini flash lite": "google/gemini-2.0-flash-lite",
    "flash": "google/gemini-2.0-flash",
    "flash lite": "google/gemini-2.0-flash-lite",
    "gemini": "google/gemini-2.0-flash",
    # GPT
    "gpt4": "openai/gpt-4o",
    "gpt-4o": "openai/gpt-4o",
    "gpt4o": "openai/gpt-4o",
    # DeepSeek
    "deepseek": "deepseek/deepseek-r1",
    "r1": "deepseek/deepseek-r1",
    # Mistral
    "mistral": "mistralai/mistral-small-3.1",
    # Qwen
    "qwen": "qwen/qwen-2.5-72b-instruct",
}


# ---------------------------------------------------------------------------
# Model Router
# ---------------------------------------------------------------------------


class ModelRouter:
    """Motor de roteamento dinâmico de modelos para o ORION Gateway.

    Seleciona automaticamente o modelo de inferência mais adequado para
    cada turno, balanceando qualidade da resposta e custo operacional.

    Exemplos de uso:
        >>> registry = ModelRegistry()
        >>> router = ModelRouter(registry=registry)
        >>> decision = router.route("List all Python files in src/")
        >>> decision.selected_model
        'google/gemini-2.0-flash-lite'
        >>> decision.complexity
        <ComplexityTier.FAST: 'fast'>

        >>> decision = router.route("/plan Refactor the auth layer to use JWT")
        >>> decision.selected_model
        'anthropic/claude-sonnet-4-5'
        >>> decision.complexity
        <ComplexityTier.HEAVY: 'heavy'>
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        classifier: Optional[ComplexityClassifier] = None,
        tier_models: Optional[dict[ComplexityTier, str]] = None,
        default_mode: RoutingMode = RoutingMode.AUTO,
        fixed_model: Optional[str] = None,
    ) -> None:
        """Inicializa o roteador.

        Args:
            registry: Catálogo de modelos (cria um padrão se None).
            classifier: Classificador de complexidade (cria um padrão se None).
            tier_models: Mapeamento tier→modelo customizado (usa padrão se None).
            default_mode: Modo inicial de operação (AUTO ou FIXED).
            fixed_model: Modelo fixo inicial (usado quando mode=FIXED).
        """
        self._registry = registry or ModelRegistry()
        self._classifier = classifier or ComplexityClassifier()
        self._tier_models: dict[ComplexityTier, str] = dict(
            tier_models or DEFAULT_TIER_MODELS
        )
        self._mode: RoutingMode = default_mode
        self._fixed_model: Optional[str] = fixed_model

        # Valida o modelo fixo inicial, se fornecido
        if self._fixed_model and self._fixed_model not in self._registry:
            raise ValueError(
                f"fixed_model {self._fixed_model!r} not found in registry. "
                f"Available: {self._registry.ids()}"
            )

        # Valida modelos padrão de tier
        for tier, model_id in self._tier_models.items():
            if model_id not in self._registry:
                raise ValueError(
                    f"Tier model for {tier.value!r} ({model_id!r}) not found in registry."
                )

    # ── Propriedades de estado ─────────────────────────────────────────────

    @property
    def mode(self) -> RoutingMode:
        """Modo de operação atual do roteador."""
        return self._mode

    @property
    def fixed_model(self) -> Optional[str]:
        """Modelo fixo atual (relevante apenas no modo FIXED)."""
        return self._fixed_model

    # ── API Pública ─────────────────────────────────────────────────────────

    def route(
        self,
        prompt: str,
        history: Optional[list[LLMMessage]] = None,
    ) -> RoutingDecision:
        """Produz a decisão de roteamento para o turno atual.

        O método:
        1. Tenta detectar intenção de mudança de modo via linguagem natural.
        2. No modo FIXED, retorna imediatamente o modelo configurado.
        3. No modo AUTO, classifica a complexidade e seleciona o modelo.

        Args:
            prompt: Texto do turno atual do usuário.
            history: Histórico de mensagens do contexto (opcional).

        Returns:
            ``RoutingDecision`` com modelo selecionado, tier e justificativa.

        Raises:
            ValueError: Se o modelo fixo configurado não existir no registry.
        """
        history = history or []

        # ── Detecção de mudança de modo via linguagem natural ─────────────
        mode_change = self._detect_mode_change(prompt)
        if mode_change is not None:
            new_mode, new_fixed_model = mode_change
            self._mode = new_mode
            if new_fixed_model:
                self._fixed_model = new_fixed_model

        # ── Modo FIXED: bypass do classificador ──────────────────────────
        if self._mode == RoutingMode.FIXED:
            return self._route_fixed(prompt)

        # ── Modo AUTO: classificação + seleção por tier ──────────────────
        return self._route_auto(prompt, history)

    def set_mode(self, mode: RoutingMode, fixed_model: Optional[str] = None) -> None:
        """Alterna o modo de operação programaticamente.

        Args:
            mode: Novo modo (AUTO ou FIXED).
            fixed_model: Modelo alvo para o modo FIXED (obrigatório se mode=FIXED).

        Raises:
            ValueError: Se mode=FIXED e fixed_model não fornecido ou inválido.
        """
        if mode == RoutingMode.FIXED:
            if not fixed_model:
                raise ValueError("fixed_model is required when setting mode to FIXED.")
            resolved = self._resolve_alias(fixed_model)
            if resolved not in self._registry:
                raise ValueError(
                    f"Model {fixed_model!r} (resolved: {resolved!r}) not found in registry."
                )
            self._fixed_model = resolved
        self._mode = mode

    def set_tier_model(self, tier: ComplexityTier, model_id: str) -> None:
        """Configura o modelo padrão para um tier específico.

        Args:
            tier: Tier a ser atualizado.
            model_id: ID canônico do modelo no registry.

        Raises:
            ValueError: Se o model_id não existir no registry.
        """
        if model_id not in self._registry:
            raise ValueError(f"Model {model_id!r} not found in registry.")
        self._tier_models[tier] = model_id

    # ── Roteamento Interno ──────────────────────────────────────────────────

    def _route_fixed(self, prompt: str) -> RoutingDecision:
        """Roteamento no modo FIXED — usa o modelo configurado sem classificar."""
        if not self._fixed_model:
            raise ValueError(
                "RoutingMode.FIXED is active but no fixed_model was configured. "
                "Call set_mode(RoutingMode.FIXED, fixed_model=...) first."
            )
        spec = self._registry.require(self._fixed_model)
        return RoutingDecision(
            selected_model=self._fixed_model,
            complexity=spec.default_tier,
            mode=RoutingMode.FIXED,
            reason=(
                f"Modo FIXED ativo: usuário fixou no modelo '{spec.name}'. "
                "Classificador de complexidade ignorado."
            ),
            confidence=1.0,
        )

    def _route_auto(
        self,
        prompt: str,
        history: list[LLMMessage],
    ) -> RoutingDecision:
        """Roteamento no modo AUTO — classifica e seleciona o modelo do tier."""
        classification: ClassificationResult = self._classifier.classify(
            prompt=prompt, history=history
        )
        tier = classification.tier
        model_id = self._tier_models[tier]
        spec = self._registry.require(model_id)
        return RoutingDecision(
            selected_model=model_id,
            complexity=tier,
            mode=RoutingMode.AUTO,
            reason=(
                f"Modo AUTO: tier={tier.value} → {spec.name}. "
                f"Classificação: {classification.reason}"
            ),
            confidence=classification.confidence,
        )

    # ── Detecção de Mudança de Modo ─────────────────────────────────────────

    def _detect_mode_change(
        self, prompt: str
    ) -> Optional[tuple[RoutingMode, Optional[str]]]:
        """Detecta intenção de mudança de modo na linguagem natural.

        Returns:
            Tupla (novo_modo, modelo_fixo) ou None se não detectado.
        """
        prompt_lower = prompt.lower()

        # Checar comando para modo AUTO
        if _PATTERN_SET_AUTO.search(prompt_lower):
            return (RoutingMode.AUTO, None)

        # Checar comando para modo FIXED + captura do modelo
        match = _PATTERN_SET_FIXED.search(prompt_lower)
        if match:
            # Recuperar o grupo de modelo não-None
            raw_model: str = next(
                (v for v in match.groupdict().values() if v is not None),
                "",
            )
            if raw_model:
                resolved = self._resolve_alias(raw_model.strip())
                if resolved in self._registry:
                    return (RoutingMode.FIXED, resolved)
                # Modelo não reconhecido — ignorar a mudança silenciosamente
                # (evita falsos positivos em prompts de código)

        return None

    @staticmethod
    def _resolve_alias(name: str) -> str:
        """Resolve aliases de linguagem natural para IDs canônicos do registry."""
        name_lower = name.lower().strip()
        if name_lower in _MODEL_ALIASES:
            return _MODEL_ALIASES[name_lower]
        return name
