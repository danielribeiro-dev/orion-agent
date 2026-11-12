"""
O.R.I.O.N TUI — Rich Console Singleton.

Fornece a instância compartilhada do Console Rich com o tema oficial Deep Cosmos & Glacial Platinum.
"""

from __future__ import annotations

from typing import Any

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


def silence_cpr_warning(app: Any) -> None:
    """Remove o aviso "terminal doesn't support CPR" de uma aplicação do prompt_toolkit (V-05).

    Sem CPR o ORION funciona igual (a status line não depende disso, ADR-040); o aviso só
    sujaria a TUI. Vale para o prompt, os modais e o ``attach``.
    """
    renderer = getattr(app, "renderer", None)
    if renderer is not None:
        renderer.cpr_not_supported_callback = None


def reset_console() -> None:
    """Reseta a instância singleton do console (útil para testes isolados)."""
    global _CONSOLE
    _CONSOLE = None
