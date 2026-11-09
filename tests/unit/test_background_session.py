"""6B ligado à AgentSession: notificação entre turnos, /tasks, /loop e cascata no encerramento."""

from __future__ import annotations

import asyncio
import io
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from orion.agents.models import AgentEventEnvelope, TaskStatus
from orion.cli import run_interactive_repl
from orion.gateway.models import LLMRequest, LLMResponseChunk, ModelSpec
from orion.tui.commands.base import CommandContext
from orion.tui.commands.registry import CommandRegistry
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.agent_helpers import wait_until
from tests.llm_script import say, use
from tests.unit.test_agent_session import ScriptedProvider

PARENT_MODEL = "anthropic/claude-sonnet-4-5"


class GatedProvider(ScriptedProvider):
    """Como o ScriptedProvider, mas só responde depois de ``gate`` (o filho em segundo plano)."""

    def __init__(self, replies, gate: threading.Event) -> None:  # type: ignore[no-untyped-def]
        super().__init__(replies)
        self.gate = gate

    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMResponseChunk]:  # type: ignore[override]
        while not self.gate.is_set():
            await asyncio.sleep(0.005)
        async for chunk in super().stream(request):
            yield chunk


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    sessions: list[AgentSession] = []

    def _build(parent: ScriptedProvider, child: ScriptedProvider) -> AgentSession:
        def factory(spec: ModelSpec) -> ScriptedProvider:
            return parent if spec.id == PARENT_MODEL else child

        console = Console(file=io.StringIO(), width=120, theme=get_orion_theme())
        session = AgentSession(
            status_bar=SessionStatusBar(), console=console, workspace=tmp_path,
            home=tmp_path / "home", provider_factory=factory, ask_pep=None,
        )
        session.set_model(PARENT_MODEL)
        sessions.append(session)
        return session

    yield _build
    for session in sessions:
        session.loops.stop_all()
        session.tasks.shutdown()


def _ctx(session: AgentSession) -> CommandContext:
    return CommandContext(session=session, console=session.console, clear_screen=lambda: None)


def _out(session: AgentSession) -> str:
    return " ".join(session.console.file.getvalue().split())  # type: ignore[attr-defined]


async def test_background_completion_reaches_the_next_turn_with_zero_polling(build) -> None:  # type: ignore[no-untyped-def]
    gate = threading.Event()
    parent = ScriptedProvider(
        [
            use("task_create", {"agent": "explore", "goal": "audite os TODOs"}),
            say("Disparei a auditoria; sigo com outra coisa."),
            say("Pronto: a auditoria achou 2 TODOs."),
            say("ok"),
        ]
    )
    child = GatedProvider([say("2 TODOs: a.py:3 e b.py:9")], gate)
    session = build(parent, child)

    answer = await session.run_turn("audite em segundo plano")
    assert "Disparei" in answer and len(parent.requests) == 2
    assert session.tasks.active_count() == 1 and session.status_bar.bg_running == 1

    await asyncio.sleep(0.15)  # esperando o término: o modelo do pai não é chamado
    assert len(parent.requests) == 2 and len(child.requests) == 0
    gate.set()
    await wait_until(lambda: session.status_bar.bg_unread == 1)
    assert len(parent.requests) == 2  # continua sem nenhuma chamada extra

    [event] = session.pop_notifications()  # o que o REPL faz antes do prompt
    assert event.kind == "task.completed" and "2 TODOs" in event.payload["summary"]
    assert session.status_bar.bg_unread == 0 and session.status_bar.bg_running == 0
    line = session.format_notification(event)
    assert event.payload["task_id"] in line and "explore" in line and "$" in line

    await session.run_turn("e então?")
    sent = " ".join(m.text for m in parent.requests[2].messages)
    assert "Background events since your last turn" in sent and event.payload["task_id"] in sent
    assert "full result: ref://agents/" in sent
    await session.run_turn("mais uma")
    again = " ".join(m.text for m in parent.requests[3].messages)
    # o aviso não é injetado de novo; a única ocorrência é a do histórico do turno anterior
    assert again.count("Background events since your last turn") == 1


async def test_child_cost_from_a_background_task_is_accounted(build) -> None:  # type: ignore[no-untyped-def]
    parent = ScriptedProvider([use("task_create", {"goal": "x"}), say("lancei")])
    session = build(parent, ScriptedProvider([say("feito")]))
    await session.run_turn("go")
    await wait_until(lambda: session.agent_usage.calls == 1)
    assert session.agent_usage.cost_usd > 0
    rows = session.ledger.list_records()
    assert any(r.origin == "subagent" and r.agent_id for r in rows)
    assert session.status_bar.session_cost_usd == pytest.approx(session.cost_total + session.agent_usage.cost_usd)


async def test_status_bar_shows_running_and_unread_tasks() -> None:
    bar = SessionStatusBar()
    assert "tasks" not in " ".join(text for _, text in bar.status_segments(120))
    bar.bg_running, bar.bg_unread = 2, 1
    for width in (120, 90, 60):
        assert "tasks 2 ● 1 ✔" in " ".join(text for _, text in bar.status_segments(width))
    bar.bg_running = 0
    assert "tasks 1 ✔" in " ".join(text for _, text in bar.status_segments(120))


async def test_tasks_command_lists_gets_and_stops(build) -> None:  # type: ignore[no-untyped-def]
    gate = threading.Event()
    parent = ScriptedProvider([use("task_create", {"agent": "explore", "goal": "varra"}), say("ok")])
    session = build(parent, GatedProvider([say("resultado final")], gate))
    registry, ctx = CommandRegistry.discover(), None
    ctx = _ctx(session)
    assert "Nenhuma task" in (await registry.dispatch("/tasks", ctx)).output_message

    await session.run_turn("lance")
    [rec] = session.tasks.list()
    await wait_until(lambda: session.runtime is not None and session.agent_runner.deps.inbox.is_open(rec.agent_id))
    await registry.dispatch("/tasks", ctx)
    assert rec.task_id in _out(session) and "running" in _out(session)

    stopped = await registry.dispatch(f"/tasks stop {rec.task_id}", ctx)
    assert stopped.success and session.tasks.get(rec.task_id).status == TaskStatus.CANCELLED  # type: ignore[union-attr]
    assert not (await registry.dispatch(f"/tasks stop {rec.task_id}", ctx)).success
    assert not (await registry.dispatch("/tasks get task_nope", ctx)).success
    assert not (await registry.dispatch("/tasks bogus", ctx)).success
    assert not (await registry.dispatch("/tasks stop", ctx)).success

    gate.set()
    done = session.tasks.start  # nova task terminando normalmente
    from orion.agents.runner import TaskRequest

    fresh = done(TaskRequest("explore", "outra"), session._parent_handle)
    session.agent_runner  # noqa: B018
    await wait_until(lambda: session.tasks.get(fresh.task_id).status == TaskStatus.DONE)  # type: ignore[union-attr]
    got = await registry.dispatch(f"/tasks get {fresh.task_id}", ctx)
    assert got.success and "resultado completo: ref://agents/" in _out(session)


async def test_tasks_command_lists_background_shells_with_unique_logs(build, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    session = build(ScriptedProvider([]), ScriptedProvider([]))
    ctx = _ctx(session)
    registry = CommandRegistry.discover()
    shell = session.shells.start("sleep 30")
    other = type(session.shells)(tmp_path / "shells2").start("sleep 30")  # outra instância, mesmo processo
    try:
        assert shell.log_path != other.log_path  # não colidem mais
        await registry.dispatch("/tasks", ctx)
        assert shell.shell_id in _out(session) and "sleep 30" in _out(session)
        out = await registry.dispatch(f"/tasks stop {shell.shell_id}", ctx)
        assert out.success and "encerrado" in out.output_message
        assert not (await registry.dispatch("/tasks stop shell_99", ctx)).success
    finally:
        session.shells.kill_all()


async def test_loop_command_starts_lists_and_stops(build) -> None:  # type: ignore[no-untyped-def]
    session = build(ScriptedProvider([]), ScriptedProvider([]))
    registry, ctx = CommandRegistry.discover(), _ctx(session)
    assert "Nenhum loop" in (await registry.dispatch("/loop", ctx)).output_message

    started = await registry.dispatch("/loop 5m --max 3 --budget 0.02 --ttl 2d --agent explore verifique o CI", ctx)
    assert started.success and "a cada 300s" in started.output_message and "até 3 disparos" in started.output_message
    [state] = session.loops.list()
    assert state.goal == "verifique o CI" and state.max_fires == 3 and state.budget_usd == 0.02
    assert state.expires_at - state.created_at == 2 * 86400 and state.agent == "explore"

    dynamic = await registry.dispatch("/loop vigie o repositório", ctx)
    assert "dinâmico" in dynamic.output_message
    await registry.dispatch("/loop list", ctx)
    assert state.loop_id in _out(session) and "disparos 0/3" in _out(session)

    assert (await registry.dispatch(f"/loop stop {state.loop_id}", ctx)).success
    assert not (await registry.dispatch("/loop stop loop_nope", ctx)).success
    assert "1 loop(s) encerrado(s)" in (await registry.dispatch("/loop stop all", ctx)).output_message
    assert session.loops.active_count() == 0


@pytest.mark.parametrize(
    "line, fragment",
    [
        ("/loop 5s verifique", "mínimo"),  # intervalo curto demais
        ("/loop 5m", "verificar"),  # sem meta
        ("/loop 5m --max x algo", "inválido"),
        ("/loop 5m --ttl 3 algo", "--ttl"),
        ("/loop 5m --budget", "precisa de um valor"),
    ],
)
async def test_loop_command_rejects_bad_input(build, line: str, fragment: str) -> None:  # type: ignore[no-untyped-def]
    session = build(ScriptedProvider([]), ScriptedProvider([]))
    result = await CommandRegistry.discover().dispatch(line, _ctx(session))
    assert not result.success and fragment in result.output_message and "Uso:" in result.output_message


async def test_session_shutdown_cascades_to_tasks_and_loops(build) -> None:  # type: ignore[no-untyped-def]
    gate = threading.Event()
    parent = ScriptedProvider([use("task_create", {"goal": "longa"}), say("lancei")])
    session = build(parent, GatedProvider([say("nunca")], gate))
    await session.run_turn("go")
    [rec] = session.tasks.list()
    await wait_until(lambda: session.agent_runner.deps.inbox.is_open(rec.agent_id))
    loop = session.loops.start("vigie", interval_s=3600)

    await asyncio.get_running_loop().run_in_executor(None, session.shutdown)
    assert session.tasks.get(rec.task_id).status == TaskStatus.CANCELLED  # type: ignore[union-attr]
    assert loop.status == "stopped" and not session.executor.started


def test_repl_prints_pending_notifications_before_each_prompt() -> None:
    event = AgentEventEnvelope(agent_id="agent_1", session_id="s", kind="task.completed")
    session = MagicMock()
    session.session_id = "s"
    session.pop_notifications.side_effect = [[event], []]
    session.format_notification.return_value = "task_ab12 · explore · ok · $0.0100"

    async def run_turn(coro, *_a, **_k):  # type: ignore[no-untyped-def]
        return await coro

    prompt = MagicMock()
    prompt.prompt.side_effect = ["/exit"]
    prompt.run_turn = run_turn
    with patch("orion.cli.console") as console:
        run_interactive_repl(prompt, session)
    printed = " ".join(str(call.args[0]) for call in console.print.call_args_list if call.args)
    assert "task_ab12 · explore · ok" in printed
    session.pop_notifications.assert_called()
