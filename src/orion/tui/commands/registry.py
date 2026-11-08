"""
O.R.I.O.N TUI — Command Registry.

Descobre as subclasses de BaseSlashCommand dos módulos de categoria e despacha
a linha digitada, validando argumentos obrigatórios.
"""

from __future__ import annotations

import importlib

from orion.tui.commands.base import BaseSlashCommand, CommandContext, CommandResult

_MODULES = ("cognitive", "memory", "context", "operation", "mcp", "session", "extend")


def _concrete_subclasses(root: type[BaseSlashCommand]) -> list[type[BaseSlashCommand]]:
    found: list[type[BaseSlashCommand]] = []
    for sub in root.__subclasses__():
        found.extend(_concrete_subclasses(sub))
        if getattr(sub, "name", ""):
            found.append(sub)
    return found


class CommandRegistry:
    """Registro central dos slash commands."""

    def __init__(self) -> None:
        self._commands: dict[str, BaseSlashCommand] = {}

    @classmethod
    def discover(cls) -> CommandRegistry:
        """Importa os módulos de categoria e registra todos os comandos."""
        for module in _MODULES:
            importlib.import_module(f"orion.tui.commands.{module}")
        registry = cls()
        for command_class in _concrete_subclasses(BaseSlashCommand):  # type: ignore[type-abstract]
            registry.register(command_class())
        return registry

    def register(self, command: BaseSlashCommand) -> None:
        """Registra o comando e seus aliases."""
        self._commands[command.name] = command
        for alias in command.aliases:
            self._commands[alias] = command

    def get(self, name: str) -> BaseSlashCommand | None:
        """Busca um comando pelo nome ou alias."""
        return self._commands.get(name)

    @property
    def names(self) -> list[str]:
        """Nomes canônicos registrados."""
        return sorted({c.name for c in self._commands.values()})

    async def dispatch(self, line: str, context: CommandContext) -> CommandResult:
        """Interpreta `/comando argumentos` e executa."""
        name, _, args = line.strip().partition(" ")
        args = args.strip()
        command = self.get(name)
        if command is None:
            return CommandResult(
                success=False,
                output_message=f"Comando desconhecido: {name}. Use /help para ver o catálogo.",
            )
        if command.requires_args and not args:
            return CommandResult(success=False, output_message=f"Uso: {command.usage}")
        return await command.execute(args, context)
