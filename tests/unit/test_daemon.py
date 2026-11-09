"""Daemon (Sprint 7): IPC, SO_PEERCRED, reconexão, disparos, idle = 0 tokens e segurança."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import tempfile
import threading
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from orion.daemon import ipc
from orion.daemon.app import OrionDaemon, ScheduleTriage, default_session_factory
from orion.daemon.client import DaemonClient, DaemonUnavailable, call_once, follow
from orion.daemon.pressure import PressureSample
from orion.daemon.probe import HardwareSnapshot
from orion.daemon.server import IpcServer
from orion.governance.pep import AutonomyMode
from orion.notify.models import OutgoingMessage
from orion.scheduler.store import Schedule, SchedulerLocked
from orion.settings.models import DaemonSettings, NotifySettings, PressureSettings
from orion.tui.session import AgentMode, AgentSession
from tests.unit.test_agent_session import ScriptedProvider

# ---------------------------------------------------------------------------
# Infra
# ---------------------------------------------------------------------------


@pytest.fixture
def sockdir() -> Iterator[Path]:
    """Diretório curto (sockets Unix têm limite de ~108 bytes no caminho)."""
    path = Path(tempfile.mkdtemp(prefix="orion-t-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


async def echo(params: dict[str, Any], conn: Any) -> Any:
    return {"echo": params}


async def boom(params: dict[str, Any], conn: Any) -> Any:
    raise RuntimeError("quebrou")


@pytest.fixture
async def server(sockdir: Path) -> AsyncIterator[IpcServer]:
    srv = IpcServer(sockdir / "run" / "d.sock")
    srv.register("echo", echo)
    srv.register("boom", boom)
    await srv.start()
    yield srv
    await srv.stop()


async def raw_exchange(path: Path, payload: bytes) -> dict[str, Any]:
    reader, writer = await asyncio.open_unix_connection(str(path))
    writer.write(payload)
    await writer.drain()
    line = await asyncio.wait_for(reader.readline(), 2)
    writer.close()
    return dict(json.loads(line))


class TestIpcProtocol:
    def test_helpers(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
        assert ipc.socket_path() == tmp_path / "orion" / "daemon.sock"
        monkeypatch.delenv("XDG_RUNTIME_DIR")
        assert ipc.socket_path(tmp_path) == tmp_path / "run" / "daemon.sock"
        assert ipc.decode(ipc.encode({"a": 1})) == {"a": 1}
        with pytest.raises(ipc.IpcError):
            ipc.decode(b"[1]")
        with pytest.raises(ipc.IpcError):
            ipc.decode(b"x" * (ipc.MAX_LINE_BYTES + 1))
        assert ipc.event({"k": 1})["method"] == "event"


class TestIpcServer:
    async def test_socket_is_private(self, server: IpcServer) -> None:
        assert stat.S_IMODE(server.path.stat().st_mode) == 0o600
        assert stat.S_IMODE(server.path.parent.stat().st_mode) == 0o700

    async def test_call_errors_and_methods(self, server: IpcServer) -> None:
        async with DaemonClient(server.path) as client:
            assert await client.call("echo", {"x": 1}) == {"echo": {"x": 1}}
            with pytest.raises(ipc.IpcError) as missing:
                await client.call("nada")
            assert missing.value.code == ipc.METHOD_NOT_FOUND
            with pytest.raises(ipc.IpcError) as broken:
                await client.call("boom")
            assert broken.value.code == ipc.INTERNAL_ERROR
            assert (await client.call("unsubscribe")) == {"subscribed": False}
        assert "subscribe" in server.methods
        bad = await raw_exchange(server.path, b"not json\n")
        assert bad["error"]["code"] == ipc.PARSE_ERROR
        invalid = await raw_exchange(server.path, b'{"jsonrpc": "1.0", "id": 3, "method": "echo"}\n')
        assert invalid["error"]["code"] == ipc.INVALID_REQUEST
        params = await raw_exchange(server.path, b'{"jsonrpc": "2.0", "id": 4, "method": "echo", "params": [1]}\n')
        assert params["error"]["code"] == ipc.INVALID_PARAMS

    async def test_refuses_other_user(self, sockdir: Path) -> None:
        """SO_PEERCRED: um UID diferente do dono é desconectado sem resposta."""
        srv = IpcServer(sockdir / "o.sock", uid=os.getuid() + 1)
        srv.register("echo", echo)
        await srv.start()
        try:
            async with DaemonClient(srv.path, timeout_s=1.0) as client:
                with pytest.raises((DaemonUnavailable, TimeoutError)):
                    await client.call("echo")
            assert srv.rejected_peers == 1
        finally:
            await srv.stop()

    async def test_publish_reaches_subscribers_from_any_thread(self, server: IpcServer) -> None:
        async with DaemonClient(server.path) as client:
            await client.call("subscribe", {"client": "teste"})
            assert server.subscriber_count == 1
            server.publish({"kind": "a"})
            thread = threading.Thread(target=server.publish, args=({"kind": "b"},))
            thread.start()
            thread.join()
            seen: list[str] = []
            async for payload in client.events():
                seen.append(payload["kind"])
                if len(seen) == 2:
                    break
            assert seen == ["a", "b"]

    async def test_stale_socket_is_replaced_and_live_one_refused(self, sockdir: Path, server: IpcServer) -> None:
        with pytest.raises(RuntimeError):
            await IpcServer(server.path).start()
        stale = sockdir / "stale.sock"
        stale.write_text("")
        other = IpcServer(stale)
        await other.start()
        assert stat.S_ISSOCK(stale.stat().st_mode)
        await other.stop()
        assert not stale.exists()

    async def test_socket_path_too_long(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="XDG_RUNTIME_DIR"):
            await IpcServer(tmp_path / ("x" * 120) / "d.sock").start()

    async def test_unavailable_daemon(self, sockdir: Path) -> None:
        with pytest.raises(DaemonUnavailable):
            await call_once(sockdir / "nada.sock", "ping")
        with pytest.raises(DaemonUnavailable):
            await DaemonClient(sockdir / "nada.sock").call("ping")

    async def test_follow_reconnects_after_restart(self, sockdir: Path) -> None:
        path = sockdir / "r.sock"
        first = IpcServer(path)
        await first.start()
        events: list[str] = []
        states: list[str] = []
        stop = asyncio.Event()

        async def on_event(payload: dict[str, Any]) -> None:
            events.append(payload["kind"])
            if len(events) == 2:
                stop.set()

        task = asyncio.create_task(
            follow(path, on_event, on_state=states.append, stop=stop, backoff_s=(0.05,))
        )
        while first.subscriber_count == 0:
            await asyncio.sleep(0.01)
        first.publish({"kind": "antes"})
        while not events:
            await asyncio.sleep(0.01)
        await first.stop()
        second = IpcServer(path)
        await second.start()
        while second.subscriber_count == 0:
            await asyncio.sleep(0.01)
        second.publish({"kind": "depois"})
        await asyncio.wait_for(task, 3)
        await second.stop()
        assert events == ["antes", "depois"]
        assert states[:3] == ["connected", "disconnected", "connected"]

    async def test_follow_gives_up_after_max_attempts(self, sockdir: Path) -> None:
        slept: list[float] = []

        async def fake_sleep(s: float) -> None:
            slept.append(s)

        await follow(sockdir / "x.sock", lambda e: None, max_attempts=3, sleep=fake_sleep, backoff_s=(1.0, 2.0))
        assert slept == [1.0, 2.0]


# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
        self.mono = 1000.0
        self.sleeps = 0

    def utc(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.mono

    async def sleep(self, seconds: float) -> None:
        self.sleeps += 1
        self.now += timedelta(seconds=seconds)
        self.mono += seconds
        await asyncio.sleep(0)


class FakeProbe:
    def __init__(self, mem_mb: int = 32_000, cpus: int = 16) -> None:
        self.snap = HardwareSnapshot(
            mem_total_mb=mem_mb,
            mem_available_mb=mem_mb // 2,
            cpu_count=cpus,
            load1=0.1,
            cpu_percent=0.05,
            psi_cpu=None,
            psi_mem=None,
            psi_io=None,
            on_battery=False,
            battery_percent=None,
            disk_free_mb=100_000,
        )

    def snapshot(self) -> HardwareSnapshot:
        return self.snap


@pytest.fixture
def daemon_env(tmp_path: Path, sockdir: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ORION_RECALL", "0")
    workspace = tmp_path / "ws"
    workspace.mkdir()
    return {"home": tmp_path / "home", "workspace": workspace, "socket": sockdir / "d.sock"}


def make_daemon(
    env: dict[str, Any],
    *,
    replies: list[str] | None = None,
    mode: AgentMode | None = None,
    clock: FakeClock | None = None,
    probe: FakeProbe | None = None,
    sample: PressureSample | None = None,
    **settings: Any,
) -> tuple[OrionDaemon, ScriptedProvider, FakeClock]:
    provider = ScriptedProvider(list(replies or []))
    clock = clock or FakeClock()

    def factory(**kwargs: Any) -> AgentSession:
        session = default_session_factory(provider_factory=lambda spec: provider, **kwargs)
        session.set_model("anthropic/claude-sonnet-4-5")
        if mode is not None:
            session.set_mode(mode)
        return session

    calm = sample or PressureSample(cpu=0.05, mem=0.3, psi=None, self_cpu=0.0, self_mem=0.0)
    daemon = OrionDaemon(
        env["home"],
        settings=DaemonSettings(
            notifications=NotifySettings(desktop=False),
            pressure=PressureSettings(min_dwell_s=0.0),
            **settings,
        ),
        socket=env["socket"],
        session_factory=factory,
        probe=probe or FakeProbe(),  # type: ignore[arg-type]
        sampler=lambda: calm,
        clock=clock.utc,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return daemon, provider, clock


async def quiesce(daemon: OrionDaemon) -> None:
    for task in daemon._tasks:  # noqa: SLF001
        task.cancel()
    await asyncio.gather(*daemon._tasks, return_exceptions=True)  # noqa: SLF001


def schedule(env: dict[str, Any], **kwargs: Any) -> Schedule:
    base: dict[str, Any] = {"spec": "every 1h", "prompt": "verifique", "workspace": str(env["workspace"]), "triage": False}
    base.update(kwargs)
    return Schedule(**base)


class TestDaemonLifecycle:
    async def test_idle_hour_makes_zero_provider_calls(self, daemon_env: dict[str, Any]) -> None:
        """ADR-022 / CA-10: 1 h simulada de idle com 0 chamadas ao provider."""
        daemon, provider, clock = make_daemon(daemon_env)
        start = clock.now
        await daemon.start()
        try:
            while clock.now < start + timedelta(hours=1):
                await asyncio.sleep(0.001)
            assert daemon.provider_calls == []
            assert daemon.idle_provider_calls(start) == 0
            assert provider.requests == []
            assert daemon.runner.fires == 0
            status = await call_once(daemon.socket, "status")
            assert status["provider_calls"] == 0
            assert status["profile"] == "full"
            assert status["components"]["scheduler"] == "awake"
        finally:
            await daemon.close()
        assert not daemon.socket.exists()

    async def test_second_daemon_is_refused(self, daemon_env: dict[str, Any], sockdir: Path) -> None:
        first, _p, _c = make_daemon(daemon_env)
        await first.start()
        try:
            env2 = dict(daemon_env, socket=sockdir / "d2.sock")
            second, _p2, _c2 = make_daemon(env2)
            with pytest.raises(SchedulerLocked):
                await second.start()
        finally:
            await first.close()

    async def test_weak_machine_boots_minimal_and_refuses_session(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env, probe=FakeProbe(mem_mb=2048, cpus=2))
        await daemon.start()
        try:
            assert daemon.profile == "minimal"
            with pytest.raises(ipc.IpcError) as info:
                await call_once(daemon.socket, "prompt", {"text": "oi"})
            assert info.value.code == ipc.DENIED
        finally:
            await daemon.close()

    async def test_stabilization_wait_is_bounded(self, daemon_env: dict[str, Any]) -> None:
        busy = FakeProbe()
        busy.snap = busy.snap.model_copy(update={"cpu_percent": 0.99})
        daemon, _p, clock = make_daemon(daemon_env, probe=busy, stabilize_max_wait_s=30.0)
        await daemon.start()
        try:
            assert daemon.stabilize is not None
            assert not daemon.stabilize.stable
            assert daemon.stabilize.waited_s <= 35.0
        finally:
            await daemon.close()

    async def test_pressure_puts_session_to_sleep_without_llm(self, daemon_env: dict[str, Any]) -> None:
        heavy = PressureSample(cpu=0.99, mem=0.95, psi=None, self_cpu=0.0, self_mem=0.0)
        daemon, provider, clock = make_daemon(daemon_env, replies=["oi"], sample=heavy)
        await daemon.start()
        try:
            await daemon.registry.acquire("session")
            assert daemon.monitor is not None
            while daemon.monitor.state != "pressured":
                await asyncio.sleep(0.001)
            states = daemon.registry.states()
            assert states["session"] == "asleep"
            assert states["scheduler"] == "awake" and states["ipc"] == "awake"
            assert daemon.provider_calls == [] and provider.requests == []
            result = await daemon.jobs.run("j", "echo oi", cwd=daemon_env["workspace"])
            assert result.status == "refused"
        finally:
            await daemon.close()


class TestScheduledFire:
    async def test_prompt_fire_uses_clean_cron_session(self, daemon_env: dict[str, Any]) -> None:
        daemon, provider, _c = make_daemon(daemon_env, replies=["tudo certo."])
        outcome = await daemon.fire(schedule(daemon_env))
        assert outcome.status == "ok"
        assert outcome.detail == "tudo certo."
        assert [origin for _at, origin in daemon.provider_calls] == ["cron"]
        items = daemon.inbox.list()
        assert items and items[0].title.endswith(": ok")
        await daemon.close()

    async def test_scheduled_nuclear_without_step_up_is_denied(self, daemon_env: dict[str, Any], tmp_path: Path) -> None:
        canary = tmp_path / "canary-dir"
        canary.mkdir()
        daemon, _p, _c = make_daemon(daemon_env, mode=AgentMode.AUTO)
        sch = schedule(
            daemon_env, action="command", command=f"rm -rf {canary}", autonomy=AutonomyMode.FULLY_AUTO
        )
        outcome = await daemon.fire(sch)
        assert outcome.status == "denied"
        assert "nuclear" in outcome.detail
        assert canary.exists()
        await daemon.close()

    async def test_supervised_schedule_cannot_mutate(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env, mode=AgentMode.AUTO)
        marker = daemon_env["workspace"] / "marker"
        outcome = await daemon.fire(schedule(daemon_env, action="command", command=f"touch {marker}"))
        assert outcome.status == "denied"
        assert not marker.exists()
        await daemon.close()

    async def test_command_job_runs_with_log_and_events(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env, mode=AgentMode.AUTO)
        published: list[dict[str, Any]] = []
        daemon.server.publish = published.append  # type: ignore[method-assign]
        daemon.jobs._publish = published.append  # noqa: SLF001
        sch = schedule(daemon_env, action="command", command="echo ola", autonomy=AutonomyMode.FULLY_AUTO)
        outcome = await daemon.fire(sch)
        assert outcome.status == "ok", outcome.detail
        assert "ola" in outcome.detail
        assert any(e.get("kind") == "job.output" and e.get("line") == "ola" for e in published)
        logs = list((daemon_env["home"] / "jobs").glob("*.log"))
        assert logs and stat.S_IMODE(logs[0].stat().st_mode) == 0o600
        await daemon.close()

    async def test_untrusted_project_does_not_run(self, daemon_env: dict[str, Any]) -> None:
        settings = daemon_env["workspace"] / ".orion" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"permissions": {"allow": ["run_command"]}}))
        daemon, provider, _c = make_daemon(daemon_env, replies=["x"])
        outcome = await daemon.fire(schedule(daemon_env))
        assert outcome.status == "denied"
        assert provider.requests == []
        await daemon.close()

    async def test_missing_workspace_fails(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env)
        outcome = await daemon.fire(schedule(daemon_env, workspace="/nao/existe"))
        assert outcome.status == "failed"
        await daemon.close()

    async def test_schedule_triage_per_workspace(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env)
        sch = daemon.store.add(schedule(daemon_env))
        triage = ScheduleTriage(daemon.store)
        from orion.agents.models import TriageContext

        unknown = await triage.should_wake(TriageContext(loop_id="sch_x", goal="g", fired=0))
        assert unknown.wake
        first = await triage.should_wake(TriageContext(loop_id=sch.id, goal="g", fired=0))
        assert first.wake  # sem git: inconclusiva, acorda
        await daemon.close()


class TestAttachedSession:
    async def test_prompt_streams_sink_events_to_client(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env, replies=["pronto."])
        await daemon.start()
        try:
            async with DaemonClient(daemon.socket) as client:
                await client.call("subscribe", {"client": "attach"})
                reply = await client.call("prompt", {"text": "oi"})
                assert reply == {"answer": "pronto."}
                text = ""
                async for payload in client.events():
                    if payload.get("kind") == "sink" and payload["method"] == "add_text":
                        text += payload["args"]["delta"]
                    if text == "pronto.":
                        break
                with pytest.raises(ipc.IpcError):
                    await client.call("prompt", {"text": " "})
            assert [o for _a, o in daemon.provider_calls] == ["daemon"]
            assert daemon.activity.last_activity() is not None
        finally:
            await daemon.close()

    async def test_remote_approval_resolved_by_client(self, daemon_env: dict[str, Any]) -> None:
        from orion.core.events import Action
        from orion.governance.permissions import ActionLevel

        daemon, _p, _c = make_daemon(daemon_env)
        await daemon.start()
        await quiesce(daemon)  # sem laços de fundo avançando o relógio falso
        try:
            action = Action(tool="write_file", params={"path": "a.txt"})
            task = asyncio.create_task(daemon._remote_approval(action, ActionLevel.LEVEL_2))  # noqa: SLF001
            while not daemon.inbox.list(status="pending"):
                await asyncio.sleep(0.01)
            pending = await call_once(daemon.socket, "inbox.list", {"status": "pending"})
            assert pending[0]["kind"] == "approval"
            resolved = await call_once(daemon.socket, "inbox.resolve", {"id": pending[0]["id"], "action": "approve"})
            assert resolved == {"resolved": True}
            assert await asyncio.wait_for(task, 3) is True
            with pytest.raises(ipc.IpcError):
                await call_once(daemon.socket, "inbox.resolve", {"id": ""})
        finally:
            await daemon.close()

    async def test_rpc_misc(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env)
        await daemon.start()
        try:
            sch = daemon.store.add(schedule(daemon_env))
            assert (await call_once(daemon.socket, "ping"))["pong"]
            listed = await call_once(daemon.socket, "schedule.list")
            assert listed[0]["id"] == sch.id
            assert await call_once(daemon.socket, "schedule.runs", {"id": sch.id}) == []
            assert await call_once(daemon.socket, "schedule.reload") == {"ok": True}
            assert await call_once(daemon.socket, "activity") == {"ok": True}
            assert await call_once(daemon.socket, "shutdown") == {"stopping": True}
        finally:
            await daemon.close()


class TestPresenceInDaemon:
    async def test_quiet_rule_from_memory_holds_and_flushes(self, daemon_env: dict[str, Any]) -> None:
        from orion.presence.rules import PresenceRule, PresenceRuleStore

        daemon, _p, clock = make_daemon(daemon_env)
        facts = daemon._open_facts()  # noqa: SLF001
        local = clock.now.astimezone()
        start = (local - timedelta(hours=1)).strftime("%H:%M")
        end = (local + timedelta(hours=1)).strftime("%H:%M")
        PresenceRuleStore(facts).confirm(PresenceRule(kind="quiet_window", window=f"{start}-{end}"))
        result = await daemon.router.send(OutgoingMessage(title="novidade", body="b"))
        assert result.held_for_digest
        await daemon.presence_tick()  # ainda em silêncio: segura
        assert not daemon.inbox.list()
        clock.now += timedelta(hours=2)
        await daemon.presence_tick()
        items = daemon.inbox.list()
        assert items and items[0].kind == "digest"
        await daemon.close()

    async def test_without_rules_default_delivery(self, daemon_env: dict[str, Any]) -> None:
        daemon, _p, _c = make_daemon(daemon_env)
        result = await daemon.router.send(OutgoingMessage(title="x"))
        assert not result.held_for_digest
        assert result.delivery.channel_cap == "voice"
        await daemon.close()


class TestRestart:
    async def test_schedule_survives_restart_and_catches_up_once(self, daemon_env: dict[str, Any]) -> None:
        """Agenda criada, daemon "cai"; o novo daemon dispara uma vez (run_once) e segue."""
        clock = FakeClock()
        first, _p1, _c1 = make_daemon(daemon_env, clock=clock)
        await first.start()
        sch = first.store.add(
            schedule(daemon_env, catchup="run_once", next_run_at=clock.now + timedelta(minutes=5))
        )
        await quiesce(first)
        await first.close()
        clock.now += timedelta(hours=5)  # cinco disparos perdidos enquanto estava fora
        restarted = clock.now
        second, provider, _c2 = make_daemon(daemon_env, replies=["ok", "ok", "ok", "ok"], clock=clock)
        await second.start()
        try:
            while not second.store.runs(sch.id):
                await asyncio.sleep(0.001)
            await quiesce(second)
            runs = second.store.runs(sch.id)
            catch_up = [r for r in runs if r.started_at < restarted + timedelta(minutes=59)]
            assert len(catch_up) == 1 and catch_up[0].status == "ok", runs
            assert all(o == "cron" for _a, o in second.provider_calls)
            saved = second.store.get(sch.id)
            assert saved is not None and saved.runs >= 1 and saved.next_run_at is not None
            assert saved.next_run_at > restarted
        finally:
            await second.close()
