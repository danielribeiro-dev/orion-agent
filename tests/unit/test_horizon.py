"""v0.5.1 Sprint 2 — identidade Horizon (ADR-039): tokens, cabeçalho, dica, status, menu, cor."""

from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from prompt_toolkit.document import Document
from rich.console import Console

from orion.tui.banner import BannerRenderer, render_hint
from orion.tui.completer import SlashCommandCompleter
from orion.tui.menu import OrionCompletion, OrionCompletionsMenuControl, _fit, menu_footer
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import ORION_COLORS, color_depth, get_orion_theme


def _lum(hex_color: str) -> float:
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    rgb = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class TestTokens:
    def test_new_tokens_and_contrast(self) -> None:
        bg = ORION_COLORS["bg_canvas"]
        assert _contrast(ORION_COLORS["rule"], bg) >= 3.0
        assert _contrast(ORION_COLORS["faint"], bg) >= 4.5
        assert _contrast(ORION_COLORS["faint"], ORION_COLORS["surface_panel"]) >= 4.5
        assert _contrast(ORION_COLORS["text_dim"], ORION_COLORS["sel"]) >= 4.5
        theme = get_orion_theme()
        assert {"rule", "faint", "sel"} <= set(theme.styles)


def _render(renderable: object, width: int) -> list[str]:
    buf = io.StringIO()
    Console(file=buf, width=width, force_terminal=False, theme=get_orion_theme()).print(renderable)
    return buf.getvalue().splitlines()


class TestHeader:
    @pytest.mark.parametrize("width", [110, 80, 60])
    def test_no_line_exceeds_width(self, width: int) -> None:
        bar = SessionStatusBar(model_name="claude-sonnet-5-5", workspace_path="/tmp/" + "x" * 80)
        lines = _render(BannerRenderer(status_bar=bar).render(terminal_width=width), width)
        assert all(len(line) <= width for line in lines), lines
        assert len(lines) <= 12

    def test_wide_puts_information_beside_the_logo(self) -> None:
        bar = SessionStatusBar(model_name="claude-sonnet-5-5")
        lines = _render(bar.render_header_panel(width=110), 110)
        assert len(lines) == 6
        assert "O.R.I.O.N" in lines[1] and "██" in lines[1]
        assert "online" in lines[4] and "claude-sonnet-5-5" in lines[4]
        assert "PEP 2 supervisionado" in lines[5]

    def test_no_provider_is_a_neutral_warning(self) -> None:
        bar = SessionStatusBar(is_online=False, model_name="qwen")
        text = "\n".join(_render(bar.render_header_panel(width=110), 110))
        assert "sem chave de provedor · /config" in text
        assert "OFFLINE" not in text


class TestHint:
    @pytest.mark.parametrize(
        ("width", "present", "absent"),
        [(110, "Alt+T", ""), (90, "Shift+Tab", "Alt+T"), (60, "@ arquivos", "Ctrl+C")],
    )
    def test_variants_fit(self, width: int, present: str, absent: str) -> None:
        hint = render_hint(width)
        assert len(hint.plain) <= width
        assert present in hint.plain
        if absent:
            assert absent not in hint.plain


class TestStatusLine:
    def _text(self, bar: SessionStatusBar, width: int = 120) -> str:
        return "".join(part for _, part in bar.status_segments(width))

    def test_states(self) -> None:
        bar = SessionStatusBar(model_name="m")
        assert self._text(bar).endswith("Pronto ●")
        bar.is_busy = True
        assert self._text(bar).endswith("Trabalhando ●")
        bar.awaiting = True
        assert self._text(bar).endswith("Aguardando ●")
        assert ("pep", "●") in bar.status_segments(120)

    def test_context_and_effort(self) -> None:
        bar = SessionStatusBar(model_name="m", context_pct=24)
        assert "m · 24% ctx · US$ 0,000 · PEP 2" in self._text(bar)
        from orion.tui.status_bar import ReasoningEffort

        bar.reasoning_effort = ReasoningEffort.LOW
        assert "esforço baixo" in self._text(bar)  # Alt+T continua visível fora do padrão


class TestCompleter:
    def test_prefix_ordered_by_category_with_category_attached(self) -> None:
        completer = SlashCommandCompleter()
        items = list(completer.get_completions(Document("/c", 2)))
        names = [c.text for c in items]
        prefix = [n for n in names if n.startswith("/c")]
        assert names[: len(prefix)] == prefix  # prefixo antes de fuzzy
        assert all(isinstance(c, OrionCompletion) for c in items)
        assert all(not c.display_text.startswith(("❯", "●", "›")) for c in items)
        order = {"cognitive": 0, "memory": 1, "context": 2, "operation": 3}
        cats = [order.get(c.category, 9) for c in items[: len(prefix)]]
        assert cats == sorted(cats)


class TestMenu:
    def test_fit(self) -> None:
        assert _fit("abc", 5) == "abc  "
        assert _fit("abcdef", 4) == "abc…"
        assert _fit("x", 0) == ""

    def _app(self, completions: list[OrionCompletion], index: int | None) -> SimpleNamespace:
        state = SimpleNamespace(completions=completions, complete_index=index)
        return SimpleNamespace(
            current_buffer=SimpleNamespace(complete_state=state),
            output=SimpleNamespace(get_size=lambda: SimpleNamespace(columns=100)),
        )

    def test_current_row_is_marked_and_categorized(self) -> None:
        items = [
            OrionCompletion("/plan", display="/plan", display_meta="Planejar", category="cognitive"),
            OrionCompletion("/cost", display="/cost", display_meta="Custos", category="operation"),
        ]
        app = self._app(items, 1)
        with patch("orion.tui.menu.get_app", return_value=app):
            content = OrionCompletionsMenuControl().create_content(78, 8)
            current = "".join(text for _, text in content.get_line(1))
            other = "".join(text for _, text in content.get_line(0))
            footer = "".join(text for _, text in menu_footer())
        assert current.startswith(" ❯ /cost") and "operação" in current
        assert other.startswith("   /plan") and "cognitivo" in other
        assert len(current) == 78
        assert "Esc fechar" in footer and footer.rstrip().endswith("2/2")
        styles = [style for style, _ in content.get_line(1)]
        assert any(style.endswith(".current") for style in styles)


class TestColorDepth:
    def test_rules(self) -> None:
        assert color_depth({"COLORTERM": "truecolor"}) == "truecolor"
        assert color_depth({"COLORTERM": "24bit"}) == "truecolor"
        assert color_depth({"TERM": "xterm-256color"}) == "256"
        assert color_depth({"COLORTERM": "truecolor", "NO_COLOR": "1"}) == "none"
        assert color_depth({"COLORTERM": "truecolor"}, is_tty=False) == "none"


def test_no_emoji_in_source() -> None:
    """Regra 1 de CLI_AGENT_RULES.md: nenhum emoji em src/ (glifos oficiais são permitidos)."""
    import re
    from pathlib import Path

    bad = re.compile(r"[\U0001F300-\U0001FAFF☀-⛿✅❌❎❓-❗️]")
    root = Path(__file__).resolve().parents[2] / "src" / "orion"
    hits = [
        f"{path.relative_to(root)}:{n}"
        for path in root.rglob("*.py")
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if bad.search(line)
    ]
    assert hits == []
