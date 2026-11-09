"""/loop: tetos no código, triagem determinística antes do modelo, origem `loop` no ledger."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from orion.agents.loops import (
    DYNAMIC_MAX_S,
    MAX_LOOPS,
    ChainedTriage,
    DeterministicTriage,
    LoopScheduler,
    ModelTriage,
    describe,
    parse_interval,
)
from orion.agents.models import TriageContext, TriageDecision
from tests.agent_helpers import FakeGateway, TaskRig, make_task_rig, wait_until
from tests.llm_script import ScriptedLLM, say


class FakeTime:
    """Relógio e sleep falsos: o loop gira sem esperar de verdade."""

    def __init__(self) -> None:
        self.now = 1_000_000.0
        self.waits: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds
        await asyncio.sleep(0.001)


class ScriptedTriage:
    def __init__(self, *decisions: TriageDecision, default: TriageDecision | None = None) -> None:
        self.decisions = list(decisions)
        self.default = default or TriageDecision(wake=True, reason="sempre")
        self.contexts: list[TriageContext] = []

    async def should_wake(self, ctx: TriageContext) -> TriageDecision:
        self.contexts.append(ctx)
        return self.decisions.pop(0) if self.decisions else self.default


@pytest.fixture
def rigs() -> Iterator[list[TaskRig]]:
    made: list[TaskRig] = []
    yield made
    for rig in made:
        rig.close()


def _scheduler(rigs, tmp_path: Path, triage, *, scripts=None, time_: FakeTime | None = None, **kw):  # type: ignore[no-untyped-def]
    gateway = FakeGateway(scripts=scripts or [ScriptedLLM(say(f"v{i}")) for i in range(40)])
    rig = make_task_rig(tmp_path, gateway=gateway)
    rigs.append(rig)
    t = time_ or FakeTime()
    scheduler = LoopScheduler(
        executor=rig.executor, manager=rig.manager, parent=lambda: rig.rig.parent, triage=triage,
        notifier=rig.queue, owner="sess-test", clock=t.clock, sleep=t.sleep, min_interval_s=0, **kw,
    )
    return scheduler, rig, t


def test_parse_interval() -> None:
    assert parse_interval("30s") == 30 and parse_interval("5m") == 300
    assert parse_interval("2h") == 7200 and parse_interval("1d") == 86400
    assert parse_interval("abc") is None and parse_interval("5") is None and parse_interval("m5") is None


# ── tetos ───────────────────────────────────────────────────────────────────


async def test_loop_expires_and_never_runs_forever(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    scheduler, rig, t = _scheduler(rigs, tmp_path, ScriptedTriage())
    state = scheduler.start("verifique o CI", interval_s=30, ttl_s=100, max_fires=50)
    await wait_until(lambda: state.status != "active")
    assert state.status == "expired" and state.fires == 3  # 30s, 60s, 90s; aos 100s expira
    event = [e for e in rig.queue.drain() if e.kind == "loop.expired"][0]
    assert event.payload["loop_id"] == state.loop_id and event.origin == "loop"
    assert scheduler.active_count() == 0


async def test_loop_stops_at_the_fire_cap(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    scheduler, rig, _ = _scheduler(rigs, tmp_path, ScriptedTriage())
    state = scheduler.start("x", interval_s=10, ttl_s=10**9, max_fires=2)
    await wait_until(lambda: state.status != "active")
    assert state.status == "done" and state.fires == 2 and len(rig.rig.gateway.made) == 2
    assert any(e.kind == "loop.done" for e in rig.queue.drain())


async def test_each_fire_is_a_budget_limited_subagent_with_loop_origin(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    scheduler, rig, _ = _scheduler(rigs, tmp_path, ScriptedTriage())
    state = scheduler.start("olhe o disco", interval_s=10, max_fires=2, budget_usd=0.05, max_turns=3)
    await wait_until(lambda: state.status == "done")
    assert [m["origin"] for m in rig.rig.gateway.made] == ["loop", "loop"]
    records = rig.manager.list()
    assert {r.origin for r in records} == {"loop"} and len(records) == 2
    assert state.cost_usd == pytest.approx(0.002) and state.last_status == "ok"
    # o 2º disparo recebe o resultado do anterior como contexto
    second_input = rig.rig.gateway.made[1]["script"].requests[0][0].text
    assert "Previous check result" in second_input and "v0" in second_input


async def test_loop_fire_budget_can_only_be_lowered(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    scripts = [ScriptedLLM(say("a"))]
    scheduler, rig, _ = _scheduler(rigs, tmp_path, ScriptedTriage(), scripts=scripts)
    # explore tem 0.10; o loop pede 0.01: a reserva (~0.04) já não cabe -> parcial, nunca ultrapassa
    state = scheduler.start("x", interval_s=10, max_fires=1, budget_usd=0.01)
    await wait_until(lambda: state.status == "done")
    assert state.last_status == "partial_budget" and state.cost_usd == 0.0


async def test_creation_validations(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    scheduler, rig, _ = _scheduler(rigs, tmp_path, ScriptedTriage(default=TriageDecision(wake=False)))
    with pytest.raises(ValueError, match="verificar"):
        scheduler.start("  ")
    for bad in ({"ttl_s": 0}, {"max_fires": 0}, {"budget_usd": 0}, {"max_turns": 0}):
        with pytest.raises(ValueError, match="positivos"):
            scheduler.start("x", interval_s=10, **bad)
    locked = LoopScheduler(
        executor=rig.executor, manager=rig.manager, parent=lambda: rig.rig.parent,
        triage=ScriptedTriage(), notifier=rig.queue, owner="s", min_interval_s=30,
    )
    with pytest.raises(ValueError, match="mínimo"):
        locked.start("x", interval_s=5)
    ids = [scheduler.start(f"l{i}", interval_s=10**6).loop_id for i in range(MAX_LOOPS)]
    with pytest.raises(ValueError, match="no máximo"):
        scheduler.start("a mais", interval_s=10)
    assert scheduler.stop_all() == MAX_LOOPS and all(not scheduler.get(i).active for i in ids)  # type: ignore[union-attr]


async def test_stop_cancels_a_sleeping_loop(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    scheduler, rig, _ = _scheduler(rigs, tmp_path, ScriptedTriage())
    real = LoopScheduler(
        executor=rig.executor, manager=rig.manager, parent=lambda: rig.rig.parent,
        triage=ScriptedTriage(), notifier=rig.queue, owner="s", min_interval_s=0,
    )
    state = real.start("x", interval_s=3600)  # dorme de verdade
    await asyncio.sleep(0.05)
    assert real.stop(state.loop_id) and state.status == "stopped"
    assert real.stop(state.loop_id) is False and real.stop("loop_nope") is False
    assert len(rig.rig.gateway.made) == 0  # dormir não custa tokens
    assert "stopped" in describe(state) and "a cada 3600s" in describe(state)


# ── triagem ─────────────────────────────────────────────────────────────────


async def test_skipped_checks_do_not_wake_the_model(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    triage = ScriptedTriage(
        TriageDecision(wake=True, reason="primeiro"),
        TriageDecision(wake=False, reason="nada mudou"),
        TriageDecision(wake=False, reason="nada mudou"),
        TriageDecision(wake=True, reason="mudou"),
    )
    scheduler, rig, _ = _scheduler(rigs, tmp_path, triage)
    state = scheduler.start("x", interval_s=10, max_fires=2)
    await wait_until(lambda: state.status == "done")
    assert state.skipped == 2 and state.fires == 2 and len(rig.rig.gateway.made) == 2
    assert state.checks >= 4 and [c.fired for c in triage.contexts[:4]] == [0, 1, 1, 1]


async def test_dynamic_interval_backs_off_when_nothing_changes(rigs, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    triage = ScriptedTriage(
        *[TriageDecision(wake=False)] * 6, TriageDecision(wake=True), default=TriageDecision(wake=False)
    )
    scheduler, rig, t = _scheduler(rigs, tmp_path, triage, dynamic_start_s=60)
    state = scheduler.start("x", interval_s=None, max_fires=1, ttl_s=10**9)
    await wait_until(lambda: state.fires == 1)
    assert t.waits[:6] == [60, 120, 240, 480, 960, DYNAMIC_MAX_S]  # dobra até o teto
    await wait_until(lambda: state.status == "active" and state.checks >= 8)
    assert t.waits[6] == DYNAMIC_MAX_S
    scheduler.stop(state.loop_id)


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for args in (("init", "-q"), ("config", "user.email", "t@t"), ("config", "user.name", "t")):
        subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)
    (path / "a.txt").write_text("1\n")
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True, capture_output=True)
    return path


async def test_deterministic_triage_follows_the_repository_state(tmp_path: Path) -> None:
    repo = _git_repo(tmp_path / "repo")
    triage = DeterministicTriage(repo)
    ctx = TriageContext(loop_id="l1", goal="g", fired=0)
    first = await triage.should_wake(ctx)
    assert first.wake and first.conclusive and first.reason == "primeiro disparo"
    again = await triage.should_wake(ctx)
    assert not again.wake and again.conclusive and "nada mudou" in again.reason

    (repo / "a.txt").write_text("2\n")  # edita um arquivo já rastreado
    assert (await triage.should_wake(ctx)).wake
    assert not (await triage.should_wake(ctx)).wake
    (repo / "b.txt").write_text("novo\n")  # arquivo novo
    assert (await triage.should_wake(ctx)).wake
    other = await triage.should_wake(TriageContext(loop_id="l2", goal="g", fired=0))
    assert other.wake and other.reason == "primeiro disparo"  # estado por loop


async def test_deterministic_triage_is_inconclusive_outside_git(tmp_path: Path) -> None:
    decision = await DeterministicTriage(tmp_path).should_wake(TriageContext(loop_id="l", goal="g", fired=0))
    assert decision.wake and not decision.conclusive


async def test_model_triage_runs_only_when_deterministic_is_inconclusive(tmp_path: Path) -> None:
    ctx = TriageContext(loop_id="l", goal="o CI passou?", fired=1, last_summary="verde", last_status="ok")
    skip_gateway = FakeGateway(scripts=[ScriptedLLM(say("SKIP"))])
    chained = ChainedTriage(DeterministicTriage(tmp_path), ModelTriage(skip_gateway))  # tmp_path não é git
    decision = await chained.should_wake(ctx)
    assert not decision.wake and "SKIP" in decision.reason
    made = skip_gateway.made[0]
    assert made["max_tokens"] == 8 and made["origin"] == "loop"  # mínimo e origem `loop`
    assert skip_gateway.resolved[0] == {"tier": "fast", "mutating": False, "profile": None, "pinned": None, "reuse": None}
    prompt = made["script"].requests[0][0].text
    assert "o CI passou?" in prompt and "verde" in prompt

    wake_gateway = FakeGateway(scripts=[ScriptedLLM(say("WAKE"))])
    assert (await ModelTriage(wake_gateway).should_wake(ctx)).wake

    repo = _git_repo(tmp_path / "repo")
    never = FakeGateway(scripts=[ScriptedLLM(say("SKIP"))])
    deterministic = ChainedTriage(DeterministicTriage(repo), ModelTriage(never))
    assert (await deterministic.should_wake(ctx)).wake  # conclusivo: o modelo nem é consultado
    assert never.made == []


async def test_model_triage_fails_open_when_unavailable() -> None:
    ctx = TriageContext(loop_id="l", goal="g", fired=0)
    no_model = FakeGateway(fail_resolve="sem candidato")
    decision = await ModelTriage(no_model).should_wake(ctx)
    assert decision.wake and not decision.conclusive

    def boom() -> None:
        raise RuntimeError("provedor caiu")

    broken = FakeGateway(scripts=[ScriptedLLM(say("x"))], on_call=boom)
    assert (await ModelTriage(broken).should_wake(ctx)).wake
    assert (await ChainedTriage(ScriptedTriage(TriageDecision(wake=False))).should_wake(ctx)).wake is False
