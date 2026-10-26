"""
O.R.I.O.N TUI — Rich Console Singleton.

Fornece a instância compartilhada do Console Rich com o tema oficial Deep Cosmos & Glacial Platinum.
"""

from __future__ import annotations

from rich.console import Console

from orion.tui.theme import get_orion_theme

_CONSOLE: Console | None = None


def get_console(force_terminal: bool | None = None) -> Console:
    """Retorna ou cria o console Rich compartilhado com o tema oficial configurado.

    Se force_terminal for especificado explicitamente, retorna uma nova instância
    configurada para o terminal emulado. Caso contrário, retorna o singleton compartilhado.
    """
    global _CONSOLE
    if force_terminal is not None:
        return Console(theme=get_orion_theme(), force_terminal=force_terminal)
    if _CONSOLE is None:
        _CONSOLE = Console(theme=get_orion_theme())
    return _CONSOLE


def reset_console() -> None:
    """Reseta a instância singleton do console (útil para testes isolados)."""
    global _CONSOLE
    _CONSOLE = None
