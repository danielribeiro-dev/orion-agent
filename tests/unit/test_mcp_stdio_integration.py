"""Real stdio handshake against a tiny FastMCP server (no mocks)."""

from __future__ import annotations

import time
from pathlib import Path

from orion.governance.permissions import _DYNAMIC_LEVELS, ActionLevel, tool_action_level
from orion.mcp.adapter import build_adapters
from orion.mcp.client import MCPClient
from orion.mcp.models import MCPServerConfig

SERVER = str(Path(__file__).parents[1] / "fixtures" / "echo_mcp_server.py")


async def test_real_stdio_roundtrip():
    _DYNAMIC_LEVELS.clear()
    cfg = MCPServerConfig(name="echo", command="python", args=[SERVER], read_only_tools=["echo"])
    c = MCPClient({"echo": cfg}, connect_timeout=30)
    t0 = time.perf_counter()
    await c.start()
    try:
        assert c.servers["echo"].status == "connected", c.servers["echo"].error
        print(f"handshake+list_tools: {(time.perf_counter() - t0) * 1000:.0f} ms")
        adapters = build_adapters(c)
        assert tool_action_level("mcp__echo__echo") == ActionLevel.LEVEL_1
        assert tool_action_level("mcp__echo__delete_record") == ActionLevel.LEVEL_2
        res = await adapters["mcp__echo__echo"].run(text="hi")
        assert res.success and "echo:hi" in res.output
        assert await c.ping("echo") is not None
    finally:
        await c.close()
    assert c.servers["echo"].status == "disabled"
    _DYNAMIC_LEVELS.clear()


async def test_real_stdio_denied_launcher_reports_error():
    cfg = MCPServerConfig(name="evil", command="bash", args=["-c", "id"])
    c = MCPClient({"evil": cfg})
    await c.start()
    assert c.servers["evil"].status == "error" and "allowlist" in c.servers["evil"].error


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def test_real_sse_roundtrip():
    import asyncio
    import subprocess
    import sys

    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, SERVER, "sse", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        for _ in range(100):  # wait for the listener (<= 10 s)
            try:
                _, w = await asyncio.open_connection("127.0.0.1", port)
                w.close()
                break
            except OSError:
                await asyncio.sleep(0.1)
        cfg = MCPServerConfig(
            name="remote", transport="sse", url=f"http://127.0.0.1:{port}/sse", read_only_tools=["echo"]
        )
        c = MCPClient({"remote": cfg}, connect_timeout=20)
        await c.start()
        try:
            assert c.servers["remote"].status == "connected", c.servers["remote"].error
            res = await build_adapters(c)["mcp__remote__echo"].run(text="sse")
            assert res.success and "echo:sse" in res.output
        finally:
            await c.close()
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        _DYNAMIC_LEVELS.clear()


async def test_sse_unreachable_is_isolated():
    cfg = MCPServerConfig(name="down", transport="sse", url=f"http://127.0.0.1:{_free_port()}/sse")
    c = MCPClient({"down": cfg}, connect_timeout=5)
    await c.start()
    assert c.servers["down"].status == "error"


async def test_sse_without_url():
    c = MCPClient({"x": MCPServerConfig(name="x", transport="sse")})
    await c.start()
    assert c.servers["x"].status == "error" and "url" in c.servers["x"].error
