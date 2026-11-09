"""Testes do agendador (Sprint 7): cronspec, store, lock e runner com relógio injetado."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from orion.agents.models import AgentEventEnvelope, TriageContext, TriageDecision
from orion.governance.pep import AutonomyMode
from orion.scheduler import (
    MAX_SCHEDULES,
    FireOutcome,
    InvalidSpec,
    Schedule,
    SchedulerLock,
    SchedulerLocked,
    SchedulerRunner,
    ScheduleRun,
    ScheduleStore,
    describe,
    next_fire,
    spec_kind,
    validate_spec,
)

UTC_TZ = UTC
T0 = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def nf(spec: str, after: datetime = T0, tz: ZoneInfo | None = None) -> datetime | None:
    return next_fire(spec, after, tz=tz or ZoneInfo("UTC"))


# ---------------------------------------------------------------- cronspec


def test_cron_basic_and_strictly_after() -> None:
    assert nf("30 12 * * *") == datetime(2026, 11, 9, 12, 30, tzinfo=UTC)
    assert nf("0 12 * * *") == datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    assert nf("* * * * *") == T0 + timedelta(minutes=1)


def test_cron_lists_ranges_steps() -> None:
    assert nf("0,30 13 * * *") == datetime(2026, 11, 9, 13, 0, tzinfo=UTC)
    assert nf("*/15 * * * *", T0 + timedelta(minutes=1)) == T0 + timedelta(minutes=15)
    assert nf("10-20/5 14 * * *") == datetime(2026, 11, 9, 14, 10, tzinfo=UTC)
    assert nf("0 9-17/4 * * *") == datetime(2026, 11, 9, 13, 0, tzinfo=UTC)
    assert nf("5/20 13 * * *") == datetime(2026, 11, 9, 13, 5, tzinfo=UTC)


def test_cron_names_and_sunday() -> None:
    # 2026-11-09 e segunda; proxima segunda as 8h.
    assert nf("0 8 * * mon") == datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
    sunday = datetime(2026, 11, 15, 0, 0, tzinfo=UTC)
    assert nf("0 0 * * 0", T0) == sunday
    assert nf("0 0 * * 7", T0) == sunday
    assert nf("0 0 * * sun", T0) == sunday
    assert nf("0 0 1 jan *") == datetime(2027, 1, 1, 0, 0, tzinfo=UTC)
    assert nf("0 0 * * mon-wed", T0) == datetime(2026, 11, 10, 0, 0, tzinfo=UTC)


def test_cron_dom_dow_or_semantics() -> None:
    # dia 15 OU segunda: a proxima segunda (16) vem depois do 15 (domingo) -> 15 vence.
    assert nf("0 0 15 * mon") == datetime(2026, 11, 15, 0, 0, tzinfo=UTC)
    # so dom restrito (dow *) => E
    assert nf("0 0 15 * *") == datetime(2026, 11, 15, 0, 0, tzinfo=UTC)
    # dow restrito + dom '*' => so dow
    assert nf("0 0 */1 * mon") == datetime(2026, 11, 16, 0, 0, tzinfo=UTC)


def test_cron_macros() -> None:
    assert nf("@hourly") == datetime(2026, 11, 9, 13, 0, tzinfo=UTC)
    assert nf("@daily") == datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    assert nf("@weekly") == datetime(2026, 11, 15, 0, 0, tzinfo=UTC)
    assert nf("@monthly") == datetime(2026, 12, 1, 0, 0, tzinfo=UTC)
    assert nf("@yearly") == datetime(2027, 1, 1, 0, 0, tzinfo=UTC)
    assert validate_spec("@Daily") == "@daily"


def test_cron_impossible_dates_return_none() -> None:
    assert nf("0 0 31 2 *") is None
    assert nf("0 0 30 feb *") is None


def test_cron_leap_day() -> None:
    assert nf("0 0 29 2 *") == datetime(2028, 2, 29, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "* * * *",
        "61 * * * *",
        "* 24 * * *",
        "* * 0 * *",
        "* * * 13 *",
        "* * * * 8",
        "5-1 * * * *",
        "*/0 * * * *",
        "*/x * * * *",
        "a * * * *",
        ",1 * * * *",
        "banana",
        "30s",
        "every 10s",
    ],
)
def test_invalid_specs(bad: str) -> None:
    with pytest.raises(InvalidSpec):
        validate_spec(bad)


def test_next_fire_requires_aware() -> None:
    with pytest.raises(ValueError):
        next_fire("* * * * *", datetime(2026, 1, 1))


def test_intervals() -> None:
    assert validate_spec("5m") == "every 5m"
    assert validate_spec("every 2h") == "every 2h"
    assert spec_kind("5m") == "interval"
    assert nf("every 5m") == T0 + timedelta(minutes=5)
    assert nf("2h") == T0 + timedelta(hours=2)
    assert nf("1d") == T0 + timedelta(days=1)
    with pytest.raises(InvalidSpec):
        next_fire("30s", T0)
    with pytest.raises(InvalidSpec):
        validate_spec("every 30s")


def test_once_past_future_and_naive() -> None:
    assert spec_kind("2026-11-10T08:00") == "once"
    assert nf("2026-11-10T08:00") == datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    assert nf("2026-11-10T08:00:00+02:00") == datetime(2026, 11, 10, 6, 0, tzinfo=UTC)
    assert nf("2026-11-01T08:00") is None
    sp = ZoneInfo("America/Sao_Paulo")
    assert nf("2026-11-10T08:00", tz=sp) == datetime(2026, 11, 10, 11, 0, tzinfo=UTC)
    # sem tz: usa a zona local do sistema (apenas garante que resolve)
    assert next_fire("2099-01-01T00:00", T0) is not None
    assert validate_spec(" 2026-11-10T08:00 ") == "2026-11-10T08:00"


def test_describe() -> None:
    assert "cron" in describe("0 8 * * *")
    assert "minuto" in describe("5m")
    assert "hora" in describe("every 2h")
    assert "dia" in describe("1d")
    assert "uma vez" in describe("2026-11-10T08:00")


def test_cron_local_default_tz_runs() -> None:
    got = next_fire("*/5 * * * *", T0)
    assert got is not None and got > T0


def test_dst_nonexistent_and_ambiguous_new_york() -> None:
    ny = ZoneInfo("America/New_York")
    # 2026-03-08 02:30 local nao existe: pula para o dia seguinte.
    after = datetime(2026, 3, 8, 5, 0, tzinfo=UTC)  # 00:00 local
    got = next_fire("30 2 * * *", after, tz=ny)
    assert got == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)  # 02:30 EDT (UTC-4)
    # 2026-11-01 01:30 ocorre duas vezes (05:30Z e 06:30Z)
    first = next_fire("30 1 * * *", datetime(2026, 11, 1, 3, 0, tzinfo=UTC), tz=ny)
    assert first == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    second = next_fire("30 1 * * *", first, tz=ny) if first else None
    assert second == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


def test_dst_sao_paulo_offset_applies() -> None:
    sp = ZoneInfo("America/Sao_Paulo")
    got = next_fire("0 8 * * *", datetime(2026, 6, 1, 0, 0, tzinfo=UTC), tz=sp)
    assert got == datetime(2026, 6, 1, 11, 0, tzinfo=UTC)


# ---------------------------------------------------------------- store


def make(ws: Path, spec: str = "5m", **kw: object) -> Schedule:
    return Schedule(spec=spec, prompt="checar", workspace=str(ws), **kw)  # type: ignore[arg-type]


def test_schedule_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Schedule(spec="nope", workspace=str(tmp_path))
    with pytest.raises(ValueError):
        Schedule(spec="5m", action="command", workspace=str(tmp_path))
    with pytest.raises(ValueError):
        Schedule(spec="5m", workspace=str(tmp_path), budget_usd=9)
    s = Schedule(spec="5m", workspace=str(tmp_path), created_at=datetime(2026, 1, 1))
    assert s.created_at.tzinfo is not None
    assert s.autonomy is AutonomyMode.SUPERVISED


def test_store_persistence_and_modes(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "sched.db"
    st = ScheduleStore(path)
    assert (path.stat().st_mode & 0o777) == 0o600
    s = st.add(make(tmp_path, "every 10m"))
    assert s.next_run_at is not None
    st.record_run(
        ScheduleRun(schedule_id=s.id, started_at=T0, finished_at=T0, status="ok", detail="x")
    )
    st.close()

    st2 = ScheduleStore(path)
    got = st2.get(s.id)
    assert got is not None and got.spec == "every 10m" and got.next_run_at == s.next_run_at
    assert [r.status for r in st2.runs(s.id)] == ["ok"]
    assert len(st2.list()) == 1
    assert st2.get("nope") is None
    got.enabled = False
    st2.update(got)
    assert st2.list(enabled_only=True) == []
    assert st2.next_due_at() is None
    assert st2.delete(s.id) is True
    assert st2.delete(s.id) is False
    assert st2.runs(s.id) == []
    st2.close()


def test_store_due_ordering_and_next_due(tmp_path: Path) -> None:
    st = ScheduleStore(tmp_path / "s.db")
    a = st.add(make(tmp_path, next_run_at=T0 + timedelta(minutes=5)))
    b = st.add(make(tmp_path, next_run_at=T0 + timedelta(minutes=1)))
    st.add(make(tmp_path, next_run_at=T0 + timedelta(hours=1)))
    assert st.next_due_at() == T0 + timedelta(minutes=1)
    assert [x.id for x in st.due(T0 + timedelta(minutes=10))] == [b.id, a.id]
    assert st.due(T0) == []
    st.close()


def test_store_max_schedules(tmp_path: Path) -> None:
    st = ScheduleStore(tmp_path / "s.db")
    for _ in range(MAX_SCHEDULES):
        st.add(make(tmp_path))
    with pytest.raises(ValueError):
        st.add(make(tmp_path))
    st.close()


def test_lock_exclusivity(tmp_path: Path) -> None:
    path = tmp_path / "run" / "sched.lock"
    a = SchedulerLock(path)
    a.acquire()
    a.acquire()  # idempotente
    with pytest.raises(SchedulerLocked):
        SchedulerLock(path).acquire()
    a.release()
    a.release()
    with SchedulerLock(path):
        with pytest.raises(SchedulerLocked), SchedulerLock(path):
            pass


# ---------------------------------------------------------------- runner


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.sleeps: list[float] = []
        self.runner: SchedulerRunner | None = None
        self.stop_at: datetime | None = None

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += timedelta(seconds=seconds)
        if self.stop_at and self.now >= self.stop_at and self.runner:
            self.runner.stop()


class Recorder:
    def __init__(self, outcome: FireOutcome | None = None, exc: Exception | None = None) -> None:
        self.calls: list[str] = []
        self.outcome = outcome or FireOutcome(status="ok", detail="feito", cost_usd=0.01)
        self.exc = exc

    async def __call__(self, s: Schedule) -> FireOutcome:
        self.calls.append(s.id)
        if self.exc:
            raise self.exc
        return self.outcome


class Notes:
    def __init__(self) -> None:
        self.events: list[AgentEventEnvelope] = []

    def notify(self, event: AgentEventEnvelope) -> None:
        self.events.append(event)


class Triage:
    def __init__(self, wake: bool = True, exc: bool = False) -> None:
        self.wake = wake
        self.exc = exc
        self.ctxs: list[TriageContext] = []

    async def should_wake(self, ctx: TriageContext) -> TriageDecision:
        self.ctxs.append(ctx)
        if self.exc:
            raise RuntimeError("boom")
        return TriageDecision(wake=self.wake, reason="nada mudou")


def build(
    tmp_path: Path, **kw: object
) -> tuple[ScheduleStore, FakeClock, Recorder, Notes, SchedulerRunner]:
    st = ScheduleStore(tmp_path / "s.db")
    clock = FakeClock(T0)
    rec = Recorder()
    notes = Notes()
    runner = SchedulerRunner(
        st,
        rec,
        notifier=notes,
        clock=clock,
        sleep=clock.sleep,
        **kw,  # type: ignore[arg-type]
    )
    clock.runner = runner
    return st, clock, rec, notes, runner


async def test_tick_fires_due_and_advances(tmp_path: Path) -> None:
    st, clock, rec, notes, runner = build(tmp_path)
    s = st.add(make(tmp_path, "every 5m", next_run_at=T0 - timedelta(seconds=1)))
    runs = await runner.tick()
    assert [r.status for r in runs] == ["ok"]
    got = st.get(s.id)
    assert got is not None
    assert got.runs == 1 and got.last_status == "ok" and got.last_summary == "feito"
    assert got.next_run_at == T0 + timedelta(minutes=5)
    assert runner.fires == 1
    assert [e.kind for e in notes.events] == ["schedule.fired"]
    assert notes.events[0].origin == "cron"
    assert await runner.tick() == []


async def test_one_shot_disabled_after_run(tmp_path: Path) -> None:
    st, _, rec, _, runner = build(tmp_path)
    s = st.add(make(tmp_path, "2026-11-09T12:30:00+00:00", next_run_at=T0 - timedelta(seconds=1)))
    await runner.tick()
    got = st.get(s.id)
    assert got is not None and got.enabled is False and got.next_run_at is None
    assert await runner.tick() == []
    assert len(rec.calls) == 1


async def test_fire_exception_becomes_failed(tmp_path: Path) -> None:
    st, clock, _, notes, _ = build(tmp_path)
    runner = SchedulerRunner(
        st, Recorder(exc=RuntimeError("x")), notifier=notes, clock=clock, sleep=clock.sleep
    )
    s = st.add(make(tmp_path, next_run_at=T0))
    runs = await runner.tick()
    assert runs[0].status == "failed" and "RuntimeError" in runs[0].detail
    assert notes.events[-1].kind == "schedule.failed"
    got = st.get(s.id)
    assert got is not None and got.enabled and got.last_status == "failed"


async def test_triage_skip_and_fail_open(tmp_path: Path) -> None:
    st, clock, rec, notes, _ = build(tmp_path)
    s = st.add(make(tmp_path, next_run_at=T0))
    runner = SchedulerRunner(
        st, rec, triage=Triage(wake=False), notifier=notes, clock=clock, sleep=clock.sleep
    )
    runs = await runner.tick()
    assert runs[0].status == "skipped" and rec.calls == [] and runner.fires == 0
    assert notes.events[-1].kind == "schedule.skipped"
    got = st.get(s.id)
    assert got is not None and got.next_run_at == T0 + timedelta(minutes=5) and got.runs == 0

    # triagem que falha -> acorda
    clock.now += timedelta(minutes=6)
    tri = Triage(exc=True)
    runner2 = SchedulerRunner(st, rec, triage=tri, clock=clock, sleep=clock.sleep)
    runs = await runner2.tick()
    assert runs[0].status == "ok" and len(rec.calls) == 1
    assert tri.ctxs[0].goal == "checar"

    # triage=False ignora a porta
    clock.now += timedelta(minutes=6)
    got2 = st.get(s.id)
    assert got2 is not None
    got2.triage = False
    st.update(got2)
    tri2 = Triage(wake=False)
    runner3 = SchedulerRunner(st, rec, triage=tri2, clock=clock, sleep=clock.sleep)
    await runner3.tick()
    assert tri2.ctxs == [] and len(rec.calls) == 2


async def test_notifier_failure_is_swallowed(tmp_path: Path) -> None:
    class Bad:
        def notify(self, event: AgentEventEnvelope) -> None:
            raise RuntimeError("x")

    st, clock, rec, _, _ = build(tmp_path)
    st.add(make(tmp_path, next_run_at=T0))
    runner = SchedulerRunner(st, rec, notifier=Bad(), clock=clock, sleep=clock.sleep)
    assert (await runner.tick())[0].status == "ok"


async def test_catch_up_skip_vs_run_once(tmp_path: Path) -> None:
    st, clock, rec, notes, runner = build(tmp_path)
    past = T0 - timedelta(hours=5)
    skip = st.add(make(tmp_path, "every 1h", next_run_at=past, catchup="skip"))
    once = st.add(make(tmp_path, "every 1h", next_run_at=past, catchup="run_once"))
    shot = st.add(make(tmp_path, "2026-11-09T08:00:00+00:00", next_run_at=past))
    future = st.add(make(tmp_path, "every 1h", next_run_at=T0 + timedelta(hours=1)))
    runs = await runner.catch_up()
    by_id = {r.schedule_id: r for r in runs}
    assert by_id[skip.id].status == "missed"
    assert by_id[once.id].status == "ok"
    assert by_id[shot.id].status == "missed"
    assert future.id not in by_id
    assert rec.calls == [once.id]  # exatamente uma vez, apesar de 5 perdidos
    g_skip, g_shot, g_once = st.get(skip.id), st.get(shot.id), st.get(once.id)
    assert g_skip is not None and g_skip.next_run_at == T0 + timedelta(hours=1)
    assert g_shot is not None and g_shot.enabled is False
    assert g_once is not None and g_once.next_run_at == T0 + timedelta(hours=1)
    assert "schedule.missed" in [e.kind for e in notes.events]


async def test_idle_hour_never_fires_and_does_not_spin(tmp_path: Path) -> None:
    st, clock, rec, _, runner = build(tmp_path)
    clock.stop_at = T0 + timedelta(hours=1)
    await asyncio.wait_for(runner.run_forever(), timeout=5)
    assert rec.calls == [] and runner.fires == 0
    assert len(clock.sleeps) <= 3
    assert clock.now >= T0 + timedelta(hours=1)
    st.close()


async def test_run_forever_fires_schedule_due_in_10_minutes_once(tmp_path: Path) -> None:
    st, clock, rec, _, runner = build(tmp_path, max_sleep_s=3600.0)
    s = st.add(make(tmp_path, "every 1d", next_run_at=T0 + timedelta(minutes=10)))
    clock.stop_at = T0 + timedelta(minutes=30)
    await asyncio.wait_for(runner.run_forever(), timeout=5)
    assert rec.calls == [s.id] and runner.fires == 1
    assert clock.sleeps[0] == 600.0
    assert len(clock.sleeps) <= 4


async def test_run_forever_max_sleep_cap_and_wake(tmp_path: Path) -> None:
    st = ScheduleStore(tmp_path / "s.db")
    clock = FakeClock(T0)
    rec = Recorder()
    gate = asyncio.Event()

    async def blocking_sleep(seconds: float) -> None:
        clock.sleeps.append(seconds)
        await gate.wait()

    runner = SchedulerRunner(st, rec, clock=clock, sleep=blocking_sleep, max_sleep_s=100.0)
    task = asyncio.create_task(runner.run_forever())
    for _ in range(5):
        await asyncio.sleep(0)
    assert clock.sleeps == [100.0]
    # nova agenda vencida + wake => dispara sem esperar o sleep terminar
    st.add(make(tmp_path, "every 5m", next_run_at=T0))
    runner.wake()
    for _ in range(20):
        await asyncio.sleep(0)
    assert len(rec.calls) == 1
    runner.stop()
    await asyncio.wait_for(task, timeout=5)
    st.close()


async def test_run_forever_wake_requested_before_wait(tmp_path: Path) -> None:
    st, clock, rec, _, runner = build(tmp_path)
    runner.wake()
    clock.stop_at = T0 + timedelta(seconds=1)
    await asyncio.wait_for(runner.run_forever(), timeout=5)
    st.close()


async def test_due_without_progress_does_not_spin(tmp_path: Path) -> None:
    st, clock, rec, _, runner = build(tmp_path)
    s = st.add(make(tmp_path, "every 5m", next_run_at=T0 - timedelta(minutes=1)))
    s.enabled = True
    clock.stop_at = T0 + timedelta(minutes=12)
    await asyncio.wait_for(runner.run_forever(), timeout=5)
    # catch_up (skip) + disparos em T0+5m e T0+10m: poucos sleeps, nunca 0
    assert all(x > 0 for x in clock.sleeps)
    assert len(clock.sleeps) <= 6
