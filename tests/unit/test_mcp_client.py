"""MCPClient / adapter / spawn policy tests with a fake session (no subprocess)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from orion.governance.permissions import _DYNAMIC_LEVELS, ActionLevel, tool_action_level
from orion.mcp.adapter import build_adapters, catalog_lines
from orion.mcp.client import MCPClient, load_server_configs
from orion.mcp.models import MCPServerConfig
from orion.mcp.spawn_policy import SpawnDenied, check_spawn


def _tool(name, desc="d", ro=None):
    ann = SimpleNamespace(read_only_hint=ro) if ro is not None else None
    return SimpleNamespace(name=name, description=desc, input_schema={"type": "object"}, annotations=ann)


class FakeSession:
    def __init__(self, tools, hang=False):
        self._tools, self._hang, self.calls = tools, hang, []

    async def list_tools(self):
        return SimpleNamespace(tools=self._tools)

    async def send_ping(self):
        return None

    async def call_tool(self, name, arguments):
        if self._hang:
            await asyncio.sleep(10)
        self.calls.append((name, arguments))
        return SimpleNamespace(content=[SimpleNamespace(text=f"ok:{name}")], is_error=False)


def opener_for(sessions):
    async def _open(cfg, stack):
        s = sessions[cfg.name]
        if isinstance(s, Exception):
            raise s
        if s == "hang":
            await asyncio.sleep(10)
        return s

    return _open


@pytest.fixture(autouse=True)
def _clean():
    _DYNAMIC_LEVELS.clear()
    yield
    _DYNAMIC_LEVELS.clear()


def cfgs(**kw):
    return {
        n: MCPServerConfig(name=n, command="uvx", read_only_tools=ro, enabled=en)
        for n, (ro, en) in kw.items()
    }


async def test_connect_list_and_levels():
    sess = FakeSession([_tool("find_symbol"), _tool("delete_record")])
    c = MCPClient(cfgs(db=(["find_symbol"], True)), opener=opener_for({"db": sess}))
    await c.start()
    try:
        assert c.servers["db"].status == "connected"
        adapters = build_adapters(c)
        assert tool_action_level("mcp__db__find_symbol") == ActionLevel.LEVEL_1
        assert tool_action_level("mcp__db__delete_record") == ActionLevel.LEVEL_2
        res = await adapters["mcp__db__find_symbol"].run(q="x")
        assert res.success and res.output == "ok:find_symbol"
        assert all(":" in line and "{" not in line for line in catalog_lines(adapters))
    finally:
        await c.close()


async def test_hidden_tools_are_not_exposed():
    sess = FakeSession([_tool("find_symbol"), _tool("rename_symbol")])
    cfg = {"s": MCPServerConfig(name="s", command="uvx", hidden_tools=["rename_symbol"])}
    c = MCPClient(cfg, opener=opener_for({"s": sess}))
    await c.start()
    assert list(build_adapters(c)) == ["mcp__s__find_symbol"]
    await c.close()


async def test_read_only_hint_promotes_to_level1():
    sess = FakeSession([_tool("peek", ro=True)])
    c = MCPClient(cfgs(s=([], True)), opener=opener_for({"s": sess}))
    await c.start()
    build_adapters(c)
    assert tool_action_level("mcp__s__peek") == ActionLevel.LEVEL_1
    await c.close()


async def test_disabled_server_is_never_opened():
    opened = []

    async def _open(cfg, stack):
        opened.append(cfg.name)

    c = MCPClient(cfgs(off=([], False)), opener=_open)
    await c.start()
    assert opened == [] and c.servers["off"].status == "disabled"


async def test_crash_and_hang_are_isolated():
    good = FakeSession([_tool("t")])
    c = MCPClient(
        cfgs(good=([], True), bad=([], True), slow=([], True)),
        connect_timeout=0.3,
        opener=opener_for({"good": good, "bad": RuntimeError("boom"), "slow": "hang"}),
    )
    await asyncio.wait_for(c.start(), 3)
    assert c.servers["good"].status == "connected"
    assert c.servers["bad"].status == "error" and "boom" in c.servers["bad"].error
    assert c.servers["slow"].status == "error"
    await c.close()


async def test_call_timeout_does_not_raise():
    c = MCPClient(cfgs(s=([], True)), call_timeout=0.1, opener=opener_for({"s": FakeSession([_tool("t")], hang=True)}))
    await c.start()
    ok, msg = await c.call_tool("s", "t", {})
    assert not ok and "timed out" in msg
    await c.close()


async def test_enable_disable_and_ping():
    c = MCPClient(cfgs(s=([], False)), opener=opener_for({"s": FakeSession([_tool("t")])}))
    await c.start()
    await c.set_enabled("s", True)
    assert c.servers["s"].status == "connected" and await c.ping("s") is not None
    await c.set_enabled("s", False)
    assert c.servers["s"].status == "disabled" and await c.ping("s") is None


async def test_call_unconnected_server():
    c = MCPClient({})
    ok, msg = await c.call_tool("nope", "t", {})
    assert not ok and "not connected" in msg


def test_config_merge_and_bundled_not_spoofable(tmp_path):
    home, ws = tmp_path / "h", tmp_path / "w"
    (ws / ".orion").mkdir(parents=True)
    home.mkdir()
    (home / "mcp_servers.json").write_text(json.dumps({"servers": {"serena": {"enabled": False},
        "mine": {"command": "npx", "bundled": True}}}))
    (ws / ".orion" / "mcp_servers.json").write_text(json.dumps({"mcpServers": {"context7": {"est_tokens": 1}}}))
    out = load_server_configs(home, ws)
    assert out["serena"].enabled is False and out["serena"].bundled is True and out["serena"].command == "uvx"
    assert out["context7"].est_tokens == 1 and out["context7"].enabled is True
    assert out["mine"].bundled is False  # user file cannot claim bundled


def test_invalid_config_file_is_ignored(tmp_path):
    (tmp_path / "mcp_servers.json").write_text("{not json")
    assert "serena" in load_server_configs(tmp_path, None)


@pytest.mark.parametrize("cmd,args,ok", [
    ("uvx", [], True), ("npx", ["-y", "x"], True), ("bash", ["-c", "rm -rf /"], False),
    ("/usr/bin/python", [], False), ("python", ["-c", "import os"], False), ("python", ["-m", "srv"], True),
    (None, [], False),
])
def test_spawn_policy(cmd, args, ok):
    cfg = MCPServerConfig(name="x", command=cmd, args=args)
    if ok:
        check_spawn(cfg)
    else:
        with pytest.raises(SpawnDenied):
            check_spawn(cfg)


def test_sse_skips_spawn_check():
    check_spawn(MCPServerConfig(name="r", transport="sse", url="http://x"))
