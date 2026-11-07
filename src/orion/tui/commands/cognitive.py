"""Comandos cognitivos: conduzem um turno do agente com uma diretriz."""

from __future__ import annotations

import subprocess

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult

_MAX_DIFF_CHARS = 40_000


class PlanCommand(BaseSlashCommand):
    name = "/plan"
    description = "Planejamento estrito: pesquisa, gera plano e colhe aprovação"
    usage = "/plan <meta>"
    requires_args = True

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.tui.session import AgentMode

        context.session.set_mode(AgentMode.PLAN)
        await context.session.run_turn(
            f"Pesquise o repositório e proponha um plano para: {args}\n"
            "Liste as decisões de design do plano; depois que eu aprovar, registre cada uma com a tool "
            "record_decision."
        )
        return CommandResult(success=True)


class GoalCommand(BaseSlashCommand):
    name = "/goal"
    description = "Execução autônoma prolongada com auto-recuperação"
    usage = "/goal <meta>"
    requires_args = True

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        from orion.tui.session import AgentMode

        context.session.set_mode(AgentMode.AUTO)
        await context.session.run_turn(
            f"Conclua esta meta de ponta a ponta, corrigindo falhas até validá-la: {args}"
        )
        return CommandResult(success=True)


class GrillMeCommand(BaseSlashCommand):
    name = "/grill-me"
    description = "Entrevista socrática para esclarecer requisitos"
    usage = "/grill-me [tema]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        topic = args or "a tarefa atual"
        await context.session.run_turn(
            f"Entreviste-me sobre {topic}: faça uma pergunta investigativa por vez, sem escrever código. "
            "Quando uma decisão for fechada comigo, registre-a com a tool record_decision."
        )
        return CommandResult(success=True)


class ReviewCommand(BaseSlashCommand):
    name = "/review"
    description = "Análise crítica de código, arquitetura e segurança nos diffs"
    usage = "/review"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        try:
            done = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=context.session.workspace,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return CommandResult(success=False, output_message=f"git indisponível: {exc}")
        diff = done.stdout.strip()
        if not diff:
            return CommandResult(success=True, output_message="Nenhuma alteração para revisar.")
        await context.session.run_turn(
            "Revise criticamente este diff (corretude, arquitetura, segurança):\n"
            f"```diff\n{diff[:_MAX_DIFF_CHARS]}\n```"
        )
        return CommandResult(success=True)
