"""v0.5.0 Sprint 2 — schemas de tools, validação e fonte única de risco (ADR-021)."""

from __future__ import annotations

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from orion.core.events import RiskLevel
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import (
    TOOL_LEVELS,
    ActionLevel,
    WorkspaceScope,
    is_read_only_tool,
    register_tool_level,
    risk_to_action_level,
    tool_action_level,
    tool_risk_level,
    unregister_tool_levels,
)
from orion.memory.facts_store import FactsStore
from orion.runtime.environment import EnvironmentMonitor
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.runtime.provider import RuntimeResult
from orion.skills.engine import SkillsEngine


@pytest.fixture()
def runtime(tmp_path: Path) -> LocalRuntimeProvider:
    scope = WorkspaceScope([tmp_path])
    store = FactsStore(tmp_path / "facts.db")
    store.initialize()
    return LocalRuntimeProvider(
        pep=PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO),
        scope=scope,
        facts_store=store,
        environment_monitor=EnvironmentMonitor(),
        skills_engine=SkillsEngine(),
    )


class TestSchemas:
    def test_every_exposed_tool_has_a_valid_schema_and_description(self, runtime: LocalRuntimeProvider) -> None:
        specs = runtime.tool_specs()
        assert {s.name for s in specs} >= {
            "read_file", "write_file", "edit_file", "run_command", "search_files",
            "memorize", "recall", "deprecate_fact", "inspect_environment", "use_skill",
        }
        for spec in specs:
            Draft202012Validator.check_schema(spec.input_schema)
            assert spec.input_schema["type"] == "object"
            assert spec.description.strip()

    def test_every_registered_tool_is_exposed(self, runtime: LocalRuntimeProvider) -> None:
        assert {s.name for s in runtime.tool_specs()} == set(runtime.available_tools)

    def test_every_tool_has_an_explicit_pep_level(self, runtime: LocalRuntimeProvider) -> None:
        # Nenhuma tool nativa pode cair no default LEVEL_3 por esquecimento.
        for name in runtime.available_tools:
            assert name in TOOL_LEVELS, f"{name} sem nível PEP explícito"

    def test_specs_are_sorted_for_cache_stability(self, runtime: LocalRuntimeProvider) -> None:
        names = [s.name for s in runtime.tool_specs()]
        assert names == sorted(names)

    def test_tool_without_contract_is_not_exposed(self, runtime: LocalRuntimeProvider) -> None:
        runtime.register_tool(lambda **_: RuntimeResult.ok("x"), name="legacy_tool")
        assert "legacy_tool" in runtime.available_tools
        assert "legacy_tool" not in {s.name for s in runtime.tool_specs()}
        unregister_tool_levels("legacy_tool")


class TestValidation:
    @pytest.mark.parametrize(
        ("tool", "params", "fragment"),
        [
            ("read_file", {}, "path"),
            ("read_file", {"path": 1}, "path"),
            ("read_file", {"path": "x", "start_line": 0}, "start_line"),
            ("write_file", {"path": "x"}, "content"),
            ("edit_file", {"path": "x"}, "target"),
            ("run_command", {"command": ["ls"]}, "command"),
            ("search_files", {"mode": "fuzzy"}, "mode"),
            ("memorize", {"key": "k", "value": "v", "category": "NOPE"}, "category"),
            ("recall", {}, "query"),
        ],
    )
    def test_invalid_params_are_rejected(
        self, runtime: LocalRuntimeProvider, tool: str, params: dict[str, object], fragment: str
    ) -> None:
        message = runtime.validate_params(tool, params)
        assert message is not None
        assert tool in message
        assert fragment in message

    def test_valid_params_pass(self, runtime: LocalRuntimeProvider) -> None:
        assert runtime.validate_params("read_file", {"path": "a", "start_line": 3}) is None
        assert runtime.validate_params("search_files", {}) is None
        assert runtime.validate_params("inexistente", {"qualquer": 1}) is None

    async def test_execute_rejects_before_running(self, runtime: LocalRuntimeProvider, tmp_path: Path) -> None:
        result = await runtime.execute("write_file", {"path": str(tmp_path / "x.txt")})
        assert not result.success
        assert result.metadata["invalid_params"] is True
        assert not (tmp_path / "x.txt").exists()

    async def test_extra_params_are_tolerated(self, runtime: LocalRuntimeProvider, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("ok")
        result = await runtime.execute("read_file", {"path": str(tmp_path / "a.txt"), "extra": True})
        assert result.success


class TestSingleSourceOfRisk:
    def test_risk_derives_from_action_level(self) -> None:
        assert tool_risk_level("read_file") == RiskLevel.SAFE
        assert tool_risk_level("edit_file") == RiskLevel.CONTROLLED
        assert tool_risk_level("run_command") == RiskLevel.CRITICAL
        assert tool_risk_level("memorize") == RiskLevel.CONTROLLED
        assert tool_risk_level("desconhecida") == RiskLevel.CRITICAL  # deny by default

    def test_read_only_classification(self) -> None:
        assert is_read_only_tool("recall")
        assert is_read_only_tool("search_files")
        assert not is_read_only_tool("memorize")
        assert not is_read_only_tool("run_command")
        assert not is_read_only_tool("desconhecida")

    def test_register_tool_with_risk_hint_updates_the_pep_level(self, runtime: LocalRuntimeProvider) -> None:
        runtime.register_tool(lambda **_: RuntimeResult.ok("x"), name="dyn_tool", risk=RiskLevel.CONTROLLED)
        assert tool_action_level("dyn_tool") == ActionLevel.LEVEL_2
        assert tool_risk_level("dyn_tool") == RiskLevel.CONTROLLED
        assert not is_read_only_tool("dyn_tool")
        unregister_tool_levels("dyn_tool")

    def test_dynamic_read_only_tool_is_parallel_safe(self) -> None:
        register_tool_level("mcp__x__peek", ActionLevel.LEVEL_1)
        assert is_read_only_tool("mcp__x__peek")
        unregister_tool_levels("mcp__x__")

    @pytest.mark.parametrize(
        ("risk", "level"),
        [
            (RiskLevel.SAFE, ActionLevel.LEVEL_1),
            (RiskLevel.CONTROLLED, ActionLevel.LEVEL_2),
            (RiskLevel.ELEVATED, ActionLevel.LEVEL_3),
            (RiskLevel.CRITICAL, ActionLevel.LEVEL_3),
        ],
    )
    def test_risk_hint_mapping_never_lowers_privilege(self, risk: RiskLevel, level: ActionLevel) -> None:
        assert risk_to_action_level(risk) == level
