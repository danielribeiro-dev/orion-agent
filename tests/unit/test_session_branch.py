"""Threads: session_branch, session_switch, /branch, /merge, /rename e /resume (v0.5.3 Sprint 3, CA-12/CA-13)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from orion.agents.definitions import FORBIDDEN_FOR_CHILD
from orion.governance.bands import TOOL_BANDS, Band
from orion.governance.permissions import ActionLevel, tool_action_level
from orion.sessions import replay
from orion.sessions.index import SessionIndex, SessionRecord
from orion.tui.commands import CommandContext, CommandRegistry
from orion.tui.commands import resume as resume_module
from orion.tui.commands.resume import ResumePicker, build_tree, tree_text
from orion.tui.session import AgentSession
from tests.unit.test_agent_session import call
from tests.unit.test_daily import Clock, make_session


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    return Clock(monkeypatch)


@pytest.fixture
def user_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "u"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    return home


def ctx(session: AgentSession) -> CommandContext:
    return CommandContext(session=session, console=session.console, clear_screen=lambda: None)


class TestGovernance:
    def test_session_tools_are_free_level_zero_and_never_given_to_children(self) -> None:
        for name in ("session_branch", "session_switch"):
            assert TOOL_BANDS[name] == Band.LIVRE
            assert tool_action_level(name) == ActionLevel.LEVEL_0
            assert name in FORBIDDEN_FOR_CHILD


class TestSessionBranchTool:
    async def test_branch_moves_to_a_thread_with_minimal_context(self, user_home: Path, clock: Clock) -> None:
        session = make_session(
            user_home,
            replies=[
                "r1",
                "r2",
                call("session_branch", title="Migração do banco para Postgres 16", reason="tópico sustentado"),
                "Abri a thread, Senhor.",
            ],
        )
        origin = session.session_id
        await session.run_turn("pedido um")
        await session.run_turn("pedido dois")
        await session.run_turn("vamos migrar o banco")
        thread = session.session_id
        assert thread != origin and session.session_kind == "thread"
        assert session.parent_session_id == origin and session.daily_id == "daily-2026-11-16"
        texts = [m.text for m in session.history]
        assert texts[0].startswith("Thread 'Migração do banco para Postgres 16' aberta a partir de 'Daily 16/11/2026")
        assert "Motivo: tópico sustentado" in texts[0] and "pedido um" in texts[0]
        assert "pedido dois" in texts and "vamos migrar o banco" in texts and "pedido um" not in texts[2:]
        assert texts[-1] == "Abri a thread, Senhor."
        # A origem guardou o turno inteiro (tool_use e tool_result pareados).
        origin_texts = [m.text for m in replay(session.sessions.load(origin))]
        assert origin_texts[-1] == "Abri a thread, Senhor."
        record = session.session_index.get(thread)
        assert record is not None and record.title == "Migração do banco para Postgres 16" and record.turn_count == 2
        links = [e.meta for e in session.sessions.load("daily-2026-11-16") if (e.meta or {}).get("event") == "thread_opened"]
        assert links and links[0]["thread_id"] == thread and links[0]["parent_id"] == origin

    async def test_thread_survives_a_reload_by_id(self, user_home: Path, clock: Clock) -> None:
        session = make_session(user_home, replies=[call("session_branch", title="Tema X", reason="r"), "ok", "segue"])
        await session.run_turn("tema x")
        thread = session.session_id
        await session.run_turn("mais sobre x")
        other = make_session(user_home)
        other.resume(thread[:8])
        assert other.session_id == thread and other.history[-1].text == "segue"
        assert other.parent_session_id == "daily-2026-11-16"

    async def test_switch_returns_to_a_session_by_name(self, user_home: Path, clock: Clock) -> None:
        repo = user_home / "proj"
        repo.mkdir()
        earlier = make_session(user_home, repo, replies=["feito"])
        await earlier.run_turn("ajustar o compactador de contexto")
        session = make_session(user_home, replies=[call("session_switch", query="compactador"), "Voltando."])
        await session.run_turn("volte para a sessão do compactador")
        assert session.session_id == earlier.session_id
        assert [m.text for m in session.history][:2] == ["ajustar o compactador de contexto", "feito"]
        assert session.session_kind == "thread" and not session._follow_today  # noqa: SLF001

    async def test_switch_without_match_keeps_the_session(self, user_home: Path, clock: Clock) -> None:
        session = make_session(user_home, replies=[call("session_switch", query="inexistente zzz"), "Não achei."])
        await session.run_turn("volte para zzz")
        assert session.session_id == "daily-2026-11-16"
        assert session.history[-1].text == "Não achei."

    async def test_second_change_in_the_same_turn_is_refused(self, user_home: Path, clock: Clock) -> None:
        session = make_session(
            user_home,
            replies=[call("session_branch", title="A", reason="r"), call("session_branch", title="B", reason="r"), "ok"],
        )
        await session.run_turn("abre duas")
        record = session.session_index.get(session.session_id)
        assert record is not None and record.title == "A"

    async def test_failed_turn_drops_the_pending_switch(self, user_home: Path, clock: Clock) -> None:
        session = make_session(user_home, replies=[call("session_branch", title="A", reason="r")])  # sem resposta final
        assert await session.run_turn("abre") is None
        assert session.session_id == "daily-2026-11-16" and session._pending_switch is None  # noqa: SLF001


class TestBranchAndMerge:
    async def test_branch_and_merge_round_trip(self, user_home: Path, clock: Clock) -> None:
        session = make_session(user_home, replies=["base", "experimento"])
        registry = CommandRegistry.discover()
        await session.run_turn("principal")
        opened = await registry.dispatch("/branch Experimento de cache", ctx(session))
        assert opened.success and "Experimento de cache" in opened.output_message
        thread = session.session_id
        await session.run_turn("tentar cache")
        merged = await registry.dispatch("/merge funcionou", ctx(session))
        assert merged.success and "funcionou" in merged.output_message
        assert session.session_id == "daily-2026-11-16"
        assert session.history[-2].text.startswith("Checkpoint da thread 'Experimento de cache'")
        assert session.session_index.get(thread).card["actions"] == ["tentar cache"]  # type: ignore[index]
        reloaded = make_session(user_home)  # o checkpoint ficou gravado na daily
        assert reloaded.history[-2].text.startswith("Checkpoint da thread")

    async def test_merge_outside_a_child_thread_fails(self, user_home: Path, clock: Clock) -> None:
        result = await CommandRegistry.discover().dispatch("/merge", ctx(make_session(user_home)))
        assert not result.success and "não é uma thread" in result.output_message


class TestRename:
    async def test_rename_is_kept_over_the_provisional_title(self, user_home: Path, clock: Clock) -> None:
        repo = user_home / "proj"
        repo.mkdir()
        session = make_session(user_home, repo, replies=["a", "b"])
        registry = CommandRegistry.discover()
        result = await registry.dispatch("/rename Auditoria do PEP", ctx(session))  # antes do 1º pedido
        assert result.success
        await session.run_turn("primeiro pedido")
        record = session.session_index.get(session.session_id)
        assert record is not None and record.title == "Auditoria do PEP" and record.title_source == "user"
        assert session.session_title == "Auditoria do PEP"
        assert not (await registry.dispatch("/rename    ", ctx(session))).success


def _seed(index: SessionIndex) -> None:
    index.register("daily-2026-11-16", "daily", title="Daily 16/11/2026 (segunda)", turn_count=2, created_at="2026-11-16T13:00:00+00:00")
    index.register("t-hoje", "thread", title="Bug do PEP", daily_id="daily-2026-11-16", workspace="/home/u/orion-agent", turn_count=1, created_at="2026-11-16T14:00:00+00:00")
    index.register("daily-2026-11-15", "daily", title="Daily 15/11/2026 (domingo)", turn_count=1, created_at="2026-11-15T13:00:00+00:00")
    index.register("t-ontem", "thread", title="Plano da v0.6", daily_id="daily-2026-11-15", turn_count=4, created_at="2026-11-15T15:00:00+00:00", closed_at="2026-11-15T18:00:00+00:00")
    index.register("t-out", "thread", title="Revisão de outubro", daily_id="daily-2026-10-02", turn_count=1, created_at="2026-10-02T15:00:00+00:00")
    index.register("t-2025", "thread", title="Antigo", daily_id="daily-2025-12-01", turn_count=1, created_at="2025-12-01T15:00:00+00:00")


class TestResumeTree:
    def test_tree_nests_threads_under_the_daily(self, tmp_path: Path) -> None:
        index = SessionIndex(tmp_path / "s.db")
        _seed(index)
        rows = build_tree(index.search())
        labels = [(r.depth, r.label) for r in rows]
        assert labels[:7] == [
            (0, "2026"),
            (1, "novembro"),
            (2, "16/11 seg"),
            (3, "Daily 16/11/2026 (segunda)"),
            (4, "Bug do PEP"),
            (2, "15/11 dom"),
            (3, "Daily 15/11/2026 (domingo)"),
        ]
        assert (1, "outubro") in labels and (3, "Revisão de outubro") in labels  # dia sem daily
        assert (0, "2025") in labels and (1, "dezembro") in labels
        text = tree_text(rows)
        assert "● Daily 16/11/2026" in text and "› Bug do PEP  (1 pedido(s) · orion-agent" in text
        assert "fechada" in text

    def test_picker_filters_moves_and_chooses(self, user_home: Path, clock: Clock) -> None:
        repo = user_home / "proj"
        repo.mkdir()
        session = make_session(user_home, repo)  # fora de ~: nenhuma daily criada antes do seed
        _seed(session.session_index)  # type: ignore[arg-type]
        picker = ResumePicker(session.nav, current=session.session_id)  # type: ignore[arg-type]
        assert len(picker.records) == 6
        for key in "ontem":
            picker.on_key(key)
        assert [r.id for r in picker.records] == ["t-ontem", "daily-2026-11-15"]
        assert picker.selected_record().id == "daily-2026-11-15"  # type: ignore[union-attr]
        picker.on_key("down")
        assert picker.selected_record().id == "t-ontem"  # type: ignore[union-attr]
        picker.on_key("down")  # volta ao topo
        assert picker.selected_record().id == "daily-2026-11-15"  # type: ignore[union-attr]
        picker.on_key("up")
        assert picker.on_key("enter") and picker.chosen == "t-ontem"
        for _ in "ontem":
            picker.on_key("backspace")
        for key in "nov":
            picker.on_key(key)
        assert {r.id for r in picker.records} == {"daily-2026-11-16", "t-hoje", "daily-2026-11-15", "t-ontem"}
        rendered = str(picker.render())
        assert rendered  # renderiza sem erro
        picker.on_key("x")
        picker.on_key("z")
        assert picker.records == [] and picker.selected_record() is None
        assert picker.on_key("enter") and picker.chosen == "t-ontem"  # nada novo escolhido
        assert picker.on_key("escape")

    async def test_resume_command_lists_filters_and_resumes(self, user_home: Path, clock: Clock, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = user_home / "proj"
        repo.mkdir()
        older = make_session(user_home, repo, replies=["feito"])
        await older.run_turn("revisar o compactador")
        session = make_session(user_home, replies=["bom dia"])
        await session.run_turn("bom dia")
        registry = CommandRegistry.discover()
        listing = await registry.dispatch("/resume hoje", ctx(session))
        assert listing.success and "revisar o compactador" in listing.output_message and older.session_id[:8] in listing.output_message
        assert not (await registry.dispatch("/resume ontem", ctx(session))).success
        assert not (await registry.dispatch("/resume zzzz", ctx(session))).success
        direct = await registry.dispatch(f"/resume {older.session_id[:8]}", ctx(session))
        assert direct.success and session.session_id == older.session_id

        async def fake_modal(controller: Any, console: Any, keep_on_screen: bool = False) -> None:
            for key in "daily":
                controller.on_key(key)
            controller.on_key("enter")

        monkeypatch.setattr(resume_module, "is_interactive", lambda: True)
        monkeypatch.setattr(resume_module, "run_modal", fake_modal)
        picked = await registry.dispatch("/resume", ctx(session))
        assert picked.success and session.session_id == "daily-2026-11-16"
        again = await registry.dispatch("/resume", ctx(session))
        assert "já é a sessão ativa" in again.output_message

    async def test_workspace_filter_and_legacy_listing(self, user_home: Path, clock: Clock) -> None:
        repo = user_home / "proj"
        repo.mkdir()
        session = make_session(user_home, repo, replies=["a"])
        await session.run_turn("pedido no projeto")
        registry = CommandRegistry.discover()
        mine = await registry.dispatch("/resume @.", ctx(session))
        assert mine.success and "pedido no projeto" in mine.output_message
        session.nav = None  # índice indisponível: listagem antiga
        legacy = await registry.dispatch("/resume", ctx(session))
        assert legacy.success


def test_record_display_title_fallbacks() -> None:
    base: dict[str, Any] = {
        "title_source": "auto", "daily_id": None, "parent_id": None, "workspace": None,
        "created_at": "", "updated_at": "", "closed_at": None, "turn_count": 0, "card": None,
        "local_date": date(2026, 11, 16).isoformat(),
    }
    assert SessionRecord(id="d", kind="daily", title="", **base).display_title == "Daily 2026-11-16"
    assert SessionRecord(id="t", kind="thread", title="", **base).display_title == "(sem título)"
