"""v0.5.1 Sprint 1: estabilidade da TUI em movimento (V-09 a V-17), nível unitário.

Os cenários de ponta a ponta ficam em ``tests/lab/`` (``pytest -m lab``).
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from rich.console import Console

from orion.tui.stream_renderer import StreamRenderer
from orion.tui.theme import get_orion_theme


def _renderer(width: int = 100, height: int = 20) -> tuple[StreamRenderer, io.StringIO]:
    buf = io.StringIO()
    console = Console(
        file=buf, width=width, height=height, theme=get_orion_theme(), force_terminal=False
    )
    return StreamRenderer(console, status_line=lambda w: "status"), buf


def _lines(renderer: StreamRenderer) -> list[str]:
    console = renderer.console
    rendered = console.render_lines(renderer, console.options, pad=False)
    return ["".join(seg.text for seg in line).rstrip() for line in rendered]


class TestToolTimer:
    """V-12: a espera da aprovação (modal com o Live pausado) não entra no tempo da ferramenta."""

    def test_pause_time_is_excluded(self) -> None:
        renderer, buf = _renderer()
        clock = [100.0]
        with patch("orion.tui.stream_renderer.time.monotonic", lambda: clock[0]):
            renderer.tool_started("run_command", {"command": "seq 3"}, key="a")
            renderer.pause()
            clock[0] += 30.0  # o Senhor pensou 30 s antes de aprovar
            renderer.resume()
            clock[0] += 0.2
            renderer.tool_finished("run_command", True, "1\n2\n3", {"exit_code": 0}, key="a")
        out = buf.getvalue()
        assert "0,2s" in out, out
        assert "30" not in out, out


class TestTailWindow:
    """V-10: a parte viva nunca passa da altura da tela; mostra as linhas mais novas."""

    def test_live_view_fits_screen_and_shows_newest(self) -> None:
        renderer, _ = _renderer(height=20)
        code = "```python\n" + "\n".join(f"linha_{n:02d} = {n}" for n in range(1, 61)) + "\n"
        renderer._buffer = code  # noqa: SLF001 - estado vivo, sem iniciar o Live
        lines = _lines(renderer)
        assert len(lines) <= 20 - 2, lines
        assert any("linha_60" in line for line in lines), lines
        assert any("linhas acima" in line for line in lines), lines

    def test_short_buffer_is_untouched(self) -> None:
        renderer, _ = _renderer(height=20)
        renderer._buffer = "uma linha"  # noqa: SLF001
        lines = _lines(renderer)
        assert not any("linhas acima" in line for line in lines)


class TestStallNotice:
    """1B.7: aviso discreto após 5 s sem nenhum evento do provedor."""

    def test_notice_after_five_seconds_without_tokens(self) -> None:
        renderer, _ = _renderer()
        clock = [10.0]
        with patch("orion.tui.stream_renderer.time.monotonic", lambda: clock[0]):
            renderer.add_text("começo ")
            clock[0] += 4.0
            assert not any("sem resposta" in line for line in _lines(renderer))
            clock[0] += 2.5
            assert any("sem resposta há 6s" in line for line in _lines(renderer))
            renderer.add_text("continua")
            assert not any("sem resposta" in line for line in _lines(renderer))

    def test_no_notice_while_a_tool_runs(self) -> None:
        renderer, _ = _renderer()
        clock = [10.0]
        with patch("orion.tui.stream_renderer.time.monotonic", lambda: clock[0]):
            renderer.tool_started("run_command", {"command": "sleep 60"}, key="k")
            clock[0] += 30.0
            assert not any("sem resposta" in line for line in _lines(renderer))

    def test_no_notice_after_close(self) -> None:
        renderer, _ = _renderer()
        clock = [10.0]
        with patch("orion.tui.stream_renderer.time.monotonic", lambda: clock[0]):
            renderer.add_text("fim\n\n")
            renderer.close()
            clock[0] += 30.0
            assert not any("sem resposta" in line for line in _lines(renderer))


class TestToolSummaries:
    """2.6: linha de resultado `›` sob cada ferramenta."""

    def test_read_grep_and_none_for_bash(self) -> None:
        from orion.tui.stream_renderer import tool_result_line

        read = tool_result_line("read_file", True, "1→a\n2→b\n")
        assert read is not None and read.plain == "  › 2 linhas"
        found = tool_result_line("grep", True, "x.py:1\n")
        assert found is not None and found.plain == "  › 1 resultado"
        assert tool_result_line("run_command", True, "ok") is None
        assert tool_result_line("read_file", False, "erro") is None


class TestExpandAndDecision:
    def test_expand_output_prints_header(self) -> None:
        renderer, buf = _renderer()
        output = "\n".join(str(n) for n in range(1, 41))
        renderer.tool_started("run_command", {"command": "seq 1 40"}, key="k")
        renderer.tool_finished("run_command", True, output, {"exit_code": 0}, key="k")
        buf.truncate(0)
        buf.seek(0)
        renderer.expand_output()
        out = buf.getvalue().splitlines()
        assert "Bash: seq 1 40" in out[0] and "saída completa" in out[0], out[:2]
        assert out[-1].endswith("40")

    def test_decision_lines(self) -> None:
        renderer, buf = _renderer()
        renderer.decision(True)
        renderer.decision(True, "sempre permitir")
        renderer.decision(False)
        out = buf.getvalue()
        assert "✔ aprovado" in out and "sempre permitir" in out and "✖ negado" in out


class TestTypeAheadLine:
    """V-11: a linha de digitação durante o turno aparece na parte viva."""

    def test_input_line_is_rendered(self) -> None:
        renderer, _ = _renderer()
        renderer.set_input_line(lambda: "❯ abc   · 1 na fila")
        renderer._buffer = "texto"  # noqa: SLF001
        lines = _lines(renderer)
        assert any("❯ abc" in line and "1 na fila" in line for line in lines), lines


class TestTypeAhead:
    def _typeahead(self) -> Any:
        from orion.tui.prompt import TypeAhead

        return TypeAhead(fd=-1)

    def test_printable_backspace_and_enter(self) -> None:
        ahead = self._typeahead()
        ahead.feed("abd\x7fc\rsegunda")
        assert ahead.queue == ["abc"]
        assert ahead.buffer == "segunda"
        line = ahead.render()
        assert line is not None and "❯ segunda" in line.plain and "1 na fila" in line.plain

    def test_escape_sequences_are_ignored(self) -> None:
        ahead = self._typeahead()
        ahead.feed("a\x1b[Ab\x1bOPc")
        assert ahead.buffer == "abc"

    def test_empty_render_is_none(self) -> None:
        assert self._typeahead().render() is None

    def test_take_returns_queue_and_partial(self) -> None:
        ahead = self._typeahead()
        ahead.feed("um\rdois\rtr")
        assert ahead.take() == (["um", "dois"], "tr")
        assert ahead.take() == ([], "")

    def test_start_is_noop_without_tty(self) -> None:
        ahead = self._typeahead()
        ahead.start()  # fd inválido: não liga nada, não levanta
        ahead.stop()


class TestKeybindings:
    def _binding(self, keys: tuple[str, ...], **kwargs: Any) -> Any:
        from orion.tui.keybindings import create_key_bindings

        kb = create_key_bindings(**kwargs)
        return [b for b in kb.bindings if tuple(k.value if hasattr(k, "value") else k for k in b.keys) == keys]

    def test_escape_with_menu_has_its_own_binding(self) -> None:
        assert len(self._binding(("escape",))) == 2

    def test_alt_shift_aliases_for_expansion(self) -> None:
        calls: list[str] = []
        assert self._binding(("escape", "E"), on_expand_output=lambda: calls.append("e"))
        assert self._binding(("escape", "R"), on_expand_reasoning=lambda: calls.append("r"))


class TestEmbeddingsOffline:
    """V-09 / ADR-040: sem modelo em cache, nada de rede; erro tipado e silencioso."""

    def test_local_only_raises_typed_error_without_download(self, tmp_path: Path) -> None:
        from orion.memory.vector_store import EmbeddingModelUnavailable, load_embedding_model

        calls: list[dict[str, Any]] = []

        class FakeTextEmbedding:
            def __init__(self, **kwargs: Any) -> None:
                calls.append(kwargs)
                raise ValueError("Could not load model from any source.")

        fake = type(sys)("fastembed")
        fake.TextEmbedding = FakeTextEmbedding  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"fastembed": fake}), pytest.raises(EmbeddingModelUnavailable):
            load_embedding_model(tmp_path / "models")
        assert calls and all(call["local_files_only"] is True for call in calls)
        assert calls[0]["cache_dir"] == str(tmp_path / "models")

    def test_vector_store_cache_lives_under_orion_home(self, tmp_path: Path) -> None:
        from orion.memory.vector_store import VectorStore

        store = VectorStore(db_path=tmp_path / ".orion" / "timeline.db")
        assert store.model_cache_dir == tmp_path / ".orion" / "models" / "fastembed"

    async def test_auto_recall_notice_once(self, tmp_path: Path) -> None:
        from orion.memory.auto_recall import AutoRecall
        from orion.memory.vector_store import EmbeddingModelUnavailable

        class NoModel:
            def __init__(self, path: Path) -> None:
                self._model = None

            async def initialize(self) -> None:
                return None

            async def add(self, *args: Any, **kwargs: Any) -> None:
                raise EmbeddingModelUnavailable("sem modelo")

            async def close(self) -> None:
                return None

        recall = AutoRecall(tmp_path / "timeline.db", None, vector_factory=NoModel)
        await recall.remember("pedido e resposta", "s1")
        first = recall.take_notice()
        assert first is not None and "Memória semântica desligada" in first
        assert recall.take_notice() is None
        await recall.remember("outro", "s1")
        assert recall.take_notice() is None


def test_monotonic_import_is_patchable() -> None:
    """Garante que os testes acima controlam o relógio do renderer."""
    import orion.tui.stream_renderer as module

    assert module.time is time
