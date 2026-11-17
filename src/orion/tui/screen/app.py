"""Aplicação em tela cheia do ORION (ADR-043, v0.5.2 Sprint 2).

Uma única ``Application`` do prompt_toolkit na tela alternativa, num só loop asyncio:

    transcrição (células, rola, auto-follow)
    menu de comandos / modal (quando abertos)
    fila de pedidos
    linha de atividade (spinner, aviso de travamento)
    régua · ❯ input (sempre ativo) · régua
    status line

O turno roda como task; o input nunca some. Enter durante o turno enfileira; Esc ou Ctrl+C
interrompem; ↑ com o input vazio traz a fila de volta para edição.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.filters import Condition, has_completions
from prompt_toolkit.formatted_text import ANSI, StyleAndTextTuples, to_formatted_text
from prompt_toolkit.history import FileHistory, History, InMemoryHistory
from prompt_toolkit.key_binding import ConditionalKeyBindings, KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl, UIContent, UIControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.processors import (
    BeforeInput,
    ConditionalProcessor,
    PasswordProcessor,
    Processor,
    Transformation,
    TransformationInput,
)
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType
from rich.console import RenderableType
from rich.padding import Padding
from rich.text import Text

from orion.tui.banner import BannerRenderer
from orion.tui.completer import OrionCompleter
from orion.tui.keybindings import create_key_bindings
from orion.tui.menu import MENU_MAX_HEIGHT, OrionCompletionsMenuControl, menu_footer
from orion.tui.modal import render_ansi
from orion.tui.prompt import get_prompt_style
from orion.tui.screen import host as host_registry
from orion.tui.screen import terminal
from orion.tui.screen.console import TranscriptConsole
from orion.tui.screen.renderer import ScreenRenderer
from orion.tui.screen.transcript import Cell, Line, Transcript, plain, rasterize
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import ORION_COLORS

EXIT_WORDS = ("/exit", "/quit", "exit", "quit", ":q")
SPINNER_INTERVAL = 0.08
"""12,5 quadros/s enquanto algo se move (ADR-045)."""
IDLE_INTERVAL = 0.5
"""Sem movimento: só confere status line e notificações; nenhum quadro se nada mudou."""
MAX_FPS = 30
DOUBLE_CTRL_C = 2.0
STARTED_AFTER = 10.0
UNFOCUSED_INTERVAL = 0.5
"""Sem foco o spinner anda a 2 quadros/s (ADR-045)."""
BELL_AFTER = 10.0
"""Turno mais longo que isso, terminado com a janela sem foco, toca o sino (N-23)."""


@dataclass
class ScreenParts:
    """Peças criadas antes da sessão (ela recebe o console e o renderer)."""

    transcript: Transcript
    console: TranscriptConsole
    renderer: ScreenRenderer


def build_parts(status_bar: SessionStatusBar) -> ScreenParts:
    transcript = Transcript()
    console = TranscriptConsole(transcript)
    renderer = ScreenRenderer(
        console, transcript, effort=lambda: status_bar.reasoning_effort.value.lower()
    )
    return ScreenParts(transcript, console, renderer)


class _Banner:
    """Banner que se redesenha na largura atual (reflow)."""

    def __init__(self, status_bar: SessionStatusBar) -> None:
        self.status_bar = status_bar

    def __rich_console__(self, console: Any, options: Any) -> Any:
        yield Text("")
        yield BannerRenderer(status_bar=self.status_bar).render(terminal_width=options.max_width)


def user_cell(text: str) -> Cell:
    """Pedido do Senhor: ``❯ texto`` com fundo ``sel``, sem réguas (N-05)."""
    line = Text(no_wrap=False)
    line.append("❯ ", style=f"bold {ORION_COLORS['accent_cyan']}")
    line.append(text, style=f"bold {ORION_COLORS['text_primary']}")
    return Cell("user", [Text(""), Padding(line, (0, 1, 0, 0), style=f"on {ORION_COLORS['sel']}", expand=True)])


class _Placeholder(Processor):
    def __init__(self, text: Callable[[], str]) -> None:
        self.text = text

    def apply_transformation(self, ti: TransformationInput) -> Transformation:
        if ti.document.text == "" and ti.lineno == 0:
            hint = self.text()
            if hint:
                return Transformation(ti.fragments + [("class:prompt.placeholder", hint)])
        return Transformation(ti.fragments)


class TranscriptControl(UIControl):
    """Desenha só a janela visível da transcrição; rola e abre blocos com o mouse."""

    def __init__(self, screen: ScreenApp) -> None:
        self.screen = screen
        self.owners: list[Cell | None] = []

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        lines, owners = self.screen.visible_lines(width, height)
        self.owners = owners

        def get_line(i: int) -> StyleAndTextTuples:
            return lines[i] if i < len(lines) else []

        return UIContent(get_line=get_line, line_count=len(lines), show_cursor=False)

    def mouse_handler(self, mouse_event: MouseEvent) -> Any:
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            self.screen.scroll(3)
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            self.screen.scroll(-3)
            return None
        if mouse_event.event_type == MouseEventType.MOUSE_UP:
            y = mouse_event.position.y
            if 0 <= y < len(self.owners) and (cell := self.owners[y]) is not None and cell.collapsible:
                self.screen.transcript.toggle(cell)
                return None
        return NotImplemented


class ScreenApp:
    """Conduz a sessão na tela cheia: input, turnos, fila, rolagem e modais."""

    def __init__(
        self,
        session: Any,
        parts: ScreenParts,
        status_bar: SessionStatusBar,
        *,
        registry: Any = None,
        history: History | None = None,
        home: Path | None = None,
        mouse: bool | None = None,
        notice: str = "",
    ) -> None:
        self.session = session
        self.transcript = parts.transcript
        self.console = parts.console
        self.renderer = parts.renderer
        self.status_bar = status_bar
        self.home = home or Path.home() / ".orion"
        self.queue: list[str] = []
        self.turn: asyncio.Task[None] | None = None
        self.turns = 0
        self.offset = 0
        self._last_total = 0
        self.unseen = 0
        self.modal: Any = None
        self._modal_done: asyncio.Future[None] | None = None
        self._answer: asyncio.Future[str] | None = None
        self._answer_question = ""
        self._secret = False
        self._last_ctrl_c = 0.0
        self.flash: tuple[str, float] | None = None
        self.relaunch = False
        self._ticker: asyncio.Task[None] | None = None
        self._started_at = 0.0
        self.mouse = mouse if mouse is not None else os.environ.get("ORION_MOUSE", "1") != "0"

        if registry is None:
            from orion.tui.commands import CommandRegistry

            registry = CommandRegistry.discover()
        self.registry = registry
        from orion.tui.commands import CommandContext

        self.context = CommandContext(session=session, console=self.console, clear_screen=self.clear)
        self.console.on_status = self._on_status
        self.renderer.on_change = self.invalidate
        self.transcript.on_change = self.invalidate
        session.tui = self

        self.buffer = Buffer(
            completer=OrionCompleter(
                workspace_root=getattr(session, "workspace", Path.cwd()),
                dynamic_commands=getattr(session, "dynamic_slash_infos", None),
                mcp_resources=getattr(session, "mcp_resource_choices", None),
            ),
            complete_while_typing=True,
            history=history or self._history(),
            multiline=False,
            accept_handler=self._accept,
            read_only=Condition(lambda: self.modal is not None or (self.full_view and not self.searching)),
        )
        self.app: Application[None] = Application(
            layout=Layout(self._layout(), focused_element=self._input_window),
            key_bindings=self._bindings(),
            style=get_prompt_style(),
            full_screen=True,
            mouse_support=Condition(lambda: self.mouse),
            min_redraw_interval=1 / MAX_FPS,
            erase_when_done=False,
        )
        # Esc sozinho é prefixo dos atalhos Alt: sem isto espera 1 s para valer (interromper
        # precisa ser imediato). Alt+tecla chega numa leitura só, então 0,25 s basta.
        self.app.timeoutlen = 0.25
        self.app.ttimeoutlen = 0.05
        self.exited = False
        self.focused = True
        self.full_view = False  # Ctrl+O: transcrição completa, tudo aberto
        self.searching = False
        self.query = ""
        self.matches: list[int] = []
        self.match_index = -1
        self.dump_requested = False
        self.sync_output = terminal.sync_supported()
        self.progress = terminal.progress_supported()
        self.transcript.add(Cell("banner", [_Banner(status_bar)]))
        if notice:
            self.transcript.add_renderables("notice", Text(notice, style="text_dim"))

    # ── Construção ──────────────────────────────────────────────────

    def _history(self) -> History:
        path = self.home / "history"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return FileHistory(str(path))
        except OSError:
            return InMemoryHistory()

    def _layout(self) -> HSplit:
        def rule() -> Window:
            return Window(height=1, char="─", style="class:prompt.border")

        menu = ConditionalContainer(
            HSplit(
                [
                    Window(
                        content=OrionCompletionsMenuControl(),
                        height=Dimension(min=1, max=MENU_MAX_HEIGHT),
                        dont_extend_width=True,
                        style="class:completion-menu",
                    ),
                    Window(
                        FormattedTextControl(menu_footer),
                        height=1,
                        dont_extend_width=True,
                        style="class:completion-menu.footer",
                    ),
                ]
            ),
            filter=has_completions,
        )
        self._input_window = Window(
            BufferControl(
                self.buffer,
                input_processors=[
                    # A máscara vem antes do prefixo: só o texto digitado vira "*", nunca o "› ".
                    ConditionalProcessor(PasswordProcessor(), Condition(lambda: self._secret)),
                    BeforeInput(self._prompt_symbol),
                    _Placeholder(self._placeholder),
                ],
            ),
            height=Dimension(min=1, max=8),
            wrap_lines=True,
            dont_extend_height=True,
        )
        return HSplit(
            [
                Window(TranscriptControl(self), wrap_lines=False, always_hide_cursor=True, style="nobold"),
                ConditionalContainer(
                    Window(FormattedTextControl(self._modal_fragments), dont_extend_height=True, style="nobold"),
                    filter=Condition(lambda: self.modal is not None),
                ),
                menu,
                Window(
                    FormattedTextControl(self._queue_fragments),
                    dont_extend_height=True,
                    height=self._queue_height,
                    style="nobold",
                ),
                Window(
                    FormattedTextControl(self._activity_fragments),
                    dont_extend_height=True,
                    height=self._activity_height,
                    style="nobold",
                ),
                rule(),
                self._input_window,
                rule(),
                Window(FormattedTextControl(self._status_fragments), height=1, style="class:bottom-toolbar nobold"),
            ]
        )

    def _prompt_symbol(self) -> StyleAndTextTuples:
        if self.searching:
            return [("class:prompt.symbol", "/ ")]
        if self._answer is not None:
            return [("class:prompt.symbol", "› ")]
        return [("class:prompt.symbol", "❯ ")]

    def _placeholder(self) -> str:
        if self.searching:
            return "buscar na transcrição (Enter busca, Esc cancela)"
        if self.full_view:
            return "transcrição · / busca · q volta"
        if self.modal is not None:
            return ""
        if self._answer is not None:
            return self._answer_question
        if self.turn is not None:
            return "Enter enfileira · Esc interrompe"
        return "digite sua instrução…"

    def _bindings(self) -> Any:
        modal_open = Condition(lambda: self.modal is not None)
        base = create_key_bindings(
            on_interrupt=self._on_ctrl_c,
            on_clear=lambda event: self.redraw(),
            on_escape=self._on_escape,
            on_cycle_mode=self.session.cycle_mode,
            on_cycle_effort=self.session.cycle_effort,
            on_toggle_fast=self.session.toggle_fast,
        )
        extra = KeyBindings()

        def _toggle(action: Callable[[], None]) -> Callable[[KeyPressEvent], None]:
            def handler(event: KeyPressEvent) -> None:
                action()
                self.invalidate()

            return handler

        for letter in ("r", "R"):
            extra.add("escape", letter)(_toggle(self.renderer.expand_reasoning))
        for letter in ("e", "E"):
            extra.add("escape", letter)(_toggle(self.renderer.expand_output))
        extra.add("pageup")(lambda event: self.scroll(max(self._height() // 2, 1)))
        extra.add("pagedown")(lambda event: self.scroll(-max(self._height() // 2, 1)))
        extra.add("c-home")(lambda event: self.scroll(10**9))
        extra.add("c-end")(lambda event: self.scroll(-(10**9)))

        @extra.add("up", filter=Condition(lambda: not self.buffer.text and bool(self.queue)))
        def _take_queue(event: KeyPressEvent) -> None:
            self.buffer.text = "\n".join(self.queue) if len(self.queue) > 1 else self.queue[0]
            self.buffer.cursor_position = len(self.buffer.text)
            self.queue.clear()

        terminal.register_focus_keys()

        @extra.add(terminal.FOCUS_IN_KEY)
        def _focus_in(event: KeyPressEvent) -> None:
            self.focused = True

        @extra.add(terminal.FOCUS_OUT_KEY)
        def _focus_out(event: KeyPressEvent) -> None:
            self.focused = False

        @extra.add("c-d", filter=Condition(lambda: not self.buffer.text))
        def _ctrl_d(event: KeyPressEvent) -> None:
            self.exit()

        @extra.add("c-o")
        def _full_view(event: KeyPressEvent) -> None:
            self.toggle_full_view()

        view = KeyBindings()
        view.add("q")(lambda event: self.toggle_full_view())
        view.add("escape", eager=True)(lambda event: self.toggle_full_view())
        view.add("c-o")(lambda event: self.toggle_full_view())

        @view.add("/")
        def _start_search(event: KeyPressEvent) -> None:
            self.searching = True
            self.buffer.reset()
            self.invalidate()

        view.add("n")(lambda event: self.next_match(1))
        view.add("N")(lambda event: self.next_match(-1))
        view.add("[")(lambda event: self.request_dump())
        for key, step in (("j", -1), ("down", -1), ("k", 1), ("up", 1)):
            view.add(key)(lambda event, step=step: self.scroll(step))
        view.add("g")(lambda event: self.scroll(10**9))
        view.add("G")(lambda event: self.scroll(-(10**9)))
        view.add("pageup")(lambda event: self.scroll(max(self._height() // 2, 1)))
        view.add("pagedown")(lambda event: self.scroll(-max(self._height() // 2, 1)))
        view.add("c-c")(lambda event: self.toggle_full_view())

        modal = KeyBindings()

        def dispatch(name: str) -> None:
            controller = self.modal
            if controller is not None and controller.on_key(name):
                self._close_modal()
            self.invalidate()

        for key, name in (
            ("up", "up"),
            ("down", "down"),
            ("tab", "tab"),
            ("s-tab", "s-tab"),
            ("enter", "enter"),
            ("backspace", "backspace"),
            ("c-c", "escape"),
        ):
            modal.add(key)(lambda event, name=name: dispatch(name))
        modal.add("escape", eager=True)(lambda event: dispatch("escape"))
        modal.add(Keys.Any)(lambda event: dispatch(event.data))
        # Com o modal aberto o input fica somente leitura, e isso liga os atalhos "estilo less"
        # do prompt_toolkit (n, N, / e ?), que venceriam o Keys.Any: o modal os declara exatos.
        for letter in ("n", "N", "/", "?"):
            modal.add(letter)(lambda event, letter=letter: dispatch(letter))
        browsing = Condition(lambda: self.full_view and not self.searching)
        return merge_key_bindings(
            [
                ConditionalKeyBindings(merge_key_bindings([base, extra]), filter=~modal_open & ~browsing),
                ConditionalKeyBindings(view, filter=browsing & ~modal_open),
                ConditionalKeyBindings(modal, filter=modal_open),
            ]
        )

    # ── Desenho ─────────────────────────────────────────────────────

    def invalidate(self) -> None:
        with contextlib.suppress(Exception):
            self.app.invalidate()

    def redraw(self) -> None:
        """Ctrl+L: refaz a tela inteira."""
        with contextlib.suppress(Exception):
            self.app.renderer.clear()
        self.invalidate()

    def _width(self) -> int:
        try:
            return self.app.output.get_size().columns
        except Exception:
            return 100

    def _height(self) -> int:
        try:
            return self.app.output.get_size().rows
        except Exception:
            return 30

    def visible_lines(self, width: int, height: int) -> tuple[list[Line], list[Cell | None]]:
        self.console.width = width
        expand = self.full_view
        tail = [] if expand else self.renderer.live_lines(width, max(height - 2, 3))
        _, _, total = self.transcript.window(width, 0, 0, tail, expand)
        if self.offset and total > self._last_total:
            grown = total - self._last_total
            self.offset += grown
            if not self.transcript.toggled:
                self.unseen += grown
        self._last_total = total
        self.offset = max(0, min(self.offset, max(total - height, 0)))
        if self.offset == 0:
            self.unseen = 0
        lines, owners, _ = self.transcript.window(width, height, self.offset, tail, expand)
        return lines, owners

    def scroll(self, lines: int) -> None:
        self.offset = max(self.offset + lines, 0)
        if self.offset == 0:
            self.unseen = 0
        self.invalidate()

    def _activity_lines(self) -> list[Line]:
        width = self._width()
        parts: list[RenderableType] = []
        if self.full_view:
            head = Text(no_wrap=True, overflow="ellipsis")
            head.append("Transcrição", style="accent_cyan")
            if self.query:
                found = f"{self.match_index + 1}/{len(self.matches)}" if self.matches else "nada encontrado"
                head.append(f" · “{self.query}” {found}", style="text_dim")
            head.append("  ·  / busca · n/N próxima · [ despeja no scrollback · q volta", style="faint")
            parts.append(head)
        elif self.offset:
            hint = Text(no_wrap=True)
            hint.append("· rolado para cima", style="faint")
            if self.unseen:
                noun = "linha nova" if self.unseen == 1 else "linhas novas"
                hint.append(f" · {self.unseen} {noun}", style="accent_blue")
            hint.append(" · Ctrl+End volta ao fim", style="faint")
            parts.append(hint)
        parts.extend(self.renderer.activity_renderables())
        if self.flash is not None:
            message, until = self.flash
            if time.monotonic() < until:
                parts.append(Text(message, style="text_dim"))
            else:
                self.flash = None
        return rasterize(parts, width) if parts else []

    def _activity_fragments(self) -> StyleAndTextTuples:
        return _join(self._activity_lines())

    def _activity_height(self) -> Dimension:
        return Dimension.exact(len(self._activity_lines()))

    def _queue_fragments(self) -> StyleAndTextTuples:
        out: StyleAndTextTuples = []
        for n, text in enumerate(self.queue):
            if n:
                out.append(("", "\n"))
            out.append((f"{ORION_COLORS['faint']}", f"· na fila: {' '.join(text.split())}"))
        if self.queue:
            out.append((f"{ORION_COLORS['faint']}", "   ↑ edita"))
        return out

    def _queue_height(self) -> Dimension:
        return Dimension.exact(len(self.queue))

    def _modal_fragments(self) -> StyleAndTextTuples:
        if self.modal is None:
            return []
        return to_formatted_text(ANSI(render_ansi(self.modal.render(), self._width())))

    def _status_fragments(self) -> StyleAndTextTuples:
        classes = {
            "mode": "class:bottom-toolbar.blue",
            "dim": "class:bottom-toolbar.dim",
            "sep": "class:bottom-toolbar.border",
            "pep": "class:bottom-toolbar.pep",
            "ok": "class:bottom-toolbar.ok",
            "offline": "class:bottom-toolbar.offline",
            "cyan": "class:bottom-toolbar.cyanstate",
        }
        return [(classes.get(role, ""), text) for role, text in self.status_bar.status_segments(self._width())]

    # ── Entrada ─────────────────────────────────────────────────────

    def _accept(self, buffer: Buffer) -> bool:
        text = buffer.text
        if self.searching:
            self.searching = False
            self.search(text.strip())
            return False
        if self._answer is not None:
            future, self._answer = self._answer, None
            if self._secret:
                # A senha nunca entra no histórico (o Buffer grava o texto depois deste handler).
                buffer.text = ""
                self._secret = False
            if not future.done():
                future.set_result(text)
            return False
        if not text.strip():
            return False
        if self.turn is not None:
            self.queue.append(text.strip())
            self.invalidate()
            return False
        self.start(text.strip())
        return False

    def start(self, text: str) -> None:
        self.turn = asyncio.ensure_future(self._run(text))

    async def _run(self, text: str) -> None:
        try:
            if text in EXIT_WORDS:
                self.exit()
                return
            self.transcript.add(user_cell(text))
            self.offset = 0
            self._signal_busy(True)
            started = time.monotonic()
            await self._dispatch(text)
            if time.monotonic() - started > BELL_AFTER and not self.focused:
                with contextlib.suppress(Exception):
                    self.app.output.bell()
                    self.app.output.flush()
        except asyncio.CancelledError:
            self.renderer.close()
            self.transcript.add_renderables(
                "notice",
                Text("! Turno interrompido pelo Senhor. Sessão e memórias preservadas.", style="pep_warn"),
            )
        except Exception as exc:  # erro de comando nunca derruba a tela
            self.renderer.close()
            self.transcript.add_renderables("notice", Text(f"✖ {exc}", style="diff_del"))
        finally:
            self.turn = None
            self.turns += 1
            self._signal_busy(False)
            self.invalidate()
        if self.relaunch:
            self.exit()
        elif self.queue and not self.exited:
            self.start(self.queue.pop(0))

    async def _dispatch(self, text: str) -> None:
        session = self.session
        set_dynamic = getattr(self.registry, "set_dynamic", None)
        if callable(set_dynamic):
            set_dynamic(session.dynamic_commands())
        if text.startswith("/") or self.registry.get(text) is not None:
            result = await self.registry.dispatch(text, self.context)
            if result is not None and result.output_message:
                style = "text_dim" if result.success else "diff_del"
                self.transcript.add_renderables("notice", Text(result.output_message, style=style))
            return
        await session.run_turn(text)

    # ── Transcrição completa (Ctrl+O) ───────────────────────────────

    def toggle_full_view(self) -> None:
        self.full_view = not self.full_view
        self.searching = False
        self.offset = 0
        self._last_total = 0
        if not self.full_view:
            self.query, self.matches, self.match_index = "", [], -1
        self.invalidate()

    def search(self, query: str) -> None:
        """Acha as linhas com *query* (sem diferenciar maiúsculas) e vai à mais recente."""
        self.query = query
        width = self._width()
        lines = self.transcript.all_lines(width, expand=True)
        needle = query.lower()
        self.matches = [n for n, line in enumerate(lines) if needle and needle in plain([line]).lower()]
        self.match_index = len(self.matches) - 1
        self._jump(len(lines))

    def next_match(self, step: int) -> None:
        if not self.matches:
            return
        self.match_index = (self.match_index + step) % len(self.matches)
        self._jump(self.transcript.total_lines(self._width(), expand=True))

    def _jump(self, total: int) -> None:
        if self.match_index < 0:
            self.invalidate()
            return
        line = self.matches[self.match_index]
        visible = max(self._height() - 6, 1)
        self.offset = max(total - line - visible // 2 - 1, 0)
        self._last_total = total
        self.invalidate()

    def request_dump(self) -> None:
        """``[``: sai da tela alternativa, escreve a conversa no scrollback e espera Enter."""
        self.dump_requested = True
        with contextlib.suppress(Exception):
            self.app.exit()

    def dump_text(self, width: int) -> str:
        """A conversa inteira em ANSI, com tudo aberto (cores preservadas no scrollback)."""
        from rich.console import Group

        parts = [render_ansi(Group(*cell.renderables(expand=True)), width) for cell in self.transcript.snapshot()]
        return "\n".join(parts)

    def _signal_busy(self, busy: bool) -> None:
        """Título da aba e progresso nativo acompanham o turno (N-23)."""
        output = self.app.output
        terminal.set_title(output, "ORION · trabalhando" if busy else "ORION")
        if self.progress:
            terminal.write(output, terminal.PROGRESS_BUSY if busy else terminal.PROGRESS_CLEAR)

    def cancel_turn(self) -> bool:
        if self.turn is not None and not self.turn.done():
            self.turn.cancel()
            return True
        return False

    def _on_escape(self, event: KeyPressEvent) -> None:
        if self.searching:
            self.searching = False
            self.buffer.reset()
            return
        if self._answer is not None:
            future, self._answer = self._answer, None
            if not future.done():
                future.set_result("")
            self.buffer.reset()
            return
        if self.cancel_turn():
            return
        if self.buffer.text:
            self.buffer.reset()

    def _on_ctrl_c(self, event: KeyPressEvent) -> None:
        if self._answer is not None:
            self._on_escape(event)
            return
        if self.cancel_turn():
            return
        if self.buffer.text:
            self.buffer.reset()
            return
        now = time.monotonic()
        if now - self._last_ctrl_c < DOUBLE_CTRL_C:
            self.exit()
            return
        self._last_ctrl_c = now
        self.flash = ("Ctrl+C de novo para sair (ou /exit)", now + DOUBLE_CTRL_C)
        self.invalidate()

    def _on_status(self, text: str | None) -> None:
        self.renderer.status_text = text
        self.invalidate()

    def clear(self) -> None:
        """``/clear``: transcrição nova com o banner."""
        self.transcript.clear()
        self.transcript.add(Cell("banner", [_Banner(self.status_bar)]))
        self.offset = 0

    def request_relaunch(self) -> None:
        """``/tui``: sai ao fim do comando e o ``cli`` reabre o ORION na mesma sessão."""
        self.relaunch = True

    def exit(self) -> None:
        self.exited = True
        if not self.app.is_done:
            with contextlib.suppress(Exception):
                self.app.exit()

    # ── Host de modais (orion.tui.modal delega para cá) ────────────

    async def run_modal(self, controller: Any, keep_on_screen: bool = False) -> None:
        loop = asyncio.get_running_loop()
        self.modal = controller
        self._modal_done = loop.create_future()
        self.invalidate()
        try:
            await self._modal_done
        finally:
            self.modal = None
            self._modal_done = None
            if keep_on_screen:
                self.transcript.add_renderables("modal", controller.render())
            self.invalidate()

    def _close_modal(self) -> None:
        future = self._modal_done
        if future is not None and not future.done():
            future.set_result(None)

    async def ask_text(self, question: str, default: str = "") -> str:
        loop = asyncio.get_running_loop()
        self._answer = loop.create_future()
        self._answer_question = question
        self.buffer.text = default
        self.buffer.cursor_position = len(default)
        self.invalidate()
        try:
            return await self._answer
        finally:
            self._answer = None
            self._answer_question = ""

    async def ask_secret(self, title: str, detail: str = "") -> str | None:
        """Senha mascarada no input (ADR-048): nunca vai para o histórico nem para a transcrição.

        Esc cancela (None). O texto digitado aparece como ``*``.
        """
        line = Text()
        line.append("[PEP] ", style="pep_warn")
        line.append(title, style="text_primary")
        if detail:
            line.append(f"  ·  {detail}", style="text_dim")
        self.transcript.add_renderables("notice", line)
        self._secret = True
        self.buffer.reset()
        try:
            answer = await self.ask_text(f"{title} (Esc cancela)")
        finally:
            self._secret = False
            self.buffer.reset()
        return answer or None

    # ── Ciclo de vida ───────────────────────────────────────────────

    async def _tick(self) -> None:
        last_status: list[tuple[str, str]] = []
        while True:
            moving = self.renderer.busy() or self.flash is not None or self.modal is not None
            if moving:
                self.invalidate()
                await asyncio.sleep(SPINNER_INTERVAL if self.focused else UNFOCUSED_INTERVAL)
                continue
            status = self.status_bar.status_segments(self._width())
            if status != last_status:
                last_status = status
                self.invalidate()
            if self.turn is None:
                pop = getattr(self.session, "pop_notifications", None)
                for event in pop() if callable(pop) else []:
                    self.transcript.add_renderables(
                        "notice", Text(f"● {self.session.format_notification(event)}", style="text_dim")
                    )
            if self._started_at and time.monotonic() - self._started_at > STARTED_AFTER:
                self._started_at = 0.0
                from orion.tui.screen.mode import mark_started

                mark_started(self.home)
            await asyncio.sleep(IDLE_INTERVAL)

    async def run_async(self) -> None:
        host_registry.set_active_host(self)
        self._started_at = time.monotonic()
        self._ticker = asyncio.ensure_future(self._tick())
        output = self.app.output
        if self.sync_output:
            terminal.enable_sync_output(output)
        terminal.write(output, terminal.FOCUS_ON)
        terminal.set_title(output, "ORION")
        try:
            while True:
                await self.app.run_async()
                if not self.dump_requested or self.exited:
                    break
                self.dump_requested = False
                await self._dump_to_scrollback()
        finally:
            terminal.write(output, terminal.FOCUS_OFF)
            if self.progress:
                terminal.write(output, terminal.PROGRESS_CLEAR)
            with contextlib.suppress(Exception):
                output.clear_title()
                output.flush()
            host_registry.set_active_host(None)
            if self._ticker is not None:
                self._ticker.cancel()
            if self.turn is not None and not self.turn.done():
                self.turn.cancel()
                with contextlib.suppress(BaseException):
                    await self.turn

    async def _dump_to_scrollback(self) -> None:
        """Escreve a conversa no scrollback normal (a busca do terminal passa a vê-la)."""
        import sys

        width = self._width()
        stream = sys.__stdout__ or sys.stdout
        stream.write(self.dump_text(width) + "\n\n")
        stream.write("── fim da transcrição · Enter volta ao ORION ──\n")
        stream.flush()
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, sys.stdin.readline)

    def run(self) -> None:
        asyncio.run(self.run_async())

    def summary(self) -> Text:
        """Linha deixada no scrollback normal ao sair (N-24)."""
        sid = str(getattr(self.session, "session_id", ""))[:8]
        line = Text()
        line.append("● ", style="accent_cyan")
        line.append("Até logo, Senhor.", style="text_primary")
        cost = getattr(self.status_bar, "session_cost_usd", 0.0)
        line.append(f"  ·  {self.turns} pedidos  ·  US$ {cost:.4f}".replace(".", ","), style="text_dim")
        if sid:
            line.append(f"  ·  retome com orion --resume {sid}", style="text_dim")
        return line


def _join(lines: list[Line]) -> StyleAndTextTuples:
    out: StyleAndTextTuples = []
    for n, line in enumerate(lines):
        if n:
            out.append(("", "\n"))
        out.extend(line)
    return out

