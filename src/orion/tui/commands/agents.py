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
        table = Table.grid(padding=(0, 2), expand=True)
        for header in ("Agente", "Origem", "Tier", "Tools"):
            table.add_column(header, no_wrap=True, overflow="fold")
        table.add_column("Descrição", no_wrap=True, overflow="ellipsis", ratio=1, min_width=12)
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


# ── /tasks ──────────────────────────────────────────────────────────────────

TASKS_USAGE = "/tasks [list | get <id> | stop <id|shell_N|all>]"
_STATUS_STYLE = {
    "running": "accent_cyan",
    "done": "diff_add",
    "failed": "diff_del",
    "cancelled": "text_dim",
    "interrupted": "pep_warn",
}


class TasksCommand(BaseSlashCommand):
    name = "/tasks"
    description = "Tasks em segundo plano e shells: listar, ver resultado e cancelar"
    usage = TASKS_USAGE

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        action, _, rest = args.strip().partition(" ")
        session = context.session
        if action in ("", "list"):
            return self._list(session, context)
        if action == "get":
            return self._get(session, rest.strip(), context)
        if action == "stop":
            return await self._stop(session, rest.strip())
        return CommandResult(success=False, output_message=f"Uso: {TASKS_USAGE}")

    def _list(self, session: Any, context: CommandContext) -> CommandResult:
        records = session.tasks.list()
        shells = session.shells.list()
        if not records and not shells:
            return CommandResult(success=True, output_message="Nenhuma task ou shell em segundo plano.")
        table = Table.grid(padding=(0, 2), expand=True)
        for header in ("Id", "Estado", "Agente / comando", "USD"):
            table.add_column(header, no_wrap=True, overflow="fold", min_width=len(header) + 6)
        table.add_column("Meta / log", no_wrap=True, overflow="ellipsis", ratio=1, min_width=12)
        for rec in records:
            style = _STATUS_STYLE.get(rec.status.value, "text_primary")
            table.add_row(
                rec.task_id,
                f"[{style}]{rec.status.value}[/]",
                rec.agent,
                f"${rec.cost_usd:.4f}",
                rec.goal[:60],
            )
        for shell in shells:
            state = "running" if shell.running else f"exit {shell.exit_code}"
            table.add_row(shell.shell_id, state, shell.command[:30], "-", str(shell.log_path))
        context.console.print(orion_panel(table, brand_title("Tasks em segundo plano")))
        if session.loops.list():
            context.console.print("[text_dim]Há loops ativos: veja /loop list.[/]")
        return CommandResult(success=True)

    def _get(self, session: Any, task_id: str, context: CommandContext) -> CommandResult:
        rec = session.tasks.get(task_id)
        if rec is None:
            return CommandResult(success=False, output_message=f"Task desconhecida: {task_id}")
        lines = [
            f"{rec.task_id} · {rec.status.value} · {rec.agent} ({rec.agent_id}) · ${rec.cost_usd:.4f}",
            f"meta: {rec.goal}",
        ]
        if rec.model_used:
            lines.append(f"modelo: {rec.model_used}")
        if rec.summary:
            lines.append(f"\n{rec.summary}")
        if rec.ref:
            lines.append(f"\nresultado completo: {rec.ref}")
        if rec.error and rec.status.value != "done":
            lines.append(f"erro: {rec.error}")
        if rec.resumable:
            lines.append("retomável: peça ao agente principal para continuar esta task.")
        context.console.print("\n".join(lines))
        return CommandResult(success=True)

    async def _stop(self, session: Any, target: str) -> CommandResult:
        import asyncio

        if not target:
            return CommandResult(success=False, output_message=f"Uso: {TASKS_USAGE}")
        loop = asyncio.get_running_loop()
        if target == "all":
            stopped = await loop.run_in_executor(None, session.tasks.stop_all)
            killed = 0
            for shell in session.shells.list():
                if shell.running and session.shells.kill(shell.shell_id):
                    killed += 1
            return CommandResult(
                success=True, output_message=f"{stopped} task(s) cancelada(s), {killed} shell(s) encerrado(s)."
            )
        if target.startswith("shell_"):
            if session.shells.get(target) is None:
                return CommandResult(success=False, output_message=f"Shell desconhecido: {target}")
            done = session.shells.kill(target)
            return CommandResult(success=True, output_message=f"{target} " + ("encerrado." if done else "já havia terminado."))
        if await loop.run_in_executor(None, session.tasks.stop, target):
            return CommandResult(success=True, output_message=f"{target} cancelada.")
        return CommandResult(success=False, output_message=f"{target} não é uma task em execução desta sessão.")


# ── /loop ───────────────────────────────────────────────────────────────────

LOOP_USAGE = (
    "/loop [intervalo] [--agent nome] [--max N] [--ttl 3d] [--budget 0.05] [--turns N] <o que verificar> "
    "| /loop list | /loop stop <id|all>"
)


class LoopCommand(BaseSlashCommand):
    name = "/loop"
    description = "Verificação recorrente em segundo plano (triagem antes de gastar tokens)"
    usage = LOOP_USAGE

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.agents.loops import describe

        session = context.session
        action, _, rest = args.strip().partition(" ")
        if action in ("", "list"):
            states = session.loops.list()
            if not states:
                return CommandResult(success=True, output_message="Nenhum loop nesta sessão.")
            for state in states:
                context.console.print(describe(state))
            return CommandResult(success=True)
        if action == "stop":
            target = rest.strip()
            if target == "all":
                return CommandResult(success=True, output_message=f"{session.loops.stop_all()} loop(s) encerrado(s).")
            if session.loops.stop(target):
                return CommandResult(success=True, output_message=f"{target} encerrado.")
            return CommandResult(success=False, output_message=f"{target} não é um loop ativo.")
        try:
            kwargs, goal = self._parse(args)
            state = session.loops.start(goal, **kwargs)
        except ValueError as exc:
            return CommandResult(success=False, output_message=f"{exc}\nUso: {LOOP_USAGE}")
        every = "intervalo dinâmico" if state.interval_s is None else f"a cada {state.interval_s:g}s"
        return CommandResult(
            success=True,
            output_message=(
                f"{state.loop_id} iniciado ({every}; até {state.max_fires} disparos de ${state.budget_usd:g}; "
                "expira em 7 dias por padrão). Só acorda o modelo se algo mudou."
            ),
        )

    @staticmethod
    def _parse(args: str) -> tuple[dict[str, Any], str]:
        from orion.agents.loops import parse_interval

        tokens = args.split()
        kwargs: dict[str, Any] = {}
        goal: list[str] = []
        index = 0
        if tokens and (interval := parse_interval(tokens[0])) is not None:
            kwargs["interval_s"] = interval
            index = 1
        flags = {"--agent": ("agent", str), "--max": ("max_fires", int), "--turns": ("max_turns", int),
                 "--budget": ("budget_usd", float), "--ttl": ("ttl_s", None)}
        while index < len(tokens):
            token = tokens[index]
            if token in flags:
                if index + 1 >= len(tokens):
                    raise ValueError(f"{token} precisa de um valor")
                key, cast = flags[token]
                raw = tokens[index + 1]
                if key == "ttl_s":
                    ttl = parse_interval(raw)
                    if ttl is None:
                        raise ValueError("--ttl aceita 30s, 5m, 2h ou 3d")
                    kwargs[key] = ttl
                else:
                    try:
                        kwargs[key] = cast(raw)  # type: ignore[misc]
                    except ValueError as exc:
                        raise ValueError(f"valor inválido para {token}: {raw}") from exc
                index += 2
            else:
                goal.append(token)
                index += 1
        return kwargs, " ".join(goal)
