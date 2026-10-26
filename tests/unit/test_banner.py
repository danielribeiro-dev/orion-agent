"""
Unit tests for O.R.I.O.N TUI BannerRenderer.
Covers: CA-01 (Larguras de Terminal 60, 80, 100, 120, 200),
recorte adaptativo, gradiente cósmico e CA-04 (Zero Quebras ANSI).
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from rich.console import Console
from rich.text import Text

from orion.tui.banner import BannerRenderer
from orion.tui.status_bar import SessionStatusBar


class TestBannerRendererInit:
    """Valida a inicialização e carregamento de arte."""

    def test_default_init_loads_art(self) -> None:
        renderer = BannerRenderer()
        assert len(renderer.raw_lines) > 0
        assert isinstance(renderer.status_bar, SessionStatusBar)

    def test_nonexistent_path_fallback(self, tmp_path: Path) -> None:
        fake_path = tmp_path / "nonexistent-art.txt"
        renderer = BannerRenderer(ascii_art_path=fake_path)
        assert renderer.raw_lines == []
        # Renderização não deve falhar mesmo com arquivo ausente
        rendered = renderer.render(terminal_width=120)
        assert rendered is not None

    def test_load_art_exception_handling(self, tmp_path: Path, monkeypatch) -> None:
        test_file = tmp_path / "art.txt"
        test_file.write_text("hello")
        renderer = BannerRenderer(ascii_art_path=test_file)
        assert len(renderer.raw_lines) == 1

        def _raise_io(*args, **kwargs):
            raise PermissionError("Access denied")

        monkeypatch.setattr("builtins.open", _raise_io)
        renderer._load_art(test_file)
        assert renderer.raw_lines == []


class TestBannerRendererCA01Widths:
    """Valida o Critério de Aceite CA-01 (Larguras de Terminal 60, 80, 100, 120 e 200)."""

    @pytest.mark.parametrize("width", [60, 80, 100, 120, 200])
    def test_render_all_widths_no_overflow_and_no_index_error(self, width: int) -> None:
        renderer = BannerRenderer()
        buf = io.StringIO()
        console = Console(
            file=buf,
            width=width,
            force_terminal=True,
            _environ={"COLUMNS": str(width), "COLORTERM": "truecolor"},
        )
        rendered = renderer.render(terminal_width=width)
        console.print(rendered)

        lines = buf.getvalue().splitlines()
        assert len(lines) > 0
        for idx, line in enumerate(lines):
            visual_len = Text.from_ansi(line).cell_len
            assert visual_len <= width, (
                f"Largura {width}: linha {idx} estourou com tamanho visual {visual_len}"
            )

    def test_render_width_under_100_uses_compact_layout(self) -> None:
        renderer = BannerRenderer()
        buf = io.StringIO()
        console = Console(
            file=buf,
            width=80,
            force_terminal=True,
            _environ={"COLUMNS": "80", "COLORTERM": "truecolor"},
        )
        console.print(renderer.render(terminal_width=80))
        output = buf.getvalue()

        # Deve conter o bloco Stellar Cyber Block e dica compacta
        assert "██████╗" in output
        assert "GATEWAY" in output
        assert "MODEL" in output
        assert "Dica:" in output

    def test_render_width_100_or_above_uses_wide_gradient_layout(self) -> None:
        renderer = BannerRenderer()
        buf = io.StringIO()
        console = Console(
            file=buf,
            width=120,
            force_terminal=True,
            _environ={"COLUMNS": "120", "COLORTERM": "truecolor"},
        )
        console.print(renderer.render(terminal_width=120))
        output = buf.getvalue()

        # Deve conter o cabeçalho amplo e a dica completa
        assert "Operational Reasoning & Intelligence Orchestration Network" in output
        assert "Non Ducor, Duco" in output
        assert "TIMELINE" in output
        assert "Ctrl+C" in output


class TestBannerArtRenderer:
    """Valida a renderização isolada de arte ASCII (render_art)."""

    def test_render_art_compact(self) -> None:
        renderer = BannerRenderer()
        art = renderer.render_art(terminal_width=80)
        buf = io.StringIO()
        console = Console(
            file=buf,
            width=80,
            force_terminal=True,
            _environ={"COLUMNS": "80", "COLORTERM": "truecolor"},
        )
        console.print(art)
        output = buf.getvalue()
        assert "██████╗" in output

    def test_render_art_wide_gradient(self) -> None:
        renderer = BannerRenderer()
        art = renderer.render_art(terminal_width=120)
        buf = io.StringIO()
        console = Console(
            file=buf,
            width=120,
            force_terminal=True,
            color_system="truecolor",
            _environ={"COLUMNS": "120", "COLORTERM": "truecolor"},
        )
        console.print(art)
        raw = buf.getvalue()
        # Deve possuir códigos ANSI de cores TrueColor (RGB 38;2;r;g;bm)
        assert "\x1b[38;2;" in raw


class TestBannerZeroAnsiBreakagesCA04:
    """Valida o Critério de Aceite CA-04 (Zero Quebras ANSI)."""

    @pytest.mark.parametrize("width", [60, 80, 100, 120, 200])
    def test_no_broken_ansi_in_banner(self, width: int) -> None:
        renderer = BannerRenderer()
        buf = io.StringIO()
        console = Console(file=buf, width=width, force_terminal=True)
        console.print(renderer.render(terminal_width=width))
        raw = buf.getvalue()

        ansi_regex = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
        stripped = ansi_regex.sub("", raw)
        assert "\x1b" not in stripped, f"Sequência ANSI inválida encontrada para width {width}"
