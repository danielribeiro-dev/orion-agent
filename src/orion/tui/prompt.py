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
from prompt_toolkit.filters import has_completions, is_done, to_filter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import ConditionalContainer, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.menus import (
    CompletionsMenu,
    CompletionsMenuControl,
    MultiColumnCompletionsMenu,
)
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
            # F-07: o texto digitado fica em negrito na cor nativa do terminal. Não fixar cor de fundo
            # nem de texto claro: em terminais de fundo claro o input ficaria invisível.
            "": "bold",
            # Réguas do input: claras (text_primary); border_subtle some em terminais escuros
            "prompt.border": f"{ORION_COLORS['text_primary']}",
            "prompt.symbol": f"{ORION_COLORS['accent_cyan']} bold",
            "prompt.dim": f"{ORION_COLORS['text_dim']}",
            "prompt.identity": f"{ORION_COLORS['text_primary']} bold",
            # Barra de status inferior — sem fundo sólido, sobre o fundo nativo do terminal (noreverse)
            "bottom-toolbar": f"noreverse {ORION_COLORS['text_dim']}",
            "bottom-toolbar.border": f"noreverse {ORION_COLORS['border_subtle']}",
            "bottom-toolbar.cyan": f"noreverse {ORION_COLORS['accent_cyan']} bold",
            "bottom-toolbar.blue": f"noreverse {ORION_COLORS['accent_blue']}",
            "bottom-toolbar.dim": f"noreverse {ORION_COLORS['text_dim']}",
            "bottom-toolbar.cost": f"noreverse {ORION_COLORS['text_primary']} bold",
            "bottom-toolbar.ok": f"noreverse {ORION_COLORS['status_ok']} bold",
            "bottom-toolbar.offline": f"noreverse {ORION_COLORS['status_offline']} bold",
            "bottom-toolbar.pep": f"noreverse {ORION_COLORS['pep_warn']} bold",
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
            reserve_space_for_menu=0,
            history=self.history,
            key_bindings=self.key_bindings,
            bottom_toolbar=self.get_bottom_toolbar,
            style=self.style,
            multiline=False,
        )

        # 6. Reconfiguração do layout: Menu Flutuante acima do prompt, sem túnel rígido
        comp_window = ConditionalContainer(
            Window(
                content=CompletionsMenuControl(),
                height=Dimension(min=1, max=8),
                right_margins=[ScrollbarMargin(display_arrows=True)],
                dont_extend_width=True,
                style="class:completion-menu",
            ),
            filter=has_completions & ~is_done,
        )

        # Estrutura HSplit: [comp_window (upward), main_input, ..., bottom_toolbar]
        # Remove linhas horizontais rígidas (top_tunnel / bottom_tunnel eliminados)
        children = self.session.layout.container.children  # type: ignore[attr-defined]
        children.insert(0, comp_window)

        # Réguas dinâmicas (estilo Claude Code): fazem parte do HSplit, logo sobem e descem com a
        # altura do input (multilinha/quebra de linha). `main_input` fica entre as duas.
        children.insert(1, self._make_rule())  # acima do input
        children.insert(3, self._make_rule())  # abaixo do input

        # Com o prompt encostado no rodapé, o HSplit recebe toda a altura disponível e a janela de
        # input a absorveria, deixando linhas vazias entre o texto e a régua de baixo ao apagar
        # linhas. Input sem esticar => as réguas seguem exatamente o texto.
        for window in self.session.layout.find_all_windows():
            if isinstance(window.content, BufferControl) and window.content.buffer is self.session.default_buffer:
                window.dont_extend_height = to_filter(True)

        # Desativa os menus flutuantes inferiores padrão para evitar menus duplicados ou truncados
        try:
            main_content = children[2]
            alt = getattr(main_content, "alternative_content", None)
            if alt and hasattr(alt, "floats"):
                alt.floats = [
                    f
                    for f in alt.floats
                    if not isinstance(
                        f.content, (CompletionsMenu, MultiColumnCompletionsMenu)
                    )
                ]
        except Exception:
            pass

    def get_prompt_prefix(self) -> FormattedText:
        """Gera o cursor minimalista `❯ `; as réguas são Windows do container (ver `__init__`)."""
        return FormattedText([("class:prompt.symbol", "❯ ")])

    def get_bottom_toolbar(self) -> FormattedText:
        """Gera a linha de status inferior sobre o fundo nativo do terminal."""
        import shutil

        try:
            term_cols = shutil.get_terminal_size((80, 24)).columns
        except Exception:
            term_cols = 80

        classes = {
            "mode": "class:bottom-toolbar.blue",
            "dim": "class:bottom-toolbar.dim",
            "sep": "class:bottom-toolbar.border",
            "pep": "class:bottom-toolbar.pep",
            "ok": "class:bottom-toolbar.ok",
            "offline": "class:bottom-toolbar.offline",
        }
        return FormattedText(
            [(classes[role], text) for role, text in self.status_bar.status_segments(term_cols)]
        )

    @staticmethod
    def _make_rule() -> Window:
        """Régua de largura total em `text_primary`, uma linha, que acompanha o redimensionamento."""
        return Window(height=1, char="─", style="class:prompt.border")

    def dock_to_bottom(self, rendered_lines: int = 15) -> None:
        """Empurra o prompt para o rodapé do terminal (aparência de tela cheia).

        Só em TTY: preenche com linhas em branco o espaço entre o banner e o prompt.
        """
        if not self.console.is_terminal:
            return
        import shutil

        rows = shutil.get_terminal_size((80, 24)).lines
        pad = rows - rendered_lines - 4  # prompt + barra de status + folga
        if pad > 0:
            self.console.print("\n" * (pad - 1))

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
                "\n[pep_warn]! Turno interrompido pelo desenvolvedor (Ctrl+C). Sessão e memórias preservadas.[/pep_warn]"
            )
            return None
