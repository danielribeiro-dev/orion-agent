"""
O.R.I.O.N — Failover Anthropic -> OpenRouter -> Ollama (v0.5.0 Sprint 1, CA-11)

Regra central: NUNCA trocar em silêncio para um modelo inferior.

  - Candidato "equi-tier" (mesmo modelo via OpenRouter): permitido, sempre com evento visível.
  - Candidato "downgrade" (tier menor ou modelo local): só com autorização explícita
    (``allow_downgrade``; o fallback local é opt-in). Mesmo autorizado, o breaker é
    aberto antes (HEAVY -> SAFE_HOLDING) e o PEP bloqueia mutações: o modelo leve serve
    apenas ao diálogo até o modelo de topo voltar.
  - Sem autorização, a falha sobe como ``DowngradeBlockedError`` com instruções claras.

O breaker só "abre" quando TODOS os candidatos equi-tier falharam (``trip``); qualquer
sucesso equi-tier o fecha (``reset``), então o SAFE_HOLDING não fica preso.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from orion.gateway.circuit_breaker import CircuitBreaker, CircuitState, FailureReason
from orion.gateway.errors import (
    DowngradeBlockedError,
    FailoverExhaustedError,
    GatewayError,
    ProviderAPIError,
    ProviderConnectionError,
    ProviderTimeoutError,
    RateLimitError,
    StreamInterruptedError,
)
from orion.gateway.models import (
    ComplexityTier,
    LLMRequest,
    LLMResponse,
    LLMResponseChunk,
    ModelSpec,
    ProviderName,
)
from orion.gateway.providers.base import BaseLLMProvider, StreamAccumulator
from orion.gateway.registry import ModelRegistry

logger = logging.getLogger(__name__)

_TIER_RANK = {ComplexityTier.FAST: 0, ComplexityTier.BALANCED: 1, ComplexityTier.HEAVY: 2}


@dataclass(frozen=True)
class FailoverCandidate:
    """Um destino possível: provider + modelo na API deste provider."""

    spec: ModelSpec  # identidade e preço (ledger)
    provider: BaseLLMProvider
    wire_model: str
    provider_name: ProviderName
    downgrade: bool = False


@dataclass(frozen=True)
class ServedBy:
    """Quem de fato atendeu (para o ledger e a barra de status)."""

    provider: ProviderName
    pricing_model: str
    wire_model: str
    downgrade: bool


@dataclass(frozen=True)
class FailoverEvent:
    """Notificação visível de troca de destino (o TUI deve exibi-la)."""

    from_model: str
    to_model: str
    to_provider: ProviderName
    reason: FailureReason
    downgrade: bool
    detail: str


def classify_exception(exc: BaseException) -> FailureReason:
    if isinstance(exc, RateLimitError):
        return FailureReason.RATE_LIMIT
    if isinstance(exc, ProviderTimeoutError):
        return FailureReason.TIMEOUT
    if isinstance(exc, ProviderConnectionError):
        return FailureReason.NETWORK_OFFLINE
    if isinstance(exc, ProviderAPIError):
        code = exc.status_code or 0
        if code in (401, 403):
            return FailureReason.AUTH_ERROR
        if code == 402:
            return FailureReason.BUDGET_EXCEEDED
        if code >= 500:
            return FailureReason.SERVER_ERROR
    return FailureReason.UNKNOWN


def is_failover_worthy(exc: BaseException) -> bool:
    """Falha do provedor/rede (troca de destino ajuda). 400/404/413 são bugs da requisição."""
    if isinstance(exc, StreamInterruptedError):
        return False
    if isinstance(exc, (ProviderTimeoutError, ProviderConnectionError)):
        return True
    if isinstance(exc, ProviderAPIError):
        code = exc.status_code or 0
        return code in (401, 402, 403, 408, 409, 429) or code >= 500
    return False


def build_candidates(
    primary: ModelSpec,
    registry: ModelRegistry,
    native: BaseLLMProvider,
    openrouter: Callable[[], BaseLLMProvider] | None = None,
    local: Callable[[ModelSpec], BaseLLMProvider] | None = None,
) -> list[FailoverCandidate]:
    """Cadeia: nativo -> mesmo modelo no OpenRouter -> melhor modelo local (downgrade)."""
    chain = [FailoverCandidate(primary, native, primary.id, primary.provider)]
    if openrouter is not None and primary.openrouter_id:
        chain.append(
            FailoverCandidate(primary, openrouter(), primary.openrouter_id, ProviderName.OPENROUTER)
        )
    if local is not None:
        locals_ = sorted(registry.local_models(), key=lambda m: _TIER_RANK[m.default_tier])
        if locals_:
            best = locals_[-1]
            chain.append(
                FailoverCandidate(best, local(best), best.id, ProviderName.OLLAMA, downgrade=True)
            )
    return chain


class FailoverProvider(BaseLLMProvider):
    """Provider composto que aplica a cadeia de failover com as regras acima."""

    def __init__(
        self,
        candidates: list[FailoverCandidate],
        breaker: CircuitBreaker | None = None,
        allow_downgrade: bool = False,
        on_event: Callable[[FailoverEvent], None] | None = None,
    ) -> None:
        if not candidates:
            raise ValueError("FailoverProvider exige ao menos um candidato")
        self._candidates = candidates
        self._breaker = breaker
        self._allow_downgrade = allow_downgrade
        self._on_event = on_event
        self.served: ServedBy | None = None

    def _downgrade_permitted(self) -> bool:
        return self._allow_downgrade

    def _emit(self, ev: FailoverEvent) -> None:
        logger.warning("Failover: %s -> %s (%s)", ev.from_model, ev.to_model, ev.reason.value)
        if self._on_event:
            try:
                self._on_event(ev)
            except Exception:  # noqa: BLE001
                logger.exception("Failover: erro no callback on_event")

    def _request_for(self, request: LLMRequest, cand: FailoverCandidate) -> LLMRequest:
        updates: dict[str, Any] = {"model": cand.wire_model}
        if cand is not self._candidates[0]:
            # extra_params do primário são específicos do provider; thinking/tools não
            # existem nos destinos legados (a Sprint 2 cuida do tool use ali).
            updates["extra_params"] = (
                {"usage": {"include": True}} if cand.provider_name == ProviderName.OPENROUTER else {}
            )
        return request.model_copy(update=updates)

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:
        primary = self._candidates[0]
        last_exc: Exception | None = None
        last_reason = FailureReason.UNKNOWN
        equi_failed = False  # algum candidato do mesmo nível falhou nesta chamada
        prev_label = primary.wire_model

        for idx, cand in enumerate(self._candidates):
            if cand.downgrade and not self._downgrade_permitted():
                raise DowngradeBlockedError(
                    f"{primary.spec.name} indisponível ({last_reason.value}) e o único destino "
                    f"restante é inferior ({cand.spec.name}). Nenhum downgrade silencioso: "
                    "autorize o fallback local (ORION_ALLOW_DOWNGRADE=1) ou aguarde a volta do serviço."
                ) from last_exc
            if cand.downgrade and equi_failed and self._breaker is not None:
                # Todos os equi-tier falharam: abre o circuito (HEAVY -> SAFE_HOLDING)
                # ANTES de servir o modelo leve, para o PEP já bloquear mutações.
                self._breaker.trip(last_reason, primary.spec.id)
            if idx > 0:
                self._emit(
                    FailoverEvent(
                        prev_label, cand.wire_model, cand.provider_name, last_reason,
                        cand.downgrade, str(last_exc),
                    )
                )
            yielded = False
            try:
                async for chunk in cand.provider.stream(self._request_for(request, cand)):
                    yielded = True
                    yield chunk
            except GatewayError as exc:
                if yielded or not is_failover_worthy(exc):
                    raise
                last_exc, last_reason = exc, classify_exception(exc)
                prev_label = cand.wire_model
                if not cand.downgrade:
                    equi_failed = True
                continue

            self.served = ServedBy(cand.provider_name, cand.spec.id, cand.wire_model, cand.downgrade)
            if self._breaker is not None and not cand.downgrade:
                if self._breaker.state != CircuitState.CLOSED:
                    self._breaker.reset()  # serviço de topo voltou
                else:
                    self._breaker.record_success()
            return

        if equi_failed and self._breaker is not None:
            self._breaker.trip(last_reason, primary.spec.id)
        raise FailoverExhaustedError(
            f"Todos os destinos falharam; último erro: {last_exc}"
        ) from last_exc

    async def complete(self, request: LLMRequest) -> LLMResponse:
        import time

        t0 = time.monotonic()
        acc = StreamAccumulator()
        async for chunk in self.stream(request):
            acc.feed(chunk)
        served = self.served
        assert served is not None
        return acc.build(served.wire_model, served.provider, (time.monotonic() - t0) * 1000.0, request)

    @property
    def provider_name(self) -> str:
        return "Failover"
