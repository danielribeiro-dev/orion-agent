"""
O.R.I.O.N — MCPClient
Manages the lifecycle of several MCP servers, isolated from each other.

Each server runs inside its own asyncio task (anyio context managers must be
entered and exited in the same task). A hung/crashed server is contained by
timeouts and never blocks the CLI.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.mcp.models import MCPServerConfig, MCPToolDefinition
from orion.mcp.transports import open_session

logger = logging.getLogger(__name__)

DEFAULT_CATALOG = Path(__file__).with_name("mcp_servers.default.json")
CONNECT_TIMEOUT = 60.0  # cold uvx/npx start downloads the package (~10 s measured)
CALL_TIMEOUT = 60.0


def load_config_file(path: Path, *, bundled: bool = False) -> dict[str, dict[str, Any]]:
    """Read ``{"servers": {...}}`` (or ``{"mcpServers": {...}}``) from *path*."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        if path.exists():
            logger.warning("Invalid MCP config %s: %s", path, exc)
        return {}
    servers = data.get("servers") or data.get("mcpServers") or {}
    out: dict[str, dict[str, Any]] = {}
    for name, cfg in servers.items():
        if isinstance(cfg, dict):
            cfg = dict(cfg)
            # ``bundled`` is decided by the loader, never by user files.
            cfg["bundled"] = bundled
            out[name] = cfg
    return out


def load_server_configs(
    global_home: Path | None = None,
    workspace: Path | None = None,
    *,
    catalog: Path = DEFAULT_CATALOG,
) -> dict[str, MCPServerConfig]:
    """Merge catalog < ~/.orion/mcp_servers.json < <ws>/.orion/mcp_servers.json.

    Later layers override earlier ones field by field (so a user can just write
    ``{"serena": {"enabled": false}}``).
    """
    layers = [load_config_file(catalog, bundled=True)]
    if global_home:
        layers.append(load_config_file(global_home / "mcp_servers.json"))
    if workspace:
        layers.append(load_config_file(workspace / ".orion" / "mcp_servers.json"))
    merged: dict[str, dict[str, Any]] = {}
    for layer in layers:
        for name, cfg in layer.items():
            base = merged.get(name, {})
            bundled = base.get("bundled", False) or cfg.get("bundled", False)
            merged[name] = {**base, **cfg, "bundled": bundled}
    result: dict[str, MCPServerConfig] = {}
    for name, cfg in merged.items():
        try:
            result[name] = MCPServerConfig(name=name, **cfg)
        except Exception as exc:  # pydantic validation
            logger.warning("Skipping MCP server %s: %s", name, exc)
    return result


@dataclass
class ServerState:
    config: MCPServerConfig
    status: str = "disabled"  # disabled | connecting | connected | error
    error: str = ""
    latency_ms: float = 0.0
    tools: list[MCPToolDefinition] = field(default_factory=list)
    session: Any = None
    task: asyncio.Task | None = None
    stop: asyncio.Event = field(default_factory=asyncio.Event)


class MCPClient:
    """Connects to every enabled server and routes tool calls."""

    def __init__(
        self,
        configs: dict[str, MCPServerConfig],
        *,
        connect_timeout: float = CONNECT_TIMEOUT,
        call_timeout: float = CALL_TIMEOUT,
        opener=open_session,
    ) -> None:
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._opener = opener
        self.servers: dict[str, ServerState] = {
            n: ServerState(config=c, status="connecting" if c.enabled else "disabled")
            for n, c in configs.items()
        }

    # ── lifecycle ────────────────────────────────────────────────────────
    async def start(self) -> None:
        """Connect all enabled servers concurrently; failures are isolated."""
        await asyncio.gather(
            *(self.connect(n) for n, s in self.servers.items() if s.config.enabled)
        )

    async def connect(self, name: str) -> None:
        state = self.servers[name]
        if state.task and not state.task.done():
            return
        state.stop = asyncio.Event()
        state.status, state.error = "connecting", ""
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        state.task = asyncio.create_task(self._run(state, ready))
        try:
            await asyncio.wait_for(asyncio.shield(ready), self._connect_timeout)
        except Exception as exc:
            state.status = "error"
            state.error = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            await self.disconnect(name, keep_error=True)

    async def _run(self, state: ServerState, ready: asyncio.Future[None]) -> None:
        stack = AsyncExitStack()
        try:
            t0 = time.perf_counter()
            session = await self._opener(state.config, stack)
            listed = await session.list_tools()
            state.latency_ms = (time.perf_counter() - t0) * 1000
            state.session = session
            state.tools = [
                MCPToolDefinition(
                    server_name=state.config.name,
                    name=t.name,
                    description=t.description or "",
                    input_schema=t.input_schema or {},
                    read_only_hint=getattr(t.annotations, "read_only_hint", None),
                )
                for t in listed.tools
            ]
            state.status = "connected"
            if not ready.done():
                ready.set_result(None)
            await state.stop.wait()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.status, state.error = "error", f"{type(exc).__name__}: {exc}"
            if not ready.done():
                ready.set_exception(exc)
        finally:
            state.session = None
            with contextlib.suppress(BaseException):  # best-effort cleanup
                await asyncio.wait_for(stack.aclose(), 5.0)

    async def disconnect(self, name: str, *, keep_error: bool = False) -> None:
        state = self.servers[name]
        state.stop.set()
        task = state.task
        if task and not task.done():
            if state.status != "connected":
                # Never reached the stop-wait (hung handshake): cancel right away.
                task.cancel()
            try:
                await asyncio.wait_for(task, 6.0)
            except BaseException:  # noqa: BLE001
                task.cancel()
        state.session, state.tools = None, [] if not keep_error else state.tools
        if not keep_error:
            state.status = "disabled"

    async def close(self) -> None:
        await asyncio.gather(*(self.disconnect(n) for n in self.servers))

    # ── operations ───────────────────────────────────────────────────────
    async def set_enabled(self, name: str, enabled: bool) -> None:
        state = self.servers[name]
        state.config = state.config.model_copy(update={"enabled": enabled})
        if enabled:
            await self.connect(name)
        else:
            await self.disconnect(name)

    async def ping(self, name: str) -> float | None:
        """Return round-trip ms, or None if the server is unreachable."""
        state = self.servers[name]
        if not state.session:
            return None
        t0 = time.perf_counter()
        try:
            await asyncio.wait_for(state.session.send_ping(), 5.0)
        except Exception:
            state.status, state.error = "error", "ping failed"
            return None
        state.latency_ms = (time.perf_counter() - t0) * 1000
        return state.latency_ms

    async def call_tool(self, server: str, tool: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        """Call a tool; returns ``(ok, text)``. Never raises for server faults."""
        state = self.servers.get(server)
        if not state or not state.session:
            return False, f"MCP server '{server}' is not connected"
        try:
            res = await asyncio.wait_for(
                state.session.call_tool(tool, arguments), self._call_timeout
            )
        except TimeoutError:
            return False, f"MCP tool '{tool}' timed out after {self._call_timeout:.0f}s"
        except Exception as exc:
            return False, f"MCP tool '{tool}' failed: {exc}"
        parts = [getattr(c, "text", None) or str(c) for c in res.content]
        return (not res.is_error), "\n".join(parts)

    def all_tools(self) -> list[MCPToolDefinition]:
        return [t for s in self.servers.values() if s.status == "connected" for t in s.tools]
