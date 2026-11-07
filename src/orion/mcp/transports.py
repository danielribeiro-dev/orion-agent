"""
O.R.I.O.N — MCP transports
Opens a ClientSession over stdio (subprocess) or SSE (HTTP), via the MCP SDK.
"""

from __future__ import annotations

import os
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from orion.mcp.models import MCPServerConfig
from orion.mcp.spawn_policy import check_spawn


async def open_session(cfg: MCPServerConfig, stack: AsyncExitStack) -> ClientSession:
    """Open and initialize a session; resources are registered on *stack*."""
    check_spawn(cfg)
    if cfg.transport == "sse":
        if not cfg.url:
            raise ValueError(f"{cfg.name}: sse server without 'url'")
        read, write = await stack.enter_async_context(sse_client(cfg.url))
    else:
        params = StdioServerParameters(
            command=cfg.command or "",
            args=cfg.args,
            env={**os.environ, **cfg.env} if cfg.env else None,
        )
        read, write = await stack.enter_async_context(stdio_client(params))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session
