"""Controle do daemon (Sprint 7): opt-in, /daemon, daemon_control, schedule_*, presença, attach e CLI."""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from rich.console import Console
from typer.testing import CliRunner

from orion.agents.definitions import FORBIDDEN_FOR_CHILD
from orion.daemon.control import DaemonControlError, DaemonController, format_status
from orion.daemon.service import ServiceManager
from orion.governance.pep import AutonomyMode
from orion.governance.permissions import ActionLevel, tool_action_level
from orion.runtime.tools.daemon_control import DaemonControlTool
from orion.runtime.tools.presence import (
    PresenceRuleCreateTool,
    PresenceRuleDeleteTool,
    PresenceRuleListTool,
)
from orion.runtime.tools.schedule import ScheduleCreateTool, ScheduleDeleteTool, ScheduleListTool
from orion.scheduler.store import ScheduleStore
from orion.settings.io import read_json_object
from orion.settings.loader import load_settings, user_settings_path
from orion.tui.attach import EventPrinter, handle_line, run_attach
from orion.tui.commands.base import CommandContext
from orion.tui.commands.daemon import DaemonCommand
from orion.tui.session import AgentSession
from orion.tui.sink import NullSink
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.unit.test_daemon import daemon_env, make_daemon, sockdir  # noqa: F401 - fixtures
from tests.unit.test_daemon_system import FakeRunner

NEW_TOOLS = (
    "daemon_control",
    "schedule_create",
    "schedule_list",
    "schedule_delete",
    "presence_rule_create",
    "presence_rule_list",
    "presence_rule_delete",
)


def console() -> Console:
    return Console(file=io.StringIO(), width=120, theme=get_orion_theme())


def out(c: Console) -> str:
    return c.file.getvalue()  # type: ignore[attr-defined]


@pytest.fixture
def controller(tmp_path: Path) -> Iterator[tuple[DaemonController, FakeRunner]]:
    runner = FakeRunner()
    service = ServiceManager(home=tmp_path / "home", unit_dir=tmp_path / "units", runner=runner, user="daniel")
    yield DaemonController(tmp_path / "home", service=service, socket=tmp_path / "none.sock"), runner


class TestGovernance:
    def test_levels_and_children(self) -> None:
        for tool in NEW_TOOLS:
            assert tool in FORBIDDEN_FOR_CHILD
        for tool in ("daemon_control", "schedule_create", "schedule_delete", "presence_rule_create"):
            assert tool_action_level(tool) == ActionLevel.LEVEL_3
        assert tool_action_level("schedule_list") == ActionLevel.LEVEL_0

    def test_project_layer_never_enables_daemon(self, tmp_path: Path) -> None:
        home, ws = tmp_path / "home", tmp_path / "ws"
        (ws / ".orion").mkdir(parents=True)
        (ws / ".orion" / "settings.local.json").write_text(json.dumps({"daemon": {"enabled": True}, "ui": {"show_thinking": True}}))
        loaded = load_settings(home, ws)
        assert loaded.effective.daemon.enabled is False
        assert loaded.effective.ui.show_thinking is True
        home.mkdir()
        user_settings_path(home).write_text(json.dumps({"daemon": {"enabled": True, "autostart": "login"}}))
        assert load_settings(home, ws).effective.daemon.autostart == "login"


class TestController:
    async def test_opt_in_levels(self, controller: tuple[DaemonController, FakeRunner]) -> None:
        ctl, runner = controller
        assert ctl.settings().enabled is False  # desligado por padrão
        status = await ctl.status()
        assert status["daemon"] is None and status["enabled"] is False
        assert "parado" in format_status(status)[0]
        msg = await ctl.install()
        assert "autostart continua desligado" in msg
        assert ctl.settings().enabled is False
        await ctl.run("start")
        assert ctl.settings().enabled and ctl.settings().autostart == "off"
        await ctl.run("enable")
        assert ctl.settings().autostart == "login"
        assert not any("loginctl" in c for c in runner.calls)
        await ctl.run("enable", boot=True)
        assert ctl.settings().autostart == "boot"
        assert ["loginctl", "enable-linger", "daniel"] in runner.calls
        await ctl.run("disable")
        settings = ctl.settings()
        assert settings.enabled is False and settings.autostart == "off"
        assert ["loginctl", "disable-linger", "daniel"] in runner.calls
        assert not ctl.service.unit_path.exists()
        data = read_json_object(user_settings_path(ctl.home))
        assert data is not None and data["daemon"]["enabled"] is False

    async def test_errors(self, controller: tuple[DaemonController, FakeRunner]) -> None:
        ctl, _runner = controller
        with pytest.raises(DaemonControlError):
            await ctl.run("explodir")
        with pytest.raises(DaemonControlError):
            await ctl.stop()  # sem unit e sem daemon
        with pytest.raises(DaemonControlError):
            await ctl.inbox()

    async def test_live_daemon(self, daemon_env: dict[str, Any], controller: tuple[DaemonController, FakeRunner]) -> None:  # noqa: F811
        daemon, _p, _c = make_daemon(daemon_env)
        await daemon.start()
        try:
            ctl = DaemonController(daemon.home, service=controller[0].service, socket=daemon.socket)
            status = await ctl.status()
            assert status["daemon"]["profile"] == "full"
            assert any("perfil full" in line for line in format_status(status))
            assert await ctl.inbox() == []
            assert await ctl.resolve("nada", "approve") is False
            assert "parado" in await ctl.stop()  # sem unit: pede shutdown pelo IPC
        finally:
            await daemon.close()


@pytest.fixture
def tools(tmp_path: Path) -> dict[str, Any]:
    state: dict[str, Any] = {"trusted": True, "mode": AutonomyMode.WORKSPACE_AUTO, "enabled": False}
    kwargs: dict[str, Any] = {
        "workspace": tmp_path,
        "autonomy": lambda: state["mode"],
        "trusted": lambda: state["trusted"],
        "daemon_enabled": lambda: state["enabled"],
        "socket": tmp_path / "none.sock",
    }
    home = tmp_path / "home"
    state.update(
        home=home,
        create=ScheduleCreateTool(home, **kwargs),
        list=ScheduleListTool(home, **kwargs),
        delete=ScheduleDeleteTool(home, **kwargs),
    )
    return state


class TestScheduleTools:
    async def test_create_list_delete(self, tools: dict[str, Any]) -> None:
        created = await tools["create"].run(spec="0 8 * * 1-5", prompt="resuma o dia", autonomy="fully_auto")
        assert created.success, created.error
        assert "capped to workspace_auto" in created.output
        assert "daemon is OFF" in created.output
        sid = created.metadata["schedule_id"]
        store = ScheduleStore(tools["home"] / "schedules.db")
        saved = store.get(sid)
        store.close()
        assert saved is not None and saved.autonomy == AutonomyMode.WORKSPACE_AUTO and saved.triage is False
        listed = await tools["list"].run()
        assert sid in listed.output
        assert (await tools["delete"].run(schedule_id=sid)).success
        assert not (await tools["delete"].run(schedule_id=sid)).success
        assert (await tools["list"].run()).output == "No schedules."

    async def test_rejections(self, tools: dict[str, Any]) -> None:
        assert not (await tools["create"].run(spec="1 2 3")).success
        assert not (await tools["create"].run(spec="every 1h")).success  # prompt vazio
        assert not (await tools["create"].run(spec="every 10s", prompt="x")).success
        tools["enabled"] = True
        ok = await tools["create"].run(spec="every 1h", prompt="x")
        assert "not running" in ok.output
        tools["trusted"] = False
        refused = await tools["create"].run(spec="every 1h", prompt="x")
        assert not refused.success and "not trusted" in (refused.error or "")


class TestDaemonControlTool:
    async def test_untrusted_and_status(self, controller: tuple[DaemonController, FakeRunner]) -> None:
        ctl, _runner = controller
        trusted = {"v": False}
        tool = DaemonControlTool(lambda: ctl, lambda: trusted["v"])
        refused = await tool.run(action="start")
        assert not refused.success and ctl.settings().enabled is False
        status = await tool.run(action="status")
        assert status.success and "opt-in desligado" in status.output
        trusted["v"] = True
        started = await tool.run(action="enable", boot=False)
        assert started.success and ctl.settings().autostart == "login"
        failed = await tool.run(action="nada")
        assert not failed.success

    async def test_runtime_failure_is_reported(self, tmp_path: Path) -> None:
        ctl = MagicMock()

        async def boom(*a: Any, **k: Any) -> Any:
            raise OSError("sem systemctl")

        ctl.run = boom
        result = await DaemonControlTool(lambda: ctl, lambda: True).run(action="start")
        assert not result.success and "sem systemctl" in (result.error or "")


class TestPresenceTools:
    async def test_lifecycle(self, tmp_path: Path) -> None:
        from orion.memory.facts_store import FactsStore

        facts = FactsStore(tmp_path / "facts.db")
        facts.initialize()
        create, listing, delete = (
            PresenceRuleCreateTool(lambda: facts),
            PresenceRuleListTool(lambda: facts),
            PresenceRuleDeleteTool(lambda: facts),
        )
        assert "No presence rules" in (await listing.run()).output
        bad = await create.run(kind="quiet_window", window="manhã", description="x")
        assert not bad.success and "window grammar" in (bad.error or "")
        saved = await create.run(
            kind="quiet_window", window="until_first_activity", description="manhã quieta", channel_cap="inbox"
        )
        assert saved.success
        assert "until_first_activity" in (await listing.run()).output
        assert (await delete.run(key=saved.metadata["key"])).success
        assert not (await delete.run(key="presence.x")).success
        none = PresenceRuleListTool(lambda: None)
        assert not (await none.run()).success
        assert not (await PresenceRuleCreateTool(lambda: None).run(kind="digest", window="daily@08:00")).success
        assert not (await PresenceRuleDeleteTool(lambda: None).run(key="k")).success


class TestSessionWiring:
    async def test_session_exposes_daemon_tools(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        session = AgentSession(workspace=tmp_path, home=tmp_path / "home", sink=NullSink())
        names = {spec.name for spec in session.runtime.tool_specs()}
        assert set(NEW_TOOLS) <= names
        result = await session.runtime.execute("schedule_list", {})
        assert result.success and result.output == "No schedules."
        session.shutdown()


class TestDaemonCommand:
    @pytest.fixture
    def context(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CommandContext:
        monkeypatch.setenv("OPENROUTER_API_KEY", "k")
        # Isola do daemon real da máquina (o socket fica em XDG_RUNTIME_DIR).
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
        c = console()
        session = AgentSession(status_bar=SessionStatusBar(), console=c, workspace=tmp_path, home=tmp_path / "home")
        return CommandContext(session=session, console=c, clear_screen=MagicMock())

    async def test_status_and_usage(self, context: CommandContext) -> None:
        cmd = DaemonCommand()
        assert (await cmd.execute("", context)).success
        assert "opt-in desligado" in out(context.console)
        bad = await cmd.execute("voar", context)
        assert not bad.success and "Uso" in bad.output_message
        inbox = await cmd.execute("inbox", context)
        assert not inbox.success
        approve = await cmd.execute("approve x", context)
        assert not approve.success

    async def test_mutations_go_through_pep(self, context: CommandContext) -> None:
        calls: list[tuple[str, dict[str, Any]]] = []

        async def run_tool(tool: str, params: dict[str, Any]) -> bool:
            calls.append((tool, params))
            return True

        context.session.run_tool = run_tool
        cmd = DaemonCommand()
        assert (await cmd.execute("enable --boot", context)).success
        assert (await cmd.execute("stop", context)).success
        assert calls == [("daemon_control", {"action": "enable", "boot": True}), ("daemon_control", {"action": "stop"})]

    async def test_inbox_with_live_daemon(self, daemon_env: dict[str, Any], context: CommandContext, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
        from orion.notify.models import NotifyAction, OutgoingMessage

        daemon, _p, _c = make_daemon(daemon_env)
        await daemon.start()
        monkeypatch.setattr("orion.daemon.ipc.socket_path", lambda home=None: daemon.socket)
        try:
            msg = OutgoingMessage(kind="approval", title="write_file?", actions=[NotifyAction(id="approve", label="Aprovar")])
            daemon.inbox.add(msg)
            cmd = DaemonCommand()
            assert (await cmd.execute("inbox", context)).success
            assert msg.id in out(context.console)
            assert (await cmd.execute(f"deny {msg.id}", context)).success
            assert not (await cmd.execute(f"approve {msg.id}", context)).success
            assert (await cmd.execute("inbox", context)).output_message == "Inbox vazia."
        finally:
            await daemon.close()


class TestAttach:
    async def test_not_running(self, tmp_path: Path) -> None:
        c = console()
        assert await run_attach(tmp_path, c, socket=tmp_path / "x.sock", read_line=_lines([])) == 1
        assert "não está em execução" in out(c)

    async def test_session_flow(self, daemon_env: dict[str, Any]) -> None:  # noqa: F811
        from orion.notify.models import OutgoingMessage

        daemon, _p, _c = make_daemon(daemon_env, replies=["pronto."])
        await daemon.start()
        c = console()
        try:
            daemon.inbox.add(OutgoingMessage(kind="approval", title="pendente"))
            pending_id = daemon.inbox.list()[0].id
            lines = ["", "/help", "/status", "/inbox", "/approve", "/foo", f"/deny {pending_id}", "oi", "/detach"]
            code = await run_attach(daemon.home, c, socket=daemon.socket, read_line=_lines(lines))
            assert code == 0
            text = out(c)
            assert "perfil full" in text and pending_id in text and "Desanexado" in text
            assert "pronto." in text  # o turno do daemon renderizado pelo RichSink local
            assert daemon.activity.last_activity() is not None
        finally:
            await daemon.close()

    async def test_event_printer_and_errors(self, tmp_path: Path) -> None:
        c = console()
        printer = EventPrinter(c, NullSink())
        printer({"kind": "notify", "message": {"id": "m1", "title": "Oi", "body": "corpo", "kind": "approval"}})
        printer({"kind": "agent_event", "event": {"kind": "schedule.fired", "agent_id": "sch_1"}})
        printer({"kind": "job.finished", "job_id": "j1", "status": "ok"})
        printer({"kind": "outro"})
        text = out(c)
        assert "● Oi" in text and "/approve m1" in text and "schedule.fired" in text and "job j1" in text
        assert await handle_line("oi", tmp_path / "nada.sock", c)
        assert "indisponível" in out(c)


def _lines(lines: list[str]) -> Any:
    queue = list(lines)

    async def read() -> str:
        await asyncio.sleep(0)
        if not queue:
            raise EOFError
        return queue.pop(0)

    return read


class TestCli:
    def test_daemon_run_requires_opt_in(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from orion.cli import app

        monkeypatch.setattr("orion.cli._orion_home", lambda: tmp_path / "home")
        result = CliRunner().invoke(app, ["daemon", "run"])
        assert result.exit_code == 2
        assert "opt-in" in result.output

    def test_status_and_errors(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from orion.cli import app

        monkeypatch.setattr("orion.cli._orion_home", lambda: tmp_path / "home")
        monkeypatch.setattr("orion.daemon.ipc.socket_path", lambda home=None: tmp_path / "x.sock")
        monkeypatch.setattr(
            "orion.daemon.control.ServiceManager",
            lambda home: ServiceManager(home=home, unit_dir=tmp_path / "u", runner=FakeRunner()),
        )
        result = CliRunner().invoke(app, ["daemon", "status"])
        assert result.exit_code == 0 and "parado" in result.output
        assert CliRunner().invoke(app, ["daemon", "install"]).exit_code == 0
        stop = CliRunner().invoke(app, ["daemon", "stop"])
        assert stop.exit_code == 0
        attach = CliRunner().invoke(app, ["attach"])
        assert attach.exit_code == 1

    def test_orion_alias_is_same_cli(self) -> None:
        import tomllib

        data = tomllib.loads(Path("pyproject.toml").read_text())
        scripts = data["project"]["scripts"]
        assert scripts["orion"] == scripts["orion-agent"] == "orion.cli:main"
