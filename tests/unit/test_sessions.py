"""Sessões persistentes, resume e rewind (Sprint 3, CA-04)."""

from __future__ import annotations

import asyncio
import io
import stat
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.gateway.models import ContentBlock, LLMMessage, MessageRole
from orion.sessions import (
    JsonlSessionStore,
    SessionNotFoundError,
    TranscriptEntry,
    file_changes_from,
    replay,
    user_turns,
)
from orion.sessions.transcript import FileSnapshot, workspace_slug
from orion.tui.commands import CommandContext, CommandRegistry
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.unit.test_agent_session import ScriptedProvider, call


def msg(role: MessageRole, text: str) -> LLMMessage:
    return LLMMessage(role=role, content=text)


@pytest.fixture
def store(tmp_path: Path) -> JsonlSessionStore:
    return JsonlSessionStore(tmp_path / "sessions", tmp_path / "ws")


class TestStore:
    def test_append_load_roundtrip_with_structured_blocks(self, store: JsonlSessionStore) -> None:
        blocks = [ContentBlock.of_text("vou"), ContentBlock.of_tool_use("t1", "read_file", {"path": "a"})]
        store.append("s1", TranscriptEntry.of_message(msg(MessageRole.USER, "oi")))
        store.append("s1", TranscriptEntry.of_message(LLMMessage(role=MessageRole.ASSISTANT, content=blocks)))
        entries = store.load("s1")
        assert [e.index for e in entries] == [0, 1, 2]  # meta + 2 mensagens
        assert entries[0].kind == "meta"
        assert replay(entries)[1].blocks[1].input == {"path": "a"}

    def test_files_are_private(self, store: JsonlSessionStore) -> None:
        store.append("s1", TranscriptEntry.of_message(msg(MessageRole.USER, "segredo")))
        path = next((store._root).glob("*/s1.jsonl"))
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        sha = store.put_blob("s1", "conteudo")
        blob = path.with_suffix(".blobs") / sha
        assert stat.S_IMODE(blob.stat().st_mode) == 0o600 and store.get_blob("s1", sha) == "conteudo"

    def test_truncated_last_line_is_ignored(self, store: JsonlSessionStore) -> None:
        store.append("s1", TranscriptEntry.of_message(msg(MessageRole.USER, "ok")))
        path = next(store._root.glob("*/s1.jsonl"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"kind": "message", "mess')  # crash no meio da escrita
        assert len(replay(store.load("s1"))) == 1

    def test_compact_entry_replaces_conversation(self, store: JsonlSessionStore) -> None:
        for i in range(4):
            store.append("s1", TranscriptEntry.of_message(msg(MessageRole.USER, f"m{i}")))
        store.append("s1", TranscriptEntry.of_compact([msg(MessageRole.USER, "resumo")]))
        store.append("s1", TranscriptEntry.of_message(msg(MessageRole.ASSISTANT, "depois")))
        assert [m.text for m in replay(store.load("s1"))] == ["resumo", "depois"]

    def test_list_is_scoped_to_workspace_and_sorted(self, tmp_path: Path) -> None:
        root = tmp_path / "sessions"
        a, b = tmp_path / "a", tmp_path / "b"
        for ws, sid in ((a, "old"), (a, "new"), (b, "other")):
            s = JsonlSessionStore(root, ws)
            s.append(sid, TranscriptEntry.of_message(msg(MessageRole.USER, f"pedido {sid}")))
        listed = JsonlSessionStore(root, a).list(a)
        assert [m.session_id for m in listed] == ["new", "old"]
        assert listed[0].preview == "pedido new" and listed[0].turns == 1
        assert workspace_slug(a) != workspace_slug(b)

    def test_resolve_prefix(self, store: JsonlSessionStore) -> None:
        for sid in ("abc123", "abd999"):
            store.append(sid, TranscriptEntry.of_message(msg(MessageRole.USER, "x")))
        assert store.resolve_id("abc") == "abc123"
        with pytest.raises(SessionNotFoundError, match="ambíguo"):
            store.resolve_id("ab")
        with pytest.raises(SessionNotFoundError):
            store.resolve_id("zzz")
        with pytest.raises(SessionNotFoundError):
            store.load("nao-existe")

    def test_rewind_truncates_and_appends_continue_numbering(self, store: JsonlSessionStore) -> None:
        for i in range(5):
            store.append("s1", TranscriptEntry.of_message(msg(MessageRole.USER, f"m{i}")))
        store.rewind("s1", 3)
        assert [e.index for e in store.load("s1")] == [0, 1, 2]
        store.append("s1", TranscriptEntry.of_message(msg(MessageRole.USER, "novo")))
        assert [e.index for e in store.load("s1")] == [0, 1, 2, 3]
        assert replay(store.load("s1"))[-1].text == "novo"

    def test_file_changes_are_returned_newest_first(self, store: JsonlSessionStore) -> None:
        store.append("s1", TranscriptEntry.of_message(msg(MessageRole.USER, "p")))
        for i in range(3):
            store.append("s1", TranscriptEntry.of_file(FileSnapshot(path=f"f{i}", after_sha="x")))
        entries = store.load("s1")
        assert [c.path for c in file_changes_from(entries, 3)] == ["f2", "f1"]
        assert user_turns(entries)[0].number == 1


# ── Sessão: resume e rewind ──────────────────────────────────────────────────


@pytest.fixture
def make(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def _make(provider: ScriptedProvider | None = None, answers: list[Any] | None = None) -> AgentSession:
        pending = list(answers or [])

        async def ask(action: Any, level: Any) -> Any:
            return pending.pop(0) if pending else "y"

        console = Console(file=io.StringIO(), width=100, theme=get_orion_theme())
        session = AgentSession(
            status_bar=SessionStatusBar(),
            console=console,
            workspace=tmp_path,
            home=tmp_path / "home",
            provider_factory=lambda spec: provider or ScriptedProvider([]),
            ask_pep=ask,
        )
        session.online = False  # compactação determinística, sem chamadas pagas
        return session

    return _make


def dump(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in messages]


class TestResume:
    async def test_resume_reproduces_conversation_faithfully(self, make, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "a.txt"
        target.write_text("v1")
        first = make(ScriptedProvider([call("read_file", path=str(target)), "li o arquivo", "outra resposta"]))
        await first.run_turn("leia a.txt")
        await first.run_turn("e agora?")

        second = make(ScriptedProvider(["continuando"]))
        note = second.resume()
        assert first.session_id[:8] in note and "2 pedido(s)" in note
        assert dump(second.history) == dump(first.history)

        await second.run_turn("mais um")
        third = make()
        third.resume(second.session_id[:6])
        assert dump(third.history) == dump(second.history)
        assert len(third.history) == len(first.history) + 2

    async def test_continue_picks_latest_session(self, make) -> None:  # type: ignore[no-untyped-def]
        older = make(ScriptedProvider(["a"]))
        await older.run_turn("velha")
        await asyncio.sleep(0.01)
        newer = make(ScriptedProvider(["b"]))
        await newer.run_turn("nova")
        fresh = make()
        fresh.resume()
        assert fresh.session_id == newer.session_id
        assert [m.preview for m in fresh.list_sessions()] == ["nova", "velha"]

    async def test_resume_without_sessions_fails_cleanly(self, make) -> None:  # type: ignore[no-untyped-def]
        with pytest.raises(SessionNotFoundError):
            make().resume()

    async def test_every_message_is_persisted_immediately(self, make) -> None:  # type: ignore[no-untyped-def]
        session = make(ScriptedProvider(["ok"]))
        await session.run_turn("oi")
        kinds = [e.kind for e in session.sessions.load(session.session_id)]
        assert kinds == ["meta", "message", "message"]

    async def test_failed_turn_leaves_transcript_equal_to_live_history(self, make) -> None:  # type: ignore[no-untyped-def]
        provider = ScriptedProvider(["primeira"])
        session = make(provider)
        await session.run_turn("um")
        provider.error = RuntimeError("falha de rede")
        assert await session.run_turn("dois") is None
        reloaded = make()
        reloaded.resume(session.session_id)
        assert dump(reloaded.history) == dump(session.history)
        assert [m.text for m in reloaded.history] == ["um", "primeira"]

    async def test_cancelled_turn_is_resumable_with_valid_pairing(self, make, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "a.txt"
        target.write_text("v")
        session = make(ScriptedProvider([call("read_file", path=str(target)), "fim"]))
        gate = asyncio.Event()
        original = session.runtime.execute

        async def slow(tool: str, params: dict[str, Any]) -> Any:
            gate.set()
            await asyncio.sleep(30)
            return await original(tool, params)

        session.runtime.execute = slow  # type: ignore[method-assign]
        task = asyncio.create_task(session.run_turn("leia"))
        await gate.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        resumed = make()
        resumed.resume(session.session_id)
        assert dump(resumed.history) == dump(session.history)
        assert resumed.history[-1].blocks[0].type == "tool_result" and resumed.history[-1].blocks[0].is_error

    async def test_resume_after_autocompaction_keeps_compacted_state(self, make) -> None:  # type: ignore[no-untyped-def]
        session = make(ScriptedProvider([f"r{i}" for i in range(6)]))
        for i in range(6):
            await session.run_turn(f"p{i}")
        await session.compact()
        other = make()
        other.resume(session.session_id)
        assert dump(other.history) == dump(session.history)
        assert "Resumo da conversa anterior" in other.history[0].text


class TestRewind:
    async def test_rewind_restores_conversation_and_files(self, make, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        existing = tmp_path / "a.py"
        existing.write_text("x = 1\n")
        created = tmp_path / "novo.py"
        provider = ScriptedProvider(
            [
                "sem mudanças",
                call("edit_file", path=str(existing), target="1", replacement="2"),
                call("write_file", path=str(created), content="y = 1\n"),
                "alterei dois arquivos",
                "ultima",
            ]
        )
        session = make(provider)
        await session.run_turn("primeiro")
        await session.run_turn("edite e crie")
        await session.run_turn("terceiro")
        assert existing.read_text() == "x = 2\n" and created.exists()

        message = session.rewind(2)
        assert "antes do pedido 2" in message and "2 arquivo(s) restaurado(s)" in message
        assert existing.read_text() == "x = 1\n"
        assert not created.exists()
        assert [m.text for m in session.history] == ["primeiro", "sem mudanças"]

        # o transcript acompanha: resume reproduz o estado revertido
        again = make()
        again.resume(session.session_id)
        assert dump(again.history) == dump(session.history)

        # e a sessão segue normalmente depois do rewind
        provider.replies.append("depois do rewind")
        await session.run_turn("quarto")
        assert session.history[-1].text == "depois do rewind"

    async def test_conversation_only_keeps_files(self, make, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "a.py"
        target.write_text("x = 1\n")
        session = make(
            ScriptedProvider(["ok", call("edit_file", path=str(target), target="1", replacement="2"), "feito"])
        )
        await session.run_turn("um")
        await session.run_turn("dois")
        session.rewind(2, files=False)
        assert target.read_text() == "x = 2\n"
        assert [m.text for m in session.history] == ["um", "ok"]

    async def test_external_edits_are_never_clobbered(self, make, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "a.py"
        target.write_text("x = 1\n")
        session = make(
            ScriptedProvider(["ok", call("edit_file", path=str(target), target="1", replacement="2"), "feito"])
        )
        await session.run_turn("um")
        await session.run_turn("dois")
        target.write_text("trabalho do usuario\n")
        message = session.rewind(2)
        assert target.read_text() == "trabalho do usuario\n"
        assert "preservado(s) por alteração externa" in message and "a.py" in message

    async def test_successive_edits_to_same_file_roll_back_in_order(self, make, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
        target = tmp_path / "a.py"
        target.write_text("v1\n")
        session = make(
            ScriptedProvider(
                [
                    "ok",
                    call("edit_file", path=str(target), target="v1", replacement="v2"),
                    call("edit_file", path=str(target), target="v2", replacement="v3"),
                    "pronto",
                ]
            )
        )
        await session.run_turn("um")
        await session.run_turn("dois")
        assert target.read_text() == "v3\n"
        session.rewind(2)
        assert target.read_text() == "v1\n"

    async def test_rewind_before_compaction_recovers_full_messages(self, make) -> None:  # type: ignore[no-untyped-def]
        session = make(ScriptedProvider([f"r{i}" for i in range(6)]))
        for i in range(6):
            await session.run_turn(f"p{i}")
        await session.compact()
        assert len(session.history) < 12
        session.rewind(4)
        assert [m.text for m in session.history] == ["p0", "r0", "p1", "r1", "p2", "r2"]

    async def test_invalid_target(self, make) -> None:  # type: ignore[no-untyped-def]
        session = make(ScriptedProvider(["ok"]))
        await session.run_turn("um")
        with pytest.raises(ValueError, match="inexistente"):
            session.rewind(9)


class TestSlashCommands:
    @pytest.fixture
    def ctx(self, make) -> CommandContext:  # type: ignore[no-untyped-def]
        session = make(ScriptedProvider(["a", "b"]))
        return CommandContext(session=session, console=session.console, clear_screen=lambda: None)

    async def test_resume_lists_and_loads(self, ctx: CommandContext, make) -> None:  # type: ignore[no-untyped-def]
        registry = CommandRegistry.discover()
        await ctx.session.run_turn("primeiro pedido")
        listing = await registry.dispatch("/resume", ctx)
        assert ctx.session.session_id[:8] in listing.output_message and "primeiro pedido" in listing.output_message
        other = make()
        other_ctx = CommandContext(session=other, console=other.console, clear_screen=lambda: None)
        loaded = await registry.dispatch(f"/resume {ctx.session.session_id[:8]}", other_ctx)
        assert loaded.success and other.session_id == ctx.session.session_id
        bad = await registry.dispatch("/resume zzzz", other_ctx)
        assert not bad.success

    async def test_rewind_lists_and_executes(self, ctx: CommandContext) -> None:
        registry = CommandRegistry.discover()
        assert "Nenhum pedido" in (await registry.dispatch("/rewind", ctx)).output_message
        await ctx.session.run_turn("um")
        await ctx.session.run_turn("dois")
        listing = await registry.dispatch("/rewind", ctx)
        assert "1  um" in listing.output_message.replace("  ", " ") or "um" in listing.output_message
        done = await registry.dispatch("/rewind 2 --conversa", ctx)
        assert done.success and [m.text for m in ctx.session.history] == ["um", "a"]
        assert not (await registry.dispatch("/rewind 9", ctx)).success


def test_cli_resume_flag_helper(make) -> None:  # type: ignore[no-untyped-def]
    from orion.cli import _resume_session

    session = make()
    assert _resume_session(session, False, "") == ""
    assert "Nenhuma sessão" in _resume_session(session, True, "")
    assert "Iniciando sessão nova" in _resume_session(session, False, "zzz")
