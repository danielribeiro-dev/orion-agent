"""Console Rich que escreve na transcrição da tela cheia (ADR-043).

Comandos (``context.console.print``), modais e avisos da sessão continuam chamando a API do Rich;
aqui cada ``print`` vira uma célula com os renderables originais, para que a quebra seja refeita
quando a largura mudar. ``clear`` limpa a transcrição e ``status`` vira a linha de atividade.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable, Iterator
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.style import Style
from rich.styled import Styled
from rich.text import Text

from orion.tui.screen.transcript import Transcript
from orion.tui.theme import get_orion_theme


class TranscriptConsole(Console):
    """``rich.Console`` cujo destino é uma :class:`Transcript`."""

    def __init__(self, transcript: Transcript, width: int = 100, height: int = 30) -> None:
        super().__init__(
            file=io.StringIO(),
            theme=get_orion_theme(),
            force_terminal=True,
            color_system="truecolor",
            width=width,
            height=height,
            legacy_windows=False,
        )
        self.transcript = transcript
        self.on_status: Callable[[str | None], None] | None = None
        self.on_clear: Callable[[], None] | None = None

    def print(self, *objects: Any, **kwargs: Any) -> None:
        style = kwargs.get("style")
        if not objects:
            renderables: list[RenderableType] = [Text("")]
        else:
            renderables = list[RenderableType](self._collect_renderables(
                objects,
                sep=str(kwargs.get("sep", " ")),
                end=str(kwargs.get("end", "\n")),
                justify=kwargs.get("justify"),
                emoji=kwargs.get("emoji"),
                markup=kwargs.get("markup"),
                highlight=kwargs.get("highlight"),
            ))
        if style is not None:
            resolved = self.get_style(style) if isinstance(style, str) else style
            if isinstance(resolved, Style):
                renderables = [Styled(Group(*renderables), resolved)]
        self.transcript.add_renderables("print", *renderables)

    def clear(self, home: bool = True) -> None:
        if self.on_clear is not None:
            self.on_clear()
        else:
            self.transcript.clear()

    @contextlib.contextmanager
    def status(self, status: Any = "", *args: Any, **kwargs: Any) -> Iterator[None]:  # type: ignore[override]
        text = status.plain if isinstance(status, Text) else str(status)
        if self.on_status is not None:
            self.on_status(Text.from_markup(text).plain)
        try:
            yield None
        finally:
            if self.on_status is not None:
                self.on_status(None)

    def input(self, *args: Any, **kwargs: Any) -> str:
        raise RuntimeError("entrada direta indisponível na tela cheia; use o host de modais")
