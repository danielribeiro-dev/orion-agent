"""Unit tests for src/orion/tui/diff_viewer.py"""

from __future__ import annotations

import io

from rich.console import Console

from orion.tui.diff_viewer import DiffViewer, diff_texts, parse_unified_diff
from orion.tui.theme import ORION_COLORS, get_orion_theme

SAMPLE = """--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +10,4 @@ class App
 keep
-old
+new
+extra
 tail
"""


def _render(diff, width: int = 80) -> str:  # type: ignore[no-untyped-def]
    buf = io.StringIO()
    console = Console(
        file=buf, width=width, theme=get_orion_theme(), force_terminal=True, color_system="truecolor"
    )
    console.print(DiffViewer().render(diff))
    return buf.getvalue()


class TestParsing:
    def test_counts_and_path(self) -> None:
        diff = parse_unified_diff(SAMPLE)
        assert diff.path == "src/app.py"
        assert (diff.added, diff.removed) == (2, 1)

    def test_line_numbers_follow_each_side(self) -> None:
        lines = parse_unified_diff(SAMPLE).hunks[0].lines
        assert [(ln.kind, ln.old_no, ln.new_no) for ln in lines] == [
            ("ctx", 10, 10),
            ("del", 11, None),
            ("add", None, 11),
            ("add", None, 12),
            ("ctx", 12, 13),
        ]

    def test_ignores_no_newline_marker(self) -> None:
        diff = parse_unified_diff("@@ -1 +1 @@\n-a\n\\ No newline at end of file\n+b\n", "x")
        assert len(diff.hunks[0].lines) == 2

    def test_diff_texts_identical_is_empty(self) -> None:
        assert diff_texts("a\n", "a\n", "x.py").hunks == []


class TestRendering:
    def test_title_has_summary(self) -> None:
        output = _render(diff_texts("a\n", "b\nc\n", "x.py"))
        assert "x.py" in output
        assert "+2" in output
        assert "-1" in output

    def test_tints_reach_the_panel_and_use_palette(self) -> None:
        output = _render(diff_texts("a\n", "b\n", "x.txt"))
        add = ORION_COLORS["diff_add_tint"].lstrip("#")
        rgb = ";".join(str(int(add[i : i + 2], 16)) for i in (0, 2, 4))
        assert f"48;2;{rgb}" in output

    def test_narrow_width_does_not_wrap(self) -> None:
        long_line = "x" * 200
        lines = _render(diff_texts("a\n", f"{long_line}\n", "x.txt"), width=60).splitlines()
        assert len(lines) == 5  # topo, hunk, -a, +xxx, base
