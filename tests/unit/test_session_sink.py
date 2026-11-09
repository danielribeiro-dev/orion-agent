"""SessionSink (ADR-032): RichSink no terminal, IpcSink no daemon e sessão headless."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orion.core.engine import ModelTurn
from orion.gateway.budget import BudgetExceededError, BudgetGuard, OriginBudgetExceededError
from orion.gateway.ledger import CostLedger
from orion.gateway.models import TokenUsage
from orion.gateway.registry import ModelRegistry
from orion.tui.diff_viewer import diff_texts
from orion.tui.session import AgentSession
from orion.tui.sink import (
    SINK_EVENT,
    IpcSink,
    NullSink,
    RichSink,
    SessionSink,
    apply_sink_event,
)
from tests.unit.test_agent_session import ScriptedProvider


class Recorder:
    """Sink que grava as chamadas recebidas."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> None:
            self.calls.append((name, {"args": args, **kwargs}))

        return record


def roundtrip(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(json.dumps(e)) for e in events]


class TestIpcSink:
    def test_protocol_conformance(self) -> None:
        assert isinstance(NullSink(), SessionSink)
        assert isinstance(IpcSink(lambda e: None), SessionSink)
        assert RichSink.__name__ == "StreamRenderer"

    def test_replay_rebuilds_calls_on_local_sink(self) -> None:
        events: list[dict[str, Any]] = []
        sink = IpcSink(events.append)
        diff = diff_texts("a.txt", "x\n", "y\n")
        sink.begin_thinking()
        sink.add_text("olá ")
        sink.end_message()
        sink.tool_started("read_file", {"path": Path("/tmp/a")}, key="k1")
        sink.tool_finished("edit_file", True, "ok", {"n": 1}, diff, key="k1")
        sink.agent_line("linha", style="accent")
        sink.warn("cuidado")
        sink.error("falhou")
        sink.pause()
        sink.resume()
        sink.close()
        assert all(e["kind"] == SINK_EVENT for e in events)
        local = Recorder()
        applied = [apply_sink_event(local, e) for e in roundtrip(events)]  # type: ignore[arg-type]
        assert all(applied)
        names = [c[0] for c in local.calls]
        assert names == [
            "begin_thinking",
            "add_text",
            "end_message",
            "tool_started",
            "tool_finished",
            "agent_line",
            "warn",
            "error",
            "close",
        ]
        finished = local.calls[4][1]
        assert finished["diff"].path == diff.path
        assert finished["diff"].added == diff.added
        assert local.calls[3][1]["params"] == {"path": "/tmp/a"}

    def test_thinking_only_with_opt_in(self) -> None:
        events: list[dict[str, Any]] = []
        IpcSink(events.append).add_reasoning("segredo")
        assert events == []
        IpcSink(events.append, show_thinking=True).add_reasoning("pensando")
        assert events[0]["method"] == "add_reasoning"

    def test_apply_rejects_unknown_or_foreign_events(self) -> None:
        local = Recorder()
        assert not apply_sink_event(local, {"kind": "other"})  # type: ignore[arg-type]
        assert not apply_sink_event(local, {"kind": SINK_EVENT, "method": "__init__"})  # type: ignore[arg-type]
        assert not apply_sink_event(local, {"kind": SINK_EVENT, "method": "pause"})  # type: ignore[arg-type]
        assert not apply_sink_event(NullSink(), {"kind": SINK_EVENT, "method": "warn", "args": {"x": 1}})
        assert local.calls == []

    def test_null_sink_keeps_text_and_notices(self) -> None:
        sink = NullSink()
        sink.add_text("a")
        sink.add_text("b")
        sink.warn("w")
        sink.error("e")
        sink.agent_line("l")
        for name in ("begin_thinking", "end_message", "pause", "resume", "close"):
            getattr(sink, name)()
        sink.add_reasoning("r")
        sink.tool_started("t", {})
        sink.tool_finished("t", True)
        assert sink.text == "ab"
        assert sink.notices == ["! w", "✖ e", "l"]


class TestHeadlessSession:
    @pytest.fixture
    def session(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AgentSession:
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        self.provider = ScriptedProvider(["pronto."])
        self.events: list[dict[str, Any]] = []
        s = AgentSession(
            workspace=tmp_path,
            home=tmp_path / "home",
            provider_factory=lambda spec: self.provider,
            sink=IpcSink(self.events.append),
            origin="daemon",
        )
        s.set_model("anthropic/claude-sonnet-4-5")
        return s

    async def test_turn_streams_through_ipc_and_ledger_has_origin(self, session: AgentSession) -> None:
        answer = await session.run_turn("oi")
        assert answer == "pronto."
        text = "".join(e["args"].get("delta", "") for e in self.events if e["method"] == "add_text")
        assert text == "pronto."
        assert session.headless
        assert not session.pep.interactive
        assert session.ledger.spent_by_origin().get("daemon", 0.0) > 0.0

    async def test_headless_never_opens_modals(self, session: AgentSession) -> None:
        assert await session._ask_user("q?", [{"label": "a"}], False) is None
        assert await session._approve_plan("plano") is False

    async def test_origin_cap_blocks_turn(self, session: AgentSession) -> None:
        session.budget.origin_budget_usd = {"daemon": 0.0}
        answer = await session.run_turn("oi")
        assert answer is None
        assert any(e["method"] == "error" and "Orçamento" in e["args"]["message"] for e in self.events)


class TestOriginBudget:
    def test_cap_per_origin(self, tmp_path: Path) -> None:
        ledger = CostLedger(db_path=tmp_path / "m.db", registry=ModelRegistry())
        guard = BudgetGuard(ledger=ledger, daily_budget_usd=0.0, origin_budget_usd={"cron": 0.01})
        guard.check(origin="cron")
        ledger.record_turn_cost(
            provider="anthropic",
            model="anthropic/claude-sonnet-4-5",
            usage=TokenUsage(prompt_tokens=100_000, completion_tokens=10_000, total_tokens=110_000),
            origin="cron",
        )
        with pytest.raises(OriginBudgetExceededError) as info:
            guard.check(origin="cron")
        assert isinstance(info.value, BudgetExceededError)
        assert "cron" in str(info.value)
        guard.check(origin="user")  # outras origens seguem livres
        guard.check(origin="cron", is_local_model=True)  # local não gasta


def test_scripted_turn_type() -> None:
    assert isinstance(ModelTurn, type)
