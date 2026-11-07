"""Governance wiring for dynamically registered (MCP) tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.governance.permissions import (
    _DYNAMIC_LEVELS,
    ActionLevel,
    is_dynamic_mutating,
    register_tool_level,
    tool_action_level,
    unregister_tool_levels,
)
from orion.mcp.models import MCPServerConfig, MCPToolDefinition


@pytest.fixture(autouse=True)
def _clean():
    _DYNAMIC_LEVELS.clear()
    yield
    _DYNAMIC_LEVELS.clear()


def test_unknown_tool_defaults_to_level3():
    assert tool_action_level("mcp__x__delete_record") == ActionLevel.LEVEL_3


def test_registered_read_tool_is_level1_and_not_mutating():
    register_tool_level("mcp__serena__find_symbol", ActionLevel.LEVEL_1)
    assert tool_action_level("mcp__serena__find_symbol") == ActionLevel.LEVEL_1
    assert not is_dynamic_mutating("mcp__serena__find_symbol")


def test_registered_mutating_tool_is_flagged():
    register_tool_level("mcp__db__delete_record", ActionLevel.LEVEL_2)
    assert is_dynamic_mutating("mcp__db__delete_record")


def test_static_levels_win_over_dynamic():
    register_tool_level("run_command", ActionLevel.LEVEL_0)
    assert tool_action_level("run_command") == ActionLevel.LEVEL_3


def test_unregister_by_prefix():
    register_tool_level("mcp__a__t1", ActionLevel.LEVEL_1)
    register_tool_level("mcp__b__t1", ActionLevel.LEVEL_1)
    unregister_tool_levels("mcp__a__")
    assert tool_action_level("mcp__a__t1") == ActionLevel.LEVEL_3
    assert tool_action_level("mcp__b__t1") == ActionLevel.LEVEL_1


def test_qualified_name():
    t = MCPToolDefinition(server_name="serena", name="find_symbol")
    assert t.qualified_name == "mcp__serena__find_symbol"


def test_default_catalog_is_valid_and_ships_only_readonly_enabled():
    path = Path(__file__).parents[2] / "src/orion/mcp/mcp_servers.default.json"
    data = json.loads(path.read_text())
    servers = [MCPServerConfig(name=n, **cfg) for n, cfg in data["servers"].items()]
    assert servers and all(s.bundled for s in servers)
    for s in servers:
        if s.enabled:
            assert s.read_only_tools, f"{s.name} enabled without read-only allowlist"


def test_default_catalog_versions_are_pinned():
    import re

    path = Path(__file__).parents[2] / "src/orion/mcp/mcp_servers.default.json"
    for name, cfg in json.loads(path.read_text())["servers"].items():
        pkg = next(a for a in cfg["args"] if re.search(r"==|@\d", a))
        assert "latest" not in pkg and "git+" not in pkg, f"{name} not pinned: {pkg}"
        # hidden tools must never be read-only allowlisted
        assert not set(cfg.get("hidden_tools", [])) & set(cfg["read_only_tools"])
