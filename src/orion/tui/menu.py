"""
O.R.I.O.N TUI — Menu de autocompletar Horizon (v0.5.1, ADR-039).

Linha ativa com fundo ``sel``, ``❯`` e nome em ciano negrito; descrição em cinza; categoria à
direita; rodapé com atalhos e posição ``n/N`` no lugar das setas ASCII de rolagem.
"""

from __future__ import annotations

from prompt_toolkit.application import get_app
from prompt_toolkit.completion import Completion
from prompt_toolkit.data_structures import Point
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.layout.controls import UIContent, UIControl
from prompt_toolkit.utils import get_cwidth

MENU_MAX_WIDTH = 80
MENU_MAX_HEIGHT = 8
_MARK = 3  # " ❯ " ou "   "
_CATEGORY_WIDTH = 10  # inclui um espaço à direita da borda do menu

CATEGORY_LABELS = {
    "cognitive": "cognitivo",
    "memory": "memória",
    "context": "contexto",
    "operation": "operação",
    "extension": "extensão",
    "general": "geral",
}


class OrionCompletion(Completion):
    """``Completion`` com a categoria do comando (para a coluna da direita)."""

    def __init__(self, *args: object, category: str = "", **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.category = category


def _fit(text: str, width: int) -> str:
    """Corta com reticências e completa com espaços até *width* células."""
    if width <= 0:
        return ""
    if get_cwidth(text) > width:
        out = ""
        for ch in text:
            if get_cwidth(out + ch) > width - 1:
                break
            out += ch
        text = out + "…"
    return text + " " * max(width - get_cwidth(text), 0)


def menu_width(available: int) -> int:
    return max(min(available, MENU_MAX_WIDTH), 20)


class OrionCompletionsMenuControl(UIControl):
    """Desenha o menu de autocompletar do buffer atual (substitui o ``CompletionsMenuControl``)."""

    def has_focus(self) -> bool:
        return False

    def preferred_width(self, max_available_width: int) -> int | None:
        return menu_width(max_available_width)

    def preferred_height(
        self, width: int, max_available_height: int, wrap_lines: bool, get_line_prefix: object
    ) -> int | None:
        state = get_app().current_buffer.complete_state
        return len(state.completions) if state else 0

    def create_content(self, width: int, height: int) -> UIContent:
        state = get_app().current_buffer.complete_state
        if not state:
            return UIContent()
        completions = state.completions
        index = state.complete_index
        name_width = min(max((get_cwidth(c.display_text) for c in completions), default=0) + 2, 20)
        has_category = any(getattr(c, "category", "") for c in completions)
        category_width = _CATEGORY_WIDTH if has_category else 0
        meta_width = max(width - _MARK - name_width - category_width - 1, 0)

        def get_line(i: int) -> StyleAndTextTuples:
            completion = completions[i]
            current = i == index
            suffix = ".current" if current else ""
            category = CATEGORY_LABELS.get(getattr(completion, "category", ""), "")
            label = _fit(category, category_width).rstrip().rjust(category_width)
            return [
                (f"class:completion-menu.mark{suffix}", " ❯ " if current else "   "),
                (f"class:completion-menu.name{suffix}", _fit(completion.display_text, name_width)),
                (f"class:completion-menu.desc{suffix}", _fit(completion.display_meta_text, meta_width)),
                (f"class:completion-menu.desc{suffix}", " "),  # respiro entre descrição e categoria
                (f"class:completion-menu.category{suffix}", label),
            ]

        return UIContent(
            get_line=get_line,
            cursor_position=Point(x=0, y=index or 0),
            line_count=len(completions),
        )


def menu_footer() -> StyleAndTextTuples:
    """``↑↓ navegar · Tab próximo · Esc fechar`` e a posição ``n/N`` à direita."""
    app = get_app()
    state = app.current_buffer.complete_state
    total = len(state.completions) if state else 0
    position = (state.complete_index or 0) + 1 if state and state.complete_index is not None else 0
    width = menu_width(app.output.get_size().columns)
    left = " ↑↓ navegar  ·  Tab próximo  ·  Esc fechar"
    right = f"{position}/{total} " if total else ""
    gap = max(width - get_cwidth(left) - get_cwidth(right), 1)
    return [("class:completion-menu.footer", left + " " * gap + right)]
