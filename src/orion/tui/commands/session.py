"""Comandos de sessão: voltar no tempo (v0.5.0 Sprint 3). ``/resume`` mora em ``resume.py``."""

from __future__ import annotations

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult


class RewindCommand(BaseSlashCommand):
    name = "/rewind"
    description = "Volta a conversa (e os arquivos) para antes de um pedido"
    usage = "/rewind [n] [--conversa]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        parts = args.split()
        files = "--conversa" not in parts
        numbers = [p for p in parts if p.isdigit()]
        if not numbers:
            targets = session.rewind_targets()
            if not targets:
                return CommandResult(success=True, output_message="Nenhum pedido nesta sessão.")
            lines = [f"{t.number:>3}  {t.preview}" for t in targets[-15:]]
            return CommandResult(
                success=True,
                output_message="Pedidos (use /rewind <n>; --conversa preserva os arquivos):\n"
                + "\n".join(lines),
                data=targets,
            )
        try:
            return CommandResult(success=True, output_message=session.rewind(int(numbers[0]), files=files))
        except ValueError as exc:
            return CommandResult(success=False, output_message=str(exc))
