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
import os
import sys
import termios
import tty
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, TypeVar

from prompt_toolkit import PromptSession
from prompt_toolkit.filters import has_completions, is_done, to_filter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import ConditionalContainer, VerticalAlign, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.menus import (
    CompletionsMenu,
    CompletionsMenuControl,
    MultiColumnCompletionsMenu,
)
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.text import Text

from orion.core.event_bus import EventBus
from orion.core.events import TurnCancelledEvent
from orion.tui.completer import OrionCompleter, SlashCommandInfo
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
        dynamic_commands: Callable[[], list[SlashCommandInfo]] | None = None,
        mcp_resources: Callable[[], list[tuple[str, str]]] | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd()
        self.event_bus = event_bus
        self.console = console or get_console()
        self.status_bar = status_bar or SessionStatusBar.from_environment()
        self.renderer: Any = None  # StreamRenderer da sessão (linha de digitação durante o turno)
        self.pending: list[str] = []  # pedidos digitados durante o turno, na fila (V-11)
        self.prefill = ""  # texto incompleto digitado durante o turno

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
        self.completer = OrionCompleter(
            workspace_root=self.workspace_root,
            dynamic_commands=dynamic_commands,
            mcp_resources=mcp_resources,
        )

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
            bottom_toolbar=None,  # status line própria abaixo (não depende de CPR, ADR-040)
            style=self.style,
            multiline=False,
            refresh_interval=1.0,  # a toolbar mostra tasks em segundo plano concluídas
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
        root = self.session.layout.container
        children = root.children  # type: ignore[attr-defined]
        children.insert(0, comp_window)
        # Com CPR o prompt_toolkit reserva a altura até o fim da tela; quando o menu fecha, o espaço
        # que ele ocupava sobra. Alinhado ao fundo, o prompt e a status line não sobem deixando
        # linhas vazias abaixo (V-16). Revisar na Sprint 2 da v0.5.1, junto com o fim do dock.
        root.align = VerticalAlign.BOTTOM  # type: ignore[attr-defined]

        # Réguas dinâmicas (estilo Claude Code): fazem parte do HSplit, logo sobem e descem com a
        # altura do input (multilinha/quebra de linha). `main_input` fica entre as duas.
        children.insert(1, self._make_rule())  # acima do input
        children.insert(3, self._make_rule())  # abaixo do input
        # Status line: a barra inferior do PromptSession só aparece quando o terminal responde ao
        # pedido de posição do cursor (filtro renderer_height_is_known). Esta janela não depende
        # disso (V-06) e ocupa o mesmo lugar, sob a régua de baixo.
        children.append(
            ConditionalContainer(
                Window(
                    FormattedTextControl(self.get_bottom_toolbar),
                    height=1,
                    dont_extend_height=True,
                    style="class:bottom-toolbar",
                ),
                filter=~is_done,
            )
        )
        # Sem CPR o prompt_toolkit imprimiria um aviso sobre o menu (V-05): o ORION funciona igual.
        self.session.app.renderer.cpr_not_supported_callback = None

        # Enter sem texto: apaga o bloco régua/❯/régua em vez de empilhá-lo no scrollback. Com texto,
        # o bloco permanece, delimitando o pedido e a resposta.
        buffer = self.session.default_buffer
        original_accept = buffer.accept_handler

        def accept(buff: Any) -> bool:
            self.session.app.erase_when_done = not buff.text.strip()
            return original_accept(buff) if original_accept is not None else False

        buffer.accept_handler = accept

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
        """Lê input do usuário de forma síncrona com captura de Ctrl+C.

        Pedidos enfileirados durante o turno anterior saem primeiro, sem abrir o prompt; o texto
        incompleto daquele turno volta já digitado (V-11).
        """
        if self.pending:
            text = self.pending.pop(0)
            self.echo_submitted(text)
            return text
        default, self.prefill = self.prefill, ""
        try:
            return self.session.prompt(message=message, default=default)
        except KeyboardInterrupt:
            if raise_on_interrupt:
                raise
            self.console.print("\n[dim]Prompt cancelado (Ctrl+C).[/dim]")
            return ""

    def echo_submitted(self, text: str) -> None:
        """Desenha no histórico o mesmo bloco régua/❯/régua de um envio pelo prompt."""
        width = self.console.width
        rule = Text("─" * width, style=ORION_COLORS["text_primary"])
        line = Text("❯ ", style=f"bold {ORION_COLORS['accent_cyan']}")
        line.append(text, style="bold")
        self.console.print(rule)
        self.console.print(line)
        self.console.print(rule)

    async def run_turn(
        self,
        task_coro: Coroutine[Any, Any, T],
        session_id: str = "",
        turn_index: int = 0,
        *,
        typeahead: bool = False,
    ) -> T | None:
        """Executa uma tarefa ou turno do agente capturando KeyboardInterrupt (Ctrl+C).

        Ao receber Ctrl+C ou CancelledError, emite TurnCancelledEvent para o EventBus
        e preserva o processo do CLI ativo para o próximo comando. Com *typeahead*, o que o
        Senhor digita durante o turno aparece na parte viva e Enter enfileira o pedido (V-11).
        """
        ahead = self._start_typeahead() if typeahead else None
        try:
            return await self._run_cancellable(task_coro, session_id, turn_index)
        finally:
            if ahead is not None:
                self._stop_typeahead(ahead)

    def _start_typeahead(self) -> TypeAhead | None:
        renderer = self.renderer
        if renderer is None or not self.console.is_terminal:
            return None
        ahead = TypeAhead()
        ahead.start()
        if not ahead.active:
            return None
        renderer.set_input_line(ahead.render)
        renderer.on_pause.append(ahead.pause)
        renderer.on_resume.append(ahead.resume)
        return ahead

    def _stop_typeahead(self, ahead: TypeAhead) -> None:
        ahead.stop()
        renderer = self.renderer
        renderer.set_input_line(None)
        with contextlib.suppress(ValueError):
            renderer.on_pause.remove(ahead.pause)
            renderer.on_resume.remove(ahead.resume)
        queued, partial = ahead.take()
        self.pending.extend(queued)
        self.prefill = partial

    async def _run_cancellable(
        self, task_coro: Coroutine[Any, Any, T], session_id: str, turn_index: int
    ) -> T | None:
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


class TypeAhead:
    """Digitação durante o turno (V-11).

    Entre os turnos o prompt_toolkit lê o teclado; durante o turno ninguém lia, e o texto ficava
    invisível até o turno acabar. Aqui o terminal fica em ``cbreak`` (sem eco, Ctrl+C continua
    gerando SIGINT), as teclas viram uma linha na parte viva e Enter enfileira o pedido.
    Modais que pausam o renderer pausam a leitura (o teclado volta para eles).
    """

    def __init__(self, fd: int | None = None) -> None:
        if fd is None:
            try:
                fd = sys.stdin.fileno()
            except (OSError, ValueError):
                fd = -1
        self.fd = fd
        self.buffer = ""
        self.queue: list[str] = []
        self.active = False
        self._paused = False
        self._escape = 0  # 0 normal, 1 viu ESC, 2 dentro de CSI, 3 dentro de SS3
        self._saved: list[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── Teclas ──
    def feed(self, data: str) -> None:
        for ch in data:
            if self._escape == 1:
                self._escape = 2 if ch == "[" else 3 if ch == "O" else 0
                continue
            if self._escape == 2:
                if "@" <= ch <= "~":
                    self._escape = 0
                continue
            if self._escape == 3:
                self._escape = 0
                continue
            if ch == "\x1b":
                self._escape = 1
            elif ch in "\r\n":
                if self.buffer.strip():
                    self.queue.append(self.buffer.strip())
                self.buffer = ""
            elif ch in "\x7f\x08":
                self.buffer = self.buffer[:-1]
            elif ch.isprintable():
                self.buffer += ch

    def render(self) -> Text | None:
        if not self.buffer and not self.queue:
            return None
        line = Text("❯ ", style=f"bold {ORION_COLORS['accent_cyan']}")
        line.append(self.buffer, style="bold")
        if self.queue:
            line.append(f"   · {len(self.queue)} na fila", style=ORION_COLORS["text_dim"])
        return line

    def take(self) -> tuple[list[str], str]:
        queued, partial = self.queue, self.buffer
        self.queue, self.buffer = [], ""
        return queued, partial

    # ── Terminal ──
    def start(self) -> None:
        try:
            if self.fd < 0 or not os.isatty(self.fd):
                return
            self._loop = asyncio.get_running_loop()
            self._saved = termios.tcgetattr(self.fd)
        except (OSError, RuntimeError, termios.error):
            return
        self.active = True
        self._attach()

    def _attach(self) -> None:
        assert self._loop is not None
        with contextlib.suppress(OSError, termios.error):
            tty.setcbreak(self.fd, termios.TCSANOW)
        self._loop.add_reader(self.fd, self._on_readable)

    def _detach(self) -> None:
        if self._loop is not None:
            with contextlib.suppress(Exception):
                self._loop.remove_reader(self.fd)
        if self._saved is not None:
            with contextlib.suppress(OSError, termios.error):
                termios.tcsetattr(self.fd, termios.TCSADRAIN, self._saved)

    def _on_readable(self) -> None:
        try:
            data = os.read(self.fd, 1024)
        except OSError:
            return
        self.feed(data.decode("utf-8", "ignore"))

    def pause(self) -> None:
        if self.active and not self._paused:
            self._paused = True
            self._detach()

    def resume(self) -> None:
        if self.active and self._paused:
            self._paused = False
            self._attach()

    def stop(self) -> None:
        if self.active:
            if not self._paused:
                self._detach()
            self.active = False
            self._paused = False
