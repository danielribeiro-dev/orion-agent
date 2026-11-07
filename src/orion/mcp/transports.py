"""
O.R.I.O.N — MCP transports
Opens a ClientSession over stdio (subprocess) or SSE (HTTP), via the MCP SDK.
"""

from __future__ import annotations

import os
import re
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from orion.mcp.models import MCPServerConfig
from orion.mcp.spawn_policy import check_spawn


def server_log_path(name: str, home: Path | None = None) -> Path:
    """Arquivo onde o stderr de um servidor MCP é gravado (nunca o terminal)."""
    base = (home or Path.home() / ".orion") / "logs"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"mcp-{re.sub(r'[^A-Za-z0-9_.-]', '_', name)}.log"


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
        # O SDK escreve o stderr do subprocesso em sys.stderr por padrão, o que
        # afoga a TUI durante o boot (uvx/npx/serena): desvia para arquivo.
        errlog = open(server_log_path(cfg.name), "a", encoding="utf-8")  # noqa: SIM115
        stack.callback(errlog.close)
        read, write = await stack.enter_async_context(stdio_client(params, errlog=errlog))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session
