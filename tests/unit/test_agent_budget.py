"""Orçamento de agentes: reserva antecipada, tetos encadeados e resultado parcial retomável."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

import pytest

from orion.agents.budget import (
    AgentBudget,
    AggregateBudget,
    BudgetExhausted,
    BudgetNode,
    DailyBudget,
    estimate_call_usd,
)
from orion.agents.models import ResolvedModel
from orion.agents.runner import TaskRequest
from orion.settings.models import AgentsSettings
from tests.agent_helpers import FakeGateway, make_rig
from tests.llm_script import ScriptedLLM, say, use


class TestBudgetNodes:
    def test_reserve_settle_moves_reserved_to_spent_along_the_chain(self) -> None:
        daily = DailyBudget(lambda: 1.0)
        aggregate = AggregateBudget(0.5, parent=daily)
        agent = AgentBudget(0.2, max_turns=5, parent=aggregate)
        reservation = agent.reserve(0.1)
        assert (agent.reserved, aggregate.reserved, daily.reserved) == (0.1, 0.1, 0.1)
        agent.settle(reservation, 0.04)
        assert (agent.reserved, agent.spent, aggregate.spent) == (0.0, 0.04, 0.04)
        agent.settle(reservation, 0.04)  # idempotente
        assert agent.spent == 0.04

    def test_each_level_can_refuse(self) -> None:
        daily = DailyBudget(lambda: 0.05)
        aggregate = AggregateBudget(0.5, parent=daily)
        agent = AgentBudget(0.2, max_turns=5, parent=aggregate)
        with pytest.raises(BudgetExhausted) as exc:
            agent.reserve(0.1)
        assert exc.value.scope == "daily"
        small = AgentBudget(0.01, max_turns=5, parent=AggregateBudget(1.0))
        with pytest.raises(BudgetExhausted) as exc2:
            small.reserve(0.02)
        assert exc2.value.scope == "agent"
        tight = AggregateBudget(0.03)
        with pytest.raises(BudgetExhausted) as exc3:
            AgentBudget(1.0, max_turns=5, parent=tight).reserve(0.04)
        assert exc3.value.scope == "aggregate"

    def test_failed_reservation_changes_nothing(self) -> None:
        aggregate = AggregateBudget(0.03)
        agent = AgentBudget(1.0, max_turns=5, parent=aggregate)
        with pytest.raises(BudgetExhausted):
            agent.reserve(0.05)
        assert agent.reserved == aggregate.reserved == 0.0

    def test_release_returns_the_reservation(self) -> None:
        node = BudgetNode(0.1)
        reservation = node.reserve(0.1)
        node.release(reservation)
        assert node.available() == pytest.approx(0.1)
        node.reserve(0.1)  # volta a caber

    def test_parallel_reservations_cannot_overshoot(self) -> None:
        """TOCTOU: 20 threads tentam reservar 0.01 contra um teto de 0.05 — cabem exatamente 5."""
        node = BudgetNode(0.05)
        granted: list[int] = []
        barrier = threading.Barrier(20)

        def worker(i: int) -> None:
            barrier.wait()
            try:
                node.reserve(0.01)
                granted.append(i)
            except BudgetExhausted:
                pass

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(granted) == 5

    def test_unbounded_node_defers_to_parents(self) -> None:
        agent = AgentBudget(None, max_turns=3, parent=AggregateBudget(0.01))
        with pytest.raises(BudgetExhausted):
            agent.reserve(0.02)
        assert BudgetNode(None).available() is None


class TestAgentBudget:
    def test_turn_limit_is_hard(self) -> None:
        budget = AgentBudget(1.0, max_turns=2)
        budget.settle(budget.reserve_call(0.0), 0.0)
        budget.settle(budget.reserve_call(0.0), 0.0)
        with pytest.raises(BudgetExhausted) as exc:
            budget.reserve_call(0.0)
        assert exc.value.scope == "turns"

    def test_time_limit_uses_the_clock(self) -> None:
        now = [100.0]
        budget = AgentBudget(1.0, max_turns=9, timeout_s=30, clock=lambda: now[0])
        budget.start_clock()
        budget.reserve_call(0.0)
        now[0] = 131.0
        with pytest.raises(BudgetExhausted) as exc:
            budget.reserve_call(0.0)
        assert exc.value.scope == "time"


def test_estimate_call_usd() -> None:
    model = ResolvedModel(model_id="m", tier="fast", cost_input_m=2.0, cost_output_m=10.0)
    assert estimate_call_usd(model, 1_000_000, 100_000) == pytest.approx(2.0 + 1.0)
    local = model.model_copy(update={"is_local": True})
    assert estimate_call_usd(local, 1_000_000, 100_000) == 0.0


# ── Runner ──────────────────────────────────────────────────────────────────


def _loop(n: int) -> list:  # n voltas com tool_use
    return [use("glob", {"pattern": "*"}) for _ in range(n)]


async def test_agent_budget_overflow_returns_resumable_partial(tmp_path: Path) -> None:
    # explore: orçamento 0.10; cada chamada reserva ~0.04 (8192 tok * $5/M) e gasta 0.03
    gateway = FakeGateway(scripts=[ScriptedLLM(*_loop(10), repeat=True)], cost_per_call=0.03)
    rig = make_rig(tmp_path, gateway=gateway)
    result = (await rig.runner.spawn_many([TaskRequest("explore", "varra tudo")], rig.parent))[0]
    assert result.status == "partial_budget" and result.resumable
    assert result.usage.cost_usd <= 0.10 + 1e-9
    assert "partial_budget" in (rig.home / "agents" / result.agent_id / "result.md").read_text()
    assert (rig.home / "agents" / result.agent_id / "transcript.jsonl").exists()


async def test_resume_continues_with_the_same_model_and_history(tmp_path: Path) -> None:
    first = ScriptedLLM(*_loop(10), repeat=True)
    second = ScriptedLLM(say("terminei"))
    gateway = FakeGateway(scripts=[first, second], cost_per_call=0.03)
    rig = make_rig(tmp_path, gateway=gateway)
    partial = (await rig.runner.spawn_many([TaskRequest("explore", "varra")], rig.parent))[0]
    assert partial.resumable
    resumed = (
        await rig.runner.spawn_many(
            [TaskRequest("explore", "conclua", resume=partial.agent_id)], rig.parent
        )
    )[0]
    assert resumed.status == "ok" and resumed.agent_id == partial.agent_id
    assert gateway.resolved[-1]["reuse"] == partial.model_used  # mesmo modelo, sem re-roteamento
    assert len(second.requests[0]) > 2  # o histórico anterior voltou ao modelo


async def test_cannot_resume_a_finished_or_unknown_agent(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, [ScriptedLLM(say("pronto"))])
    done = (await rig.runner.spawn_many([TaskRequest("explore", "x")], rig.parent))[0]
    for target in (done.agent_id, "agent_000000"):
        res = (await rig.runner.spawn_many([TaskRequest("explore", "x", resume=target)], rig.parent))[0]
        assert res.status == "error" and "cannot resume" in res.summary


async def test_turn_limit_returns_partial_turns(tmp_path: Path) -> None:
    gateway = FakeGateway(scripts=[ScriptedLLM(*_loop(10), repeat=True)], cost_per_call=0.0001)
    rig = make_rig(tmp_path, gateway=gateway)
    result = (
        await rig.runner.spawn_many([TaskRequest("explore", "x", max_turns=3)], rig.parent)
    )[0]
    assert result.status == "partial_turns" and result.resumable


async def test_request_can_only_lower_the_budget(tmp_path: Path) -> None:
    gateway = FakeGateway(scripts=[ScriptedLLM(*_loop(20), repeat=True)], cost_per_call=0.03)
    rig = make_rig(tmp_path, gateway=gateway)
    res = (await rig.runner.spawn_many([TaskRequest("explore", "x", budget_usd=0.045)], rig.parent))[0]
    # a definição permite 0.10, mas o pedido baixou para 0.045: sobra 0.015 < reserva (~0.04)
    assert res.status == "partial_budget" and res.usage.cost_usd == pytest.approx(0.03)


async def test_aggregate_budget_caps_the_whole_delegation(tmp_path: Path) -> None:
    """Dois filhos, cada um com 0.10, dividem um agregado de 0.05: só cabe uma reserva."""
    gateway = FakeGateway(
        scripts=[ScriptedLLM(say("a")), ScriptedLLM(say("b"))],
        cost_per_call=0.001,
        on_call=lambda: asyncio.sleep(0.02),  # as duas chamadas ficam em voo ao mesmo tempo
    )
    rig = make_rig(tmp_path, gateway=gateway, limits=AgentsSettings(aggregate_budget_usd=0.05))
    results = await rig.runner.spawn_many(
        [TaskRequest("explore", "a"), TaskRequest("explore", "b")], rig.parent
    )
    assert sorted(r.status for r in results) == ["ok", "partial_budget"]


async def test_parallel_reservation_never_exceeds_the_cap(tmp_path: Path) -> None:
    """6 filhos paralelos, agregado 0.10, reserva ~0.04 por chamada: no máximo 2 chamadas em voo."""
    peak = {"now": 0, "max": 0}

    async def slow() -> None:
        peak["now"] += 1
        peak["max"] = max(peak["max"], peak["now"])
        await asyncio.sleep(0.02)
        peak["now"] -= 1

    gateway = FakeGateway(scripts=[ScriptedLLM(say(str(i))) for i in range(6)], on_call=slow)
    rig = make_rig(
        tmp_path, gateway=gateway,
        limits=AgentsSettings(aggregate_budget_usd=0.10, max_concurrent=6),
    )
    results = await rig.runner.spawn_many([TaskRequest("explore", str(i)) for i in range(6)], rig.parent)
    assert peak["max"] <= 2
    assert all(r.status in {"ok", "partial_budget"} for r in results)
    total = sum(r.usage.cost_usd for r in results)
    assert total <= 0.10 + 1e-9


async def test_daily_ceiling_stops_children(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, [ScriptedLLM(say("x"))], daily_headroom=lambda: 0.0)
    result = (await rig.runner.spawn_many([TaskRequest("explore", "x")], rig.parent))[0]
    assert result.status == "partial_budget" and "daily" in (result.error or "")


async def test_global_gateway_budget_error_becomes_partial(tmp_path: Path) -> None:
    from orion.gateway.budget import BudgetExceededError

    def boom() -> None:
        raise BudgetExceededError(1.0, 1.0, 100.0)

    gateway = FakeGateway(scripts=[ScriptedLLM(say("x"))], on_call=boom)
    rig = make_rig(tmp_path, gateway=gateway)
    result = (await rig.runner.spawn_many([TaskRequest("explore", "x")], rig.parent))[0]
    assert result.status == "partial_budget" and result.resumable


async def test_concurrency_gate_queues_extra_children(tmp_path: Path) -> None:
    active = {"now": 0, "max": 0}

    async def slow() -> None:
        active["now"] += 1
        active["max"] = max(active["max"], active["now"])
        await asyncio.sleep(0.03)
        active["now"] -= 1

    gateway = FakeGateway(scripts=[ScriptedLLM(say(str(i))) for i in range(5)], on_call=slow)
    rig = make_rig(tmp_path, gateway=gateway, limits=AgentsSettings(max_concurrent=2, aggregate_budget_usd=5))
    results = await rig.runner.spawn_many([TaskRequest("explore", str(i)) for i in range(5)], rig.parent)
    assert all(r.status == "ok" for r in results)
    assert active["max"] == 2  # o teto vale no código, não no prompt
