"""Transcrição em células, console de transcrição, renderer e escolha de modo (ADR-043)."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel
from rich.style import Style
from rich.text import Text

from orion.tui.screen import mode
from orion.tui.screen.console import TranscriptConsole
from orion.tui.screen.renderer import ScreenRenderer
from orion.tui.screen.transcript import Cell, Transcript, plain, pt_style, rasterize


def _text(transcript: Transcript, width: int = 60, height: int = 200, offset: int = 0) -> str:
    lines, _, _ = transcript.window(width, height, offset)
    return plain(lines)


def test_pt_style_maps_color_bold_and_background() -> None:
    style = Style(color="#112233", bgcolor="#445566", bold=True, italic=False)
    assert pt_style(style) == "#112233 bg:#445566 bold noitalic"
    assert pt_style(None) == ""


def test_rasterize_reflows_by_width() -> None:
    words = Text(" ".join(["palavra"] * 30))
    narrow, wide = rasterize([words], 40), rasterize([words], 100)
    assert len(narrow) > len(wide)
    assert all(len("".join(t for _, t in line)) <= 40 for line in narrow)
    assert rasterize([], 40) == []


def test_window_follows_end_and_scrolls() -> None:
    transcript = Transcript()
    for n in range(10):
        transcript.add_renderables("print", Text(f"linha {n}"))
    lines, owners, total = transcript.window(40, 3, 0)
    assert plain(lines).splitlines() == ["linha 7", "linha 8", "linha 9"]
    assert total == 10 and all(owner is not None for owner in owners)
    lines, _, _ = transcript.window(40, 3, 4)
    assert plain(lines).splitlines() == ["linha 3", "linha 4", "linha 5"]
    tail = rasterize([Text("viva")], 40)
    lines, owners, total = transcript.window(40, 2, 0, tail)
    assert plain(lines).splitlines() == ["linha 9", "viva"] and owners[-1] is None and total == 11


def test_collapsible_cell_opens_in_place_and_caches_per_width() -> None:
    transcript = Transcript()
    transcript.add_renderables("print", Text("antes"))
    cell = transcript.add(Cell("thinking", [Text("▸ fechado")], expanded=[Text("▾ aberto"), Text("detalhe")]))
    transcript.add_renderables("print", Text("depois"))
    assert _text(transcript).splitlines() == ["antes", "▸ fechado", "depois"]
    assert transcript.toggle_last("thinking") is cell
    assert transcript.toggled
    assert _text(transcript).splitlines() == ["antes", "▾ aberto", "detalhe", "depois"]
    transcript.toggle(cell)
    assert _text(transcript).splitlines() == ["antes", "▸ fechado", "depois"]
    plain_cell = transcript.add_renderables("print", Text("x"))
    assert not plain_cell.collapsible and plain_cell.toggle() is True
    assert cell.lines(30) is cell.lines(30)
    cell.invalidate()
    assert transcript.last("nada") is None and transcript.toggle_last("nada") is None


def test_transcript_notifies_and_clears() -> None:
    transcript = Transcript()
    calls: list[int] = []
    transcript.on_change = lambda: calls.append(transcript.version)
    transcript.add_renderables("print")
    transcript.clear()
    assert calls == [1, 2] and transcript.total_lines(40) == 0


def test_transcript_console_records_prints_as_cells() -> None:
    transcript = Transcript()
    console = TranscriptConsole(transcript, width=50)
    console.print("[bold]olá[/bold]", "Senhor")
    console.print()
    console.print(Panel("caixa"), style="text_dim")
    console.print("só estilo", style=Style(color="#ff0000"))
    assert [c.kind for c in transcript.snapshot()] == ["print"] * 4
    text = _text(transcript, 50)
    assert "olá Senhor" in text and "caixa" in text and "só estilo" in text
    statuses: list[str | None] = []
    console.on_status = statuses.append
    with console.status("[bold]instalando[/bold]…"):
        pass
    assert statuses == ["instalando…", None]
    cleared: list[bool] = []
    console.on_clear = lambda: cleared.append(True)
    console.clear()
    assert cleared == [True]
    console.on_clear = None
    console.clear()
    assert transcript.snapshot() == []
    try:
        console.input("x")
    except RuntimeError as exc:
        assert "tela cheia" in str(exc)


def test_screen_renderer_writes_cells_and_toggles_in_place() -> None:
    transcript = Transcript()
    renderer = ScreenRenderer(TranscriptConsole(transcript), transcript)
    changes: list[int] = []
    renderer.on_change = lambda: changes.append(1)
    renderer.begin_thinking()
    assert renderer.busy() and renderer.activity_renderables()
    renderer.add_reasoning("primeira linha do raciocínio\nsegunda linha " + "longa " * 30)
    renderer.add_text("Resposta **parcial** em construção")
    assert renderer.live_lines(60, 10)
    renderer.end_message()
    thinking = transcript.last("thinking")
    assert thinking is not None and thinking.collapsible
    assert "▸ Raciocínio" in _text(transcript)
    renderer.expand_reasoning()
    opened = _text(transcript, 60)
    assert "▾ Raciocínio" in opened and opened.count("│") >= 3  # guia em cada linha quebrada
    renderer.tool_started("run_command", {"command": "seq 1 20"}, key="a")
    renderer.tool_finished("run_command", True, "\n".join(str(n) for n in range(1, 21)), {"exit_code": 0}, key="a")
    out = _text(transcript)
    assert "+15 linhas ocultas" in out and "Alt+E abre" in out
    renderer.expand_output()
    assert "\n  │ 10" in _text(transcript)
    renderer.close()
    assert not renderer.busy() and changes


def test_screen_renderer_notices_without_blocks() -> None:
    transcript = Transcript()
    renderer = ScreenRenderer(TranscriptConsole(transcript), transcript)
    renderer.expand_reasoning()
    renderer.expand_output()
    renderer.tool_started("run_command", {"command": "true"}, key="b")
    renderer.tool_finished("run_command", True, "ok", {"exit_code": 0}, key="b")
    renderer.expand_output()  # saída curta não recolhe
    text = _text(transcript)
    assert "Nenhum raciocínio" in text and text.count("Nenhuma saída recolhida") == 2
    renderer.status_text = "baixando"
    assert renderer.busy() and renderer.activity_renderables()
    assert renderer.live_lines(40, 5) == []


def test_choose_mode(tmp_path: Path) -> None:
    tty = {"TERM": "xterm-256color"}
    assert mode.choose(tmp_path, tty, is_tty=True) == mode.Choice("fullscreen", "padrão")
    assert mode.choose(tmp_path, {**tty, "ORION_TUI": "classic"}, is_tty=True).mode == "classic"
    assert mode.choose(tmp_path, tty, is_tty=False).mode == "classic"
    assert mode.choose(tmp_path, {"TERM": "dumb"}, is_tty=True).mode == "classic"
    assert mode.choose(tmp_path, {}, is_tty=True).reason == "TERM=vazio"
    mode.mark_starting(tmp_path)
    assert mode.choose(tmp_path, tty, is_tty=True).mode == "fullscreen"
    mode.mark_starting(tmp_path)
    assert "duas vezes" in mode.choose(tmp_path, tty, is_tty=True).reason
    assert mode.choose(tmp_path, {**tty, "ORION_TUI": "fullscreen"}, is_tty=True).mode == "fullscreen"
    mode.mark_started(tmp_path)
    mode.save_preference(tmp_path, "classic")
    assert mode.choose(tmp_path, tty, is_tty=True).reason == "preferência salva (/tui)"
    (tmp_path / mode.STATE_FILE).write_text("[]")
    assert mode.read_state(tmp_path) == {}
    (tmp_path / mode.STATE_FILE).write_text("{quebrado")
    assert mode.read_state(tmp_path) == {}
