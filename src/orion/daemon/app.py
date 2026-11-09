"""O daemon do ORION: o corpo permanente; a sessão é o cérebro (ADR-032, ADR-035, ADR-036).

Composição, de baixo para cima:

1. **Arranque escalonado:** sonda o hardware, escolhe o perfil (``minimal|standard|full``), sobe
   o IPC (essencial) e espera a máquina estabilizar, com teto, antes do resto.
2. **Componentes:** IPC, scheduler e auditoria são essenciais e nunca dormem. A sessão do daemon
   (cara) e o Telegram carregam sob demanda e dormem sob pressão (``PressureMonitor``).
3. **Agenda:** ``SchedulerRunner`` dorme até o próximo vencimento. Cada disparo abre uma sessão
   LIMPA, headless e não interativa, com ``origin=cron`` e autonomia ``min(configurada, do
   agendamento)``: perguntas do PEP viram negação, nuclear inclusive (ADR-022, ADR-028).
4. **Saída:** tudo passa pela política de presença (regras da memória) e pelo roteador
   (cliente anexado > notificação nativa > Telegram), com Inbox de pendências.

Em idle, nada aqui chama o provider: os laços só dormem em ``sleep``/``accept``. O medidor
:attr:`OrionDaemon.provider_calls` conta toda chamada (ADR-022, prova em teste).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from orion import __version__
from orion.agents.loops import DeterministicTriage
from orion.agents.models import AgentEventEnvelope, TriageContext, TriageDecision
from orion.daemon import ipc
from orion.daemon.jobs import JobSupervisor
from orion.daemon.pressure import PressureMonitor, PressureSample, default_sampler
from orion.daemon.probe import (
    PROFILE_COMPONENTS,
    BootProfile,
    HardwareProbe,
    StabilizeResult,
    choose_profile,
    wait_until_stable,
)
from orion.daemon.server import Connection, IpcServer
from orion.daemon.sleepable import (
    ComponentNotAllowed,
    ComponentRegistry,
    FunctionComponent,
    Sleepable,
)
from orion.notify.desktop import DesktopNotifier
from orion.notify.inbox import Inbox
from orion.notify.models import Delivery, NotifyAction, OutgoingMessage
from orion.notify.router import OutputRouter
from orion.notify.telegram import TelegramNotifier, load_telegram_token
from orion.presence.activity import ActivityLog
from orion.presence.policy import PresencePolicy
from orion.presence.rules import PresenceRule, PresenceRuleStore
from orion.scheduler.runner import FireOutcome, SchedulerRunner
from orion.scheduler.store import Schedule, SchedulerLock, ScheduleStore
from orion.settings.models import DaemonSettings, HookSpec, UiSettings
from orion.tui.sink import IpcSink, NullSink, SessionSink

if TYPE_CHECKING:
    from orion.core.events import Action
    from orion.governance.permissions import ActionLevel
    from orion.tui.session import AgentSession

logger = logging.getLogger(__name__)

SessionFactory = Callable[..., "AgentSession"]
PRESENCE_TICK_S = 60.0


def _utcnow() -> datetime:
    return datetime.now(UTC)


def default_session_factory(**kwargs: Any) -> AgentSession:
    from orion.tui.session import AgentSession

    return AgentSession(**kwargs)


class _ClientPort:
    """``AttachedClientPort`` sobre o servidor IPC."""

    def __init__(self, server: IpcServer) -> None:
        self._server = server

    def has_clients(self) -> bool:
        return self._server.subscriber_count > 0

    async def deliver(self, message: OutgoingMessage, delivery: Delivery) -> None:
        self._server.publish(
            {
                "kind": "notify",
                "message": message.model_dump(mode="json"),
                "delivery": delivery.model_dump(mode="json"),
            }
        )


class _EnvelopeNotifier:
    """``NotifierPort`` que publica envelopes no stream do IPC."""

    def __init__(self, publish: Callable[[dict[str, Any]], None]) -> None:
        self._publish = publish

    def notify(self, event: AgentEventEnvelope) -> None:
        self._publish({"kind": "agent_event", "event": event.model_dump(mode="json")})


class ScheduleTriage:
    """Triagem determinística por workspace do agendamento (custo zero)."""

    def __init__(self, store: ScheduleStore) -> None:
        self._store = store
        self._by_workspace: dict[Path, DeterministicTriage] = {}

    async def should_wake(self, ctx: TriageContext) -> TriageDecision:
        schedule = self._store.get(ctx.loop_id)
        if schedule is None:
            return TriageDecision(wake=True, reason="agendamento sem registro", conclusive=False)
        workspace = Path(schedule.workspace)
        triage = self._by_workspace.setdefault(workspace, DeterministicTriage(workspace))
        return await triage.should_wake(ctx)


class OrionDaemon:
    """Processo de usuário opt-in que mantém agenda, Inbox e sessão vivas."""

    def __init__(
        self,
        home: Path,
        *,
        settings: DaemonSettings | None = None,
        ui: UiSettings | None = None,
        socket: Path | None = None,
        session_factory: SessionFactory = default_session_factory,
        probe: HardwareProbe | None = None,
        sampler: Callable[[], PressureSample] | None = None,
        desktop: DesktopNotifier | None = None,
        telegram: TelegramNotifier | None = None,
        clock: Callable[[], datetime] = _utcnow,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
        wait_stable: bool = True,
    ) -> None:
        self.home = home
        self.settings = settings or DaemonSettings()
        self.ui = ui or UiSettings()
        self.socket = socket or ipc.socket_path(home)
        self._session_factory = session_factory
        self._probe = probe or HardwareProbe(home=home)
        self._sampler = sampler
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._wait_stable = wait_stable
        self.daemon_id = f"daemon_{uuid.uuid4().hex[:8]}"

        self.server = IpcServer(self.socket)
        self.registry = ComponentRegistry()
        self.store = ScheduleStore(home / "schedules.db")
        self.inbox = Inbox(home / "inbox.db", clock=clock)
        self.activity = ActivityLog(home / "activity.json")
        self._facts: Any = None
        self.presence = PresencePolicy(self._presence_rules, self.activity)
        self._desktop = desktop
        self._telegram = telegram
        self.router = OutputRouter(
            inbox=self.inbox,
            presence=self.presence,
            clients=_ClientPort(self.server),
            desktop=self._desktop_notifier(),
            telegram=telegram,
            clock=clock,
        )
        self.notifier = _EnvelopeNotifier(self.server.publish)
        self.jobs = JobSupervisor(
            home,
            publish=self._publish_job,
            headroom=self._headroom,
            max_concurrent=self.settings.max_concurrent_jobs,
        )
        self.runner = SchedulerRunner(
            self.store,
            self.fire,
            triage=ScheduleTriage(self.store),
            notifier=self.notifier,
            clock=clock,
            sleep=sleep,
            owner=self.daemon_id,
        )
        self.monitor: PressureMonitor | None = None
        self.profile: BootProfile = "minimal"
        self.stabilize: StabilizeResult | None = None
        #: Toda criação de chamada ao provider, com origem (prova de idle = 0, ADR-022).
        self.provider_calls: list[tuple[datetime, str]] = []
        self.started_at: datetime | None = None
        self._session: AgentSession | None = None
        self._session_lock = asyncio.Lock()
        self._stop = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []
        self._lock: SchedulerLock | None = None
        self._briefings_sent: dict[str, date] = {}
        self._register_methods()

    # ------------------------------------------------------------------
    # Montagem
    # ------------------------------------------------------------------

    def _desktop_notifier(self) -> DesktopNotifier | None:
        if self._desktop is not None:
            return self._desktop
        if not self.settings.notifications.desktop:
            return None
        notifier = DesktopNotifier()
        return notifier if notifier.available() else None

    def _open_facts(self) -> Any:
        if self._facts is None:
            try:
                from orion.memory.facts_store import FactsStore

                store = FactsStore(self.home / "facts.db")
                store.initialize()
                self._facts = store
            except Exception as exc:
                logger.warning("daemon: memória indisponível para a presença: %s", exc)
                return None
        return self._facts

    def _presence_rules(self) -> list[PresenceRule]:
        facts = self._open_facts()
        return PresenceRuleStore(facts).list_active() if facts is not None else []

    def _register_components(self) -> None:
        for name in ("ipc", "scheduler", "audit"):
            self.registry.register(FunctionComponent(name, essential=True, cost="low"))
        self.registry.register(FunctionComponent("notifier", cost="low"))
        self.registry.register_lazy("session", self._load_session_component, cost="high")
        self.registry.register_lazy("telegram", self._load_telegram_component, cost="medium")

    async def _load_session_component(self) -> Sleepable:
        return FunctionComponent("session", cost="high", on_sleep=self._drop_session)

    async def _load_telegram_component(self) -> Sleepable:
        notify = self.settings.notifications
        if self._telegram is None and notify.telegram and notify.telegram_chat_id is not None:
            token = load_telegram_token(self.home)
            if token:
                self._telegram = TelegramNotifier(token, notify.telegram_chat_id)
                self.router._telegram = self._telegram  # noqa: SLF001 - carga preguiçosa

        async def drop() -> None:
            if self._telegram is not None:
                with contextlib.suppress(Exception):
                    await self._telegram.aclose()
            self._telegram = None
            self.router._telegram = None  # noqa: SLF001

        return FunctionComponent("telegram", cost="medium", on_sleep=drop)

    async def _drop_session(self) -> None:
        async with self._session_lock:
            if self._session is not None:
                await asyncio.to_thread(self._session.shutdown)
                self._session = None

    def _register_methods(self) -> None:
        s = self.server
        s.register("ping", self._rpc_ping)
        s.register("status", self._rpc_status)
        s.register("activity", self._rpc_activity)
        s.register("inbox.list", self._rpc_inbox_list)
        s.register("inbox.resolve", self._rpc_inbox_resolve)
        s.register("schedule.list", self._rpc_schedule_list)
        s.register("schedule.runs", self._rpc_schedule_runs)
        s.register("schedule.reload", self._rpc_schedule_reload)
        s.register("prompt", self._rpc_prompt)
        s.register("shutdown", self._rpc_shutdown)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Arranque escalonado. Levanta ``SchedulerLocked`` se outro daemon já roda."""
        self._lock = SchedulerLock(self.home / "daemon.lock")
        self._lock.acquire()
        self.started_at = self._clock()
        snapshot = await asyncio.to_thread(self._probe.snapshot)
        self.profile = choose_profile(snapshot, self.settings.boot_profile)
        self.registry.allowed = PROFILE_COMPONENTS[self.profile]
        self._register_components()
        await self.server.start()  # o IPC sobe antes: status responde durante a espera
        if self._wait_stable:
            self.stabilize = await wait_until_stable(
                self._probe,
                thresholds=self.settings.pressure,
                max_wait_s=self.settings.stabilize_max_wait_s,
                clock=self._monotonic,
                sleep=self._sleep,
            )
        sampler = self._sampler or default_sampler()
        self.monitor = PressureMonitor(self.registry, self.settings.pressure, sampler, clock=self._monotonic)
        self._tasks = [
            asyncio.create_task(self.runner.run_forever(), name="orion-scheduler"),
            asyncio.create_task(self.monitor.run(sleep=self._sleep), name="orion-pressure"),
            asyncio.create_task(self._presence_loop(), name="orion-presence"),
        ]
        logger.info("daemon %s ativo (perfil %s)", self.daemon_id, self.profile)

    async def serve_forever(self) -> None:
        await self.start()
        try:
            await self._stop.wait()
        finally:
            await self.close()

    def request_stop(self) -> None:
        self._stop.set()

    async def close(self) -> None:
        self.runner.stop()
        if self.monitor is not None:
            self.monitor.stop()
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks = []
        await self._drop_session()
        await self.server.stop()
        if self._telegram is not None:
            with contextlib.suppress(Exception):
                await self._telegram.aclose()
        self.store.close()
        self.inbox.close()
        if self._facts is not None:
            with contextlib.suppress(Exception):
                self._facts.close()
        if self._lock is not None:
            self._lock.release()
            self._lock = None

    # ------------------------------------------------------------------
    # Pressão, presença, jobs
    # ------------------------------------------------------------------

    def _headroom(self) -> str | None:
        if self.monitor is not None and self.monitor.state == "pressured":
            return "sistema sob pressão: job adiado"
        return None

    def _publish_job(self, payload: dict[str, Any]) -> None:
        self.server.publish(payload)

    async def _presence_loop(self) -> None:
        while not self._stop.is_set():
            await self._sleep(PRESENCE_TICK_S)
            await self.presence_tick()

    async def presence_tick(self) -> None:
        """Expira aprovações vencidas e entrega o resumo quando a regra permite (sem LLM)."""
        now = self._clock()
        self.inbox.expire_due(now)
        due = self.presence.due_briefings(now, self._briefings_sent)
        for rule in due:
            self._briefings_sent[rule.key] = now.date()
        if due or not self.presence.quiet_now(now):
            await self.router.flush_digest()

    # ------------------------------------------------------------------
    # Disparo de agendamentos
    # ------------------------------------------------------------------

    def _counting(self, factory: Callable[[Any], Any], origin: str) -> Callable[[Any], Any]:
        def wrapped(spec: Any) -> Any:
            self.provider_calls.append((self._clock(), origin))
            return factory(spec)

        return wrapped

    def _new_session(
        self,
        workspace: Path,
        *,
        origin: str,
        sink: SessionSink,
        ask_pep: Callable[[Action, ActionLevel], Awaitable[Any]] | None,
    ) -> AgentSession:
        session = self._session_factory(
            workspace=workspace, home=self.home, sink=sink, origin=origin, ask_pep=ask_pep
        )
        session._provider_factory = self._counting(session._provider_factory, origin)  # noqa: SLF001
        return session

    async def fire(self, schedule: Schedule) -> FireOutcome:
        """Um disparo: sessão limpa, não interativa e com autonomia limitada (origin=cron)."""
        from orion.core.events import Action
        from orion.governance.pep import ActionDenied, min_mode

        workspace = Path(schedule.workspace)
        if not workspace.is_dir():
            return FireOutcome(status="failed", detail=f"workspace inexistente: {workspace}")
        sink = NullSink()
        session = await asyncio.to_thread(
            self._new_session, workspace, origin="cron", sink=sink, ask_pep=None
        )
        try:
            if session.settings.project_needs_trust:
                return FireOutcome(status="denied", detail="projeto não confiável: agendamento não roda")
            session.pep.set_interactive(False)
            session.pep.set_mode(min_mode(session.pep.mode, schedule.autonomy))
            await session.fire_hook("ScheduleFire", {"schedule_id": schedule.id, "spec": schedule.spec})
            if schedule.action == "command":
                outcome = await self._fire_command(session, schedule, Action, ActionDenied)
            else:
                answer = await session.run_turn(schedule.prompt)
                cost = session.cost_total + session.agent_usage.cost_usd
                if answer is None:
                    detail = "; ".join(sink.notices) or "turno sem resposta"
                    outcome = FireOutcome(status="failed", detail=detail, cost_usd=cost)
                else:
                    outcome = FireOutcome(status="ok", detail=answer, cost_usd=cost)
        finally:
            await asyncio.to_thread(session.shutdown)
        await self.router.send(
            OutgoingMessage(
                kind="job" if schedule.action == "command" else "message",
                title=f"Agendamento {schedule.id}: {outcome.status}",
                body=outcome.detail[:1500],
                priority="high" if outcome.status in ("failed", "denied") else "normal",
                origin="cron",
                payload={"schedule_id": schedule.id},
            )
        )
        return outcome

    async def _fire_command(
        self, session: AgentSession, schedule: Schedule, action_cls: Any, denied_cls: Any
    ) -> FireOutcome:
        command = schedule.command or ""
        action = action_cls(tool="run_command", params={"command": command})
        try:
            approved = await session.pep.evaluate(action)
        except denied_cls as exc:
            return FireOutcome(status="denied", detail=str(exc))
        if not approved:
            return FireOutcome(status="denied", detail="o PEP negou o comando")
        result = await self.jobs.run(
            f"{schedule.id}_{uuid.uuid4().hex[:6]}", command, cwd=Path(schedule.workspace)
        )
        status = {"ok": "ok", "refused": "skipped"}.get(result.status, "failed")
        detail = result.reason or result.tail[-1000:]
        return FireOutcome(status=status, detail=detail)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Sessão do daemon (attach)
    # ------------------------------------------------------------------

    async def _remote_approval(self, action: Action, level: ActionLevel) -> bool:
        params = ", ".join(f"{k}={str(v)[:80]}" for k, v in action.params.items())
        message = OutgoingMessage(
            kind="approval",
            title=f"{action.tool} aguardando autorização",
            body=params[:600],
            priority="high",
            origin="daemon",
            actions=[NotifyAction(id="approve", label="Aprovar"), NotifyAction(id="deny", label="Negar")],
            ttl_s=self.settings.notifications.approval_ttl_s,
            payload={"action_id": action.event_id, "level": int(level)},
        )
        outcome = await self.router.request_approval(message, ttl_s=message.ttl_s or 600)
        return outcome.approved

    async def session(self) -> AgentSession:
        """Sessão viva do daemon (carregada sob demanda; dorme sob pressão)."""
        await self.registry.acquire("session")
        async with self._session_lock:
            if self._session is None:
                sink = IpcSink(self.server.publish, show_thinking=self.ui.show_thinking)
                self._session = await asyncio.to_thread(
                    self._new_session,
                    Path.home(),
                    origin="daemon",
                    sink=sink,
                    ask_pep=self._remote_approval,
                )
            return self._session

    # ------------------------------------------------------------------
    # Métodos RPC
    # ------------------------------------------------------------------

    async def _rpc_ping(self, params: dict[str, Any], conn: Connection) -> Any:
        return {"pong": True, "version": __version__, "protocol": ipc.PROTOCOL_VERSION}

    def idle_provider_calls(self, since: datetime) -> int:
        return sum(1 for at, _origin in self.provider_calls if at >= since)

    async def _rpc_status(self, params: dict[str, Any], conn: Connection) -> Any:
        next_due = self.store.next_due_at()
        return {
            "daemon_id": self.daemon_id,
            "pid": os.getpid(),
            "version": __version__,
            "profile": self.profile,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "components": self.registry.states(),
            "pressure": self.monitor.state if self.monitor else "normal",
            "schedules": len(self.store.list(enabled_only=True)),
            "next_due": next_due.isoformat() if next_due else None,
            "inbox_pending": self.inbox.pending_count(),
            "clients": self.server.subscriber_count,
            "provider_calls": len(self.provider_calls),
            "quiet": self.presence.quiet_now(self._clock()),
            "stabilized": None if self.stabilize is None else self.stabilize.stable,
        }

    async def _rpc_activity(self, params: dict[str, Any], conn: Connection) -> Any:
        self.activity.record(self._clock())
        return {"ok": True}

    async def _rpc_inbox_list(self, params: dict[str, Any], conn: Connection) -> Any:
        status = params.get("status")
        items = self.inbox.list(status=status if status in ("pending", "resolved", "expired", "read") else None)
        return [item.model_dump(mode="json") for item in items]

    async def _rpc_inbox_resolve(self, params: dict[str, Any], conn: Connection) -> Any:
        item_id = str(params.get("id", ""))
        action = str(params.get("action", ""))
        if not item_id or not action:
            raise ipc.IpcError(ipc.INVALID_PARAMS, "informe id e action")
        self.activity.record(self._clock())
        return {"resolved": self.inbox.resolve(item_id, action, "client")}

    async def _rpc_schedule_list(self, params: dict[str, Any], conn: Connection) -> Any:
        return [s.model_dump(mode="json") for s in self.store.list()]

    async def _rpc_schedule_runs(self, params: dict[str, Any], conn: Connection) -> Any:
        runs = self.store.runs(str(params.get("id", "")), limit=int(params.get("limit", 20)))
        return [r.model_dump(mode="json") for r in runs]

    async def _rpc_schedule_reload(self, params: dict[str, Any], conn: Connection) -> Any:
        self.runner.wake()
        return {"ok": True}

    async def _rpc_prompt(self, params: dict[str, Any], conn: Connection) -> Any:
        text = str(params.get("text", "")).strip()
        if not text:
            raise ipc.IpcError(ipc.INVALID_PARAMS, "texto vazio")
        self.activity.record(self._clock())
        try:
            session = await self.session()
        except ComponentNotAllowed as exc:
            raise ipc.IpcError(
                ipc.DENIED, f"perfil {self.profile} não carrega a sessão ({exc}); use a TUI local"
            ) from exc
        session.origin = "user"  # o Senhor digitando pelo attach
        answer = await session.run_turn(text)
        return {"answer": answer}

    async def _rpc_shutdown(self, params: dict[str, Any], conn: Connection) -> Any:
        asyncio.get_running_loop().call_later(0.05, self.request_stop)
        return {"stopping": True}


async def run_daemon(
    home: Path,
    settings: DaemonSettings,
    ui: UiSettings,
    *,
    hooks: dict[str, list[HookSpec]] | None = None,
) -> None:
    """Ponto de entrada de ``orion-agent daemon run`` (o que a unit do systemd executa).

    Os hooks ``DaemonStart``/``DaemonStop`` vêm só da camada do usuário (o daemon não tem projeto).
    """
    import signal

    from orion.hooks import HookRunner

    daemon = OrionDaemon(home, settings=settings, ui=ui)
    runner = HookRunner(lambda: hooks or {}, cwd=home)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, daemon.request_stop)
    await daemon.start()
    with contextlib.suppress(Exception):
        await runner.run("DaemonStart", {"daemon_id": daemon.daemon_id, "profile": daemon.profile})
    try:
        await daemon._stop.wait()  # noqa: SLF001
    finally:
        with contextlib.suppress(Exception):
            await runner.run("DaemonStop", {"daemon_id": daemon.daemon_id})
        await daemon.close()
