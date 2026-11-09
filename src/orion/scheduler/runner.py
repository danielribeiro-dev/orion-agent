"""Laço do agendador: dorme até o próximo horário devido e dispara, sem chamar modelo ocioso.

Determinístico (ADR-022): em espera só há um ``sleep`` até ``next_due_at`` (limitado por
``max_sleep_s``). O disparo em si é delegado à porta ``FirePort`` do daemon. Relógio e sleep são
injetáveis para testes.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from orion.agents.models import AgentEventEnvelope, TriageContext
from orion.agents.ports import NotifierPort, TriagePort
from orion.scheduler.cronspec import next_fire, spec_kind
from orion.scheduler.store import Schedule, ScheduleRun, ScheduleStore

logger = logging.getLogger(__name__)

_MIN_IDLE_SLEEP_S = 1.0


class FireOutcome(BaseModel):
    """Resultado de um disparo, devolvido pela porta."""

    status: Literal["ok", "failed", "denied", "skipped"]
    detail: str = ""
    cost_usd: float = 0.0


FirePort = Callable[[Schedule], Awaitable[FireOutcome]]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SchedulerRunner:
    """Executa as agendas vencidas e dorme até a próxima."""

    def __init__(
        self,
        store: ScheduleStore,
        fire: FirePort,
        *,
        triage: TriagePort | None = None,
        notifier: NotifierPort | None = None,
        clock: Callable[[], datetime] = _utc_now,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        max_sleep_s: float = 3600.0,
        owner: str = "daemon",
    ) -> None:
        self._store = store
        self._fire = fire
        self._triage = triage
        self._notifier = notifier
        self._clock = clock
        self._sleep = sleep
        self._max_sleep_s = max_sleep_s
        self._owner = owner
        self._fires = 0
        self._stopped = False
        self._wake: asyncio.Event | None = None
        self._wake_requested = False

    @property
    def fires(self) -> int:
        """Quantas vezes ``fire`` foi realmente chamado (prova de ociosidade)."""
        return self._fires

    def wake(self) -> None:
        """Pede ao laço que recalcule o próximo horário (agendas mudaram)."""
        self._wake_requested = True
        if self._wake is not None:
            self._wake.set()

    def stop(self) -> None:
        """Encerra ``run_forever`` de forma limpa."""
        self._stopped = True
        self.wake()

    def _emit(self, s: Schedule, kind: str, payload: dict[str, Any]) -> None:
        if self._notifier is None:
            return
        try:
            self._notifier.notify(
                AgentEventEnvelope(
                    agent_id=s.id,
                    session_id=self._owner,
                    origin="cron",
                    kind=kind,
                    payload=payload,
                    timestamp=self._clock(),
                )
            )
        except Exception:
            logger.exception("falha ao notificar %s", kind)

    def _advance(self, s: Schedule, now: datetime) -> None:
        """Calcula o próximo disparo; one-shots (ou specs esgotadas) são desabilitados."""
        nxt = next_fire(s.spec, now) if spec_kind(s.spec) != "once" else None
        s.next_run_at = nxt
        if nxt is None:
            s.enabled = False

    def _finish(
        self,
        s: Schedule,
        now: datetime,
        status: Literal["ok", "failed", "denied", "skipped", "missed"],
        detail: str,
        cost: float,
        *,
        fired: bool,
    ) -> ScheduleRun:
        self._advance(s, now)
        finished = self._clock()
        if fired:
            s.runs += 1
            s.last_run_at = now
        s.last_status = status
        s.last_summary = detail[:2000]
        self._store.update(s)
        run = ScheduleRun(
            schedule_id=s.id,
            started_at=now,
            finished_at=finished,
            status=status,
            detail=detail[:2000],
            cost_usd=cost,
        )
        self._store.record_run(run)
        return run

    async def _should_wake(self, s: Schedule) -> tuple[bool, str]:
        if not s.triage or self._triage is None:
            return True, ""
        ctx = TriageContext(
            loop_id=s.id,
            goal=s.prompt or s.command or "",
            fired=s.runs,
            last_summary=s.last_summary,
            last_status=s.last_status,
        )
        try:
            decision = await self._triage.should_wake(ctx)
        except Exception:
            logger.exception("triagem falhou; seguindo o caminho normal")
            return True, ""
        return decision.wake, decision.reason

    async def _run_one(self, s: Schedule, now: datetime) -> ScheduleRun:
        wake, reason = await self._should_wake(s)
        if not wake:
            self._emit(s, "schedule.skipped", {"reason": reason[:200]})
            return self._finish(
                s, now, "skipped", reason or "triagem: sem mudanças", 0.0, fired=False
            )
        self._fires += 1
        try:
            outcome = await self._fire(s)
        except Exception as exc:
            logger.exception("disparo %s falhou", s.id)
            outcome = FireOutcome(status="failed", detail=f"{type(exc).__name__}: {exc}")
        kind = "schedule.fired" if outcome.status == "ok" else "schedule.failed"
        self._emit(s, kind, {"status": outcome.status, "detail": outcome.detail[:200]})
        return self._finish(s, now, outcome.status, outcome.detail, outcome.cost_usd, fired=True)

    async def catch_up(self) -> list[ScheduleRun]:
        """Trata disparos perdidos enquanto o daemon esteve parado (chamado uma vez ao iniciar)."""
        now = self._clock()
        runs: list[ScheduleRun] = []
        for s in self._store.list(enabled_only=True):
            if s.next_run_at is None or s.next_run_at >= now:
                continue
            if s.catchup == "run_once":
                runs.append(await self._run_one(s, now))
                continue
            self._emit(s, "schedule.missed", {"was_due": s.next_run_at.isoformat()})
            runs.append(
                self._finish(s, now, "missed", "disparo perdido (catchup=skip)", 0.0, fired=False)
            )
        return runs

    async def tick(self) -> list[ScheduleRun]:
        """Dispara, em sequência, todas as agendas vencidas."""
        now = self._clock()
        return [await self._run_one(s, now) for s in self._store.due(now)]

    def _seconds_until_next(self) -> float:
        nxt = self._store.next_due_at()
        if nxt is None:
            return self._max_sleep_s
        return min(max((nxt - self._clock()).total_seconds(), 0.0), self._max_sleep_s)

    async def _wait(self, seconds: float) -> None:
        """Dorme ``seconds`` ou até ``wake()``/``stop()``, o que vier primeiro."""
        assert self._wake is not None
        if self._wake_requested:
            self._wake_requested = False
            self._wake.clear()
            return
        sleeper = asyncio.ensure_future(self._sleep(seconds))
        waiter = asyncio.ensure_future(self._wake.wait())
        try:
            await asyncio.wait({sleeper, waiter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (sleeper, waiter):
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
        if sleeper.done() and not sleeper.cancelled():
            sleeper.result()
        self._wake.clear()
        self._wake_requested = False

    async def run_forever(self) -> None:
        """``catch_up`` e, depois, dorme até o próximo horário devido e dispara."""
        self._wake = asyncio.Event()
        self._stopped = False
        await self.catch_up()
        while not self._stopped:
            seconds = self._seconds_until_next()
            if seconds > 0:
                await self._wait(seconds)
                if self._stopped:
                    break
            runs = await self.tick()
            if not runs and seconds <= 0 and not self._stopped:
                await self._wait(_MIN_IDLE_SLEEP_S)
