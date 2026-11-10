"""Modelos ``:free`` do OpenRouter: catálogo, preferência por tier e regra de mutação."""

from __future__ import annotations

import pytest

from orion.gateway.models import ComplexityTier
from orion.gateway.registry import ModelRegistry
from orion.gateway.router import ANTHROPIC_TIER_MODELS, ModelRouter, NoModelForTier
from orion.settings.loader import merge
from orion.settings.models import ModelsSettings, Settings

REGISTRY = ModelRegistry()
FREE = {m.id for m in REGISTRY.all_models() if m.is_free}


def _router(native: bool = False) -> ModelRouter:
    return ModelRouter(registry=REGISTRY, tier_models=ANTHROPIC_TIER_MODELS if native else None)


def _any(_spec: object) -> bool:
    return True


def test_catalog_has_free_models_with_tools_and_zero_cost() -> None:
    assert "google/gemma-4-31b-it:free" in FREE and len(FREE) == 4
    for model_id in FREE:
        spec = REGISTRY.require(model_id)
        assert model_id.endswith(":free") and spec.supports_tool_use and not spec.is_local
    assert not REGISTRY.require("qwen2.5-coder:1.5b").is_free  # local não conta como free de nuvem
    assert not REGISTRY.require("google/gemini-2.0-flash").is_free


def test_default_routing_never_picks_free() -> None:
    router = _router()
    for tier in ComplexityTier:
        assert router.tier_model(tier) not in FREE
        assert not set(router.tier_candidates(tier)) & FREE


def test_prefer_free_puts_free_first_and_keeps_paid_as_fallback() -> None:
    router = _router(native=True)
    router.set_prefer_free(True)
    cands = router.tier_candidates(ComplexityTier.BALANCED)
    assert cands[0] in FREE and "claude-sonnet-5-5" in cands
    assert router.tier_candidates(ComplexityTier.FAST)[0] == "google/gemma-4-26b-a4b-it:free"
    router.set_prefer_free(False)
    assert router.tier_candidates(ComplexityTier.BALANCED)[0] == "claude-sonnet-5-5"


def test_prefer_free_applies_to_auto_routing() -> None:
    router = _router()
    router.set_prefer_free(True)
    decision = router.route("oi")
    assert decision.selected_model in FREE


def test_explicit_tier_list_wins_over_prefer_free() -> None:
    router = _router()
    router.set_prefer_free(True)
    router.set_tier_candidates({"fast": ["qwen/qwen-2.5-72b-instruct"]})
    assert router.tier_candidates(ComplexityTier.FAST) == ["qwen/qwen-2.5-72b-instruct"]


def test_mutating_agent_skips_fast_free_model_but_readonly_uses_it() -> None:
    router = _router()
    router.set_prefer_free(True)
    ro = router.resolve_for_agent(ComplexityTier.FAST, mutating=False, available=_any)
    assert ro.id == "google/gemma-4-26b-a4b-it:free"
    mut = router.resolve_for_agent(ComplexityTier.BALANCED, mutating=True, available=_any)
    assert mut.id in FREE and mut.default_tier != ComplexityTier.FAST
    with pytest.raises(NoModelForTier):
        router.resolve_for_agent(ComplexityTier.FAST, mutating=True, available=_any)


def test_settings_prefer_free_merges_by_layer() -> None:
    user = Settings(models=ModelsSettings(prefer_free=True))
    top = Settings(models=ModelsSettings(tiers={"fast": ["qwen/qwen-2.5-72b-instruct"]}))
    eff = merge([user, top])
    assert eff.models.prefer_free is True
    assert eff.models.tiers["fast"] == ["qwen/qwen-2.5-72b-instruct"]
    off = merge([user, Settings(models=ModelsSettings(prefer_free=False))])
    assert off.models.prefer_free is False
