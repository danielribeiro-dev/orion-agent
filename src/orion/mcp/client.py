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
import inspect
import json
import logging
import time
from collections.abc import Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp.types import (
    PaginatedRequestParams,
    PromptListChangedNotification,
    ResourceListChangedNotification,
    ToolListChangedNotification,
)

from orion.mcp.models import (
    MCPPrompt,
    MCPPromptArgument,
    MCPResource,
    MCPServerConfig,
    MCPToolDefinition,
)
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
    extra_layers: list[dict[str, dict[str, Any]]] | None = None,
) -> dict[str, MCPServerConfig]:
    """Merge catalog < settings/plugins < ~/.orion/mcp_servers.json < <ws>/.orion/mcp_servers.json.

    ``extra_layers`` (``mcp`` dos settings efetivos e dos plugins) entram logo após o catálogo.

    Later layers override earlier ones field by field (so a user can just write
    ``{"serena": {"enabled": false}}``).
    """
    layers = [load_config_file(catalog, bundled=True)]
    layers.extend({n: {**c, "bundled": False} for n, c in layer.items()} for layer in extra_layers or [])
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


MAX_PAGES = 50
RECONNECT_DELAY_CAP = 30.0
INTERACTIVE_CONNECT_TIMEOUT = 300.0


def _flatten(exc: BaseException) -> list[BaseException]:
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for sub in exc.exceptions for leaf in _flatten(sub)]
    return [exc]


def describe_error(exc: BaseException, server: str) -> str:
    """Mensagem curta e acionável (desembrulha grupos de exceções do anyio)."""
    from orion.mcp.oauth import AuthRequired

    leaves = _flatten(exc)
    for leaf in leaves:
        if isinstance(leaf, AuthRequired):
            return f"autenticação necessária: use /mcp auth {server}"
    leaf = leaves[0]
    status = getattr(getattr(leaf, "response", None), "status_code", None)
    if status == 401:
        return f"não autorizado (401): use /mcp auth {server} ou revise os headers"
    text = str(leaf)
    return f"{type(leaf).__name__}: {text}" if text else type(leaf).__name__


@dataclass
class ServerState:
    config: MCPServerConfig
    status: str = "disabled"  # disabled | connecting | connected | reconnecting | error
    error: str = ""
    latency_ms: float = 0.0
    tools: list[MCPToolDefinition] = field(default_factory=list)
    resources: list[MCPResource] = field(default_factory=list)
    prompts: list[MCPPrompt] = field(default_factory=list)
    session: Any = None
    task: asyncio.Task[None] | None = None
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    pending: set[str] = field(default_factory=set)
    dropped_reason: str = ""
    suspect: bool = False
    interactive: bool = False
    reconnects: int = 0
    connected_once: bool = False
    auth_required: bool = False


class MCPClient:
    """Connects to every enabled server and routes tool, resource and prompt calls."""

    def __init__(
        self,
        configs: dict[str, MCPServerConfig],
        *,
        connect_timeout: float = CONNECT_TIMEOUT,
        call_timeout: float = CALL_TIMEOUT,
        opener: Callable[..., Any] = open_session,
        home: Path | None = None,
        on_auth_url: Callable[[str, str], None] | None = None,
        open_browser: Callable[[str], Any] | None = None,
        ping_interval: float = 30.0,
        max_reconnects: int = 5,
        backoff_base: float = 1.0,
    ) -> None:
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._opener = opener
        self._home = home or Path.home() / ".orion"
        self._on_auth_url = on_auth_url
        self._open_browser = open_browser
        self._ping_interval = ping_interval
        self._max_reconnects = max_reconnects
        self._backoff_base = backoff_base
        self._opener_params = inspect.signature(opener).parameters
        #: Bumps whenever tools/resources/prompts change (connect, list_changed, reconnect).
        self.generation = 0
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

    async def connect(self, name: str, *, interactive: bool = False) -> None:
        state = self.servers[name]
        if state.task and not state.task.done():
            return
        state.stop = asyncio.Event()
        state.changed = asyncio.Event()
        state.pending, state.dropped_reason, state.suspect = set(), "", False
        state.interactive = interactive
        state.connected_once = False
        state.auth_required = False
        state.status, state.error = "connecting", ""
        ready: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        state.task = asyncio.create_task(self._run(state, ready))
        timeout = max(self._connect_timeout, INTERACTIVE_CONNECT_TIMEOUT) if interactive else self._connect_timeout
        try:
            await asyncio.wait_for(asyncio.shield(ready), timeout)
        except Exception as exc:
            state.status = "error"
            if not state.error or isinstance(exc, TimeoutError):
                state.error = describe_error(exc, name)
            await self.disconnect(name, keep_error=True)

    def _kwargs_for_opener(self, state: ServerState, auth: Any) -> dict[str, Any]:
        wanted = {"on_message": self._message_handler(state), "auth": auth}
        accepts_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in self._opener_params.values())
        return {k: v for k, v in wanted.items() if accepts_any or k in self._opener_params}

    async def _run(self, state: ServerState, ready: asyncio.Future[None]) -> None:
        """Serve one server for its whole life: connect, watch, reconnect with backoff."""
        attempt = 0
        first = True
        while True:
            outcome = await self._serve_once(state, ready if first else None)
            if state.status == "connected":
                attempt = 0
            first = False
            if outcome in ("stopped", "failed"):
                return
            attempt += 1
            state.reconnects += 1
            if attempt > self._max_reconnects:
                state.status = "error"
                state.error = f"reconexão esgotada ({state.dropped_reason or 'conexão perdida'})"
                self.generation += 1
                return
            state.status = "reconnecting"
            self.generation += 1
            delay = min(self._backoff_base * 2 ** (attempt - 1), RECONNECT_DELAY_CAP)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(state.stop.wait(), delay)
            if state.stop.is_set():
                return
            state.dropped_reason, state.suspect = "", False
            state.changed.clear()

    async def _serve_once(self, state: ServerState, ready: asyncio.Future[None] | None) -> str:
        """One connection lifetime. Returns ``stopped`` | ``dropped`` | ``failed``.

        The connection runs in its own task: when a transport dies the SDK cancels the
        anyio scope owned by that task, and that cancellation must read as "dropped",
        not kill the supervisor.
        """
        inner = asyncio.create_task(self._connection(state, ready))
        try:
            await asyncio.wait({inner})
        except asyncio.CancelledError:
            inner.cancel()
            with contextlib.suppress(BaseException):
                await inner
            raise
        if state.auth_required and not state.stop.is_set():
            message = f"autenticação necessária: use /mcp auth {state.config.name}"
            state.status, state.error, state.dropped_reason = "error", message, message
            if ready is not None and not ready.done():
                ready.set_exception(PermissionError(message))
            return "failed"  # sem login não adianta reconectar em loop
        if inner.cancelled():
            if state.stop.is_set():
                return "stopped"
            state.dropped_reason = state.dropped_reason or "conexão interrompida"
            state.status = "error"
            state.error = state.error or state.dropped_reason
            if ready is not None and not ready.done():
                ready.set_exception(ConnectionError(state.dropped_reason))
            return "dropped" if state.connected_once else "failed"
        if (exc := inner.exception()) is not None:
            state.status, state.error = "error", describe_error(exc, state.config.name)
            if ready is not None and not ready.done():
                ready.set_exception(exc)
            return "dropped" if state.connected_once else "failed"
        return inner.result()

    async def _connection(self, state: ServerState, ready: asyncio.Future[None] | None) -> str:
        stack = AsyncExitStack()
        setup: Any = None
        try:
            auth = None
            cfg = state.config
            if cfg.auth == "oauth" and cfg.transport != "stdio":
                from orion.mcp.oauth import build_oauth

                extra: dict[str, Any] = (
                    {"open_browser": self._open_browser} if self._open_browser else {}
                )
                setup = await build_oauth(
                    cfg,
                    self._home,
                    interactive=state.interactive,
                    notify=self._on_auth_url,
                    on_auth_required=lambda: setattr(state, "auth_required", True),
                    **extra,
                )
                auth = setup.provider
            t0 = time.perf_counter()
            session = await self._opener(cfg, stack, **self._kwargs_for_opener(state, auth))
            await self._load_catalog(state, session)
            state.latency_ms = (time.perf_counter() - t0) * 1000
            state.session = session
            state.status, state.error = "connected", ""
            state.connected_once = True
            self.generation += 1
            if ready is not None and not ready.done():
                ready.set_result(None)
            return await self._watch(state, session)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            state.status = "error"
            state.error = describe_error(exc, state.config.name)
            state.dropped_reason = state.error
            if ready is not None and not ready.done():
                ready.set_exception(exc)
                return "failed"
            return "dropped" if state.connected_once else "failed"
        finally:
            state.session = None
            if setup is not None:
                with contextlib.suppress(BaseException):
                    await setup.close()
            with contextlib.suppress(BaseException):  # best-effort cleanup
                await asyncio.wait_for(stack.aclose(), 5.0)

    async def _watch(self, state: ServerState, session: Any) -> str:
        """Block until stop, a refresh request or a dead connection."""
        while True:
            waiters = {
                asyncio.ensure_future(state.stop.wait()),
                asyncio.ensure_future(state.changed.wait()),
            }
            try:
                await asyncio.wait(waiters, timeout=self._ping_interval, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for waiter in waiters:
                    waiter.cancel()
            if state.stop.is_set():
                return "stopped"
            if state.changed.is_set():
                state.changed.clear()
                if state.pending:
                    await self._refresh(state, session)
                if not state.suspect:
                    continue
            try:  # keepalive (rede apenas, zero tokens) ou verificação após erro de transporte
                await asyncio.wait_for(session.send_ping(), 5.0)
                state.suspect = False
            except Exception as exc:  # noqa: BLE001
                state.dropped_reason = describe_error(exc, state.config.name)
                state.status = "reconnecting"
                return "dropped"

    def _message_handler(self, state: ServerState) -> Callable[[Any], Any]:
        async def handle(message: Any) -> None:
            if isinstance(message, Exception):
                state.suspect = True
                state.changed.set()
                return
            root = getattr(message, "root", message)
            if isinstance(root, ToolListChangedNotification):
                state.pending.add("tools")
            elif isinstance(root, ResourceListChangedNotification):
                state.pending.add("resources")
            elif isinstance(root, PromptListChangedNotification):
                state.pending.add("prompts")
            else:
                return
            state.changed.set()

        return handle

    # ── catalog (tools / resources / prompts) ────────────────────────────
    @staticmethod
    async def _paginate(call: Callable[..., Any], attr: str) -> list[Any]:
        items: list[Any] = []
        cursor: str | None = None
        for _ in range(MAX_PAGES):
            result = await (call() if cursor is None else call(params=PaginatedRequestParams(cursor=cursor)))
            items.extend(getattr(result, attr))
            cursor = getattr(result, "next_cursor", None)
            if not cursor:
                break
        return items

    async def _load_tools(self, state: ServerState, session: Any) -> None:
        state.tools = [
            MCPToolDefinition(
                server_name=state.config.name,
                name=t.name,
                description=t.description or "",
                input_schema=t.input_schema or {},
                read_only_hint=getattr(t.annotations, "read_only_hint", None),
            )
            for t in await self._paginate(session.list_tools, "tools")
        ]

    async def _load_resources(self, state: ServerState, session: Any) -> None:
        state.resources = [
            MCPResource(
                server_name=state.config.name,
                uri=str(r.uri),
                name=r.name or "",
                description=getattr(r, "description", None) or "",
                mime_type=getattr(r, "mime_type", None) or "",
            )
            for r in await self._paginate(session.list_resources, "resources")
        ]

    async def _load_prompts(self, state: ServerState, session: Any) -> None:
        state.prompts = [
            MCPPrompt(
                server_name=state.config.name,
                name=p.name,
                description=p.description or "",
                arguments=[
                    MCPPromptArgument(
                        name=a.name,
                        description=getattr(a, "description", None) or "",
                        required=bool(getattr(a, "required", False)),
                    )
                    for a in (p.arguments or [])
                ],
            )
            for p in await self._paginate(session.list_prompts, "prompts")
        ]

    async def _load_catalog(self, state: ServerState, session: Any) -> None:
        await self._load_tools(state, session)
        caps = getattr(session, "server_capabilities", None)
        if caps is not None and getattr(caps, "resources", None):
            await self._load_resources(state, session)
        if caps is not None and getattr(caps, "prompts", None):
            await self._load_prompts(state, session)

    async def _refresh(self, state: ServerState, session: Any) -> None:
        pending, state.pending = set(state.pending), set()
        loaders = {"tools": self._load_tools, "resources": self._load_resources, "prompts": self._load_prompts}
        for kind in sorted(pending):
            try:
                await loaders[kind](state, session)
            except Exception as exc:  # noqa: BLE001 - servidor instável não derruba o cliente
                logger.warning("MCP %s: falha ao atualizar %s: %s", state.config.name, kind, exc)
        self.generation += 1

    # ── shutdown / membership ────────────────────────────────────────────
    async def disconnect(self, name: str, *, keep_error: bool = False) -> None:
        state = self.servers[name]
        state.stop.set()
        task = state.task
        if task and not task.done():
            if state.status not in ("connected", "reconnecting"):
                # Never reached the stop-wait (hung handshake): cancel right away.
                task.cancel()
            try:
                await asyncio.wait_for(task, 6.0)
            except BaseException:  # noqa: BLE001
                task.cancel()
        state.session = None
        if not keep_error:
            state.tools, state.resources, state.prompts = [], [], []
            state.status = "disabled"
        self.generation += 1

    async def close(self) -> None:
        await asyncio.gather(*(self.disconnect(n) for n in self.servers))

    async def add_server(self, config: MCPServerConfig) -> None:
        """Register (and connect, if enabled) a server at runtime."""
        if config.name in self.servers:
            await self.disconnect(config.name)
        self.servers[config.name] = ServerState(
            config=config, status="connecting" if config.enabled else "disabled"
        )
        if config.enabled:
            await self.connect(config.name)
        self.generation += 1

    async def remove_server(self, name: str) -> bool:
        if name not in self.servers:
            return False
        await self.disconnect(name)
        self.servers.pop(name, None)
        self.generation += 1
        return True

    async def authenticate(self, name: str) -> None:
        """Interactive OAuth login: reconnect letting the SDK open the browser."""
        await self.disconnect(name)
        self.servers[name].config = self.servers[name].config.model_copy(update={"enabled": True})
        await self.connect(name, interactive=True)

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

    async def read_resource(self, server: str, uri: str) -> tuple[bool, str]:
        """Read a resource; binary contents are summarised, never inlined."""
        state = self.servers.get(server)
        if not state or not state.session:
            return False, f"MCP server '{server}' is not connected"
        try:
            res = await asyncio.wait_for(state.session.read_resource(uri), self._call_timeout)
        except TimeoutError:
            return False, f"MCP resource '{uri}' timed out after {self._call_timeout:.0f}s"
        except Exception as exc:
            return False, f"MCP resource '{uri}' failed: {exc}"
        parts: list[str] = []
        for item in getattr(res, "contents", []):
            text = getattr(item, "text", None)
            if text is not None:
                parts.append(text)
            else:
                blob = getattr(item, "blob", "") or ""
                mime = getattr(item, "mime_type", None) or "application/octet-stream"
                parts.append(f"[binary content omitted: {mime}, {len(blob)} base64 chars]")
        return True, "\n".join(parts)

    async def get_prompt(self, server: str, name: str, arguments: dict[str, str]) -> tuple[bool, str]:
        """Render a prompt template into plain text."""
        state = self.servers.get(server)
        if not state or not state.session:
            return False, f"MCP server '{server}' is not connected"
        try:
            res = await asyncio.wait_for(
                state.session.get_prompt(name, arguments or None), self._call_timeout
            )
        except TimeoutError:
            return False, f"MCP prompt '{name}' timed out after {self._call_timeout:.0f}s"
        except Exception as exc:
            return False, f"MCP prompt '{name}' failed: {exc}"
        messages = list(getattr(res, "messages", []))
        lines: list[str] = []
        for message in messages:
            content = getattr(message, "content", None)
            text = getattr(content, "text", None) or (str(content) if content is not None else "")
            role = getattr(message, "role", "user")
            lines.append(text if len(messages) == 1 else f"{role}: {text}")
        return True, "\n\n".join(lines)

    def all_tools(self) -> list[MCPToolDefinition]:
        return [t for s in self.servers.values() if s.status == "connected" for t in s.tools]

    def all_resources(self) -> list[MCPResource]:
        return [r for s in self.servers.values() if s.status == "connected" for r in s.resources]

    def all_prompts(self) -> list[MCPPrompt]:
        return [p for s in self.servers.values() if s.status == "connected" for p in s.prompts]
