"""
O.R.I.O.N — BackgroundMCPClient
The CLI runs each turn in a fresh ``asyncio.run`` loop, but MCP sessions need a
loop that lives as long as the process. This facade owns a daemon thread with a
persistent loop and exposes the same async API as :class:`MCPClient`.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any

from orion.mcp.client import MCPClient
from orion.mcp.models import MCPServerConfig, MCPToolDefinition


class BackgroundMCPClient:
    def __init__(self, configs: dict[str, MCPServerConfig], **kwargs: Any) -> None:
        self._inner = MCPClient(configs, **kwargs)
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._serve, name="orion-mcp", daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    # ── submission helpers ───────────────────────────────────────────────
    def submit(self, coro: Coroutine[Any, Any, Any]) -> asyncio.futures.Future[Any]:
        """Fire-and-forget (non-blocking) scheduling on the MCP loop."""
        return asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[return-value]

    async def _call(self, coro: Coroutine[Any, Any, Any]) -> Any:
        return await asyncio.wrap_future(self.submit(coro))

    # ── MCPClient API ────────────────────────────────────────────────────
    @property
    def servers(self):  # noqa: ANN201
        return self._inner.servers

    def start_in_background(self) -> None:
        """Connect enabled servers without blocking the caller."""
        self.submit(self._inner.start())

    async def start(self) -> None:
        await self._call(self._inner.start())

    async def set_enabled(self, name: str, enabled: bool) -> None:
        await self._call(self._inner.set_enabled(name, enabled))

    async def ping(self, name: str) -> float | None:
        return await self._call(self._inner.ping(name))

    async def call_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        return await self._call(self._inner.call_tool(server, tool, arguments))

    def all_tools(self) -> list[MCPToolDefinition]:
        return self._inner.all_tools()

    async def close(self) -> None:
        if self._loop.is_closed():
            return
        try:
            await self._call(self._inner.close())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
