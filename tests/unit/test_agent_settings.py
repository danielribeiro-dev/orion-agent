"""Chaves ``agents.*`` e ``models.*`` dos settings: camadas, confiança e padrões seguros."""

from __future__ import annotations

import json
from pathlib import Path

from orion.settings import ProjectTrust, load_settings
from orion.settings.models import HOOK_EVENTS, AgentsSettings, ModelsSettings, Settings


def test_defaults_are_safe_and_never_unlimited() -> None:
    limits = AgentsSettings().resolved()
    assert (limits.max_concurrent, limits.max_depth, limits.default_max_turns) == (4, 1, 20)
    assert limits.result_max_tokens == 1500 and not limits.allow_pinned_model
    assert limits.default_budget_usd > 0 and limits.aggregate_budget_usd > 0 and limits.default_timeout_s > 0


def test_invalid_values_invalidate_the_layer_instead_of_unlimiting() -> None:
    notices: list[str] = []
    from orion.settings.loader import _parse

    parsed = _parse({"agents": {"max_concurrent": 0}}, "user", notices)
    assert parsed.agents.max_concurrent is None and notices  # camada inválida é ignorada
    assert _parse({"agents": {"max_depth": 99}}, "user", []).agents.max_depth is None


def test_hook_events_include_subagent_start_and_stop() -> None:
    assert {"SubagentStart", "SubagentStop"} <= set(HOOK_EVENTS)


def test_layers_merge_scalars_and_replace_tier_lists(tmp_path: Path) -> None:
    home, ws = tmp_path / "home", tmp_path / "ws"
    (home).mkdir()
    (ws / ".orion").mkdir(parents=True)
    (home / "settings.json").write_text(
        json.dumps(
            {
                "agents": {"max_concurrent": 2, "default_budget_usd": 0.2},
                "models": {"tiers": {"fast": ["a", "b"]}, "profiles": {"barato": {"tier": "fast"}}},
            }
        )
    )
    (ws / ".orion" / "settings.local.json").write_text(
        json.dumps({"agents": {"max_concurrent": 3}, "models": {"tiers": {"fast": ["c"]}}})
    )
    loaded = load_settings(home, ws, trust=ProjectTrust(home))
    eff = loaded.effective
    assert eff.agents.max_concurrent == 3 and eff.agents.default_budget_usd == 0.2
    assert eff.models.tiers == {"fast": ["c"]} and eff.models.profiles["barato"].tier == "fast"


def test_project_layer_with_agents_or_models_needs_trust(tmp_path: Path) -> None:
    home, ws = tmp_path / "home", tmp_path / "ws"
    home.mkdir()
    (ws / ".orion").mkdir(parents=True)
    path = ws / ".orion" / "settings.json"
    path.write_text(json.dumps({"agents": {"max_concurrent": 16}, "models": {"tiers": {"heavy": ["x"]}}}))
    trust = ProjectTrust(home)
    loaded = load_settings(home, ws, trust=trust)
    assert loaded.project_needs_trust
    assert loaded.effective.agents.max_concurrent is None and not loaded.effective.models.tiers

    assert loaded.project_digest is not None
    trust.trust(ws, loaded.project_digest)
    trusted = load_settings(home, ws, trust=trust)
    assert trusted.effective.agents.max_concurrent == 16 and trusted.effective.models.tiers == {"heavy": ["x"]}


def test_restricted_drops_agents_and_models() -> None:
    risky = Settings(agents=AgentsSettings(max_concurrent=9), models=ModelsSettings(tiers={"fast": ["x"]}))
    assert risky.has_risky_content()
    safe = risky.restricted()
    assert not safe.agents.is_set() and not safe.models.is_set() and not safe.has_risky_content()
