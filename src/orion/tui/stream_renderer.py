"""
O.R.I.O.N TUI — Live Stream Renderer.

Renderiza o turno do agente em tempo real sem prender o terminal: blocos de Markdown
concluídos vão direto para o scrollback e só a cauda em construção fica no Rich.Live,
que é transiente. Assim a rolagem nativa nunca recebe linhas duplicadas.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.live import Live
from rich.markdown import CodeBlock, Heading, Markdown
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text

from orion.tui.diff_viewer import DiffViewer, FileDiff
from orion.tui.theme import get_syntax_theme

MAX_INLINE_OUTPUT_LINES = 5
_HEAD_LINES = 3
_TAIL_LINES = 2

_TOOL_LABELS: dict[str, tuple[str, str]] = {
    "run_command": ("Bash", "command"),
    "read_file": ("Read", "path"),
    "write_file": ("Write", "path"),
    "edit_file": ("Edit", "path"),
    "search_files": ("Search", "pattern"),
    "recall": ("Recall", "query"),
    "memorize": ("Memorize", "key"),
}


class _LeftHeading(Heading):
    """Títulos alinhados à esquerda, sem a caixa padrão do Rich."""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        text = self.text
        text.justify = "left"
        yield text


class _RoundedCodeBlock(CodeBlock):
    """Bloco de código com borda fina arredondada e tema restrito à paleta."""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        code = str(self.text).rstrip()
        syntax = Syntax(
            code,
            self.lexer_name,
            theme=get_syntax_theme(),
            background_color="default",
            word_wrap=True,
        )
        yield Panel(syntax, box=box.ROUNDED, border_style="border_subtle", padding=(0, 1))


class OrionMarkdown(Markdown):
    """Markdown com os elementos do Design System."""

    elements = {
        **Markdown.elements,
        "heading_open": _LeftHeading,
        "fence": _RoundedCodeBlock,
        "code_block": _RoundedCodeBlock,
    }


def split_committable(buffer: str) -> tuple[str, str]:
    """Separa o buffer em blocos prontos e cauda aberta, sem cortar blocos de código."""
    in_fence = False
    cut = 0
    position = 0
    for line in buffer.splitlines(keepends=True):
        position += len(line)
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        elif not in_fence and not line.strip() and line.endswith("\n"):
            cut = position
    return buffer[:cut], buffer[cut:]


def format_tool_label(tool: str, params: dict[str, Any]) -> str:
    """Rótulo curto do card: `Bash: pytest`, `Edit: src/x.py`."""
    label, key = _TOOL_LABELS.get(tool, (tool, ""))
    value = str(params.get(key, "")) if key else ""
    value = " ".join(value.split())
    return f"{label}: {value}" if value else label


def collapse_output(output: str) -> tuple[list[str], list[str], int]:
    """Aplica a regra de colapso: 5 linhas inteiras, senão 3 primeiras e 2 últimas."""
    lines = output.rstrip("\n").splitlines()
    if len(lines) <= MAX_INLINE_OUTPUT_LINES:
        return lines, [], 0
    return lines[:_HEAD_LINES], lines[-_TAIL_LINES:], len(lines) - _HEAD_LINES - _TAIL_LINES


class StreamRenderer:
    """Fluxo vivo do turno: raciocínio, Markdown em streaming e cards de ferramenta."""

    def __init__(
        self,
        console: Console,
        effort: Callable[[], str] = lambda: "high",
        status_line: Callable[[int], RenderableType] | None = None,
        diff_viewer: DiffViewer | None = None,
    ) -> None:
        self.console = console
        self._effort = effort
        self._status_line = status_line
        self._diff_viewer = diff_viewer or DiffViewer()
        self._live: Live | None = None
        self._spinner = Spinner("dots", style="accent_cyan")
        self._activity: Callable[[], Text] | None = None
        self._buffer = ""
        self._reasoning = ""
        self._thinking_started: float | None = None
        self._tool_started = 0.0
        self._tool_label = ""
        self._last_block = "user"
        self.last_reasoning = ""
        self.last_output = ""

    # ── Ciclo do Live ───────────────────────────────────────────────

    def __rich__(self) -> RenderableType:
        parts: list[RenderableType] = []
        if self._buffer:
            parts.append(OrionMarkdown(self._buffer))
        if self._activity is not None:
            self._spinner.update(text=self._activity())
            parts.append(self._spinner)
        if self._status_line is not None:
            parts.extend((Text(""), self._status_line(self.console.width)))
        return Group(*parts)

    def _ensure_live(self) -> None:
        if self._live is None:
            self._live = Live(
                self,
                console=self.console,
                refresh_per_second=12,
                transient=True,
                vertical_overflow="crop",
            )
            self._live.start()

    def _start_block(self, kind: str) -> None:
        """Separa blocos de naturezas diferentes com uma linha em branco."""
        if kind != self._last_block:
            self.console.print()
        self._last_block = kind

    def pause(self) -> None:
        """Encerra o Live para que um diálogo possa usar o terminal."""
        if self._live is not None:
            self._live.stop()
            self._live = None

    def resume(self) -> None:
        """Retoma o Live depois de um diálogo, se ainda houver atividade."""
        if self._activity is not None or self._buffer:
            self._ensure_live()

    def close(self) -> None:
        """Conclui o turno, gravando o que restar no scrollback."""
        self._flush_thinking()
        self._activity = None
        self._flush_text()
        self.pause()
        self._last_block = "user"

    # ── Raciocínio ──────────────────────────────────────────────────

    def begin_thinking(self) -> None:
        """Mostra o spinner enquanto o modelo formula a resposta."""
        self._thinking_started = time.monotonic()
        self._reasoning = ""
        effort = self._effort()
        tag = f" [{effort} effort]" if effort != "off" else ""

        def activity() -> Text:
            elapsed = time.monotonic() - (self._thinking_started or time.monotonic())
            return Text(f"Pensando{tag}... ({elapsed:.1f}s)", style="text_dim")

        self._activity = activity
        self._ensure_live()

    def add_reasoning(self, delta: str) -> None:
        """Acumula o raciocínio recebido do provedor."""
        self._reasoning += delta

    def _flush_thinking(self) -> None:
        if self._thinking_started is None:
            return
        elapsed = time.monotonic() - self._thinking_started
        self._thinking_started = None
        self._activity = None
        if self._reasoning.strip():
            self.last_reasoning = self._reasoning
            self._start_block("thinking")
            line = Text(no_wrap=True)
            line.append("▼ ", style="accent_blue")
            line.append(
                f"Raciocínio formulado em {elapsed:.1f}s (pressione Alt+R para expandir)",
                style="text_dim",
            )
            self.console.print(line)

    # ── Texto ───────────────────────────────────────────────────────

    def add_text(self, delta: str) -> None:
        """Recebe um delta de texto e grava os blocos já concluídos."""
        self._flush_thinking()
        self._buffer += delta
        done, tail = split_committable(self._buffer)
        if done:
            self._buffer = tail
            self._start_block("text")
            self.console.print(OrionMarkdown(done))
        self._ensure_live()

    def _flush_text(self) -> None:
        if self._buffer.strip():
            self._start_block("text")
            self.console.print(OrionMarkdown(self._buffer))
        self._buffer = ""

    def end_message(self) -> None:
        """Fecha a mensagem atual do modelo."""
        self._flush_thinking()
        self._flush_text()

    # ── Ferramentas ─────────────────────────────────────────────────

    def tool_started(self, tool: str, params: dict[str, Any]) -> None:
        """Mostra o card em execução com spinner Braille."""
        self.end_message()
        self._tool_label = format_tool_label(tool, params)
        self._tool_started = time.monotonic()
        label = Text(self._tool_label, style="text_primary", no_wrap=True, overflow="ellipsis")
        self._activity = lambda: label
        self._ensure_live()

    def tool_finished(
        self,
        tool: str,
        success: bool,
        output: str = "",
        metadata: dict[str, Any] | None = None,
        diff: FileDiff | None = None,
    ) -> None:
        """Substitui o spinner pelo card concluído, seguido de saída e diff."""
        self._activity = None
        metadata = metadata or {}
        self._start_block("tool")
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append("✔ " if success else "✖ ", style="status_ok" if success else "diff_del")
        line.append(self._tool_label, style="text_primary")
        meta = f" · {time.monotonic() - self._tool_started:.1f}s"
        if "exit_code" in metadata:
            meta += f" · exit {metadata['exit_code']}"
        if diff is not None:
            meta += f" · +{diff.added} / -{diff.removed}"
        line.append(meta, style="text_dim")
        self.console.print(line)

        if diff is not None and diff.hunks:
            self.console.print(self._diff_viewer.render(diff))
        if tool == "run_command" or not success:
            self._print_output(output)

    def _print_output(self, output: str) -> None:
        if not output.strip():
            return
        self.last_output = output
        head, tail, hidden = collapse_output(output)
        for text in head:
            self._guide(text)
        if hidden:
            note = Text(no_wrap=True)
            note.append("│ ", style="border_subtle")
            note.append(
                f"[+{hidden} linhas ocultas · pressione Alt+E para expandir]",
                style="accent_blue",
            )
            self.console.print(note)
        for text in tail:
            self._guide(text)

    def _guide(self, text: str, style: str = "text_dim") -> None:
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append("│ ", style="border_subtle")
        line.append(text, style=style)
        self.console.print(line)

    # ── Expansão sob demanda ────────────────────────────────────────

    def expand_reasoning(self) -> None:
        """Imprime o último raciocínio com guia vertical."""
        if not self.last_reasoning.strip():
            self.console.print(Text("Nenhum raciocínio nesta sessão.", style="text_dim"))
            return
        for text in self.last_reasoning.rstrip().splitlines():
            self._guide(text)

    def expand_output(self) -> None:
        """Imprime a última saída de ferramenta sem colapso."""
        if not self.last_output.strip():
            self.console.print(Text("Nenhuma saída de ferramenta nesta sessão.", style="text_dim"))
            return
        for text in self.last_output.rstrip().splitlines():
            self._guide(text)

    def warn(self, message: str) -> None:
        """Aviso não fatal (ex.: failover de provedor); não encerra o Live."""
        line = Text()
        line.append("! ", style="text_primary")
        line.append(message, style="text_primary")
        self.console.print(line)

    def error(self, message: str) -> None:
        """Encerra o Live e mostra um erro operacional."""
        self.close()
        line = Text()
        line.append("✖ ", style="diff_del")
        line.append(message, style="text_primary")
        self.console.print(line)
