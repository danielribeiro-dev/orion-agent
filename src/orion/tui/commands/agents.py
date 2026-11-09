"""Comando /agents — catálogo e execuções dos subagents (Sprint 6)."""

from __future__ import annotations

from typing import Any

from rich.table import Table

from orion.agents.definitions import AgentDefinition
from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.panels import brand_title, orion_panel

USAGE = "/agents [list | show <nome> | runs | trust]"


def _tools_label(agent: AgentDefinition) -> str:
    if agent.tools is None:
        return "herda do pai"
    return ", ".join(agent.tools) or "(nenhuma)"


class AgentsCommand(BaseSlashCommand):
    name = "/agents"
    description = "Listar subagents, ver detalhes, execuções e confiar nos agentes do projeto"
    usage = USAGE

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        action, _, rest = args.strip().partition(" ")
        session = context.session
        if action in ("", "list"):
            return self._list(session, context)
        if action == "show":
            return self._show(session, rest.strip(), context)
        if action == "runs":
            return self._runs(session, context)
        if action == "trust":
            return self._trust(session)
        return CommandResult(success=False, output_message=f"Uso: {USAGE}")

    # ------------------------------------------------------------------

    def _list(self, session: Any, context: CommandContext) -> CommandResult:
        catalog = session.agent_catalog
        table = Table.grid(padding=(0, 2))
        for header in ("Agente", "Origem", "Tier", "Tools", "Descrição"):
            table.add_column(header, no_wrap=header != "Descrição", overflow="ellipsis")
        for agent in sorted(catalog.agents.values(), key=lambda a: a.name):
            origin = agent.source + ("" if agent.trusted else " (restrito)")
            table.add_row(
                f"[accent_cyan]{agent.name}[/]", origin, agent.model_tier, _tools_label(agent), agent.description
            )
        context.console.print(orion_panel(table, brand_title("Subagents")))
        if catalog.project_needs_trust:
            context.console.print(
                "[pep_warn]! Agentes de projeto sem confiança: rodam restritos (somente leitura). "
                "Revise .orion/agents e use /agents trust.[/]"
            )
        for notice in catalog.notices:
            context.console.print(f"[text_dim]· {notice}[/]")
        limits = session.agent_limits()
        context.console.print(
            f"[text_dim]tetos: {limits.max_concurrent} simultâneos · profundidade {limits.max_depth} · "
            f"${limits.default_budget_usd:.2f}/agente · ${limits.aggregate_budget_usd:.2f}/delegação[/]"
        )
        return CommandResult(success=True)

    def _show(self, session: Any, name: str, context: CommandContext) -> CommandResult:
        agent = session.agent_catalog.get(name)
        if agent is None:
            return CommandResult(success=False, output_message=f"Agente desconhecido: {name}")
        rows = [
            ("Descrição", agent.description),
            ("Origem", agent.source + ("" if agent.trusted else " (restrito: projeto sem confiança)")),
            ("Tools", _tools_label(agent)),
            ("Bloqueadas", ", ".join(agent.disallowed_tools) or "-"),
            ("Tier", agent.model_profile and f"perfil {agent.model_profile}" or agent.model_tier),
            ("Turnos", str(agent.max_turns)),
            ("Orçamento", f"${agent.budget_usd:.2f}" if agent.budget_usd else "padrão"),
            ("Isolamento", agent.isolation),
            ("Arquivo", agent.path or "(embutido)"),
        ]
        table = Table.grid(padding=(0, 2))
        table.add_column(style="text_dim", no_wrap=True)
        table.add_column()
        for key, value in rows:
            table.add_row(key, str(value))
        context.console.print(orion_panel(table, brand_title(agent.name)))
        context.console.print(f"[text_dim]{agent.prompt}[/]")
        return CommandResult(success=True)

    def _runs(self, session: Any, context: CommandContext) -> CommandResult:
        if not session.agent_costs:
            return CommandResult(success=True, output_message="Nenhum subagent executou nesta sessão.")
        table = Table.grid(padding=(0, 2))
        for header in ("Agent id", "Agente", "USD"):
            table.add_column(header, no_wrap=True)
        for agent_id, cost in session.agent_costs.items():
            table.add_row(agent_id, session.agent_names.get(agent_id, "?"), f"${cost:.4f}")
        table.add_row("[accent_cyan]Total[/]", "", f"[accent_cyan]${session.agent_usage.cost_usd:.4f}[/]")
        context.console.print(orion_panel(table, brand_title("Execuções de subagents")))
        return CommandResult(success=True)

    def _trust(self, session: Any) -> CommandResult:
        if not session.agent_catalog.project_needs_trust:
            return CommandResult(success=True, output_message="Nada a confiar: sem agentes de projeto pendentes.")
        if session.trust_project_agents():
            return CommandResult(success=True, output_message="Agentes do projeto confiados (hash gravado).")
        return CommandResult(success=False, output_message="Não foi possível gravar a confiança.")
