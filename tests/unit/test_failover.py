"""Failover Anthropic -> OpenRouter -> Ollama sem downgrade silencioso (CA-11)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from orion.gateway.circuit_breaker import CircuitBreaker, CircuitState
from orion.gateway.credentials import inspect_anthropic_key, load_anthropic_key
from orion.gateway.errors import (
    DowngradeBlockedError,
    FailoverExhaustedError,
    ProviderAPIError,
    ProviderConnectionError,
    StreamInterruptedError,
)
from orion.gateway.failover import FailoverEvent, FailoverProvider, build_candidates
from orion.gateway.models import (
    ComplexityTier,
    LLMMessage,
    LLMRequest,
    LLMResponseChunk,
    MessageRole,
    ProviderName,
)
from orion.gateway.providers.base import BaseLLMProvider
from orion.gateway.registry import ModelRegistry


class Fake(BaseLLMProvider):
    def __init__(self, text: str = "", error: Exception | None = None, partial: bool = False) -> None:
        self.text, self.error, self.partial, self.calls = text, error, partial, []

    async def complete(self, request: LLMRequest) -> Any:  # pragma: no cover
        raise NotImplementedError

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[override]
        self.calls.append(request.model)
        if self.partial:
            yield LLMResponseChunk(delta="meio")
        if self.error:
            raise self.error
        yield LLMResponseChunk(delta=self.text)
        yield LLMResponseChunk(is_final=True)


def req(model: str = "claude-opus-5-5") -> LLMRequest:
    return LLMRequest(model=model, messages=[LLMMessage(role=MessageRole.USER, content="x")])


async def run(p: FailoverProvider) -> str:
    return "".join([c.delta async for c in p.stream(req())])


def chain(native: Fake, router: Fake | None, local: Fake | None, model: str = "claude-opus-5-5"):
    reg = ModelRegistry()
    return build_candidates(
        reg.require(model), reg, native,
        openrouter=(lambda: router) if router else None,
        local=(lambda spec: local) if local else None,
    )


def breaker(tier: ComplexityTier = ComplexityTier.HEAVY, lite: bool = False) -> CircuitBreaker:
    return CircuitBreaker("claude-opus-5-5", tier, intentional_lite_mode=lite)


DOWN = ProviderAPIError("overloaded", status_code=529)


async def test_primary_ok_no_event() -> None:
    events: list[FailoverEvent] = []
    p = FailoverProvider(chain(Fake("a"), Fake("b"), Fake("c")), breaker(), on_event=events.append)
    assert await run(p) == "a"
    assert events == [] and p.served and p.served.provider == ProviderName.ANTHROPIC


async def test_equi_tier_failover_is_visible_and_uses_openrouter_slug() -> None:
    events: list[FailoverEvent] = []
    router = Fake("via-or")
    b = breaker()
    p = FailoverProvider(chain(Fake(error=DOWN), router, Fake("local")), b, on_event=events.append)
    assert await run(p) == "via-or"
    assert router.calls == ["anthropic/claude-opus-5-5"]
    assert len(events) == 1 and not events[0].downgrade
    assert p.served and p.served.provider == ProviderName.OPENROUTER
    assert p.served.pricing_model == "claude-opus-5-5"  # tarifa do modelo, não do local
    assert b.state == CircuitState.CLOSED and not b.is_mutation_blocked()


async def test_no_silent_downgrade_when_only_local_remains() -> None:
    local = Fake("local")
    b = breaker()
    p = FailoverProvider(chain(Fake(error=DOWN), Fake(error=DOWN), local), b)
    with pytest.raises(DowngradeBlockedError, match="Nenhum downgrade silencioso"):
        await run(p)
    assert local.calls == []  # o modelo inferior nunca foi chamado


async def test_explicit_allow_downgrade() -> None:
    events: list[FailoverEvent] = []
    b = breaker()
    p = FailoverProvider(chain(Fake(error=DOWN), None, Fake("local")), b, allow_downgrade=True, on_event=events.append)
    assert await run(p) == "local"
    assert events[-1].downgrade  # sempre visível
    assert p.served and p.served.provider == ProviderName.OLLAMA and p.served.downgrade
    # modelo leve só para diálogo: breaker abriu antes e o PEP bloqueia mutações
    assert b.state == CircuitState.SAFE_HOLDING and b.is_mutation_blocked()


async def test_recovery_closes_safe_holding() -> None:
    from orion.gateway.circuit_breaker import FailureReason

    b = breaker()
    b.trip(FailureReason.SERVER_ERROR)
    assert b.state == CircuitState.SAFE_HOLDING
    assert await run(FailoverProvider(chain(Fake("volta"), None, None), b)) == "volta"
    assert b.state == CircuitState.CLOSED


async def test_lite_primary_does_not_enter_safe_holding() -> None:
    b = CircuitBreaker("claude-haiku-5-5", ComplexityTier.FAST)
    p = FailoverProvider(chain(Fake(error=DOWN), None, Fake("l"), "claude-haiku-5-5"), b)
    with pytest.raises(DowngradeBlockedError):
        await run(p)
    assert not b.is_mutation_blocked()


async def test_mid_stream_failure_is_not_failed_over() -> None:
    router = Fake("outro")
    p = FailoverProvider(chain(Fake(error=StreamInterruptedError("cortou"), partial=True), router, None), breaker())
    got: list[str] = []
    with pytest.raises(StreamInterruptedError):
        async for c in p.stream(req()):
            got.append(c.delta)
    assert got == ["meio"] and router.calls == []


async def test_bad_request_is_not_failed_over() -> None:
    router = Fake("x")
    p = FailoverProvider(chain(Fake(error=ProviderAPIError("ruim", status_code=400)), router, None), breaker())
    with pytest.raises(ProviderAPIError):
        await run(p)
    assert router.calls == []


async def test_all_fail_without_local_is_exhausted() -> None:
    err = ProviderConnectionError("off")
    p = FailoverProvider(chain(Fake(error=err), Fake(error=err), None), breaker())
    with pytest.raises(FailoverExhaustedError):
        await run(p)


async def test_no_openrouter_key_skips_to_policy() -> None:
    p = FailoverProvider(chain(Fake(error=DOWN), None, Fake("l")), breaker())
    with pytest.raises(DowngradeBlockedError):
        await run(p)


async def test_complete_uses_chain() -> None:
    p = FailoverProvider(chain(Fake(error=DOWN), Fake("ok"), None), breaker())
    resp = await p.complete(req())
    assert resp.content == "ok" and resp.provider == ProviderName.OPENROUTER


def test_empty_chain_rejected() -> None:
    with pytest.raises(ValueError):
        FailoverProvider([])


# ── Credenciais ───────────────────────────────────────────────────────────────


def test_key_env_wins_over_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "anthropic_api_key").write_text("sk-ant-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
    assert load_anthropic_key(tmp_path) == "sk-ant-env"
    assert inspect_anthropic_key(tmp_path).source == "env"


def test_key_file_permissions_and_format(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    f = tmp_path / "anthropic_api_key"
    assert inspect_anthropic_key(tmp_path).found is False
    f.write_text("sk-ant-abc")
    f.chmod(0o644)
    st = inspect_anthropic_key(tmp_path)
    assert st.found and st.file_too_open and not st.ok and "chmod 600" in st.detail
    f.chmod(0o600)
    assert inspect_anthropic_key(tmp_path).ok
    f.write_text("lixo")
    assert not inspect_anthropic_key(tmp_path).well_formed
