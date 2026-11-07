"""Comandos de contexto e ramificações."""

from __future__ import annotations

from orion.timeline.branch_manager import BranchError
from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.panels import render_context


class CompactCommand(BaseSlashCommand):
    name = "/compact"
    description = "Compacta a janela de tokens preservando a cauda vital"
    usage = "/compact [foco]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        if not context.session.history:
            return CommandResult(success=True, output_message="Conversa vazia, nada a compactar.")
        return CommandResult(success=True, output_message=context.session.compact(args or None))


class ContextCommand(BaseSlashCommand):
    name = "/context"
    description = "Composição de tokens da janela de contexto ativa"
    usage = "/context"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        width = min(context.console.width - 8, 96)
        parts = session.context_breakdown()
        context.console.print(render_context(parts, session.context_window(), bar_width=width))
        return CommandResult(success=True, data=parts)


class BranchCommand(BaseSlashCommand):
    name = "/branch"
    description = "Abre uma ramificação de contexto isolada"
    usage = "/branch <nome>"
    requires_args = True

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        try:
            context.session.create_branch(args)
        except BranchError as exc:
            return CommandResult(success=False, output_message=str(exc))
        return CommandResult(success=True, output_message=f"Branch de contexto ativa: {args}")


class MergeCommand(BaseSlashCommand):
    name = "/merge"
    description = "Sintetiza a branch ativa em checkpoint na Main Timeline"
    usage = "/merge [resultado]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        try:
            checkpoint = await context.session.merge_branch(args or "Merged successfully")
        except BranchError as exc:
            return CommandResult(success=False, output_message=str(exc))
        return CommandResult(success=True, output_message=checkpoint)
