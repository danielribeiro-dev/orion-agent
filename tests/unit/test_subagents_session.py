"""Subagents ligados à AgentSession: breaker, ledger, custo, ChangeTracker e comandos."""

from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.gateway.circuit_breaker import CircuitState
from orion.gateway.ledger import CostLedger
from orion.gateway.models import ComplexityTier, ModelSpec, TokenUsage
from orion.sessions import JsonlSessionStore
from orion.tui.commands.base import CommandContext
from orion.tui.commands.registry import CommandRegistry
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.llm_script import say, use
from tests.unit.test_agent_session import ScriptedProvider


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _build(provider: ScriptedProvider) -> AgentSession:
        console = Console(file=io.StringIO(), width=110, theme=get_orion_theme())
        session = AgentSession(
            status_bar=SessionStatusBar(),
            console=console,
            workspace=tmp_path,
            home=tmp_path / "home",
            provider_factory=lambda spec: provider,
            ask_pep=None,
        )
        session.set_model("anthropic/claude-sonnet-4-5")
        return session

    return _build


def _out(session: AgentSession) -> str:
    return session.console.file.getvalue()  # type: ignore[attr-defined]


async def test_full_turn_delegates_and_accounts_cost_by_origin(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    provider = ScriptedProvider(
        [
            use("task", {"agent": "explore", "goal": "ache os TODOs"}),  # pai
            say("TODO em a.py:3"),  # filho
            say("Encontrei um TODO em a.py:3."),  # pai
        ]
    )
    session = build(provider)
    answer = await session.run_turn("procure TODOs")
    assert answer == "Encontrei um TODO em a.py:3."

    rows = session.ledger.list_records()
    assert sorted((r.origin, r.agent_id is not None) for r in rows) == [
        ("subagent", True),
        ("user", False),
        ("user", False),
    ]
    child_row = next(r for r in rows if r.origin == "subagent")
    assert child_row.task_id == session.session_id and child_row.complexity_level == "fast"
    assert session.ledger.spent_by_origin()["subagent"] == pytest.approx(child_row.cost_usd)
    assert session.ledger.spent_by_agent(child_row.agent_id or "") == pytest.approx(child_row.cost_usd)

    # custo dos filhos somado em /cost, na status bar e em /agents runs
    assert session.agent_usage.cost_usd == pytest.approx(child_row.cost_usd)
    assert session.status_bar.session_cost_usd == pytest.approx(session.cost_total + child_row.cost_usd)
    assert child_row.agent_id in session.agent_costs


async def test_cost_command_adds_a_subagents_row(build) -> None:  # type: ignore[no-untyped-def]
    provider = ScriptedProvider([use("task", {"agent": "explore", "goal": "x"}), say("r"), say("fim")])
    session = build(provider)
    await session.run_turn("delegue")
    registry = CommandRegistry.discover()
    ctx = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
    await registry.dispatch("/cost", ctx)
    assert "Subagents" in _out(session)


async def test_child_failure_never_touches_the_parents_circuit_breaker(build) -> None:  # type: ignore[no-untyped-def]
    provider = ScriptedProvider([], error=RuntimeError("provedor caiu"))
    session = build(provider)
    session.breaker.set_intentional_lite_mode(True)
    before = (session.breaker.state, session.breaker.intentional_lite_mode, session.breaker.is_mutation_blocked())
    result = await session.run_subagent("explore", "algo")
    assert result.status == "error" and "provedor caiu" in (result.error or "")
    after = (session.breaker.state, session.breaker.intentional_lite_mode, session.breaker.is_mutation_blocked())
    assert before == after and session.breaker.state == CircuitState.CLOSED


async def test_child_with_a_light_tier_does_not_flip_intentional_lite_mode(build) -> None:  # type: ignore[no-untyped-def]
    provider = ScriptedProvider([say("ok")])
    session = build(provider)
    session.breaker.set_intentional_lite_mode(False)
    result = await session.run_subagent("explore", "x")  # tier fast
    assert result.status == "ok" and session.breaker.intentional_lite_mode is False


async def test_default_provider_for_children_uses_isolated_breaker(build, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    session = build(ScriptedProvider([]))
    captured: dict[str, Any] = {}

    def fake_default(spec: ModelSpec, **kwargs: Any) -> ScriptedProvider:
        captured.update(kwargs)
        return ScriptedProvider([say("ok")])

    monkeypatch.setattr(session, "_default_provider", fake_default)
    monkeypatch.setattr(session, "_provider_factory", session._default_provider)
    spec = session.registry.require("google/gemini-2.0-flash-lite")
    session._agent_provider(spec)
    assert captured["breaker"] is session.agent_breaker and session.agent_breaker is not session.breaker
    assert captured["allow_downgrade"] is False and captured["on_event"] is None


async def test_child_edit_is_tracked_with_agent_id_and_can_be_undone(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "novo.txt"
    provider = ScriptedProvider(
        [
            use("task", {"agent": "general-purpose", "goal": "crie novo.txt"}),
            use("write_file", {"path": str(target), "content": "criado pelo filho"}),
            say("criei"),
            say("pronto"),
        ]
    )
    session = build(provider)
    await session.run_turn("crie o arquivo")
    assert target.read_text() == "criado pelo filho"
    change = session.tracker.changes[-1]
    assert change.agent_id is not None and change.path == target.resolve()

    # /rewind guarda o autor no snapshot
    store = JsonlSessionStore(tmp_path / "home" / "sessions", tmp_path)
    entries = store.load(session.session_id) if hasattr(store, "load") else []
    snapshots = [e.file for e in entries if getattr(e, "file", None)]
    assert snapshots and snapshots[-1].agent_id == change.agent_id

    undone = session.tracker.undo()
    assert undone is not None and not target.exists()


async def test_child_cannot_write_in_manual_mode(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from orion.tui.session import AgentMode

    target = tmp_path / "bloqueado.txt"
    provider = ScriptedProvider(
        [
            use("task", {"agent": "general-purpose", "goal": "escreva"}),
            use("write_file", {"path": str(target), "content": "x"}),
            say("não consegui"),
            say("relatado"),
        ]
    )
    session = build(provider)
    session.set_mode(AgentMode.MANUAL)
    await session.run_turn("escreva")
    assert not target.exists()  # modo manual do pai + sem humano = filho não escreve
    assert session.tracker.changes == []


async def test_agents_command_lists_shows_runs_and_trusts(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    project = tmp_path / ".orion" / "agents"
    project.mkdir(parents=True)
    (project / "auditor.md").write_text(
        "---\nname: auditor\ndescription: Audita TODOs\ntools: [read_file, write_file]\n---\nAudite.\n"
    )
    session = build(ScriptedProvider([say("feito")]))
    registry = CommandRegistry.discover()
    ctx = CommandContext(session=session, console=session.console, clear_screen=lambda: None)

    assert (await registry.dispatch("/agents", ctx)).success
    text = " ".join(_out(session).split())  # o terminal quebra linhas
    assert "explore" in text and "auditor" in text and "restrito" in text and "/agents trust" in text

    shown = await registry.dispatch("/agents show auditor", ctx)
    assert shown.success
    detail = _out(session).split("Audita TODOs")[-1]  # painel do /agents show
    assert "read_file" in detail  # restrito: write_file caiu
    assert "write_file" not in detail.split("Audite.")[0].split("Tools")[-1]
    assert not (await registry.dispatch("/agents show ghost", ctx)).success

    empty = await registry.dispatch("/agents runs", ctx)
    assert "Nenhum subagent" in empty.output_message

    trusted = await registry.dispatch("/agents trust", ctx)
    assert trusted.success and "confiados" in trusted.output_message
    assert session.agent_catalog.get("auditor").tools == ["read_file", "write_file"]  # type: ignore[union-attr]
    assert "Nada a confiar" in (await registry.dispatch("/agents trust", ctx)).output_message
    assert not (await registry.dispatch("/agents bogus", ctx)).success


async def test_review_delegates_the_diff_to_the_code_review_agent(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    import subprocess

    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)  # noqa: E731
    run("init")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (tmp_path / "f").write_text("a\n")
    run("add", ".")
    run("commit", "-m", "x")
    (tmp_path / "f").write_text("b\n")

    provider = ScriptedProvider([say("Achado: f:1 troca a por b sem teste.")])
    session = build(provider)
    registry = CommandRegistry.discover()
    ctx = CommandContext(session=session, console=session.console, clear_screen=lambda: None)
    result = await registry.dispatch("/review segurança", ctx)

    assert result.success
    request = provider.requests[0]
    sent = " ".join(m.text for m in request.messages)
    assert "+b" in sent and "segurança" in sent  # diff + foco chegam ao filho
    assert "f:1" in _out(session) and "code-review" in _out(session)
    assert session.history[-1].text.startswith("Achado: f:1")  # follow-up possível no pai
    assert {t.name for t in request.tools} <= {"read_file", "glob", "grep", "search_files"}  # somente leitura


def test_ledger_migration_adds_origin_and_agent_id_idempotently(tmp_path: Path) -> None:
    db = tmp_path / "metrics.db"
    conn = sqlite3.connect(db)
    conn.execute(
        """CREATE TABLE token_ledger (
            id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
            routing_mode TEXT NOT NULL, complexity_level TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0,
            cached_tokens INTEGER NOT NULL DEFAULT 0, cache_write_tokens INTEGER NOT NULL DEFAULT 0,
            cost_usd REAL NOT NULL DEFAULT 0.0, cost_brl REAL NOT NULL DEFAULT 0.0,
            task_id TEXT, latency_ms REAL NOT NULL DEFAULT 0.0)"""
    )
    conn.execute(
        "INSERT INTO token_ledger (id, timestamp, provider, model, routing_mode, complexity_level, cost_usd)"
        " VALUES ('old', '2026-01-01T00:00:00+00:00', 'openrouter', 'm', 'auto', 'fast', 0.5)"
    )
    conn.commit()
    conn.close()

    for _ in range(2):  # reabrir não quebra
        ledger = CostLedger(db_path=db)
        ledger.record_turn_cost(
            "anthropic", "claude-haiku-5-5", TokenUsage(prompt_tokens=1000, completion_tokens=100),
            complexity=ComplexityTier.FAST, origin="subagent", agent_id="agent_x",
        )
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(token_ledger)")}
    assert {"origin", "agent_id"} <= cols
    assert ledger.spent_by_agent("agent_x") > 0
    assert set(ledger.spent_by_origin()) == {"subagent"}
    assert set(ledger.spent_by_agents()) == {"agent_x"}
    row = sqlite3.connect(db).execute("SELECT origin, agent_id FROM token_ledger WHERE id='old'").fetchone()
    assert row == ("user", None)  # linhas antigas ganham a origem padrão


async def test_agents_settings_are_ignored_from_an_untrusted_project(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / ".orion").mkdir()
    (tmp_path / ".orion" / "settings.json").write_text(
        json.dumps({"agents": {"max_concurrent": 16, "default_budget_usd": 99}, "models": {"tiers": {"fast": ["claude-opus-5-5"]}}})
    )
    session = build(ScriptedProvider([]))
    limits = session.agent_limits()
    assert limits.max_concurrent == 4 and limits.default_budget_usd == 0.50
    assert session.settings.project_needs_trust
