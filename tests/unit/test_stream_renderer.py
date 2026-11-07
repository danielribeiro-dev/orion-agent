"""Unit tests for src/orion/tui/stream_renderer.py"""

from __future__ import annotations

import io

from rich.console import Console

from orion.tui.diff_viewer import diff_texts
from orion.tui.stream_renderer import (
    StreamRenderer,
    collapse_output,
    format_tool_label,
    split_committable,
)
from orion.tui.theme import get_orion_theme


def _renderer(width: int = 100) -> tuple[StreamRenderer, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, width=width, theme=get_orion_theme(), force_terminal=False)
    return StreamRenderer(console), buf


class TestSplitCommittable:
    def test_commits_up_to_last_blank_line(self) -> None:
        assert split_committable("a\n\nb") == ("a\n\n", "b")

    def test_keeps_open_fence_together(self) -> None:
        text = "```py\na\n\nb\n"
        assert split_committable(text) == ("", text)

    def test_closed_fence_can_commit(self) -> None:
        text = "```py\na\n```\n\nfim"
        assert split_committable(text)[1] == "fim"

    def test_no_blank_line_keeps_all(self) -> None:
        assert split_committable("abc") == ("", "abc")


class TestCollapse:
    def test_five_lines_stay_inline(self) -> None:
        head, tail, hidden = collapse_output("\n".join("12345"))
        assert (len(head), tail, hidden) == (5, [], 0)

    def test_six_lines_collapse_to_three_and_two(self) -> None:
        head, tail, hidden = collapse_output("\n".join("123456"))
        assert (head, tail, hidden) == (["1", "2", "3"], ["5", "6"], 1)


class TestLabels:
    def test_bash(self) -> None:
        assert format_tool_label("run_command", {"command": "ls  -a\n"}) == "Bash: ls -a"

    def test_unknown_tool(self) -> None:
        assert format_tool_label("x", {}) == "x"


class TestStreaming:
    def test_500_tokens_with_incomplete_markdown(self) -> None:
        renderer, buf = _renderer()
        renderer.begin_thinking()
        for index in range(500):
            renderer.add_text("**pal" if index % 7 == 0 else f"tok{index} `x")
            if index % 50 == 0:
                renderer.add_text("\n\n")
        renderer.close()
        assert "tok499" in buf.getvalue()

    def test_each_block_is_printed_once(self) -> None:
        renderer, buf = _renderer()
        renderer.add_text("primeiro\n\nsegundo\n\nterceiro")
        renderer.close()
        output = buf.getvalue()
        for word in ("primeiro", "segundo", "terceiro"):
            assert output.count(word) == 1

    def test_code_block_has_rounded_border(self) -> None:
        renderer, buf = _renderer()
        renderer.add_text("```python\nprint(1)\n```\n")
        renderer.close()
        assert "╭" in buf.getvalue()

    def test_reasoning_collapses_and_expands(self) -> None:
        renderer, buf = _renderer()
        renderer.begin_thinking()
        renderer.add_reasoning("linha secreta")
        renderer.add_text("resposta")
        renderer.close()
        output = buf.getvalue()
        assert "Raciocínio formulado" in output
        assert "Alt+R" in output
        assert "linha secreta" not in output
        renderer.expand_reasoning()
        assert "│ linha secreta" in buf.getvalue()

    def test_no_reasoning_prints_no_marker(self) -> None:
        renderer, buf = _renderer()
        renderer.begin_thinking()
        renderer.add_text("oi")
        renderer.close()
        assert "Raciocínio" not in buf.getvalue()


class TestToolCards:
    def test_success_card_with_exit_code(self) -> None:
        renderer, buf = _renderer()
        renderer.tool_started("run_command", {"command": "pytest"})
        renderer.tool_finished("run_command", True, "ok", {"exit_code": 0})
        renderer.close()
        output = buf.getvalue()
        assert "✔ Bash: pytest" in output
        assert "exit 0" in output
        assert "│ ok" in output

    def test_error_card(self) -> None:
        renderer, buf = _renderer()
        renderer.tool_started("run_command", {"command": "make"})
        renderer.tool_finished("run_command", False, "boom", {"exit_code": 2})
        renderer.close()
        assert "✖ Bash: make" in buf.getvalue()

    def test_long_output_collapses_and_expands(self) -> None:
        renderer, buf = _renderer()
        output_text = "\n".join(f"l{i}" for i in range(20))
        renderer.tool_started("run_command", {"command": "x"})
        renderer.tool_finished("run_command", True, output_text)
        renderer.close()
        assert "+15 linhas ocultas" in buf.getvalue()
        assert "l10" not in buf.getvalue()
        renderer.expand_output()
        assert "l10" in buf.getvalue()

    def test_read_does_not_dump_file(self) -> None:
        renderer, buf = _renderer()
        renderer.tool_started("read_file", {"path": "a.py"})
        renderer.tool_finished("read_file", True, "conteudo")
        renderer.close()
        assert "conteudo" not in buf.getvalue()

    def test_edit_shows_diff_panel(self) -> None:
        renderer, buf = _renderer()
        renderer.tool_started("edit_file", {"path": "a.py"})
        renderer.tool_finished("edit_file", True, "", diff=diff_texts("a\n", "b\n", "a.py"))
        renderer.close()
        assert "+1 / -1" in buf.getvalue()

    def test_pause_and_resume_keep_activity(self) -> None:
        renderer, _ = _renderer()
        renderer.tool_started("run_command", {"command": "x"})
        renderer.pause()
        assert renderer._live is None
        renderer.resume()
        assert renderer._live is not None
        renderer.close()
        assert renderer._live is None


class TestBlockSpacing:
    def test_blank_line_between_text_and_tool(self) -> None:
        renderer, buf = _renderer()
        renderer.add_text("texto")
        renderer.tool_started("read_file", {"path": "a"})
        renderer.tool_finished("read_file", True)
        renderer.close()
        lines = [line.rstrip() for line in buf.getvalue().splitlines()]
        assert lines[lines.index("texto") + 1] == ""

    def test_consecutive_tools_stay_together(self) -> None:
        renderer, buf = _renderer()
        for name in ("a", "b"):
            renderer.tool_started("read_file", {"path": name})
            renderer.tool_finished("read_file", True)
        renderer.close()
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        assert buf.getvalue().count("\n") == len(lines) + 1  # só a linha antes do primeiro card
