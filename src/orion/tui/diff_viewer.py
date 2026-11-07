"""
O.R.I.O.N TUI — Surgical Diff Viewer.

Converte diffs unificados em painéis Rich com números de linha, resumo +X / -Y,
realce sintático e tinta de fundo restrita à largura do painel.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

from rich import box
from rich.console import Console, ConsoleOptions, RenderResult
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from orion.tui.theme import get_syntax_theme

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")


@dataclass(frozen=True)
class DiffLine:
    """Uma linha do diff: kind é add, del ou ctx."""

    kind: str
    old_no: int | None
    new_no: int | None
    text: str


@dataclass
class DiffHunk:
    """Bloco @@ do diff."""

    header: str
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class FileDiff:
    """Diff completo de um arquivo."""

    path: str
    hunks: list[DiffHunk] = field(default_factory=list)

    @property
    def added(self) -> int:
        return sum(1 for h in self.hunks for ln in h.lines if ln.kind == "add")

    @property
    def removed(self) -> int:
        return sum(1 for h in self.hunks for ln in h.lines if ln.kind == "del")


def parse_unified_diff(text: str, path: str = "") -> FileDiff:
    """Faz o parsing de um diff unificado de um único arquivo."""
    result = FileDiff(path=path)
    hunk: DiffHunk | None = None
    old_no = new_no = 0

    for raw in text.splitlines():
        if raw.startswith("+++ "):
            if not result.path:
                result.path = raw[4:].split("\t")[0].removeprefix("b/")
            continue
        if raw.startswith("--- ") and hunk is None:
            continue
        match = _HUNK_RE.match(raw)
        if match:
            old_no, new_no = int(match.group(1)), int(match.group(2))
            hunk = DiffHunk(header=raw)
            result.hunks.append(hunk)
            continue
        if hunk is None or raw.startswith("\\"):
            continue
        marker, body = raw[:1], raw[1:]
        if marker == "+":
            hunk.lines.append(DiffLine("add", None, new_no, body))
            new_no += 1
        elif marker == "-":
            hunk.lines.append(DiffLine("del", old_no, None, body))
            old_no += 1
        else:
            hunk.lines.append(DiffLine("ctx", old_no, new_no, body))
            old_no += 1
            new_no += 1
    return result


def diff_texts(before: str, after: str, path: str) -> FileDiff:
    """Calcula o diff entre dois conteúdos de arquivo."""
    lines = difflib.unified_diff(
        before.splitlines(), after.splitlines(), fromfile=path, tofile=path, lineterm=""
    )
    return parse_unified_diff("\n".join(lines), path=path)


class _DiffBody:
    """Corpo do painel: conhece a largura real para pintar a tinta até a borda."""

    def __init__(self, diff: FileDiff) -> None:
        self.diff = diff
        try:
            lexer = Syntax.guess_lexer(diff.path)
        except Exception:
            lexer = "text"
        self._lexer = lexer
        self._theme = get_syntax_theme()

    def _code(self, source: str) -> Text:
        if not source:
            return Text()
        syntax = Syntax(source, self._lexer, theme=self._theme, background_color="default")
        highlighted = syntax.highlight(source)
        highlighted.rstrip()
        return highlighted

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        for hunk in self.diff.hunks:
            yield Text(hunk.header, style="accent_blue", no_wrap=True)
            for line in hunk.lines:
                old = str(line.old_no) if line.old_no is not None else ""
                new = str(line.new_no) if line.new_no is not None else ""
                sign = {"add": "+", "del": "-", "ctx": " "}[line.kind]
                row = Text(no_wrap=True, overflow="ellipsis")
                row.append(f"{old:>4} {new:>4} ", style="text_dim")
                row.append(f"{sign} ", style={"add": "diff_add", "del": "diff_del"}.get(line.kind, ""))
                row.append_text(self._code(line.text))
                row.truncate(width, overflow="ellipsis", pad=True)
                if line.kind != "ctx":
                    row.stylize(f"diff_{line.kind}_line")
                yield row


class DiffViewer:
    """Renderizador de painéis de diff do Design System."""

    def render(self, diff: FileDiff) -> Panel:
        """Gera o painel do diff com título `caminho +X / -Y`."""
        title = Text()
        title.append(f" {self._display_path(diff.path)} ", style="text_primary")
        title.append(f"+{diff.added}", style="diff_add")
        title.append(" / ", style="text_dim")
        title.append(f"-{diff.removed}", style="diff_del")
        title.append(" ")
        return Panel(
            _DiffBody(diff),
            title=title,
            title_align="left",
            box=box.ROUNDED,
            border_style="border_subtle",
            padding=(0, 1),
        )

    @staticmethod
    def _display_path(path: str) -> str:
        try:
            return str(Path(path).resolve().relative_to(Path.cwd()))
        except ValueError:
            return path
