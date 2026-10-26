"""
Unit tests for O.R.I.O.N TUI Theme and Design System ("Deep Cosmos & Glacial Platinum").
"""

from __future__ import annotations

import re

from rich.console import Console
from rich.theme import Theme

from orion.tui.console import get_console, reset_console
from orion.tui.theme import ORION_COLORS, get_orion_theme


class TestOrionColors:
    """Valida a fidelidade das constantes do Design System."""

    def test_all_official_colors_present(self) -> None:
        required_keys = [
            "bg_canvas",
            "surface_panel",
            "border_subtle",
            "text_primary",
            "text_dim",
            "text_user",
            "accent_cyan",
            "accent_blue",
            "diff_add",
            "diff_del",
            "pep_warn",
            "status_ok",
            "status_offline",
        ]
        for key in required_keys:
            assert key in ORION_COLORS, f"Cor obrigatória ausente: {key}"

    def test_color_hex_formats_valid(self) -> None:
        hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
        for name, val in ORION_COLORS.items():
            assert hex_pattern.match(val), f"Formato hex inválido para {name}: {val}"

    def test_palette_values_exact(self) -> None:
        assert ORION_COLORS["bg_canvas"] == "#0B0E14"
        assert ORION_COLORS["surface_panel"] == "#151B23"
        assert ORION_COLORS["border_subtle"] == "#262F3D"
        assert ORION_COLORS["text_primary"] == "#E6EDF3"
        assert ORION_COLORS["text_dim"] == "#8B949E"
        assert ORION_COLORS["text_user"] == "#F0F6FC"
        assert ORION_COLORS["accent_cyan"] == "#00D2FF"
        assert ORION_COLORS["accent_blue"] == "#3A7BD5"
        assert ORION_COLORS["diff_add"] == "#3FB950"
        assert ORION_COLORS["diff_del"] == "#F85149"
        assert ORION_COLORS["pep_warn"] == "#D29922"
        assert ORION_COLORS["status_ok"] == "#2EA043"
        assert ORION_COLORS["status_offline"] == "#DA3633"


class TestOrionTheme:
    """Valida o mapeamento do Theme do Rich."""

    def test_get_orion_theme_returns_theme_instance(self) -> None:
        theme = get_orion_theme()
        assert isinstance(theme, Theme)

    def test_semantic_styles_registered(self) -> None:
        theme = get_orion_theme()
        expected_styles = [
            "orion.bg",
            "orion.panel",
            "orion.border",
            "orion.text",
            "orion.text_dim",
            "orion.text_user",
            "orion.cyan",
            "orion.blue",
            "orion.diff_add",
            "orion.diff_del",
            "orion.pep_warn",
            "orion.status_ok",
            "orion.status_offline",
        ]
        for style_name in expected_styles:
            assert style_name in theme.styles, f"Estilo Rich ausente no tema: {style_name}"


class TestOrionConsole:
    """Valida o singleton do console e sua configuração."""

    def test_get_console_singleton(self) -> None:
        reset_console()
        c1 = get_console()
        c2 = get_console()
        assert c1 is c2
        assert isinstance(c1, Console)

    def test_get_console_force_terminal(self) -> None:
        c = get_console(force_terminal=True)
        assert c.is_terminal is True

    def test_reset_console(self) -> None:
        reset_console()
        c1 = get_console()
        reset_console()
        c2 = get_console()
        assert c1 is not c2
