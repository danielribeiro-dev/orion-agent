"""Linguagem de movimento (ADR-045, v0.5.2 Sprint 3): pensamento, escrita, erros, rodapé de turno,
status line, sinais do terminal e transcrição completa."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console
from rich.text import Text

from orion.tui.modal import _print_decision
from orion.tui.screen import terminal
from orion.tui.screen.console import TranscriptConsole
from orion.tui.screen.renderer import ScreenRenderer
from orion.tui.screen.transcript import Transcript, plain
from orion.tui.status_bar import ReasoningEffort, SessionStatusBar
from orion.tui.stream_renderer import (
    StreamRenderer,
    format_tokens,
    format_usd,
    friendly_tool_error,
)


def _classic() -> tuple[StreamRenderer, io.StringIO]:
    buf = io.StringIO()
    console = Console(file=buf, width=100, force_terminal=False)
    return StreamRenderer(console, effort=lambda: "low"), buf


def _screen() -> tuple[ScreenRenderer, Transcript]:
    transcript = Transcript()
    return ScreenRenderer(TranscriptConsole(transcript), transcript, effort=lambda: "high"), transcript


def test_number_formats_are_pt_br() -> None:
    assert format_tokens(412) == "412 tok"
    assert format_tokens(1200) == "1,2k tok"
    assert format_tokens(2000) == "2k tok"
    assert format_usd(0.005) == "US$ 0,0050"
    assert format_usd(1.5, 2) == "US$ 1,50"


def test_thinking_activity_shows_time_tokens_effort_and_ticker() -> None:
    renderer, _ = _classic()
    renderer.begin_thinking()
    assert renderer._activity is not None
    first = renderer._activity().plain
    assert first.startswith("Pensando · ") and "esforço baixo" in first and "Ctrl+C cancela" in first
    assert "[" not in first  # nada de "[high effort]" (N-06)
    assert renderer.thinking_ticker() is None
    renderer.add_reasoning("Primeiro leio o arquivo. Depois troco o f-string e rodo os testes do módulo.")
    line = renderer._activity().plain
    assert " tok" in line
    ticker = renderer.thinking_ticker()
    assert ticker is not None and ticker.plain.startswith("  │ Depois troco")
    renderer.add_reasoning(" palavra" * 60)
    long_ticker = renderer.thinking_ticker()
    assert long_ticker is not None and "palavra" in long_ticker.plain
    renderer.close()


def test_writing_activity_while_text_streams() -> None:
    renderer, _ = _classic()
    renderer.begin_thinking()
    renderer.add_text("primeira parte")
    assert renderer._activity is not None and renderer._activity().plain.startswith("Escrevendo · ")
    renderer.end_message()
    assert renderer._activity is None
    renderer.close()


def test_screen_renderer_uses_escape_hint_and_awaiting_state() -> None:
    renderer, _ = _screen()
    renderer.begin_thinking()
    renderer.add_reasoning("pensando bastante sobre o pedido do Senhor " * 3)
    parts = renderer.activity_renderables()
    assert len(parts) == 2  # spinner + linha viva do raciocínio
    assert "Esc interrompe" in renderer._activity().plain  # type: ignore[misc]
    renderer.tool_started("run_command", {"command": "ls"}, key="k")
    renderer.pause()
    waiting = renderer.activity_renderables()
    assert len(waiting) == 1 and "Aguardando autorização" in waiting[0].plain  # type: ignore[union-attr]
    renderer.resume()
    renderer.tool_finished("run_command", True, "a", {"exit_code": 0}, key="k")
    renderer.close()


def test_friendly_tool_error_and_summary_line() -> None:
    assert friendly_tool_error("Invalid parameters for 'edit_file': 'target' is a required property")
    assert friendly_tool_error("Unknown tool: xyz")
    assert friendly_tool_error("arquivo não encontrado") is None
    assert friendly_tool_error("") is None
    renderer, transcript = _screen()
    renderer.tool_started("edit_file", {"path": "a.py"}, key="e")
    renderer.tool_finished(
        "edit_file", False, "Invalid parameters for 'edit_file': 'target' is a required property", key="e"
    )
    text = plain(transcript.all_lines(100))
    assert "✖ Edit" in text and "parâmetros inválidos do modelo" in text
    assert "Invalid parameters" in text  # o detalhe continua visível na saída


def test_turn_summary_counts_tools_tokens_and_cost() -> None:
    renderer, transcript = _screen()
    for key in ("a", "b"):
        renderer.tool_started("read_file", {"path": "x"}, key=key)
        renderer.tool_finished("read_file", True, "1\n2", key=key)
    renderer.turn_summary(12.43, tokens=2100, cost_usd=0.005)
    last = plain(transcript.all_lines(100)).splitlines()[-1]
    assert last == "✔ 12,4s · 2 ferramentas · 2,1k tok · US$ 0,0050"
    renderer.turn_summary(1.0)
    assert plain(transcript.all_lines(100)).splitlines()[-1] == "✔ 1,0s"


def test_pep_decision_is_aligned_and_names_the_action_level() -> None:
    transcript = Transcript()
    console = TranscriptConsole(transcript)
    _print_decision(console, "y", level=3)
    _print_decision(console, "n", level=2)
    _print_decision(console, "e", "ls -la", level=3)
    lines = plain(transcript.all_lines(100)).splitlines()
    assert lines[0] == "✔ aprovado · ação de nível 3"
    assert lines[1] == "✖ negado · ação de nível 2"
    assert lines[2].startswith("✔ aprovado · ação de nível 3 · editado: ls -la")


@pytest.mark.parametrize("width", [60, 79, 80, 109, 110])
def test_status_line_never_drops_mode_or_pep(width: int) -> None:
    bar = SessionStatusBar(model_name="anthropic/claude-sonnet-5-5", pep_level=2, context_pct=12)
    text = "".join(part for _, part in bar.status_segments(width))
    assert text.startswith("auto · ") and "PEP 2" in text and text.endswith("Pronto ●")
    assert len(text) <= width


def test_status_line_states_and_effort_in_portuguese() -> None:
    bar = SessionStatusBar(model_name="m", reasoning_effort=ReasoningEffort.MEDIUM, fast_mode=True)
    text = "".join(part for _, part in bar.status_segments(120))
    assert "m (rápido) · esforço médio" in text
    bar.awaiting = True
    assert "Aguardando ●" in "".join(p for _, p in bar.status_segments(120))
    bar.is_online = False
    assert "Offline ●" in "".join(p for _, p in bar.status_segments(120))


def test_sync_output_wraps_each_frame() -> None:
    class Output:
        def __init__(self) -> None:
            self._buffer: list[str] = []
            self.written: list[str] = []

        def flush(self) -> None:
            self.written.append("".join(self._buffer))
            self._buffer = []

    output = Output()
    assert terminal.enable_sync_output(output)
    assert not terminal.enable_sync_output(output)  # idempotente
    output._buffer.append("quadro")
    output.flush()
    output.flush()  # quadro vazio não escreve sequência
    assert output.written == [terminal.BEGIN_SYNC + "quadro" + terminal.END_SYNC, ""]
    assert not terminal.enable_sync_output(object())


def test_terminal_switches_and_focus_keys() -> None:
    assert terminal.sync_supported({"TERM": "xterm"})
    assert not terminal.sync_supported({"TERM": "linux"})
    assert not terminal.sync_supported({"ORION_SYNC_OUTPUT": "0"})
    assert terminal.progress_supported({}) and not terminal.progress_supported({"ORION_PROGRESS": "0"})
    terminal.register_focus_keys()
    from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES

    assert ANSI_SEQUENCES["\x1b[I"] == terminal.FOCUS_IN_KEY
    assert ANSI_SEQUENCES["\x1b[O"] == terminal.FOCUS_OUT_KEY

    calls: list[str] = []

    class Out:
        def write_raw(self, data: str) -> None:
            calls.append(data)

        def set_title(self, text: str) -> None:
            calls.append(f"title:{text}")

        def flush(self) -> None:
            calls.append("flush")

    terminal.write(Out(), "x")
    terminal.set_title(Out(), "ORION")
    terminal.write(object(), "ignorado")  # saída sem write_raw não quebra
    assert calls == ["x", "flush", "title:ORION", "flush"]


def test_full_view_search_and_dump(tmp_path: Path) -> None:
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from orion.tui.screen.app import ScreenApp, build_parts

    class Session:
        workspace = tmp_path
        session_id = "x"

        def __getattr__(self, name: str) -> Any:
            return lambda *a, **k: []

    with create_pipe_input() as pipe, create_app_session(input=pipe, output=DummyOutput()):
        status = SessionStatusBar()
        parts = build_parts(status)
        screen = ScreenApp(Session(), parts, status, registry=object(), home=tmp_path, mouse=False)
        renderer = parts.renderer
        renderer.begin_thinking()
        renderer.add_reasoning("segredo escondido no raciocínio " * 5)
        time.sleep(0.01)
        renderer.add_text("resposta visível")
        renderer.close()
        for n in range(40):
            parts.transcript.add_renderables("print", Text(f"linha {n}"))
        collapsed = plain(parts.transcript.all_lines(80))
        assert "segredo" not in collapsed
        screen.toggle_full_view()
        assert screen.full_view and screen.buffer.read_only()
        lines, _ = screen.visible_lines(80, 200)
        assert "segredo escondido" in plain(lines)  # tudo aberto na transcrição completa
        assert "Transcrição" in plain(screen._activity_lines())
        screen.search("SEGREDO")
        assert screen.matches and screen.match_index == len(screen.matches) - 1
        assert "“SEGREDO”" in plain(screen._activity_lines())
        screen.next_match(1)
        assert screen.match_index == 0
        screen.search("nada disso")
        assert screen.matches == [] and "nada encontrado" in plain(screen._activity_lines())
        screen.next_match(1)
        dumped = screen.dump_text(80)
        assert "segredo escondido" in dumped and "linha 39" in dumped
        screen.searching = True
        assert screen._prompt_symbol()[0][1] == "/ " and "buscar" in screen._placeholder()
        screen.searching = False
        assert "q volta" in screen._placeholder()
        screen.request_dump()
        assert screen.dump_requested
        screen.toggle_full_view()
        assert not screen.full_view and screen.query == ""
