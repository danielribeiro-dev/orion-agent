"""
O.R.I.O.N TUI — Slash Command Contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel
from rich.console import Console


class CommandResult(BaseModel):
    """Resultado de um slash command."""

    success: bool
    output_message: str = ""
    data: Any = None


@dataclass
class CommandContext:
    """Dependências disponíveis para os comandos."""

    session: Any
    console: Console
    clear_screen: Callable[[], None]


class BaseSlashCommand(ABC):
    """Contrato de todo comando: metadados e execução assíncrona."""

    name: ClassVar[str]
    description: ClassVar[str]
    usage: ClassVar[str] = ""
    aliases: ClassVar[tuple[str, ...]] = ()
    requires_args: ClassVar[bool] = False

    @abstractmethod
    async def execute(self, args: str, context: CommandContext) -> CommandResult:
        """Executa o comando e devolve o resultado."""
