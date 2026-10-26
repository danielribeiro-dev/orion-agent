"""
O.R.I.O.N TUI — Interactive Prompt Engine.

High-performance developer input engine powered by prompt_toolkit:
- Persistent command history (~/.orion/history)
- Floating auto-completion for Slash Commands (/) and Files (@)
- Multiline support (Alt+Enter) and Deep Cosmos design system styling
- Dynamic Rich bottom status toolbar with USD/BRL metrics
- Graceful signal handling (Ctrl+C emits TurnCancelledEvent without terminating CLI)
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from rich.console import Console

from orion.core.event_bus import EventBus
from orion.core.events import TurnCancelledEvent
from orion.tui.completer import OrionCompleter
from orion.tui.console import get_console
from orion.tui.keybindings import create_key_bindings
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import ORION_COLORS

T = TypeVar("T")


def get_prompt_style() -> Style:
    """Gera a tabela de estilos do prompt_toolkit alinhada com a paleta Deep Cosmos."""
    return Style.from_dict(
        {
            "prompt.symbol": f"{ORION_COLORS['accent_cyan']} bold",
            "prompt.dim": f"{ORION_COLORS['text_dim']}",
            "prompt.identity": f"{ORION_COLORS['text_primary']} bold",
            # Barra de status inferior
            "bottom-toolbar": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['text_primary']}",
            "bottom-toolbar.cyan": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['accent_cyan']} bold",
            "bottom-toolbar.blue": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['accent_blue']}",
            "bottom-toolbar.dim": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['text_dim']}",
            "bottom-toolbar.cost": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['text_primary']} bold",
            "bottom-toolbar.ok": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['status_ok']} bold",
            "bottom-toolbar.offline": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['status_offline']} bold",
            "bottom-toolbar.pep": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['pep_warn']} bold",
            # Menu flutuante de autocompletar
            "completion-menu": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['text_primary']}",
            "completion-menu.completion": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['text_primary']}",
            "completion-menu.completion.current": f"bg:{ORION_COLORS['border_subtle']} {ORION_COLORS['accent_cyan']} bold",
            "completion-menu.meta": f"bg:{ORION_COLORS['surface_panel']} {ORION_COLORS['text_dim']}",
            "completion-menu.meta.completion.current": f"bg:{ORION_COLORS['border_subtle']} {ORION_COLORS['accent_blue']}",
            "scrollbar.background": f"bg:{ORION_COLORS['bg_canvas']}",
            "scrollbar.button": f"bg:{ORION_COLORS['border_subtle']}",
        }
    )


class InteractivePrompt:
    """Motor de entrada interativa do desenvolvedor com prompt_toolkit."""

    def __init__(
        self,
        workspace_root: Path | str | None = None,
        history_path: Path | str | None = None,
        status_bar: SessionStatusBar | None = None,
        event_bus: EventBus | None = None,
        console: Console | None = None,
        custom_key_bindings: KeyBindings | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self.event_bus = event_bus
        self.console = console or get_console()
        self.status_bar = status_bar or SessionStatusBar.from_environment()

        # 1. Configuração de histórico persistente
        self.history_path = (
            Path(history_path).resolve()
            if history_path
            else Path.home() / ".orion" / "history"
        )
        self.history: History
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            self.history = FileHistory(str(self.history_path))
        except Exception:
            # Fallback seguro para ambientes de teste ou sem permissão de escrita
            self.history = InMemoryHistory()

        # 2. Autocompletador unificado
        self.completer = OrionCompleter(workspace_root=self.workspace_root)

        # 3. Atalhos de teclado
        self.key_bindings = custom_key_bindings or create_key_bindings()

        # 4. Estilos do Design System
        self.style = get_prompt_style()

        # 5. Instanciação da PromptSession
        self.session: PromptSession[str] = PromptSession(
            message=self.get_prompt_prefix,
            completer=self.completer,
            complete_while_typing=True,
            history=self.history,
            key_bindings=self.key_bindings,
            bottom_toolbar=self.get_bottom_toolbar,
            style=self.style,
            multiline=False,
        )

    def get_prompt_prefix(self) -> FormattedText:
        """Gera o indicador visual do prompt oficial do ORION."""
        return FormattedText(
            [
                ("class:prompt.symbol", "✦ orion "),
                ("class:prompt.dim", "› "),
            ]
        )

    def get_bottom_toolbar(self) -> FormattedText:
        """Gera a barra de status inferior integrada ao layout do prompt_toolkit."""
        cost_str = (
            f"{self.status_bar.format_cost_usd()} (~R$ {self.status_bar.format_cost_brl()})"
        )
        status_dot_str = "Ready ●" if self.status_bar.is_online else "Offline ●"
        status_dot_class = (
            "class:bottom-toolbar.ok"
            if self.status_bar.is_online
            else "class:bottom-toolbar.offline"
        )

        return FormattedText(
            [
                ("class:bottom-toolbar.cyan", f" [{self.status_bar.model_name}] "),
                (
                    "class:bottom-toolbar.blue",
                    f"[Thinking: {self.status_bar.reasoning_effort.value}] ",
                ),
                ("class:bottom-toolbar.pep", f"[PEP: Level {self.status_bar.pep_level}] "),
                ("class:bottom-toolbar.dim", "│ "),
                (
                    "class:bottom-toolbar.dim",
                    f"Tokens: {self.status_bar.session_tokens_in:,}/{self.status_bar.session_tokens_out:,} ",
                ),
                ("class:bottom-toolbar.dim", "│ "),
                ("class:bottom-toolbar.cost", f"{cost_str} "),
                ("class:bottom-toolbar.dim", "│ "),
                (status_dot_class, f"{status_dot_str} "),
            ]
        )

    async def prompt_async(
        self,
        message: Any = None,
        raise_on_interrupt: bool = False,
    ) -> str:
        """Lê input do usuário de forma assíncrona com captura de Ctrl+C."""
        try:
            return await self.session.prompt_async(message=message)
        except KeyboardInterrupt:
            if raise_on_interrupt:
                raise
            self.console.print("\n[dim]Prompt cancelado (Ctrl+C).[/dim]")
            return ""

    def prompt(
        self,
        message: Any = None,
        raise_on_interrupt: bool = False,
    ) -> str:
        """Lê input do usuário de forma síncrona com captura de Ctrl+C."""
        try:
            return self.session.prompt(message=message)
        except KeyboardInterrupt:
            if raise_on_interrupt:
                raise
            self.console.print("\n[dim]Prompt cancelado (Ctrl+C).[/dim]")
            return ""

    async def run_turn(
        self,
        task_coro: Coroutine[Any, Any, T],
        session_id: str = "",
        turn_index: int = 0,
    ) -> T | None:
        """Executa uma tarefa ou turno do agente capturando KeyboardInterrupt (Ctrl+C).

        Ao receber Ctrl+C ou CancelledError, emite TurnCancelledEvent para o EventBus
        e preserva o processo do CLI ativo para o próximo comando.
        """
        try:
            return await task_coro
        except (KeyboardInterrupt, asyncio.CancelledError) as exc:
            event = TurnCancelledEvent(
                session_id=session_id,
                turn_index=turn_index,
                reason=f"Turn interrupted by user (Ctrl+C): {exc}" if str(exc) else "Turn interrupted by user (Ctrl+C)",
            )
            if self.event_bus is not None:
                with contextlib.suppress(Exception):
                    await self.event_bus.publish(event)
            self.console.print(
                "\n[bold yellow]⚠ Turno interrompido pelo desenvolvedor (Ctrl+C). Sessão e memórias preservadas.[/bold yellow]"
            )
            return None
