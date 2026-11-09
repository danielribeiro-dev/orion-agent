"""Comando /mcp — inspeção e gerenciamento dos servidores MCP."""

from __future__ import annotations

import re
import shlex
from pathlib import Path
from typing import Any

from rich.table import Table

from orion.mcp.models import MCPPrompt, MCPServerConfig
from orion.mcp.oauth import FileTokenStorage
from orion.mcp.spawn_policy import SERVER_NAME_RE, SpawnDenied, check_remote_url, check_spawn
from orion.settings.io import read_json_object, write_private_json
from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.panels import brand_title, orion_panel

_STATUS_STYLE = {
    "connected": "diff_add",
    "error": "diff_del",
    "connecting": "accent_cyan",
    "reconnecting": "pep_warn",
}
USAGE = (
    "/mcp [list | enable <srv> | disable <srv> | ping <srv> | tools <srv> | resources [srv] | "
    "prompts [srv] | add <nome> <url|comando> [--transport http|sse] [--header K=V] [--oauth] "
    "[--scope S] | remove <srv> | auth <srv>]"
)


def _servers_key(data: dict[str, Any]) -> str:
    return "mcpServers" if "mcpServers" in data and "servers" not in data else "servers"


def _read_servers_file(home: Path) -> dict[str, Any]:
    return read_json_object(home / "mcp_servers.json") or {}


def persist_enabled(home: Path, name: str, enabled: bool) -> None:
    """Merge ``{"servers": {name: {"enabled": ...}}}`` into ~/.orion/mcp_servers.json (0600)."""
    data = _read_servers_file(home)
    data.setdefault(_servers_key(data), {}).setdefault(name, {})["enabled"] = enabled
    write_private_json(home / "mcp_servers.json", data)


def persist_server(home: Path, name: str, entry: dict[str, Any] | None) -> None:
    """Add/replace (or, with ``None``, delete) a server in ~/.orion/mcp_servers.json (0600)."""
    data = _read_servers_file(home)
    servers = data.setdefault(_servers_key(data), {})
    if entry is None:
        servers.pop(name, None)
    else:
        servers[name] = entry
    write_private_json(home / "mcp_servers.json", data)


def parse_add(tokens: list[str]) -> tuple[str, dict[str, Any]]:
    """Parse ``<nome> <url|comando...> [flags]`` into ``(name, config_entry)``.

    Raises ``ValueError`` with a user-facing message on bad input.
    """
    if len(tokens) < 2:
        raise ValueError("informe o nome e a URL (ou o comando) do servidor")
    name, target, rest = tokens[0], tokens[1], tokens[2:]
    if not re.match(SERVER_NAME_RE, name):
        raise ValueError("nome inválido: use letras, números, '-' e '_' (até 40)")
    transport: str | None = None
    headers: dict[str, str] = {}
    oauth = False
    scope: str | None = None
    positional: list[str] = []
    it = iter(rest)
    for token in it:
        if token == "--transport":
            transport = next(it, "")
            if transport not in ("http", "sse", "stdio"):
                raise ValueError("--transport aceita http, sse ou stdio")
        elif token == "--header":
            pair = next(it, "")
            key, sep, value = pair.partition("=")
            if not sep or not key:
                raise ValueError("--header espera CHAVE=VALOR")
            headers[key.strip()] = value
        elif token == "--oauth":
            oauth = True
        elif token == "--scope":
            scope = next(it, "") or None
        else:
            positional.append(token)
    if re.match(r"https?://", target):
        entry: dict[str, Any] = {"url": target, "transport": transport or "http"}
        if headers:
            entry["headers"] = headers
        if oauth:
            entry["auth"] = "oauth"
        if scope:
            entry["scope"] = scope
        return name, entry
    if oauth or headers:
        raise ValueError("--oauth e --header só valem para servidores remotos (URL)")
    return name, {"transport": "stdio", "command": target, "args": positional}


class MCPPromptCommand(BaseSlashCommand):
    """Prompt de um servidor MCP exposto como ``/mcp__<srv>__<prompt>``."""

    def __init__(self, prompt: MCPPrompt) -> None:
        self.prompt = prompt
        self.name = prompt.command_name  # type: ignore[misc]
        self.description = prompt.description or f"Prompt MCP de {prompt.server_name}"  # type: ignore[misc]
        arg_names = " ".join(f"<{a.name}>" if a.required else f"[{a.name}]" for a in prompt.arguments)
        self.usage = f"{self.name} {arg_names}".strip()  # type: ignore[misc]

    def _bind(self, args: str) -> dict[str, str]:
        """``chave=valor`` casa pelo nome; o restante preenche os argumentos em ordem."""
        try:
            parts = shlex.split(args)
        except ValueError:
            parts = args.split()
        names = [a.name for a in self.prompt.arguments]
        bound: dict[str, str] = {}
        loose: list[str] = []
        for part in parts:
            key, sep, val = part.partition("=")
            if sep and key in names:
                bound[key] = val
            else:
                loose.append(part)
        free = iter(loose)
        for name in names:
            if name not in bound:
                nxt = next(free, None)
                if nxt is not None:
                    bound[name] = nxt
        return bound

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        client = getattr(context.session, "mcp", None)
        if client is None:
            return CommandResult(success=False, output_message="Cliente MCP inativo.")
        bound = self._bind(args)
        missing = [a.name for a in self.prompt.arguments if a.required and a.name not in bound]
        if missing:
            return CommandResult(success=False, output_message=f"Uso: {self.usage} (falta: {', '.join(missing)})")
        ok, text = await client.get_prompt(self.prompt.server_name, self.prompt.name, bound)
        if not ok:
            return CommandResult(success=False, output_message=text)
        await context.session.run_turn(text)
        return CommandResult(success=True)


class McpCommand(BaseSlashCommand):
    name = "/mcp"
    description = "Gerencia servidores MCP (status, ativar/desativar, ping, tools)"
    usage = USAGE

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        client = getattr(session, "mcp", None)
        if client is None:
            return CommandResult(
                success=False,
                output_message="Cliente MCP inativo (ORION_MCP=0 ou falha ao iniciar).",
            )
        parts = args.split()
        action = parts[0] if parts else "list"
        target = parts[1] if len(parts) > 1 else ""
        if action == "list":
            return self._list(client, context)
        if action == "add":
            return await self._add(client, session, args)
        if action in {"resources", "prompts"}:
            return self._catalog(client, action, target)
        if action not in {"enable", "disable", "ping", "tools", "remove", "auth"} or not target:
            return CommandResult(success=False, output_message=f"Uso: {USAGE}")
        if target not in client.servers:
            known = ", ".join(sorted(client.servers)) or "nenhum"
            return CommandResult(
                success=False, output_message=f"Servidor '{target}' desconhecido. Disponíveis: {known}"
            )
        if action == "remove":
            return await self._remove(client, session, target)
        if action == "auth":
            return await self._auth(client, session, target)
        if action in {"enable", "disable"}:
            enabled = action == "enable"
            persist_enabled(session.home, target, enabled)
            await client.set_enabled(target, enabled)
            session.refresh_mcp()
            state = client.servers[target]
            msg = f"{target}: {'ativado' if enabled else 'desativado'}"
            if enabled and state.status == "error":
                return CommandResult(success=False, output_message=f"{msg}, mas falhou: {state.error}")
            return CommandResult(success=True, output_message=msg)
        if action == "ping":
            ms = await client.ping(target)
            if ms is None:
                return CommandResult(success=False, output_message=f"{target}: sem resposta")
            return CommandResult(success=True, output_message=f"{target}: {ms:.0f} ms")
        tools = client.servers[target].tools
        lines = [f"{t.qualified_name} — {' '.join(t.description.split())[:70]}" for t in tools]
        return CommandResult(success=True, output_message="\n".join(lines) or f"{target}: sem tools")

    async def _add(self, client: Any, session: Any, args: str) -> CommandResult:
        try:
            tokens = shlex.split(args)[1:]
            name, entry = parse_add(tokens)
            config = MCPServerConfig(name=name, **entry)
            check_spawn(config)
            check_remote_url(config)
        except (ValueError, SpawnDenied) as exc:
            return CommandResult(success=False, output_message=f"{exc}\nUso: {USAGE}")
        persist_server(session.home, name, entry)
        await client.add_server(config)
        session.refresh_mcp()
        state = client.servers[name]
        notes = [f"{name}: adicionado ({config.transport})"]
        if any("${" not in v for v in config.headers.values()):
            notes.append("! header com valor literal gravado em ~/.orion (0600); prefira ${VARIAVEL}.")
        if state.status == "error":
            return CommandResult(success=False, output_message="\n".join([*notes, state.error]))
        return CommandResult(success=True, output_message="\n".join(notes))

    async def _remove(self, client: Any, session: Any, name: str) -> CommandResult:
        if client.servers[name].config.bundled:
            return CommandResult(
                success=False,
                output_message=f"{name} é do starter pack: use '/mcp disable {name}'.",
            )
        persist_server(session.home, name, None)
        await client.remove_server(name)
        revoked = FileTokenStorage(session.home, name).revoke()
        session.refresh_mcp()
        extra = " (tokens OAuth apagados)" if revoked else ""
        return CommandResult(success=True, output_message=f"{name}: removido{extra}")

    async def _auth(self, client: Any, session: Any, name: str) -> CommandResult:
        if client.servers[name].config.auth != "oauth":
            return CommandResult(
                success=False,
                output_message=f"{name} não usa OAuth (cadastre com '/mcp add ... --oauth').",
            )
        await client.authenticate(name)
        session.refresh_mcp()
        state = client.servers[name]
        if state.status == "connected":
            return CommandResult(success=True, output_message=f"{name}: autenticado e conectado")
        return CommandResult(success=False, output_message=f"{name}: {state.error or state.status}")

    @staticmethod
    def _catalog(client: Any, kind: str, target: str) -> CommandResult:
        lines: list[str] = []
        for name, state in sorted(client.servers.items()):
            if target and name != target:
                continue
            if kind == "resources":
                lines.extend(
                    f"@{r.server_name}:{r.uri}" + (f" — {r.name}" if r.name else "")
                    for r in state.resources
                )
            else:
                for p in state.prompts:
                    args = " ".join(a.name for a in p.arguments)
                    lines.append(f"{p.command_name} {args}".strip())
        return CommandResult(success=True, output_message="\n".join(lines) or f"Nenhum(a) {kind} disponível.")

    @staticmethod
    def _list(client, context: CommandContext) -> CommandResult:  # type: ignore[no-untyped-def]
        table = Table.grid(padding=(0, 2))
        for header in ("Servidor", "Status", "Tools", "Latência", "~Tokens", "Origem"):
            table.add_column(header, style="text_dim" if header != "Servidor" else "text_primary")
        total = 0
        for name, state in sorted(client.servers.items()):
            style = _STATUS_STYLE.get(state.status, "text_dim")
            status = state.status if not state.error else f"{state.status}"
            cfg = state.config
            if state.status == "connected":
                total += cfg.est_tokens
            table.add_row(
                name,
                f"[{style}]{status}[/{style}]",
                str(len(state.tools)) if state.status == "connected" else "-",
                f"{state.latency_ms:.0f} ms" if state.status == "connected" else "-",
                str(cfg.est_tokens) if cfg.est_tokens else "-",
                "starter pack" if cfg.bundled else "usuário",
            )
            if state.error:
                table.add_row("", f"[diff_del]{state.error[:70]}[/diff_del]", "", "", "", "")
        context.console.print(orion_panel(table, brand_title("Servidores MCP")))
        context.console.print(f"[text_dim]Overhead estimado (se carregado por completo): ~{total} tokens[/text_dim]")
        return CommandResult(success=True)
