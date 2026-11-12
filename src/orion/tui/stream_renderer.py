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
from rich.segment import Segment
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text

from orion.tui.diff_viewer import DiffViewer, FileDiff
from orion.tui.theme import ORION_COLORS, get_syntax_theme

MAX_INLINE_OUTPUT_LINES = 5
STALL_NOTICE_S = 5.0
"""Sem nenhum evento do provedor por este tempo, a parte viva avisa (``sem resposta há Ns``)."""
_LIVE_MARGIN = 2
"""Linhas livres abaixo da parte viva: ela nunca ocupa a tela inteira (V-10)."""
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
    "deprecate_fact": ("Deprecate", "key"),
    "use_skill": ("Skill", "skill_name"),
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
        yield Panel(syntax, box=box.ROUNDED, border_style="rule", padding=(0, 1))


class OrionMarkdown(Markdown):
    """Markdown com os elementos do Design System."""

    elements = {
        **Markdown.elements,
        "heading_open": _LeftHeading,
        "fence": _RoundedCodeBlock,
        "code_block": _RoundedCodeBlock,
    }


class _TailWindow:
    """Mostra só as últimas *max_lines* linhas de um renderable, com aviso das que ficaram acima.

    Um bloco de código aberto não pode ir para o histórico pela metade; enquanto ele cresce, a
    parte viva exibe a cauda (o que acabou de chegar) e cabe na tela. Se a parte viva ocupasse a
    tela inteira, o Rich não conseguiria apagar o quadro anterior e deixaria lixo no histórico.
    """

    def __init__(self, renderable: RenderableType, max_lines: int) -> None:
        self.renderable = renderable
        self.max_lines = max(max_lines, 2)

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        lines = console.render_lines(self.renderable, options, pad=False)
        if len(lines) > self.max_lines:
            hidden = len(lines) - (self.max_lines - 1)
            yield Text(f"· {hidden} linhas acima, completas ao fim do bloco", style="text_dim")
            lines = lines[hidden:]
        for line in lines:
            yield from line
            yield Segment.line()


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


def tool_parts(tool: str, params: dict[str, Any]) -> tuple[str, str]:
    """Nome curto e argumento principal da ferramenta: (`Bash`, `pytest -q`)."""
    label, key = _TOOL_LABELS.get(tool, (tool, ""))
    value = str(params.get(key, "")) if key else ""
    return label, " ".join(value.split())


def format_tool_label(tool: str, params: dict[str, Any]) -> str:
    """Rótulo curto do card: `Bash: pytest`, `Edit: src/x.py`."""
    label, value = tool_parts(tool, params)
    return f"{label}: {value}" if value else label


def _seconds(value: float) -> str:
    """Tempo com vírgula decimal (`0,2s`), como no resto da interface em PT-BR."""
    return f"{value:.1f}s".replace(".", ",")


def tool_result_line(
    tool: str, success: bool, output: str, diff: FileDiff | None = None
) -> Text | None:
    """Resumo de uma linha sob a ferramenta (`  › 212 linhas`); None quando não há o que resumir."""
    if not success:
        return None
    line = Text(no_wrap=True, overflow="ellipsis")
    line.append("  › ", style="faint")
    if diff is not None and tool in ("edit_file", "write_file", "notebook_edit"):
        line.append(f"+{diff.added}", style="diff_add")
        line.append(" ")
        line.append(f"−{diff.removed}", style="diff_del")
        return line
    count = len([row for row in output.splitlines() if row.strip()])
    if tool == "read_file":
        line.append(f"{count} {'linha' if count == 1 else 'linhas'}", style="text_dim")
        return line
    if tool in ("grep", "glob", "search_files"):
        line.append(f"{count} {'resultado' if count == 1 else 'resultados'}", style="text_dim")
        return line
    return None


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
        self._tools: dict[str, tuple[str, float]] = {}
        self._tool_parts: dict[str, tuple[str, str]] = {}
        self._last_block = "user"
        self._last_event: float | None = None  # último sinal do provedor (None: fora de turno)
        self._paused_at: float | None = None
        self._input_line: Callable[[], RenderableType | None] | None = None
        self.on_pause: list[Callable[[], None]] = []
        self.on_resume: list[Callable[[], None]] = []
        self.last_reasoning = ""
        self.last_output = ""
        self.last_output_label = ""

    # ── Ciclo do Live ───────────────────────────────────────────────

    def __rich__(self) -> RenderableType:
        footer: list[RenderableType] = []
        if self._activity is not None:
            self._spinner.update(text=self._activity())
            footer.append(self._spinner)
        if (notice := self._stall_notice()) is not None:
            footer.append(notice)
        if self._input_line is not None and (typed := self._input_line()) is not None:
            footer.append(typed)
        if self._status_line is not None:
            footer.extend((Text(""), self._status_line(self.console.width)))
        parts: list[RenderableType] = []
        if self._buffer:
            room = self.console.height - len(footer) - _LIVE_MARGIN
            parts.append(_TailWindow(OrionMarkdown(self._buffer), room))
        return Group(*parts, *footer)

    def _print(self, *renderables: RenderableType) -> None:
        """Imprime no histórico sem disputar o terminal com a thread de refresh do Live.

        O Rich só segura o lock do Live por um instante ao calcular quantas linhas apagar; se o
        refresh desenhar um quadro mais alto antes da escrita, as linhas extras ficam no histórico
        como quadro fantasma (V-10). Com o lock durante o print inteiro, o refresh espera.
        """
        live = self._live
        if live is None:
            self.console.print(*renderables)
            return
        with live._lock:  # noqa: SLF001 - RLock do Live; reentrante em process_renderables
            self.console.print(*renderables)

    def _touch(self) -> None:
        """Registra um sinal de vida do provedor (zera o aviso de travamento)."""
        self._last_event = time.monotonic()

    def _stall_notice(self) -> Text | None:
        if self._last_event is None or self._tools or self._paused_at is not None:
            return None
        silent = time.monotonic() - self._last_event
        if silent < STALL_NOTICE_S:
            return None
        return Text(f"sem resposta há {int(silent)}s  ·  Ctrl+C cancela", style="faint")

    def set_input_line(self, render: Callable[[], RenderableType | None] | None) -> None:
        """Linha de digitação durante o turno (V-11); ``None`` remove."""
        self._input_line = render

    def status_renderable(self) -> RenderableType | None:
        """A linha de status atual (para modais que pausam o Live)."""
        return self._status_line(self.console.width) if self._status_line is not None else None

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
            self._print()
        self._last_block = kind

    def pause(self) -> None:
        """Encerra o Live para que um diálogo possa usar o terminal.

        O tempo pausado (o Senhor decidindo no modal) não conta para as ferramentas em
        execução nem para o aviso de travamento (V-12).
        """
        if self._paused_at is None and self._last_event is not None:
            self._paused_at = time.monotonic()
        if self._live is not None:
            self._live.stop()
            self._live = None
        for hook in self.on_pause:
            hook()

    def resume(self) -> None:
        """Retoma o Live depois de um diálogo, se ainda houver atividade."""
        if self._paused_at is not None:
            waited = time.monotonic() - self._paused_at
            self._paused_at = None
            self._tools = {key: (label, started + waited) for key, (label, started) in self._tools.items()}
            self._touch()
        for hook in self.on_resume:
            hook()
        if self._activity is not None or self._buffer:
            self._ensure_live()

    def close(self) -> None:
        """Conclui o turno, gravando o que restar no scrollback."""
        self._flush_thinking()
        self._activity = None
        self._flush_text()
        self._last_event = None
        self._paused_at = None
        self.pause()
        self._last_block = "user"

    # ── Raciocínio ──────────────────────────────────────────────────

    def begin_thinking(self) -> None:
        """Mostra o spinner enquanto o modelo formula a resposta."""
        self._thinking_started = time.monotonic()
        self._touch()
        self._reasoning = ""
        effort = self._effort()
        tag = f" [{effort} effort]" if effort != "off" else ""

        def activity() -> Text:
            elapsed = time.monotonic() - (self._thinking_started or time.monotonic())
            return Text(f"Pensando{tag}… ({_seconds(elapsed)})", style="text_dim")

        self._activity = activity
        self._ensure_live()

    def add_reasoning(self, delta: str) -> None:
        """Acumula o raciocínio recebido do provedor."""
        self._touch()
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
            line.append(f"Raciocínio · {_seconds(elapsed)}", style="text_dim")
            line.append("   Alt+R expande", style="faint")
            self._print(line)

    # ── Texto ───────────────────────────────────────────────────────

    def add_text(self, delta: str) -> None:
        """Recebe um delta de texto e grava os blocos já concluídos."""
        self._flush_thinking()
        self._touch()
        self._buffer += delta
        done, tail = split_committable(self._buffer)
        if done:
            self._buffer = tail
            self._start_block("text")
            self._print(OrionMarkdown(done))
        self._ensure_live()

    def _flush_text(self) -> None:
        if self._buffer.strip():
            self._start_block("text")
            self._print(OrionMarkdown(self._buffer))
        self._buffer = ""

    def end_message(self) -> None:
        """Fecha a mensagem atual do modelo."""
        self._flush_thinking()
        self._flush_text()

    # ── Ferramentas ─────────────────────────────────────────────────

    def tool_started(self, tool: str, params: dict[str, Any], key: str = "") -> None:
        """Mostra o card em execução com spinner Braille.

        *key* identifica a chamada (action_id); tools paralelas coexistem, cada uma
        com o seu rótulo e cronômetro.
        """
        self.end_message()
        self._touch()
        self._tools[key] = (format_tool_label(tool, params), time.monotonic())
        self._tool_parts[key] = tool_parts(tool, params)

        def running() -> Text:
            line = Text(no_wrap=True, overflow="ellipsis")
            for n, (name, arg) in enumerate(self._tool_parts.values()):
                if n:
                    line.append("  ·  ", style="faint")
                line.append(name, style=f"bold {ORION_COLORS['text_primary']}")
                if arg:
                    line.append(f"  {arg}", style="text_dim")
            started = min((t for _, t in self._tools.values()), default=time.monotonic())
            line.append(f"  ·  {int(time.monotonic() - started)}s  ·  Ctrl+C cancela", style="faint")
            return line

        self._activity = running
        self._ensure_live()

    def tool_finished(
        self,
        tool: str,
        success: bool,
        output: str = "",
        metadata: dict[str, Any] | None = None,
        diff: FileDiff | None = None,
        key: str = "",
    ) -> None:
        """Substitui o spinner pelo card concluído, seguido de saída e diff."""
        label, started = self._tools.pop(key, (tool, time.monotonic()))
        name, arg = self._tool_parts.pop(key, (label, ""))
        self._touch()
        if not self._tools:
            self._activity = None
        metadata = metadata or {}
        self._start_block("tool")
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append("✔ " if success else "✖ ", style="status_ok" if success else "diff_del")
        line.append(name, style=f"bold {ORION_COLORS['text_primary']}")
        if arg:
            line.append(f"  {arg}", style="text_dim")
        meta = f"  ·  {_seconds(time.monotonic() - started)}"
        if "exit_code" in metadata:
            meta += f"  ·  exit {metadata['exit_code']}"
        line.append(meta, style="faint")
        self._print(line)
        summary = tool_result_line(tool, success, output, diff)
        if summary is not None:
            self._print(summary)

        if diff is not None and diff.hunks:
            self._print(self._diff_viewer.render(diff))
        if tool == "todo_write" and success:
            for row in output.splitlines():
                self._guide(row, style="text_primary" if row.lstrip().startswith("●") else "text_dim")
        elif tool == "run_command" or not success:
            self._print_output(output, label, success)

    def _print_output(self, output: str, label: str = "", success: bool = True) -> None:
        if not output.strip():
            return
        self.last_output = output
        self.last_output_label = f"{'✔' if success else '✖'} {label}" if label else ""
        head, tail, hidden = collapse_output(output)
        for text in head:
            self._guide(text)
        if hidden:
            note = Text(no_wrap=True)
            note.append("  │ ", style="rule")
            note.append(f"+{hidden} linhas ocultas", style="accent_blue")
            note.append("  ·  Alt+E expande", style="faint")
            self._print(note)
        for text in tail:
            self._guide(text)

    def _guide(self, text: str, style: str = "text_dim") -> None:
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append("  │ ", style="rule")
        line.append(text, style=style)
        self._print(line)

    # ── Expansão sob demanda ────────────────────────────────────────

    def expand_reasoning(self) -> None:
        """Imprime o último raciocínio com guia vertical."""
        if not self.last_reasoning.strip():
            self._print(Text("Nenhum raciocínio nesta sessão.", style="text_dim"))
            return
        for text in self.last_reasoning.rstrip().splitlines():
            self._guide(text)

    def expand_output(self) -> None:
        """Imprime a última saída de ferramenta sem colapso."""
        if not self.last_output.strip():
            self._print(Text("Nenhuma saída de ferramenta nesta sessão.", style="text_dim"))
            return
        header = Text(no_wrap=True, overflow="ellipsis")
        header.append(self.last_output_label or "Saída", style="text_primary")
        header.append(" · saída completa", style="text_dim")
        self._print(header)
        for text in self.last_output.rstrip().splitlines():
            self._guide(text)

    def decision(self, approved: bool, note: str = "") -> None:
        """Registra no histórico a decisão do Senhor sobre uma autorização PEP (V-13)."""
        line = Text("  ")
        if approved:
            line.append("✔ aprovado", style="status_ok")
        else:
            line.append("✖ negado", style="diff_del")
        if note:
            line.append(f" · {note}", style="text_dim")
        self._print(line)

    def agent_line(self, text: str, *, style: str = "text_dim") -> None:
        """Uma linha compacta de progresso de subagent (sem Live próprio)."""
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append("› ", style="accent_cyan")
        line.append(text, style=style)
        self._print(line)

    def warn(self, message: str) -> None:
        """Aviso não fatal (ex.: failover de provedor); não encerra o Live."""
        line = Text()
        line.append("! ", style="text_primary")
        line.append(message, style="text_primary")
        self._print(line)

    def error(self, message: str) -> None:
        """Encerra o Live e mostra um erro operacional."""
        self.close()
        line = Text()
        line.append("✖ ", style="diff_del")
        line.append(message, style="text_primary")
        self._print(line)
