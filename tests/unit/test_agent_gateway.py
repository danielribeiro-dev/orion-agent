"""Tiers por capacidade, sem downgrade silencioso (ADR-031) e o gateway dos subagents."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import pytest

from orion.agents.models import ResolvedModel
from orion.agents.ports import ModelGatewayPort, NoSuitableModel
from orion.gateway.agent_gateway import AgentGateway
from orion.gateway.budget import BudgetExceededError, BudgetGuard
from orion.gateway.ledger import CostLedger
from orion.gateway.models import ComplexityTier, ModelSpec, TokenUsage
from orion.gateway.registry import ModelRegistry
from orion.gateway.router import ANTHROPIC_TIER_MODELS, ModelRouter, NoModelForTier
from tests.llm_script import say, use
from tests.unit.test_agent_session import ScriptedProvider

REGISTRY = ModelRegistry()


def _everything(_spec: ModelSpec) -> bool:
    return True


def _only(*ids: str) -> Callable[[ModelSpec], bool]:
    return lambda spec: spec.id in ids


def _router(native: bool = False) -> ModelRouter:
    return ModelRouter(registry=REGISTRY, tier_models=ANTHROPIC_TIER_MODELS if native else None)


class TestCapabilityFlags:
    def test_anthropic_models_declare_prompt_cache_and_tool_use(self) -> None:
        for model_id in ANTHROPIC_TIER_MODELS.values():
            spec = REGISTRY.require(model_id)
            assert spec.supports_prompt_cache and spec.supports_tool_use
        assert not REGISTRY.require("google/gemini-2.0-flash").supports_prompt_cache


class TestTierCandidates:
    def test_defaults_put_the_active_family_first_then_the_other(self) -> None:
        assert _router(native=True).tier_candidates(ComplexityTier.BALANCED) == [
            "claude-sonnet-5-5",
            "google/gemini-2.0-flash",
        ]
        assert _router().tier_candidates(ComplexityTier.BALANCED)[0] == "google/gemini-2.0-flash"

    def test_settings_override_with_ordered_list_and_warnings(self) -> None:
        router = _router()
        notes = router.set_tier_candidates(
            {"fast": ["qwen/qwen-2.5-72b-instruct", "ghost/model"], "weird": ["x"]}
        )
        assert router.tier_candidates(ComplexityTier.FAST) == ["qwen/qwen-2.5-72b-instruct"]
        assert any("ghost/model" in n for n in notes) and any("weird" in n for n in notes)
        router.set_tier_candidates({})
        assert router.tier_candidates(ComplexityTier.FAST)[0] == "google/gemini-2.0-flash-lite"


class TestResolveForAgent:
    def test_picks_first_available_candidate_in_order(self) -> None:
        spec = _router(native=True).resolve_for_agent(
            ComplexityTier.BALANCED, mutating=False, available=_everything
        )
        assert spec.id == "claude-sonnet-5-5"
        fallback = _router(native=True).resolve_for_agent(
            ComplexityTier.BALANCED, mutating=False, available=_only("google/gemini-2.0-flash")
        )
        assert fallback.id == "google/gemini-2.0-flash"

    def test_mutating_agents_refuse_the_fast_tier(self) -> None:
        with pytest.raises(NoModelForTier, match="mutating"):
            _router().resolve_for_agent(ComplexityTier.FAST, mutating=True, available=_everything)

    def test_mutating_agents_never_fall_back_to_a_local_or_fast_model(self) -> None:
        local_only = _only("qwen2.5-coder:1.5b", "qwen2.5-coder:3b", "qwen2.5-coder:7b")
        with pytest.raises(NoModelForTier) as exc:
            _router(native=True).resolve_for_agent(
                ComplexityTier.BALANCED, mutating=True, available=local_only
            )
        assert "unavailable" in str(exc.value)
        router = _router()
        router.set_tier_candidates({"balanced": ["google/gemini-2.0-flash-lite"]})  # candidato de tier FAST
        with pytest.raises(NoModelForTier, match="tier too low"):
            router.resolve_for_agent(
                ComplexityTier.BALANCED, mutating=True, available=_only("google/gemini-2.0-flash-lite")
            )

    def test_read_only_agents_may_fall_back_to_the_local_model(self) -> None:
        local = REGISTRY.local_models()[0]
        spec = _router(native=True).resolve_for_agent(
            ComplexityTier.HEAVY, mutating=False, available=_only(local.id)
        )
        assert spec.is_local and spec.id == local.id

    def test_nothing_available_explains_what_was_tried(self) -> None:
        with pytest.raises(NoModelForTier, match="claude-opus-5-5"):
            _router(native=True).resolve_for_agent(
                ComplexityTier.HEAVY, mutating=False, available=lambda s: False
            )


def _gateway(
    tmp_path: Path,
    provider: ScriptedProvider | None = None,
    *,
    available: Callable[[ModelSpec], bool] = _everything,
    profiles: dict[str, str] | None = None,
    budget: BudgetGuard | None = None,
    router: ModelRouter | None = None,
) -> tuple[AgentGateway, CostLedger]:
    ledger = CostLedger(db_path=tmp_path / "metrics.db", registry=REGISTRY)
    gateway = AgentGateway(
        registry=REGISTRY,
        router=router or _router(),
        provider_factory=lambda spec: provider or ScriptedProvider([say("ok")]),
        ledger=ledger,
        budget=budget,
        available=available,
        profiles=lambda: profiles or {},
        session_id=lambda: "sess-1",
    )
    return gateway, ledger


class TestAgentGatewayResolve:
    def test_implements_the_port(self, tmp_path: Path) -> None:
        gateway, _ = _gateway(tmp_path)
        assert isinstance(gateway, ModelGatewayPort)

    def test_tier_resolves_to_a_priced_model(self, tmp_path: Path) -> None:
        gateway, _ = _gateway(tmp_path)
        model = gateway.resolve(tier="fast", mutating=False)
        assert model.model_id == "google/gemini-2.0-flash-lite" and model.tier == "fast"
        assert model.cost_output_m > 0 and not model.is_local

    def test_profile_maps_to_a_tier_and_unknown_profile_fails(self, tmp_path: Path) -> None:
        gateway, _ = _gateway(tmp_path, profiles={"barato": "fast"})
        assert gateway.resolve(tier="heavy", mutating=False, profile="barato").tier == "fast"
        with pytest.raises(NoSuitableModel, match="unknown model profile"):
            gateway.resolve(tier="fast", mutating=False, profile="nope")

    def test_no_candidate_raises_the_port_error(self, tmp_path: Path) -> None:
        gateway, _ = _gateway(tmp_path, available=lambda s: False)
        with pytest.raises(NoSuitableModel):
            gateway.resolve(tier="balanced", mutating=True)

    def test_reuse_pins_the_recorded_model_but_still_checks_it(self, tmp_path: Path) -> None:
        gateway, _ = _gateway(tmp_path)
        assert gateway.resolve(tier="fast", mutating=False, reuse="claude-sonnet-5-5").model_id == "claude-sonnet-5-5"
        weak = REGISTRY.local_models()[0].id
        with pytest.raises(NoSuitableModel, match="too weak"):
            gateway.resolve(tier="balanced", mutating=True, reuse=weak)
        offline, _ = _gateway(tmp_path, available=lambda s: False)
        with pytest.raises(NoSuitableModel, match="not available"):
            offline.resolve(tier="fast", mutating=False, reuse="claude-sonnet-5-5")

    def test_pinned_model_goes_through_the_same_checks(self, tmp_path: Path) -> None:
        gateway, _ = _gateway(tmp_path)
        assert gateway.resolve(tier="fast", mutating=True, pinned="claude-sonnet-5-5").model_id == "claude-sonnet-5-5"
        with pytest.raises(NoSuitableModel):
            gateway.resolve(tier="fast", mutating=False, pinned="does/not-exist")

    def test_unknown_tier_is_rejected(self, tmp_path: Path) -> None:
        gateway, _ = _gateway(tmp_path)
        with pytest.raises(NoSuitableModel, match="unknown tier"):
            gateway.resolve(tier="ultra", mutating=False)


class TestAgentGatewayCalls:
    async def test_llm_records_cost_with_origin_agent_and_reports_usage(self, tmp_path: Path) -> None:
        provider = ScriptedProvider([use("glob", {"pattern": "*"})])
        gateway, ledger = _gateway(tmp_path, provider)
        model = gateway.resolve(tier="fast", mutating=False)
        seen: list[tuple[ResolvedModel, TokenUsage, float]] = []
        llm = gateway.make_llm(
            model, agent_id="agent_1", origin="loop", max_tokens=2048,
            on_usage=lambda m, u, c: seen.append((m, u, c)),
        )
        turn = await llm(system="sys", messages=[], tools=[])
        assert turn.tool_uses[0].name == "glob"
        [record] = ledger.list_records()
        assert (record.origin, record.agent_id, record.task_id) == ("loop", "agent_1", "sess-1")
        assert record.complexity_level == "fast" and record.routing_mode == "agent"
        assert seen and seen[0][2] == pytest.approx(record.cost_usd) and seen[0][1].prompt_tokens == 1000
        assert provider.requests[0].max_tokens == 2048

    async def test_daily_budget_guard_blocks_the_call(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "metrics.db"
        ledger = CostLedger(db_path=ledger_path, registry=REGISTRY)
        ledger.record_turn_cost("openrouter", "google/gemini-2.0-flash-lite", TokenUsage(prompt_tokens=10**7))
        guard = BudgetGuard(ledger=ledger, daily_budget_usd=0.01)
        gateway, _ = _gateway(tmp_path, ScriptedProvider([say("x")]), budget=guard)
        model = gateway.resolve(tier="fast", mutating=False)
        llm = gateway.make_llm(model, agent_id="a", origin="subagent", max_tokens=100, on_usage=lambda *a: None)
        with pytest.raises(BudgetExceededError):
            await llm(system="s", messages=[], tools=[])

    async def test_failover_cost_uses_the_serving_model_tariff(self, tmp_path: Path) -> None:
        class Failover(ScriptedProvider):
            served = SimpleNamespace(
                pricing_model="google/gemini-2.0-flash", provider=REGISTRY.require("google/gemini-2.0-flash").provider
            )

        gateway, ledger = _gateway(tmp_path, Failover([say("x")]))
        model = gateway.resolve(tier="fast", mutating=False)
        used: list[ResolvedModel] = []
        llm = gateway.make_llm(model, agent_id="a", origin="subagent", max_tokens=100,
                               on_usage=lambda m, u, c: used.append(m))
        await llm(system="s", messages=[], tools=[])
        assert used[0].model_id == "google/gemini-2.0-flash"
        assert ledger.list_records()[0].model == "google/gemini-2.0-flash"

    async def test_anthropic_calls_split_the_system_into_cacheable_layers(self, tmp_path: Path) -> None:
        provider = ScriptedProvider([say("x")])
        gateway, _ = _gateway(tmp_path, provider)
        model = gateway.resolve(tier="balanced", mutating=False, reuse="claude-sonnet-5-5")
        llm = gateway.make_llm(model, agent_id="a", origin="subagent", max_tokens=100, on_usage=lambda *a: None)
        from orion.core.engine import LAYER_BREAK

        await llm(system=f"estável{LAYER_BREAK}volátil", messages=[], tools=[])
        request = provider.requests[0]
        assert isinstance(request.system, list) and len(request.system) == 2
        assert request.system[1].cache_control is not None and request.system[0].cache_control is None
        assert request.thinking is not None and request.thinking.effort == "low"  # filhos pensam pouco
