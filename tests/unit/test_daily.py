"""Daily: id estável, virada, cartão e resumo de abertura (v0.5.3 Sprint 3, ADR-051, CA-11)."""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from rich.console import Console

from orion.gateway.models import LLMMessage, MessageRole
from orion.sessions import JsonlSessionStore, TranscriptEntry
from orion.sessions import daily as daily_module
from orion.sessions.daily import OPENING_MAX_CHARS, DailyBook, daily_title
from orion.sessions.index import SessionIndex
from orion.settings import user_settings_path
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.unit.test_agent_session import ScriptedProvider

SP = ZoneInfo("America/Sao_Paulo")


class Clock:
    """Relógio controlado do ``DailyBook``."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = datetime(2026, 11, 16, 10, 0, tzinfo=SP)
        monkeypatch.setattr(daily_module, "local_now", lambda tz=None: self.now)

    def set(self, *args: int) -> None:
        self.now = datetime(*args, tzinfo=SP)  # type: ignore[misc]


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    return Clock(monkeypatch)


@pytest.fixture
def book(tmp_path: Path) -> DailyBook:
    index = SessionIndex(tmp_path / "sessions.db", tz=SP)
    return DailyBook(index, JsonlSessionStore(tmp_path / "sessions", tmp_path, index=index))


class TestDailyBook:
    def test_id_is_stable_and_shifted_by_day_start(self, book: DailyBook, clock: Clock) -> None:
        first = book.ensure()
        assert first.created and first.today.id == "daily-2026-11-16"
        second = book.ensure()
        assert not second.created and second.today.id == first.today.id
        clock.set(2026, 11, 17, 3, 59)  # antes das 04:00 ainda é o dia 16
        assert book.ensure().today.id == "daily-2026-11-16"
        assert first.today.title == daily_title("daily-2026-11-16") == "Daily 16/11/2026 (segunda)"

    def test_rollover_closes_yesterday_with_card_and_opens_with_summary(self, book: DailyBook, clock: Clock) -> None:
        book.ensure()
        book.store.append("daily-2026-11-16", TranscriptEntry.of_message(LLMMessage(role=MessageRole.USER, content="ver agenda")))
        book.index.record_turn("daily-2026-11-16", "ver agenda")
        book.index.register("t1", "thread", title="Bug do PEP", daily_id="daily-2026-11-16", turn_count=3, workspace="/w")
        book.index.register("t0", "thread", daily_id="daily-2026-11-16")  # vazia: fora do cartão
        clock.set(2026, 11, 17, 4, 1)
        state = book.ensure()
        assert state.created and state.closed == ["daily-2026-11-16"]
        yesterday = book.index.get("daily-2026-11-16")
        assert yesterday is not None and yesterday.closed_at is not None
        card = yesterday.card or {}
        assert card["turns"] == 1 and card["thread_count"] == 1 and card["requests"] == ["ver agenda"]
        assert card["threads"][0]["title"] == "Bug do PEP"
        opening = state.today.opening or ""
        assert "Daily de 16/11/2026" in opening and "'Bug do PEP' (3)" in opening and "ver agenda" in opening

    def test_rollover_skips_missing_days_and_closes_every_open_daily(self, book: DailyBook, clock: Clock) -> None:
        book.index.register("daily-2026-11-10", "daily", turn_count=1)
        book.index.register("daily-2026-11-12", "daily", turn_count=0)
        state = book.ensure()
        assert state.closed == ["daily-2026-11-10", "daily-2026-11-12"]
        assert state.today.opening is None  # a anterior (dia 12) não teve nada

    def test_opening_is_capped_at_about_300_tokens(self, book: DailyBook, clock: Clock) -> None:
        book.ensure()
        for i in range(60):
            book.index.register(f"t{i}", "thread", title=f"thread número {i} com título comprido o bastante", daily_id="daily-2026-11-16", turn_count=1)
        clock.set(2026, 11, 17, 9, 0)
        opening = book.ensure().today.opening or ""
        assert 0 < len(opening) <= OPENING_MAX_CHARS and opening.endswith(".")


@pytest.fixture
def user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "u"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return home


def make_session(user_home: Path, workspace: Path | None = None, replies: list[Any] | None = None, **kwargs: Any) -> AgentSession:
    console = Console(file=io.StringIO(), width=100, theme=get_orion_theme())
    provider = ScriptedProvider(list(replies or []))

    async def ask(action: Any, level: Any) -> Any:
        return "y"

    return AgentSession(
        status_bar=SessionStatusBar(),
        console=console,
        workspace=workspace or user_home,
        home=user_home / ".orion",
        provider_factory=lambda spec: provider,
        ask_pep=ask,
        **kwargs,
    )


class TestSessionAttachesToDaily:
    async def test_home_attaches_to_the_daily_and_reload_keeps_the_id(self, user_home: Path, clock: Clock) -> None:
        first = make_session(user_home, replies=["oi, Senhor"])
        assert first.session_id == "daily-2026-11-16" and first.session_kind == "daily"
        assert "Daily 16/11/2026" in first.session_notice
        await first.run_turn("bom dia")
        second = make_session(user_home)
        assert second.session_id == first.session_id  # M-09: recarga não troca de sessão
        assert [m.text for m in second.history] == ["bom dia", "oi, Senhor"]
        assert "1 pedido(s)" in second.session_notice
        assert second.session_index.get("daily-2026-11-16").turn_count == 1  # type: ignore[union-attr]

    async def test_daemon_uses_the_daily_and_cron_does_not(self, user_home: Path, clock: Clock) -> None:
        assert make_session(user_home, origin="daemon").session_id == "daily-2026-11-16"
        cron = make_session(user_home, origin="cron")
        assert cron.session_kind == "thread" and not cron.session_id.startswith("daily-")

    async def test_repo_opens_a_thread_linked_to_the_daily(self, user_home: Path, clock: Clock) -> None:
        repo = user_home / "orion-agent"
        repo.mkdir()
        session = make_session(user_home, repo, replies=["feito"])
        assert session.session_kind == "thread" and session.session_notice == ""
        await session.run_turn("corrigir o parser de shell")
        record = session.session_index.get(session.session_id)
        assert record is not None and record.daily_id == "daily-2026-11-16"
        assert record.workspace == str(repo.resolve()) and record.title == "corrigir o parser de shell"
        links = [e.meta for e in session.sessions.load("daily-2026-11-16") if e.kind == "meta" and (e.meta or {}).get("event")]
        assert links == [
            {
                "event": "thread_opened",
                "thread_id": session.session_id,
                "title": "corrigir o parser de shell",
                "workspace": str(repo.resolve()),
                "parent_id": "",
            }
        ]

    async def test_daily_flag_attaches_inside_a_repo(self, user_home: Path, clock: Clock) -> None:
        repo = user_home / "repo"
        repo.mkdir()
        assert make_session(user_home, repo, daily=True).session_id == "daily-2026-11-16"

    async def test_rollover_while_open_moves_to_the_new_daily_with_summary(self, user_home: Path, clock: Clock) -> None:
        session = make_session(user_home, replies=["ok", "bom dia"])
        await session.run_turn("revisar a agenda")
        clock.set(2026, 11, 17, 8, 0)
        await session.run_turn("e hoje?")
        assert session.session_id == "daily-2026-11-17"
        assert session.history[0].text.startswith("Resumo da daily anterior")
        assert "revisar a agenda" in session.history[0].text
        assert [m.text for m in session.history[-2:]] == ["e hoje?", "bom dia"]
        old = session.session_index.get("daily-2026-11-16")
        assert old is not None and old.closed_at is not None and old.card["turns"] == 1  # type: ignore[index]
        reopened = make_session(user_home)  # a semente foi gravada no transcript da nova daily
        assert reopened.history[0].text.startswith("Resumo da daily anterior")

    async def test_resumed_old_daily_does_not_follow_the_rollover(self, user_home: Path, clock: Clock) -> None:
        session = make_session(user_home, replies=["ok", "ok2", "ok3"])
        await session.run_turn("dia 16")
        clock.set(2026, 11, 17, 9, 0)
        await session.run_turn("dia 17")
        session.resume("daily-2026-11-16")
        await session.run_turn("voltei ao 16")
        assert session.session_id == "daily-2026-11-16"

    async def test_day_start_comes_from_settings(self, user_home: Path, clock: Clock) -> None:
        settings = user_settings_path(user_home / ".orion")
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps({"memory": {"day_starts_at": "06:00"}}), encoding="utf-8")
        clock.set(2026, 11, 17, 5, 0)
        assert make_session(user_home).session_id == "daily-2026-11-16"

    async def test_home_continue_lists_previous_dailies(self, user_home: Path, clock: Clock) -> None:
        first = make_session(user_home, replies=["ok"])
        await first.run_turn("ontem")
        clock.set(2026, 11, 17, 9, 0)
        today = make_session(user_home)
        assert [m.session_id for m in today.list_sessions()] == ["daily-2026-11-16"]
        assert "Daily 16/11/2026" in today.resume()
