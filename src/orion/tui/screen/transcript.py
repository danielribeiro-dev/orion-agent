"""Transcrição da tela cheia como lista de células (ADR-043).

Cada célula guarda renderables Rich (não texto já impresso): a largura muda e as linhas são
refeitas (reflow), um bloco recolhido abre no lugar, e só a parte visível é desenhada. As linhas
de cada célula ficam em cache por largura e estado; a tela soma alturas e recorta de baixo para cima.
"""

from __future__ import annotations

import io
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from prompt_toolkit.formatted_text import StyleAndTextTuples
from rich.console import Console, Group, RenderableType
from rich.style import Style
from rich.text import Text

from orion.tui.theme import get_orion_theme

Line = StyleAndTextTuples

_consoles: dict[int, Console] = {}


def render_console(width: int) -> Console:
    """Console de rasterização (sem terminal) com o tema do ORION, um por largura."""
    console = _consoles.get(width)
    if console is None:
        console = Console(
            file=io.StringIO(),
            theme=get_orion_theme(),
            force_terminal=True,
            color_system="truecolor",
            width=max(width, 10),
            legacy_windows=False,
        )
        _consoles[width] = console
    return console


_style_cache: dict[Style | None, str] = {}


def pt_style(style: Style | None) -> str:
    """Estilo Rich → string de estilo do prompt_toolkit (cor exata, negrito, itálico...)."""
    cached = _style_cache.get(style)
    if cached is not None:
        return cached
    parts: list[str] = []
    if style is not None:
        if style.color is not None and not style.color.is_default:
            parts.append(style.color.get_truecolor().hex)
        if style.bgcolor is not None and not style.bgcolor.is_default:
            parts.append("bg:" + style.bgcolor.get_truecolor().hex)
        for attr in ("bold", "italic", "underline", "strike", "reverse"):
            value = getattr(style, attr)
            if value is True:
                parts.append(attr)
            elif value is False:
                parts.append("no" + attr)
    result = " ".join(parts)
    _style_cache[style] = result
    return result


def rasterize(renderables: Sequence[RenderableType], width: int) -> list[Line]:
    """Renderiza na largura dada e converte cada linha em fragmentos do prompt_toolkit."""
    if not renderables:
        return []
    console = render_console(width)
    target: RenderableType = renderables[0] if len(renderables) == 1 else Group(*renderables)
    lines = console.render_lines(target, console.options.update_width(width), pad=False)
    out: list[Line] = []
    for segments in lines:
        out.append([(pt_style(seg.style), seg.text) for seg in segments if seg.text and not seg.control])
    return out


def plain(lines: Iterable[Line]) -> str:
    """Texto puro das linhas (testes, busca, despejo no scrollback)."""
    return "\n".join("".join(frag[1] for frag in line).rstrip() for line in lines)


@dataclass(eq=False)
class Cell:
    """Um bloco da conversa: pedido, raciocínio, texto, ferramenta, saída, aviso..."""

    kind: str
    body: Sequence[RenderableType]
    expanded: Sequence[RenderableType] | None = None
    """Versão aberta (blocos recolhíveis); ``None``: a célula não recolhe."""
    collapsed: bool = True
    meta: dict[str, Any] = field(default_factory=dict)
    _cache: dict[tuple[int, bool], list[Line]] = field(default_factory=dict, repr=False)

    @property
    def collapsible(self) -> bool:
        return self.expanded is not None

    def toggle(self) -> bool:
        """Abre ou fecha no lugar; devolve o novo estado (True = recolhido)."""
        if self.expanded is None:
            return self.collapsed
        self.collapsed = not self.collapsed
        return self.collapsed

    def renderables(self) -> Sequence[RenderableType]:
        if self.expanded is not None and not self.collapsed:
            return self.expanded
        return self.body

    def lines(self, width: int) -> list[Line]:
        key = (width, self.collapsed)
        cached = self._cache.get(key)
        if cached is None:
            cached = rasterize(self.renderables(), width)
            if len(self._cache) > 8:
                self._cache.clear()
            self._cache[key] = cached
        return cached

    def invalidate(self) -> None:
        self._cache.clear()


class Transcript:
    """Lista de células com trava (a sessão pode escrever de outras threads) e aviso de mudança."""

    def __init__(self) -> None:
        self.cells: list[Cell] = []
        self._lock = threading.RLock()
        self.on_change: Callable[[], None] | None = None
        self.version = 0
        self.toggled = False
        """A última mudança foi abrir/fechar um bloco (não conta como conteúdo novo)."""

    def _changed(self, toggled: bool = False) -> None:
        self.toggled = toggled
        self.version += 1
        if self.on_change is not None:
            self.on_change()

    def add(self, cell: Cell) -> Cell:
        with self._lock:
            self.cells.append(cell)
        self._changed()
        return cell

    def add_renderables(self, kind: str, *renderables: RenderableType, **meta: Any) -> Cell:
        return self.add(Cell(kind, list(renderables) or [Text("")], meta=dict(meta)))

    def clear(self) -> None:
        with self._lock:
            self.cells.clear()
        self._changed()

    def last(self, kind: str) -> Cell | None:
        with self._lock:
            for cell in reversed(self.cells):
                if cell.kind == kind:
                    return cell
        return None

    def toggle_last(self, kind: str) -> Cell | None:
        cell = self.last(kind)
        if cell is not None and cell.collapsible:
            cell.toggle()
            self._changed(toggled=True)
        return cell

    def toggle(self, cell: Cell) -> None:
        if cell.collapsible:
            cell.toggle()
            self._changed(toggled=True)

    def snapshot(self) -> list[Cell]:
        with self._lock:
            return list(self.cells)

    def total_lines(self, width: int) -> int:
        return sum(len(cell.lines(width)) for cell in self.snapshot())

    def window(
        self, width: int, height: int, offset: int, tail: list[Line] | None = None
    ) -> tuple[list[Line], list[Cell | None], int]:
        """As *height* linhas que terminam *offset* linhas acima do fim (0 = segue o fim).

        Devolve as linhas, a célula de cada linha (para o clique) e o total de linhas. *tail* são
        as linhas da parte viva (não ficam em cache), sempre depois da última célula.
        """
        tail = tail or []
        need = height + offset
        lines: list[Line] = list(tail[-need:]) if need else []
        owners: list[Cell | None] = [None] * len(lines)
        total = len(tail)
        cells = self.snapshot()
        for index in range(len(cells) - 1, -1, -1):
            cell_lines = cells[index].lines(width)
            total += len(cell_lines)
            if len(lines) < need:
                take = cell_lines[-(need - len(lines)):] if need - len(lines) < len(cell_lines) else cell_lines
                lines = list(take) + lines
                owner: list[Cell | None] = [cells[index]] * len(take)
                owners = owner + owners
        end = len(lines) - offset if offset else len(lines)
        end = max(end, 0)
        start = max(end - height, 0)
        return lines[start:end], owners[start:end], total

