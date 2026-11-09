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

from orion.mcp.client import MCPClient, ServerState
from orion.mcp.models import MCPPrompt, MCPResource, MCPServerConfig, MCPToolDefinition


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
    def servers(self) -> dict[str, ServerState]:
        return self._inner.servers

    @property
    def generation(self) -> int:
        """Changes whenever tools, resources or prompts change (list_changed, reconnect)."""
        return self._inner.generation

    def start_in_background(self) -> None:
        """Connect enabled servers without blocking the caller."""
        self.submit(self._inner.start())

    async def start(self) -> None:
        await self._call(self._inner.start())

    async def set_enabled(self, name: str, enabled: bool) -> None:
        await self._call(self._inner.set_enabled(name, enabled))

    async def ping(self, name: str) -> float | None:
        result: float | None = await self._call(self._inner.ping(name))
        return result

    async def call_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        result: tuple[bool, str] = await self._call(self._inner.call_tool(server, tool, arguments))
        return result

    async def add_server(self, config: MCPServerConfig) -> None:
        await self._call(self._inner.add_server(config))

    async def remove_server(self, name: str) -> bool:
        return bool(await self._call(self._inner.remove_server(name)))

    async def authenticate(self, name: str) -> None:
        await self._call(self._inner.authenticate(name))

    async def read_resource(self, server: str, uri: str) -> tuple[bool, str]:
        result: tuple[bool, str] = await self._call(self._inner.read_resource(server, uri))
        return result

    async def get_prompt(
        self, server: str, name: str, arguments: dict[str, str]
    ) -> tuple[bool, str]:
        result: tuple[bool, str] = await self._call(self._inner.get_prompt(server, name, arguments))
        return result

    def all_tools(self) -> list[MCPToolDefinition]:
        return self._inner.all_tools()

    def all_resources(self) -> list[MCPResource]:
        return self._inner.all_resources()

    def all_prompts(self) -> list[MCPPrompt]:
        return self._inner.all_prompts()

    async def close(self) -> None:
        if self._loop.is_closed():
            return
        try:
            await self._call(self._inner.close())
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
