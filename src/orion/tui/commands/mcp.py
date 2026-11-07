"""Comando /mcp — inspeção e gerenciamento dos servidores MCP."""

from __future__ import annotations

import json
from pathlib import Path

from rich.table import Table

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.panels import brand_title, orion_panel

_STATUS_STYLE = {"connected": "diff_add", "error": "diff_del", "connecting": "accent_cyan"}
USAGE = "/mcp [list | enable <srv> | disable <srv> | ping <srv> | tools <srv>]"


def persist_enabled(home: Path, name: str, enabled: bool) -> None:
    """Merge ``{"servers": {name: {"enabled": ...}}}`` into ~/.orion/mcp_servers.json."""
    path = home / "mcp_servers.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        data = {}
    key = "mcpServers" if "mcpServers" in data and "servers" not in data else "servers"
    data.setdefault(key, {}).setdefault(name, {})["enabled"] = enabled
    home.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


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
        if action not in {"enable", "disable", "ping", "tools"} or not target:
            return CommandResult(success=False, output_message=f"Uso: {USAGE}")
        if target not in client.servers:
            known = ", ".join(sorted(client.servers)) or "nenhum"
            return CommandResult(
                success=False, output_message=f"Servidor '{target}' desconhecido. Disponíveis: {known}"
            )
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
