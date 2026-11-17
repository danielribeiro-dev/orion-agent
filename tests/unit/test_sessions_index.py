"""Índice de sessões, filtros de data e migração (v0.5.3 Sprint 3, ADR-051, CA-13)."""

from __future__ import annotations

import json
import stat
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from orion.gateway.models import LLMMessage, MessageRole
from orion.sessions import JsonlSessionStore, TranscriptEntry, replay
from orion.sessions.clock import day_of_daily, local_day, parse_hhmm
from orion.sessions.index import SessionIndex, card_text, provisional_title
from orion.sessions.query import SessionQuery, fts_expression, parse_query

SP = ZoneInfo("America/Sao_Paulo")
TODAY = date(2026, 11, 16)  # segunda-feira


def msg(role: MessageRole, text: str) -> LLMMessage:
    return LLMMessage(role=role, content=text)


@pytest.fixture
def index(tmp_path: Path) -> SessionIndex:
    return SessionIndex(tmp_path / "sessions.db", tz=SP)


class TestTitles:
    def test_provisional_title_is_first_request_up_to_60_chars(self) -> None:
        assert provisional_title("  corrigir   o bug\n do PEP ") == "corrigir o bug do PEP"
        long = "refatorar o motor de reversibilidade para suportar reflink em btrfs e snapshots"
        title = provisional_title(long)
        assert len(title) <= 60 and long.startswith(title) and not title.endswith(" ")
        assert long[len(title)] == " "  # não corta palavra

    def test_card_text_flattens_values(self) -> None:
        assert card_text({"a": "um", "b": ["dois", {"c": "três"}], "n": 3}) == "um dois três"
        assert card_text(None) == ""


class TestIndex:
    def test_db_is_private_and_register_is_idempotent(self, index: SessionIndex, tmp_path: Path) -> None:
        assert stat.S_IMODE((tmp_path / "sessions.db").stat().st_mode) == 0o600
        first = index.register("t1", "thread", title="a", workspace="/w")
        again = index.register("t1", "thread", title="outro")
        assert first == again and again.title == "a"

    def test_record_turn_counts_and_sets_provisional_title_once(self, index: SessionIndex) -> None:
        index.register("t1", "thread")
        index.record_turn("t1", "primeiro pedido do dia")
        index.record_turn("t1", "segundo pedido")
        record = index.get("t1")
        assert record is not None and record.turn_count == 2 and record.title == "primeiro pedido do dia"

    def test_user_title_is_never_overwritten(self, index: SessionIndex) -> None:
        index.register("t1", "thread")
        assert index.rename("t1", "  Migração   Postgres ")
        assert not index.set_auto_title("t1", "título do Mordomo")
        index.record_turn("t1", "outro pedido")
        record = index.get("t1")
        assert record is not None and record.title == "Migração Postgres" and record.title_source == "user"
        assert not index.rename("t1", "   ")
        assert index.search(SessionQuery(terms=["migracao"]))[0].id == "t1"  # sem acento acha

    def test_auto_title_replaces_provisional(self, index: SessionIndex) -> None:
        index.register("t1", "thread")
        index.record_turn("t1", "pedido")
        assert index.set_auto_title("t1", "Título definitivo")
        assert index.get("t1").title == "Título definitivo"  # type: ignore[union-attr]

    def test_fts_on_title_and_card_with_prefix(self, index: SessionIndex) -> None:
        index.register("t1", "thread", title="Ajustar daemon", turn_count=1)
        index.register("t2", "thread", title="Outra coisa", turn_count=1, card={"summary": "falamos de sessões e daily"})
        assert [r.id for r in index.search(SessionQuery(terms=["daem"]))] == ["t1"]
        assert [r.id for r in index.search(SessionQuery(terms=["sessoes"]))] == ["t2"]
        index.set_card("t1", {"summary": "sessoes"})
        assert {r.id for r in index.search(SessionQuery(terms=["sessoes"]))} == {"t1", "t2"}
        assert index.search(SessionQuery(terms=['"*)('])) == []  # termo sem palavra não quebra

    def test_empty_sessions_are_hidden_by_default(self, index: SessionIndex) -> None:
        index.register("t1", "thread")
        assert index.search() == []
        assert [r.id for r in index.search(include_empty=True)] == ["t1"]

    def test_local_date_respects_timezone_and_day_start(self, index: SessionIndex) -> None:
        # 05:30 UTC = 02:30 em São Paulo: antes das 04:00, ainda é a daily do dia 15.
        index.register("madrugada", "thread", created_at="2026-11-16T05:30:00+00:00", turn_count=1)
        index.register("manha", "thread", created_at="2026-11-16T08:00:00+00:00", turn_count=1)
        assert index.get("madrugada").local_date == "2026-11-15"  # type: ignore[union-attr]
        assert index.get("manha").local_date == "2026-11-16"  # type: ignore[union-attr]
        found = index.search(parse_query("ontem", TODAY))
        assert [r.id for r in found] == ["madrugada"]

    def test_filters_by_kind_workspace_and_children(self, index: SessionIndex) -> None:
        index.register("daily-2026-11-16", "daily", daily_id="daily-2026-11-16", turn_count=2)
        index.register("t1", "thread", daily_id="daily-2026-11-16", workspace="/home/u/orion-agent", turn_count=1)
        index.register("t2", "thread", daily_id="daily-2026-11-16", workspace="/home/u/outro", turn_count=1)
        assert [r.id for r in index.search(SessionQuery(kind="daily"))] == ["daily-2026-11-16"]
        assert [r.id for r in index.search(SessionQuery(workspace="/home/u/outro"))] == ["t2"]
        assert [r.id for r in index.search(SessionQuery(workspace_name="orion"))] == ["t1"]
        assert [r.id for r in index.children("daily-2026-11-16")] == ["t1", "t2"]
        assert index.get("daily-2026-11-16").local_date == "2026-11-16"  # type: ignore[union-attr]

    def test_close_reopen_and_resolve(self, index: SessionIndex) -> None:
        index.register("daily-2026-11-15", "daily")
        index.register("daily-2026-11-16", "daily")
        assert [r.id for r in index.open_dailies_before("daily-2026-11-16")] == ["daily-2026-11-15"]
        index.close_session("daily-2026-11-15", card={"summary": "x"})
        assert index.open_dailies_before("daily-2026-11-16") == []
        assert index.latest_daily_before("daily-2026-11-16").card == {"summary": "x"}  # type: ignore[union-attr]
        index.reopen("daily-2026-11-15")
        assert index.get("daily-2026-11-15").closed_at is None  # type: ignore[union-attr]
        assert index.resolve("daily-2026-11") == ["daily-2026-11-15", "daily-2026-11-16"]
        assert index.resolve("daily_") == []  # curinga do LIKE escapado


class TestQuery:
    @pytest.mark.parametrize(
        ("text", "start", "end"),
        [
            ("hoje", date(2026, 11, 16), date(2026, 11, 16)),
            ("ontem", date(2026, 11, 15), date(2026, 11, 15)),
            ("semana", date(2026, 11, 16), date(2026, 11, 16)),
            ("semana passada", date(2026, 11, 9), date(2026, 11, 15)),
            ("mês", date(2026, 11, 1), date(2026, 11, 30)),
            ("mes", date(2026, 11, 1), date(2026, 11, 30)),
            ("nov", date(2026, 11, 1), date(2026, 11, 30)),
            ("Novembro", date(2026, 11, 1), date(2026, 11, 30)),
            ("dez", date(2025, 12, 1), date(2025, 12, 31)),  # mês futuro = ano passado
            ("março 2025", date(2025, 3, 1), date(2025, 3, 31)),
            ("2026-11", date(2026, 11, 1), date(2026, 11, 30)),
            ("2026", date(2026, 1, 1), date(2026, 12, 31)),
            ("16/11", date(2026, 11, 16), date(2026, 11, 16)),
            ("20/11", date(2025, 11, 20), date(2025, 11, 20)),  # futuro = ano passado
            ("16/11/2025", date(2025, 11, 16), date(2025, 11, 16)),
            ("2026-11-02", date(2026, 11, 2), date(2026, 11, 2)),
            ("nov ontem", date(2026, 11, 15), date(2026, 11, 15)),  # interseção
        ],
    )
    def test_date_filters(self, text: str, start: date, end: date) -> None:
        query = parse_query(text, TODAY)
        assert (query.date_from, query.date_to) == (start, end) and query.terms == []

    def test_week_on_a_thursday_starts_on_monday(self) -> None:
        query = parse_query("semana", date(2026, 11, 19))
        assert (query.date_from, query.date_to) == (date(2026, 11, 16), date(2026, 11, 19))

    def test_kind_workspace_and_terms(self, tmp_path: Path) -> None:
        query = parse_query("daily @. pep bug", TODAY, tmp_path)
        assert query.kind == "daily" and query.workspace == str(tmp_path.resolve())
        assert query.terms == ["pep", "bug"] and not query.has_dates
        assert parse_query("thread @orion", TODAY).workspace_name == "orion"
        assert parse_query("31/02 32/13", TODAY).terms == ["31/02", "32/13"]
        assert "pep" in query.describe() and "daily" in query.describe()
        assert parse_query("hoje", TODAY).describe() == "16/11/2026"

    def test_fts_expression_quotes_every_word(self) -> None:
        assert fts_expression(['pep"bug', "sessão"]) == '"pep"* "bug"* "sessão"*'
        assert fts_expression(["***"]) == ""


class TestClock:
    def test_day_start_parsing_and_local_day(self) -> None:
        assert parse_hhmm("06:30").hour == 6 and parse_hhmm("lixo").hour == 4
        moment = datetime(2026, 11, 17, 6, 0, tzinfo=UTC)  # 03:00 em São Paulo
        assert local_day(moment, parse_hhmm("04:00"), SP) == date(2026, 11, 16)
        assert local_day(moment, parse_hhmm("02:00"), SP) == date(2026, 11, 17)
        assert day_of_daily("daily-2026-11-16") == date(2026, 11, 16)
        assert day_of_daily("daily-xx") is None and day_of_daily("abc") is None


class TestStoreWithIndex:
    def test_daily_lives_in_its_own_folder_without_workspace(self, tmp_path: Path, index: SessionIndex) -> None:
        store = JsonlSessionStore(tmp_path / "sessions", tmp_path / "ws", index=index)
        store.append("daily-2026-11-16", TranscriptEntry.of_message(msg(MessageRole.USER, "oi")))
        path = tmp_path / "sessions" / "daily" / "daily-2026-11-16.jsonl"
        assert path.is_file()
        assert "workspace" not in (store.load("daily-2026-11-16")[0].meta or {})
        assert store.resolve_id("daily-2026-11-16") == "daily-2026-11-16"

    def test_append_event_is_unnumbered_and_ignored_by_replay(self, tmp_path: Path) -> None:
        store = JsonlSessionStore(tmp_path / "sessions", tmp_path / "ws")
        store.append("d", TranscriptEntry.of_message(msg(MessageRole.USER, "a")))
        other = JsonlSessionStore(tmp_path / "sessions", tmp_path / "x")
        other.append_event("d", TranscriptEntry.of_meta(event="thread_opened", thread_id="t"))
        store.append("d", TranscriptEntry.of_message(msg(MessageRole.ASSISTANT, "b")))
        entries = store.load("d")
        numbered = [e.index for e in entries if e.index >= 0]
        assert len(numbered) == len(set(numbered)) and [e.index for e in entries].count(-1) == 1
        assert [m.text for m in replay(entries)] == ["a", "b"]
        other.append_event("nova", TranscriptEntry.of_meta(event="x"))  # cria o arquivo
        assert other.load("nova")[0].kind == "meta"

    def test_list_comes_from_the_index(self, tmp_path: Path, index: SessionIndex) -> None:
        ws = tmp_path / "ws"
        store = JsonlSessionStore(tmp_path / "sessions", ws, index=index)
        store.append("t1", TranscriptEntry.of_message(msg(MessageRole.USER, "pedido")))
        index.register("t1", "thread", workspace=str(ws.resolve()), title="Título", turn_count=1)
        index.register("fantasma", "thread", workspace=str(ws.resolve()), turn_count=1)  # sem arquivo
        listed = store.list(ws)
        assert [m.session_id for m in listed] == ["t1"] and listed[0].title == "Título"


def _write_jsonl(path: Path, entries: list[TranscriptEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(e.model_dump_json(exclude_none=True) + "\n" for e in entries), encoding="utf-8")


class TestMigration:
    def _legacy_home(self, tmp_path: Path) -> Path:
        home = tmp_path / "orion"
        entries = [
            TranscriptEntry.of_meta(session_id="abc", workspace="/home/u/proj").model_copy(
                update={"index": 0, "ts": "2026-11-10T15:00:00+00:00"}
            ),
            TranscriptEntry.of_message(msg(MessageRole.USER, "ajustar o parser de shell")).model_copy(
                update={"index": 1, "ts": "2026-11-10T15:00:01+00:00"}
            ),
            TranscriptEntry.of_message(msg(MessageRole.ASSISTANT, "feito")).model_copy(
                update={"index": 2, "ts": "2026-11-10T15:05:00+00:00"}
            ),
        ]
        _write_jsonl(home / "sessions" / "proj-123" / "abc.jsonl", entries)
        (home / "sessions" / "proj-123" / "lixo.jsonl").write_text("não é json\n", encoding="utf-8")
        archive = home / "timeline" / "archive"
        archive.mkdir(parents=True)
        (archive / "refactor-auth_20261101_120000.json").write_text(
            json.dumps(
                {
                    "branch_name": "refactor-auth",
                    "created_at": "2026-11-01T12:00:00+00:00",
                    "actions_summary": ["trocou o hash"],
                    "modified_files": ["auth.py"],
                }
            ),
            encoding="utf-8",
        )
        (archive / "quebrado.json").write_text("{", encoding="utf-8")
        return home

    def test_migration_indexes_backs_up_and_is_idempotent(self, tmp_path: Path) -> None:
        home = self._legacy_home(tmp_path)
        index = SessionIndex(home / "sessions.db", tz=SP)
        report = index.migrate(home)
        assert (report.sessions, report.branches) == (1, 1) and "1 sessão" in report.summary()
        record = index.get("abc")
        assert record is not None
        assert (record.kind, record.title, record.turn_count) == ("thread", "ajustar o parser de shell", 1)
        assert record.daily_id == "daily-2026-11-10" and record.workspace == "/home/u/proj"
        backup = home / "backup" / "v0.5.2"
        assert (backup / "sessions" / "proj-123" / "abc.jsonl").is_file()
        assert (backup / "timeline-archive" / "refactor-auth_20261101_120000.json").is_file()
        assert stat.S_IMODE(backup.stat().st_mode) == 0o700
        again = index.migrate(home)
        assert (again.sessions, again.branches, again.backed_up) == (0, 0, 0)
        assert index.meta("migrated_v0.5.2") is not None

    def test_archived_branch_becomes_a_closed_resumable_thread(self, tmp_path: Path) -> None:
        home = self._legacy_home(tmp_path)
        index = SessionIndex(home / "sessions.db", tz=SP)
        index.migrate(home)
        branch = index.get("branch-refactor-auth_20261101_120000")
        assert branch is not None and branch.closed_at is not None and branch.title == "refactor auth"
        assert branch.card == {"branch": "refactor-auth", "actions": ["trocou o hash"], "files": ["auth.py"]}
        store = JsonlSessionStore(home / "sessions", tmp_path, index=index)
        history = replay(store.load(branch.id))
        assert "trocou o hash" in history[0].text and history[1].text == "Entendido."
        assert index.search(SessionQuery(terms=["auth"]))[0].id == branch.id
