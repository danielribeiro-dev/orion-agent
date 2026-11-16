"""Memória legível e correções da auditoria (v0.5.2 Sprint 4, N-18 a N-21, A-01 a A-07)."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from rich.console import Console

from orion.daemon.control import format_status
from orion.tui.memory_views import (
    Entry,
    FactRow,
    FactsView,
    TimelineView,
    day_label,
    entries_from_records,
    markdown_to_plain,
    role_label,
)


def _render(renderable: Any, width: int = 80) -> list[str]:
    buf = io.StringIO()
    Console(file=buf, width=width, force_terminal=False).print(renderable)
    return buf.getvalue().rstrip("\n").splitlines()


ANSWER = (
    "Pronto, Senhor. A saudação agora é formal.\n\n## Mudanças\n\n- `greet()` usa **Senhor**\n\n"
    "```python\ndef greet(name: str) -> str:\n    return name\n```\n\n"
    "| arquivo | linhas |\n|---|---|\n| sample.py | +1 -1 |\n\n> nota\n\n[docs](http://x)"
)


def test_markdown_to_plain_removes_markup() -> None:
    flat = markdown_to_plain(ANSWER)
    for junk in ("```", "|", "##", "**", "`", "---", "](", "> nota"):
        assert junk not in flat, junk
    assert flat.startswith("Pronto, Senhor. A saudação agora é formal. Mudanças greet() usa Senhor")
    assert "def greet(name: str) -> str: return name" in flat
    assert "arquivo linhas sample.py +1 -1" in flat and flat.endswith("nota docs")


def test_roles_and_days_in_portuguese() -> None:
    assert role_label("user") == "Senhor" and role_label("assistant") == "ORION"
    assert role_label("observation") == "ferramenta" and role_label("checkpoint") == "sistema"
    assert role_label("outro") == "outro" and role_label("") == "evento"
    today = date(2026, 11, 16)
    assert day_label(today, today) == "hoje"
    assert day_label(date(2026, 11, 15), today) == "ontem"
    assert day_label(date(2026, 11, 2), today) == "02/11"
    assert day_label(date(2025, 11, 2), today) == "02/11/2025"


def test_timeline_view_one_line_per_event_grouped_by_day() -> None:
    entries = [
        Entry(datetime(2026, 11, 16, 2, 5), "ORION", ANSWER * 3),
        Entry(datetime(2026, 11, 16, 2, 4), "Senhor", "ajuste a saudacao do sample.py"),
        Entry(datetime(2026, 11, 15, 22, 0), "sistema", "checkpoint"),
    ]
    lines = _render(TimelineView(entries, "Linha do tempo", today=date(2026, 11, 16), footer="rodapé"), 80)
    assert lines[0] == "Linha do tempo · 3 eventos"
    assert lines[1] == "ontem" and lines[3] == "hoje"
    assert lines[4].startswith("  02:04  Senhor     ajuste a saudacao")
    assert lines[5].startswith("  02:05  ORION      Pronto, Senhor.") and lines[5].endswith("…")
    assert all(len(line) <= 80 for line in lines) and lines[-1] == "rodapé"
    narrow = _render(TimelineView(entries[:1], "x", today=date(2026, 11, 16)), 40)
    assert len(narrow) == 3 and len(narrow[2]) <= 40  # reflow: uma linha por evento em qualquer largura


def test_facts_view_badges_and_highlight() -> None:
    facts = [FactRow("linguagem", "Python 3.11+", "CONFIRMED"), FactRow("tema", "escuro", "INFERRED")]
    lines = _render(FactsView(facts, highlight="python"), 60)
    assert lines[0] == "Fatos · 2"
    assert "confirmado" in lines[1] and "linguagem: Python 3.11+" in lines[1]
    assert "inferido" in lines[2]


def test_entries_from_records_skips_records_without_time() -> None:
    @dataclass
    class Rec:
        timestamp: Any
        event_type: str
        content: str

    records = [Rec(datetime(2026, 1, 1, 9, 0), "user", "oi"), Rec(None, "user", "sem hora")]
    assert entries_from_records(records) == [Entry(datetime(2026, 1, 1, 9, 0), "Senhor", "oi")]


class _Timeline:
    def __init__(self, records: list[Any]) -> None:
        self.records = records

    async def get_recent_history(self, limit: int) -> list[Any]:
        return self.records[:limit]

    async def search_lexical(self, query: str, limit: int) -> list[Any]:
        return [r for r in self.records if query.lower() in r.content.lower()][:limit]

    async def close(self) -> None:
        return None


def _context(records: list[Any], tmp_path: Path, facts: Any = None, history: Any = ()) -> Any:
    console = Console(file=io.StringIO(), width=100, force_terminal=False)
    timeline = _Timeline(records)

    async def open_timeline() -> _Timeline:
        return timeline

    session = SimpleNamespace(open_timeline=open_timeline, facts=facts, history=list(history), home=tmp_path)
    return SimpleNamespace(session=session, console=console)


def _out(ctx: Any) -> str:
    return str(ctx.console.file.getvalue())


@pytest.mark.asyncio
async def test_timeline_and_recall_commands(tmp_path: Path) -> None:
    from orion.tui.commands.memory import RecallCommand, TimelineCommand

    rec = SimpleNamespace
    records = [
        rec(timestamp=datetime.now(), event_type="user", content="ajuste a saudação"),
        rec(timestamp=datetime.now(), event_type="assistant", content=ANSWER),
    ]
    ctx = _context(records, tmp_path)
    result = await TimelineCommand().execute("", ctx)
    out = _out(ctx)
    assert result.success and "Linha do tempo · 2 eventos" in out and "hoje" in out
    assert "```" not in out and "| arquivo" not in out and "Senhor" in out and "ORION" in out
    assert "/timeline 45 mostra mais" in out
    assert not (await TimelineCommand().execute("abc", ctx)).success
    empty = _context([], tmp_path)
    assert (await TimelineCommand().execute("", empty)).output_message == "Linha do tempo vazia."

    fact = SimpleNamespace(key="saudação", value="formal", status=SimpleNamespace(value="CONFIRMED"))
    facts = SimpleNamespace(search=lambda limit: [fact])
    ctx = _context(records, tmp_path, facts=facts)
    result = await RecallCommand().execute("saudação", ctx)
    out = _out(ctx)
    assert result.success and result.data == 3 and "Fatos · 1" in out and "Episódios · 2 eventos" in out
    none = _context(records, tmp_path)
    assert "Nada encontrado" in (await RecallCommand().execute("inexistente", none)).output_message


def test_profile_comes_from_orion_home(tmp_path: Path) -> None:
    from orion.tui.commands.memory import _load_profile

    assert _load_profile(tmp_path).call_sign == "Senhor"
    (tmp_path / "profile.json").write_text('{"name": "Daniel", "call_sign": "Chefe"}')
    assert _load_profile(tmp_path).call_sign == "Chefe"
    (tmp_path / "profile.json").write_text("{quebrado")
    assert _load_profile(tmp_path).call_sign == "Senhor"


@pytest.mark.asyncio
async def test_learn_and_grill_me_do_not_spend_a_turn_without_conversation(tmp_path: Path) -> None:
    from orion.tui.commands.cognitive import GrillMeCommand
    from orion.tui.commands.memory import LearnCommand

    calls: list[str] = []

    async def run_turn(text: str) -> None:
        calls.append(text)

    ctx = _context([], tmp_path)
    ctx.session.run_turn = run_turn
    assert not (await LearnCommand().execute("", ctx)).success
    assert "Uso" in (await GrillMeCommand().execute("", ctx)).output_message
    assert calls == []
    assert (await GrillMeCommand().execute("arquitetura", ctx)).success and len(calls) == 1


@pytest.mark.asyncio
async def test_voice_points_to_v060() -> None:
    from orion.tui.commands.operation import VoiceCommand

    result = await VoiceCommand().execute("", SimpleNamespace())
    assert "v0.6.0" in result.output_message


def test_daemon_status_is_readable() -> None:
    lines = format_status({"enabled": False, "autostart": "off", "service": {}, "daemon": None})
    assert lines[0] == "● Daemon parado · desligado (opt-in) · início automático: não"
    assert lines[1] == "serviço systemd não instalado · roda só com o Senhor logado"
    lines = format_status(
        {"enabled": True, "autostart": "login", "service": {"installed": True, "enabled": True, "linger_by_orion": True}}
    )
    assert "ligado pelo Senhor" in lines[0] and "início automático: login" in lines[0]
    assert lines[1] == "serviço systemd instalado e habilitado · roda sem login (linger ligado pelo ORION)"
