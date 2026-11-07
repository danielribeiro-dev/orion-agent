"""/mcp slash command + session wiring (fake MCP client, no subprocess)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from rich.console import Console

from orion.governance.permissions import _DYNAMIC_LEVELS
from orion.mcp.models import MCPServerConfig, MCPToolDefinition
from orion.tui.commands.base import CommandContext
from orion.tui.commands.registry import CommandRegistry
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme


class FakeClient:
    def __init__(self):
        cfg = MCPServerConfig(name="srv", command="uvx", read_only_tools=["look"], est_tokens=500, bundled=True)
        tool = MCPToolDefinition(server_name="srv", name="look", description="Look around", input_schema={"type": "object"})
        self.servers = {"srv": SimpleNamespace(config=cfg, status="connected", error="", latency_ms=12.0, tools=[tool])}

    async def set_enabled(self, name, enabled):
        self.servers[name].status = "connected" if enabled else "disabled"

    async def ping(self, name):
        return 3.0

    async def call_tool(self, server, tool, args):
        return True, "seen"


@pytest.fixture
def ctx(tmp_path: Path, monkeypatch) -> CommandContext:
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    _DYNAMIC_LEVELS.clear()
    console = Console(file=io.StringIO(), width=110, theme=get_orion_theme())
    session = AgentSession(status_bar=SessionStatusBar(), console=console, workspace=tmp_path, home=tmp_path / "home")
    session.start_mcp(FakeClient())
    yield CommandContext(session=session, console=console, clear_screen=MagicMock())
    _DYNAMIC_LEVELS.clear()


@pytest.fixture
def registry():
    return CommandRegistry.discover()


async def test_list_shows_table_and_overhead(registry, ctx):
    r = await registry.dispatch("/mcp", ctx)
    out = ctx.console.file.getvalue()
    assert r.success and "srv" in out and "starter pack" in out and "~500" in out


async def test_disable_persists_and_applies(registry, ctx):
    r = await registry.dispatch("/mcp disable srv", ctx)
    assert r.success and "desativado" in r.output_message
    data = json.loads((ctx.session.home / "mcp_servers.json").read_text())
    assert data["servers"]["srv"]["enabled"] is False
    assert ctx.session.mcp.servers["srv"].status == "disabled"
    await registry.dispatch("/mcp enable srv", ctx)
    assert json.loads((ctx.session.home / "mcp_servers.json").read_text())["servers"]["srv"]["enabled"] is True


async def test_ping_tools_and_errors(registry, ctx):
    assert "3 ms" in (await registry.dispatch("/mcp ping srv", ctx)).output_message
    assert "mcp__srv__look" in (await registry.dispatch("/mcp tools srv", ctx)).output_message
    assert not (await registry.dispatch("/mcp ping nope", ctx)).success
    assert not (await registry.dispatch("/mcp enable", ctx)).success


async def test_inactive_client_message(registry, ctx):
    ctx.session.mcp = None
    r = await registry.dispatch("/mcp", ctx)
    assert not r.success and "inativo" in r.output_message


async def test_session_registers_lazy_tools_and_prompt(ctx):
    s = ctx.session
    s.refresh_mcp()
    assert "mcp__srv__look" in s.runtime.available_tools and "mcp_schema" in s.runtime.available_tools
    prompt = s.system_prompt()
    assert "mcp__srv__look: Look around" in prompt and '"type"' not in prompt.split("MCP tools")[1]
    res = await s.runtime.execute_direct("mcp_schema", {"tool": "mcp__srv__look"})
    assert res.success and "object" in res.output
    ok = await s.runtime.execute("mcp__srv__look", {})
    assert ok.success and ok.output == "seen"
