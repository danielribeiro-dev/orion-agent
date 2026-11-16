"""``ScreenRenderer``: o fluxo do turno escrito na transcrição da tela cheia (ADR-043).

Herda o contrato e a lógica do :class:`StreamRenderer` (blocos concluídos, cronômetros, fila de
ferramentas, aviso de travamento). Muda só o destino: em vez de imprimir no terminal e manter um
``Rich.Live``, grava células na :class:`Transcript`; a parte viva (cauda do texto e linha de
atividade) é desenhada pela aplicação a cada quadro. Raciocínio e saída de ferramenta viram
células recolhíveis que abrem e fecham no lugar.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from rich.console import Console, ConsoleOptions, RenderableType, RenderResult
from rich.segment import Segment
from rich.text import Text

from orion.tui.screen.transcript import Cell, Line, Transcript, rasterize
from orion.tui.stream_renderer import OrionMarkdown, StreamRenderer, collapse_output


class ScreenRenderer(StreamRenderer):
    """StreamRenderer sem ``Rich.Live``: células na transcrição e parte viva sob demanda."""

    def __init__(
        self,
        console: object,
        transcript: Transcript,
        effort: Callable[[], str] = lambda: "high",
    ) -> None:
        super().__init__(console, effort=effort)  # type: ignore[arg-type]
        self.transcript = transcript
        self.on_change: Callable[[], None] | None = None
        self.status_text: str | None = None  # ``console.status(...)`` de comandos

    # ── Destino ─────────────────────────────────────────────────────

    def _notify(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def _print(self, *renderables: RenderableType) -> None:
        self.transcript.add_renderables("print", *(renderables or (Text(""),)))

    def _ensure_live(self) -> None:
        self._notify()

    def busy(self) -> bool:
        """Há algo em movimento (spinner, cauda de texto, aviso de travamento)."""
        return (
            self._activity is not None
            or bool(self._buffer)
            or self.status_text is not None
            or self._stall_notice() is not None
        )

    # ── Parte viva ──────────────────────────────────────────────────

    def live_lines(self, width: int, max_lines: int) -> list[Line]:
        """Cauda do Markdown em construção (só as últimas *max_lines* linhas)."""
        if not self._buffer:
            return []
        lines = rasterize([OrionMarkdown(self._buffer)], width)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        return lines

    def activity_renderables(self) -> list[RenderableType]:
        """Linha de atividade acima do input (spinner, aviso de travamento, status de comando)."""
        parts: list[RenderableType] = []
        if self._activity is not None:
            self._spinner.update(text=self._activity())
            parts.append(self._spinner)
        elif self.status_text is not None:
            self._spinner.update(text=Text(self.status_text, style="text_dim"))
            parts.append(self._spinner)
        if (notice := self._stall_notice()) is not None:
            parts.append(notice)
        return parts

    # ── Blocos recolhíveis ──────────────────────────────────────────

    def _flush_thinking(self) -> None:
        if self._thinking_started is None:
            return
        elapsed = time.monotonic() - self._thinking_started
        self._thinking_started = None
        self._activity = None
        if not self._reasoning.strip():
            return
        self.last_reasoning = self._reasoning
        self._start_block("thinking")
        self.transcript.add(self.thinking_cell(self._reasoning, elapsed))

    def thinking_cell(self, reasoning: str, elapsed: float) -> Cell:
        def header(opened: bool) -> Text:
            line = Text(no_wrap=True, overflow="ellipsis")
            line.append("▾ " if opened else "▸ ", style="accent_blue")
            line.append(f"Raciocínio · {_secs(elapsed)}", style="text_dim")
            line.append("   Alt+R fecha" if opened else "   Alt+R abre", style="faint")
            return line

        body = [header(False)]
        text = "\n".join(row for row in reasoning.rstrip().splitlines() if row.strip())
        return Cell("thinking", body, expanded=[header(True), Guided(Text(text, style="text_dim"))])

    def _print_output(self, output: str, label: str = "", success: bool = True) -> None:
        if not output.strip():
            return
        self.last_output = output
        self.last_output_label = f"{'✔' if success else '✖'} {label}" if label else ""
        head, tail, hidden = collapse_output(output)
        if not hidden:
            self.transcript.add_renderables("output", *[self._guide_text(t) for t in head])
            return
        note = Text(no_wrap=True)
        note.append("  │ ", style="rule")
        note.append(f"+{hidden} linhas ocultas", style="accent_blue")
        note.append("  ·  Alt+E abre", style="faint")
        body = [*(self._guide_text(t) for t in head), note, *(self._guide_text(t) for t in tail)]
        full = [self._guide_text(t) for t in output.rstrip("\n").splitlines()]
        closing = Text("  │ ", style="rule")
        closing.append("Alt+E fecha", style="faint")
        self.transcript.add(Cell("output", body, expanded=[*full, closing]))

    @staticmethod
    def _guide_text(text: str, style: str = "text_dim") -> Text:
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append("  │ ", style="rule")
        line.append(text, style=style)
        return line

    def _guide(self, text: str, style: str = "text_dim") -> None:
        self.transcript.add_renderables("print", self._guide_text(text, style))

    def expand_reasoning(self) -> None:
        if self.transcript.toggle_last("thinking") is None:
            self.transcript.add_renderables("notice", Text("Nenhum raciocínio nesta sessão.", style="text_dim"))

    def expand_output(self) -> None:
        cell = self.transcript.last("output")
        if cell is None or not cell.collapsible:
            self.transcript.add_renderables(
                "notice", Text("Nenhuma saída recolhida nesta sessão.", style="text_dim")
            )
            return
        self.transcript.toggle(cell)


class Guided:
    """Texto que quebra na largura com o guia ``  │ `` em toda linha (raciocínio aberto)."""

    PREFIX = "  │ "

    def __init__(self, text: Text) -> None:
        self.text = text

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        inner = options.update_width(max(options.max_width - len(self.PREFIX), 10))
        for line in console.render_lines(self.text, inner, pad=False):
            yield Segment(self.PREFIX, console.get_style("rule"))
            yield from line
            yield Segment.line()


def _secs(value: float) -> str:
    return f"{value:.1f}s".replace(".", ",")
