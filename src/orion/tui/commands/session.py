"""Comandos de sessão: retomar conversas anteriores e voltar no tempo (v0.5.0 Sprint 3)."""

from __future__ import annotations

from orion.sessions import SessionNotFoundError
from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult


def _short(iso: str) -> str:
    return iso[:16].replace("T", " ")


class ResumeCommand(BaseSlashCommand):
    name = "/resume"
    description = "Lista ou retoma sessões anteriores deste workspace"
    usage = "/resume [id]"

    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        session = context.session
        if not args:
            sessions = session.list_sessions()
            if not sessions:
                return CommandResult(success=True, output_message="Nenhuma sessão anterior neste workspace.")
            lines = [
                f"{m.session_id[:8]}  {_short(m.updated_at)}  {m.turns:>3} pedido(s)  {m.preview}"
                for m in sessions[:15]
            ]
            return CommandResult(
                success=True,
                output_message="Sessões (use /resume <id>):\n" + "\n".join(lines),
                data=sessions,
            )
        try:
            return CommandResult(success=True, output_message=session.resume(args))
        except SessionNotFoundError as exc:
            return CommandResult(success=False, output_message=str(exc))


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
