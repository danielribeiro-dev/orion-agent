"""
O.R.I.O.N — MCP transports
Opens a ClientSession over stdio (subprocess), SSE or streamable HTTP, via the MCP SDK.
"""

from __future__ import annotations

import os
import re
from contextlib import AsyncExitStack
from pathlib import Path

import httpx2
from mcp import ClientSession, StdioServerParameters
from mcp.client.session import MessageHandlerFnT
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

from orion.mcp.models import MCPServerConfig
from orion.mcp.spawn_policy import check_remote_url, check_spawn

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
HTTP_TIMEOUT = httpx2.Timeout(30.0, read=300.0)


class MissingEnvVar(ValueError):
    """Header referencia ``${VAR}`` que não está definida no ambiente."""


def expand_env(value: str, env: dict[str, str] | None = None) -> str:
    """Expande ``${VAR}``; variável ausente é erro (nunca envia o segredo vazio)."""
    source = os.environ if env is None else env

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in source:
            raise MissingEnvVar(f"variável de ambiente {name} não definida")
        return source[name]

    return _ENV_REF.sub(sub, value)


def expand_headers(headers: dict[str, str], env: dict[str, str] | None = None) -> dict[str, str]:
    return {k: expand_env(v, env) for k, v in headers.items()}


def server_log_path(name: str, home: Path | None = None) -> Path:
    """Arquivo onde o stderr de um servidor MCP é gravado (nunca o terminal)."""
    base = (home or Path.home() / ".orion") / "logs"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"mcp-{re.sub(r'[^A-Za-z0-9_.-]', '_', name)}.log"
    if not path.exists():
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT, 0o600))  # logs podem conter segredos
    return path


async def open_session(
    cfg: MCPServerConfig,
    stack: AsyncExitStack,
    *,
    on_message: MessageHandlerFnT | None = None,
    auth: httpx2.Auth | None = None,
) -> ClientSession:
    """Open and initialize a session; resources are registered on *stack*."""
    check_spawn(cfg)
    check_remote_url(cfg)
    if cfg.transport == "sse":
        read, write = await stack.enter_async_context(
            sse_client(cfg.url or "", headers=expand_headers(cfg.headers) or None, auth=auth)
        )
    elif cfg.transport == "http":
        client = await stack.enter_async_context(
            httpx2.AsyncClient(
                headers=expand_headers(cfg.headers) or None,
                auth=auth,
                timeout=HTTP_TIMEOUT,
                follow_redirects=True,
            )
        )
        read, write = await stack.enter_async_context(
            streamable_http_client(cfg.url or "", http_client=client)
        )
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
    session = await stack.enter_async_context(
        ClientSession(read, write, message_handler=on_message)
    )
    await session.initialize()
    return session
