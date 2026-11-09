"""Gateway de modelos para subagents (Sprint 6, ADR-031).

Duas peças reaproveitadas pela sessão principal (``AgentSession._llm``) e pelos filhos:

* :func:`build_llm_request` — monta a ``LLMRequest`` (camadas de cache do system, thinking, extras).
* :func:`consume_stream` — lê o stream do provedor e devolve blocos tipados + uso.

E o adaptador :class:`AgentGateway`, que implementa ``ModelGatewayPort`` para o núcleo de
agentes: resolve *tier/perfil* em modelo (sem downgrade silencioso) e entrega um ``llm`` que
**nunca** toca o circuit breaker, o renderer, a status bar nem os contadores da sessão — só o
ledger (com ``origin`` e ``agent_id``) e o ``on_usage`` do chamador.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from orion.agents.models import ResolvedModel
from orion.agents.ports import LLMPort, NoSuitableModel
from orion.core.engine import LAYER_BREAK, ModelTurn, split_layers
from orion.gateway.budget import BudgetGuard
from orion.gateway.ledger import CostLedger
from orion.gateway.models import (
    CacheControl,
    ComplexityTier,
    ContentBlock,
    LLMMessage,
    LLMRequest,
    LLMResponseChunk,
    MessageRole,
    ModelSpec,
    ProviderName,
    ThinkingConfig,
    TokenUsage,
    ToolSpec,
)
from orion.gateway.providers.base import BaseLLMProvider
from orion.gateway.registry import ModelRegistry
from orion.gateway.router import ModelRouter, NoModelForTier
from orion.timeline.compactor import estimate_tokens

_NON_ANTHROPIC_MAX_TOKENS = 4096


# ---------------------------------------------------------------------------
# Requisição e stream (compartilhados com a sessão principal)
# ---------------------------------------------------------------------------


def build_llm_request(
    spec: ModelSpec,
    tier: ComplexityTier,
    system: str,
    messages: list[LLMMessage],
    tools: list[ToolSpec],
    *,
    max_tokens: int,
    extra_params: dict[str, Any],
    thinking: ThinkingConfig | None,
    volatile_layers: int = 0,
) -> tuple[LLMRequest, list[LLMMessage]]:
    """Monta a requisição. Devolve ``(request, wire_messages)``.

    Anthropic: o system vai em blocos, com o breakpoint de cache no fim das camadas estáveis
    (``volatile_layers`` finais, como avisos de modo plano, ficam fora). Demais provedores:
    system como primeira mensagem.
    """
    anthropic = spec.provider == ProviderName.ANTHROPIC
    if anthropic:
        layers = split_layers(system)
        stable = len(layers) - 1 - (volatile_layers if len(layers) > 1 else 0)
        system_blocks: list[ContentBlock] | None = [
            ContentBlock.of_text(layer, CacheControl() if i == stable else None)
            for i, layer in enumerate(layers)
        ]
        wire = list(messages)
    else:
        system_blocks = None
        wire = [
            LLMMessage(role=MessageRole.SYSTEM, content=system.replace(LAYER_BREAK, "\n\n")),
            *messages,
        ]
    request = LLMRequest(
        model=spec.id,
        messages=wire,
        system=system_blocks,
        tools=tools,
        max_tokens=max_tokens if anthropic else min(max_tokens, _NON_ANTHROPIC_MAX_TOKENS),
        complexity_tier=tier,
        extra_params=extra_params,
        thinking=thinking,
        cache_control=CacheControl() if anthropic else None,
    )
    return request, wire


@dataclass
class StreamedTurn:
    """O que um stream completo entregou."""

    blocks: list[ContentBlock] = field(default_factory=list)
    text: str = ""
    reasoning_chars: int = 0
    usage: TokenUsage | None = None
    stop_reason: str | None = None

    def to_model_turn(self) -> ModelTurn:
        blocks = list(self.blocks)
        if not any(b.type == "text" for b in blocks) and self.text.strip():
            # Providers legados só emitem deltas: monta o bloco de texto a partir deles.
            blocks.insert(0, ContentBlock.of_text(self.text))
        return ModelTurn(blocks=blocks, stop_reason=self.stop_reason or "end_turn")


async def consume_stream(
    provider: BaseLLMProvider,
    request: LLMRequest,
    *,
    on_reasoning: Callable[[str], None] | None = None,
    on_text: Callable[[str], None] | None = None,
    on_notice: Callable[[str], None] | None = None,
) -> StreamedTurn:
    """Consome ``provider.stream`` acumulando blocos, texto, uso e motivo de parada."""
    out = StreamedTurn()
    chunk: LLMResponseChunk
    async for chunk in provider.stream(request):
        if chunk.reasoning_delta:
            out.reasoning_chars += len(chunk.reasoning_delta)
            if on_reasoning is not None:
                on_reasoning(chunk.reasoning_delta)
        if chunk.delta:
            out.text += chunk.delta
            if on_text is not None:
                on_text(chunk.delta)
        if chunk.block is not None:
            out.blocks.append(chunk.block)
        if chunk.notice and on_notice is not None:
            on_notice(chunk.notice)
        if chunk.stop_reason:
            out.stop_reason = chunk.stop_reason
        if chunk.usage is not None:
            out.usage = chunk.usage
    return out


def estimate_stream_usage(messages: list[LLMMessage], text: str, reasoning_chars: int) -> TokenUsage:
    """Uso estimado quando o provedor não reporta (4 caracteres por token)."""
    prompt_tokens = sum(estimate_tokens(m.text) for m in messages)
    completion = estimate_tokens(text) + reasoning_chars // 4
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion,
        total_tokens=prompt_tokens + completion,
    )


# ---------------------------------------------------------------------------
# Adaptador para o núcleo de agentes
# ---------------------------------------------------------------------------

_TIERS = {"fast": ComplexityTier.FAST, "balanced": ComplexityTier.BALANCED, "heavy": ComplexityTier.HEAVY}


def to_resolved(spec: ModelSpec, tier: ComplexityTier) -> ResolvedModel:
    return ResolvedModel(
        model_id=spec.id,
        tier=tier.value,
        is_local=spec.is_local,
        cost_input_m=spec.cost_input_m,
        cost_output_m=spec.cost_output_m,
        context_window=spec.context_window,
        supports_prompt_cache=spec.supports_prompt_cache,
        supports_tool_use=spec.supports_tool_use,
    )


class AgentGateway:
    """Implementa ``ModelGatewayPort`` sobre registry, router, providers e ledger da sessão."""

    def __init__(
        self,
        *,
        registry: ModelRegistry,
        router: ModelRouter,
        provider_factory: Callable[[ModelSpec], BaseLLMProvider],
        ledger: CostLedger,
        budget: BudgetGuard | None,
        available: Callable[[ModelSpec], bool],
        profiles: Callable[[], dict[str, str]],
        session_id: Callable[[], str],
    ) -> None:
        self._registry = registry
        self._router = router
        self._provider_factory = provider_factory
        self._ledger = ledger
        self._budget = budget
        self._available = available
        self._profiles = profiles
        self._session_id = session_id

    # -- resolução ------------------------------------------------------

    def resolve(
        self,
        *,
        tier: str,
        mutating: bool,
        profile: str | None = None,
        pinned: str | None = None,
        reuse: str | None = None,
    ) -> ResolvedModel:
        try:
            if reuse:
                return self._explicit(reuse, mutating, "the model recorded for this task")
            if pinned:
                return self._explicit(pinned, mutating, "the pinned model")
            effective = tier
            if profile:
                known = self._profiles()
                if profile not in known:
                    raise NoSuitableModel(f"unknown model profile '{profile}'")
                effective = known[profile]
            tier_enum = _TIERS.get(effective)
            if tier_enum is None:
                raise NoSuitableModel(f"unknown tier '{effective}'")
            spec = self._router.resolve_for_agent(tier_enum, mutating=mutating, available=self._available)
            return to_resolved(spec, tier_enum)
        except NoModelForTier as exc:
            raise NoSuitableModel(str(exc)) from exc

    def _explicit(self, model_id: str, mutating: bool, what: str) -> ResolvedModel:
        spec = self._registry.get(model_id)
        if spec is None or not self._available(spec):
            raise NoSuitableModel(f"{what} ('{model_id}') is not available")
        if mutating and (spec.is_local or spec.default_tier == ComplexityTier.FAST):
            raise NoSuitableModel(f"{what} ('{model_id}') is too weak for an agent with mutating tools")
        return to_resolved(spec, spec.default_tier)

    # -- chamadas -------------------------------------------------------

    def make_llm(
        self,
        model: ResolvedModel,
        *,
        agent_id: str,
        origin: str,
        max_tokens: int,
        on_usage: Callable[[ResolvedModel, TokenUsage, float], None],
    ) -> LLMPort:
        tier = _TIERS[model.tier]

        async def llm(*, system: str, messages: list[LLMMessage], tools: list[ToolSpec]) -> ModelTurn:
            spec = self._registry.require(model.model_id)
            if self._budget is not None:
                # Teto diário global: levanta BudgetExceededError (o runner a converte em parcial).
                self._budget.check(is_local_model=spec.is_local)
            request, wire = build_llm_request(
                spec,
                tier,
                system,
                messages,
                tools,
                max_tokens=max_tokens,
                extra_params=self._extra_params(spec),
                thinking=self._thinking(spec),
            )
            started = time.monotonic()
            provider = self._provider_factory(spec)
            streamed = await consume_stream(provider, request)
            usage = streamed.usage or estimate_stream_usage(
                wire if spec.provider != ProviderName.ANTHROPIC
                else [LLMMessage(role=MessageRole.SYSTEM, content=system), *wire],
                streamed.text,
                streamed.reasoning_chars,
            )
            served = getattr(provider, "served", None)
            priced = self._registry.require(served.pricing_model) if served is not None else spec
            record = self._ledger.record_turn_cost(
                provider=served.provider if served is not None else spec.provider,
                model=priced.id,
                usage=usage,
                routing_mode="agent",
                complexity=tier,
                task_id=self._session_id(),
                latency_ms=(time.monotonic() - started) * 1000,
                origin=origin,
                agent_id=agent_id,
            )
            on_usage(to_resolved(priced, tier), usage, record.cost_usd)
            return streamed.to_model_turn()

        return llm

    @staticmethod
    def _extra_params(spec: ModelSpec) -> dict[str, Any]:
        if spec.provider in (ProviderName.OLLAMA, ProviderName.ANTHROPIC):
            return {}
        return {"usage": {"include": True}}

    @staticmethod
    def _thinking(spec: ModelSpec) -> ThinkingConfig | None:
        """Filhos pensam pouco (esforço baixo): a economia de tokens é o objetivo."""
        if spec.provider != ProviderName.ANTHROPIC or not spec.supports_thinking:
            return None
        return ThinkingConfig(type="adaptive", effort="low")

