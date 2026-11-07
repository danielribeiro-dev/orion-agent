"""O.R.I.O.N TUI — Catálogo de Slash Commands."""

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult
from orion.tui.commands.registry import CommandRegistry

__all__ = ["BaseSlashCommand", "CommandContext", "CommandRegistry", "CommandResult"]
