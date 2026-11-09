"""
O.R.I.O.N — MCP spawn policy
Gate applied to a server's ``command`` before any subprocess is created.

Only well-known package launchers/interpreters are allowed; shell binaries and
paths are rejected so a poisoned mcp_servers.json cannot run arbitrary commands.
"""

from __future__ import annotations

import os

from orion.mcp.models import MCPServerConfig

ALLOWED_LAUNCHERS: frozenset[str] = frozenset(
    {"uvx", "uv", "npx", "node", "python", "python3", "pipx", "bunx", "deno"}
)
_FORBIDDEN_ARGS: frozenset[str] = frozenset({"-c", "-e", "--eval", "--exec"})


class SpawnDenied(Exception):
    """Raised when a server command is rejected by the spawn policy."""


def check_spawn(cfg: MCPServerConfig) -> None:
    """Raise :class:`SpawnDenied` unless *cfg* may be spawned (stdio only)."""
    if cfg.transport != "stdio":
        return
    if not cfg.command:
        raise SpawnDenied(f"{cfg.name}: stdio server without 'command'")
    if os.sep in cfg.command or cfg.command != cfg.command.strip():
        raise SpawnDenied(f"{cfg.name}: command must be a bare launcher name, got {cfg.command!r}")
    if cfg.command not in ALLOWED_LAUNCHERS:
        raise SpawnDenied(f"{cfg.name}: launcher {cfg.command!r} not in allowlist")
    if cfg.command in {"python", "python3", "node", "deno"} and any(
        a in _FORBIDDEN_ARGS for a in cfg.args
    ):
        raise SpawnDenied(f"{cfg.name}: inline code execution flags are not allowed")


_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
SERVER_NAME_RE = r"^[A-Za-z0-9_-]{1,40}$"


def check_remote_url(cfg: MCPServerConfig) -> None:
    """Validate the URL of a remote (sse/http) server.

    Servers are configured by the Senhor, so loopback is allowed (dev servers).
    Required: http(s) scheme, a host, no credentials embedded in the URL, and
    https for any non-loopback host when headers or OAuth carry credentials.
    """
    if cfg.transport == "stdio":
        return
    from urllib.parse import urlsplit

    if not cfg.url:
        raise SpawnDenied(f"{cfg.name}: servidor remoto sem 'url'")
    parts = urlsplit(cfg.url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise SpawnDenied(f"{cfg.name}: URL inválida (use http:// ou https://): {cfg.url}")
    if parts.username or parts.password:
        raise SpawnDenied(f"{cfg.name}: credenciais embutidas na URL não são permitidas")
    sends_secrets = bool(cfg.headers) or cfg.auth == "oauth"
    if sends_secrets and parts.scheme != "https" and parts.hostname not in _LOOPBACK:
        raise SpawnDenied(
            f"{cfg.name}: credenciais só trafegam por https (ou loopback); recebido {parts.scheme}://"
        )
