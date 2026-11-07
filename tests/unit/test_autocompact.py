"""Auto-compactação, poda e limites de saída (Sprint 3, CA-03)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from orion.core.engine import ReActEngine, truncate_output
from orion.core.event_bus import EventBus
from orion.gateway.models import ComplexityTier, ContentBlock, LLMMessage, MessageRole
from orion.timeline.autocompact import (
    PRUNED_MARK,
    AutoCompactor,
    compact_messages,
    deterministic_summary,
    estimate_messages,
    prune_tool_results,
    turn_starts,
)
from orion.timeline.compactor import ContextCompactor
from orion.tui.session import AgentSession
from orion.tui.status_bar import SessionStatusBar
from orion.tui.theme import get_orion_theme
from tests.llm_script import ScriptedLLM, say, use
from tests.unit.test_agent_session import ScriptedProvider

_n = iter(range(10_000))


def user(text: str) -> LLMMessage:
    return LLMMessage(role=MessageRole.USER, content=text)


def assistant(text: str = "", *tools: tuple[str, dict[str, Any]]) -> tuple[LLMMessage, list[str]]:
    blocks = [ContentBlock.of_text(text)] if text else []
    ids = []
    for name, params in tools:
        ids.append(f"toolu_{next(_n)}")
        blocks.append(ContentBlock.of_tool_use(ids[-1], name, params))
    return LLMMessage(role=MessageRole.ASSISTANT, content=blocks), ids


def results(ids: list[str], body: str = "x" * 3000) -> LLMMessage:
    return LLMMessage(role=MessageRole.USER, content=[ContentBlock.of_tool_result(i, body) for i in ids])


def tool_turn(request: str, path: str, body: str = "x" * 3000, answer: str = "feito") -> list[LLMMessage]:
    call, ids = assistant("", ("read_file", {"path": path}))
    return [user(request), call, results(ids, body), assistant(answer)[0]]


def conversation(turns: int) -> list[LLMMessage]:
    out: list[LLMMessage] = []
    for i in range(turns):
        out += tool_turn(f"pedido {i}", f"src/f{i}.py", answer=f"resposta {i}")
    return out


def assert_valid(messages: list[LLMMessage]) -> None:
    """Todo tool_use é respondido na mensagem seguinte e todo tool_result tem origem imediata."""
    assert messages and messages[0].role == MessageRole.USER
    for i, message in enumerate(messages):
        uses = [b.id for b in message.blocks if b.type == "tool_use"]
        if uses:
            nxt = messages[i + 1] if i + 1 < len(messages) else None
            assert nxt is not None, "tool_use sem resposta"
            answered = {b.tool_use_id for b in nxt.blocks if b.type == "tool_result"}
            assert set(uses) <= answered
        answers = [b.tool_use_id for b in message.blocks if b.type == "tool_result"]
        if answers:
            prev = messages[i - 1]
            assert set(answers) <= {b.id for b in prev.blocks if b.type == "tool_use"}, "tool_result órfão"


class TestPrune:
    def test_old_results_lose_body_recent_stay(self) -> None:
        messages = conversation(10)
        pruned, count = prune_tool_results(messages, keep_recent=3)
        assert count == 7
        assert_valid(pruned)
        bodies = [b.content for m in pruned for b in m.blocks if b.type == "tool_result"]
        assert all(PRUNED_MARK in str(b) for b in bodies[:7])
        assert all(len(str(b)) == 3000 for b in bodies[7:])
        assert estimate_messages(pruned) < estimate_messages(messages)

    def test_ids_and_errors_survive(self) -> None:
        call, ids = assistant("", ("read_file", {"path": "a"}))
        err = LLMMessage(
            role=MessageRole.USER, content=[ContentBlock.of_tool_result(ids[0], "e" * 3000, is_error=True)]
        )
        pruned, _ = prune_tool_results([user("p"), call, err, assistant("x")[0]], keep_recent=0)
        block = pruned[2].blocks[0]
        assert block.tool_use_id == ids[0] and block.is_error

    def test_short_results_and_idempotence(self) -> None:
        messages = [m for i in range(4) for m in tool_turn(f"p{i}", "a", body="curto")]
        assert prune_tool_results(messages, keep_recent=1)[1] == 0
        once, _ = prune_tool_results(conversation(8), keep_recent=2)
        assert prune_tool_results(once, keep_recent=2)[1] == 0


class TestCompactMessages:
    async def test_cross_turn_keeps_tail_and_active_request(self) -> None:
        messages = conversation(8) + [user("ATIVO: corrija o bug em src/core.py")]
        outcome = await compact_messages(messages, compactor=ContextCompactor(), keep_turns=2)
        assert outcome is not None
        assert_valid(outcome.messages)
        assert outcome.messages[-1].text == "ATIVO: corrija o bug em src/core.py"
        assert outcome.tokens_after < outcome.tokens_before
        summary = outcome.messages[0].text
        assert "pedido 0" in summary and "src/f3.py" in summary
        assert len(turn_starts(outcome.messages)) == 3  # resumo + 2 turnos da cauda

    async def test_llm_summary_is_used_and_files_are_appended(self) -> None:
        seen: list[str] = []

        async def summarizer(transcript: str, focus: str | None) -> str:
            seen.append(transcript)
            return "RESUMO DO MODELO"

        outcome = await compact_messages(
            conversation(6), compactor=ContextCompactor(), summarizer=summarizer, keep_turns=2
        )
        assert outcome is not None and outcome.used_llm
        text = outcome.messages[0].text
        assert "RESUMO DO MODELO" in text and "src/f0.py" in text
        assert "pedido 0" in seen[0] and "[tool_use] read_file" in seen[0]

    async def test_summarizer_failure_falls_back(self) -> None:
        async def boom(transcript: str, focus: str | None) -> str:
            raise RuntimeError("sem rede")

        outcome = await compact_messages(
            conversation(6), compactor=ContextCompactor(), summarizer=boom, keep_turns=2
        )
        assert outcome is not None and not outcome.used_llm
        assert "Pedidos do usuário" in outcome.messages[0].text

    async def test_intra_turn_cut_keeps_instruction_and_pairing(self) -> None:
        # um único pedido com 12 passos de tools (tarefa longa)
        messages: list[LLMMessage] = [user("REFATORE tudo em src/pkg e rode os testes")]
        for i in range(12):
            call, ids = assistant(f"passo {i}", ("read_file", {"path": f"src/pkg/m{i}.py"}))
            messages += [call, results(ids)]
        outcome = await compact_messages(messages, compactor=ContextCompactor(), keep_turns=2)
        assert outcome is not None
        assert_valid(outcome.messages)
        first = outcome.messages[0]
        assert first.role == MessageRole.USER
        assert "REFATORE tudo em src/pkg e rode os testes" in first.text
        assert "src/pkg/m0.py" in first.text
        assert len(outcome.messages) < len(messages)

    async def test_manual_mode_never_cuts_inside_a_turn(self) -> None:
        messages = conversation(2)
        assert await compact_messages(
            messages, compactor=ContextCompactor(), keep_turns=3, allow_intra=False
        ) is None

    async def test_nothing_to_compact(self) -> None:
        assert await compact_messages([], compactor=ContextCompactor()) is None
        assert await compact_messages([user("só um"), assistant("ok")[0]], compactor=ContextCompactor()) is None

    async def test_focus_is_recorded(self) -> None:
        outcome = await compact_messages(
            conversation(6), compactor=ContextCompactor(), focus="banco de dados", keep_turns=2
        )
        assert outcome is not None and "Foco: banco de dados" in outcome.messages[0].text

    def test_deterministic_summary_lists_requests_and_files(self) -> None:
        text = deterministic_summary(conversation(3))
        assert "pedido 2" in text and "read_file" in text and "src/f1.py" in text


class TestAutoCompactor:
    def make(self, window: int, **kw: Any) -> AutoCompactor:
        return AutoCompactor(
            compactor=ContextCompactor(), window=lambda: window, overhead=lambda: 0, **kw
        )

    async def test_below_threshold_is_untouched(self) -> None:
        messages = conversation(4)
        assert await self.make(1_000_000)(messages) is None

    async def test_between_thresholds_only_prunes(self) -> None:
        messages = conversation(10)
        tokens = estimate_messages(messages)
        compactor = self.make(int(tokens / 0.7))  # ~70% de uso
        out = await compactor(messages)
        assert out is not None and len(out) == len(messages)
        assert any(PRUNED_MARK in str(b.content) for m in out for b in m.blocks if b.type == "tool_result")

    async def test_above_threshold_compacts_and_notifies(self) -> None:
        messages = conversation(12) + [user("ATIVO")]
        events: list[Any] = []
        replaced: list[list[LLMMessage]] = []
        compactor = self.make(
            estimate_messages(messages) // 2, on_compact=events.append, on_replace=replaced.append
        )
        out = await compactor(messages)
        assert out is not None and len(out) < len(messages)
        assert out[-1].text == "ATIVO"
        assert_valid(out)
        assert len(events) == 1 and replaced == [out]

    async def test_observe_calibrates_estimate(self) -> None:
        compactor = self.make(1000)
        messages = conversation(1)
        base = compactor.estimate(messages)
        compactor.observe(base * 2)
        assert compactor.estimate(messages) == pytest.approx(base * 2, rel=0.05)
        compactor.observe(10**9)
        assert compactor.ratio <= 3.0


class TestEngineIntegration:
    async def test_prepare_hook_replaces_messages_before_each_call(self) -> None:
        calls: list[int] = []

        async def prepare(messages: list[LLMMessage]) -> list[LLMMessage] | None:
            calls.append(len(messages))
            return None

        llm = ScriptedLLM(use("read_file", {"path": "x"}), say("fim"))
        engine = ReActEngine(EventBus(), llm, prepare_messages=prepare)
        await engine.run("oi")
        assert calls == [1, 3]

    async def test_replacement_is_what_the_model_sees_and_the_run_continues(self) -> None:
        async def prepare(messages: list[LLMMessage]) -> list[LLMMessage] | None:
            return [user("RESUMIDO")] if len(messages) > 1 else None

        llm = ScriptedLLM(use("read_file", {"path": "x"}), say("fim"))
        engine = ReActEngine(EventBus(), llm, prepare_messages=prepare)
        assert await engine.run("oi") == "fim"
        assert llm.requests[1][0].text == "RESUMIDO"

    async def test_on_message_sees_every_appended_message(self) -> None:
        seen: list[str] = []
        llm = ScriptedLLM(use("read_file", {"path": "x"}), say("fim"))
        engine = ReActEngine(EventBus(), llm, on_message=lambda m: seen.append(m.role.value))
        await engine.run("oi")
        assert seen == ["user", "assistant", "user", "assistant"]

    def test_tool_output_is_truncated_in_the_middle(self) -> None:
        text = "A" * 5000 + "FIM-IMPORTANTE"
        out = truncate_output(text, 1000)
        assert len(out) < 1200 and out.endswith("FIM-IMPORTANTE") and "omitidos" in out
        assert truncate_output("curto", 1000) == "curto"

    async def test_engine_limits_tool_results(self) -> None:
        class Runtime:
            def is_read_only(self, tool: str) -> bool:
                return True

            def tool_specs(self) -> list[Any]:
                return []

            async def execute(self, tool: str, params: dict[str, Any]) -> Any:
                from orion.runtime.provider import RuntimeResult

                return RuntimeResult.ok("Z" * 100_000)

        llm = ScriptedLLM(use("read_file", {"path": "x"}), say("fim"))
        engine = ReActEngine(EventBus(), llm, runtime=Runtime(), tool_output_limit=2000)  # type: ignore[arg-type]
        await engine.run("oi")
        body = str(llm.requests[1][-1].blocks[0].content)
        assert len(body) < 2400 and "omitidos" in body


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    def make(provider: ScriptedProvider) -> AgentSession:
        console = Console(file=io.StringIO(), width=100, theme=get_orion_theme())
        return AgentSession(
            status_bar=SessionStatusBar(),
            console=console,
            workspace=tmp_path,
            home=tmp_path / "home",
            provider_factory=lambda spec: provider,
        )

    return make


class TestSessionAutoCompaction:
    async def test_long_session_never_overflows_and_keeps_active_task(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        # Janela minúscula força a compactação; o resumidor é o determinístico (replies esgotadas).
        replies = [f"resposta {i} " + "palavra " * 200 for i in range(14)]
        provider = ScriptedProvider(replies)
        session = session_factory(provider)
        session.context_window = lambda: 4000  # type: ignore[method-assign]
        session.online = False  # resumo determinístico (sem chamada paga)

        for i in range(12):
            await session.run_turn(f"pedido {i}: " + "contexto " * 150)
        await session.run_turn("ATIVO: finalize o módulo X")

        assert_valid(session.history)
        assert any("ATIVO: finalize o módulo X" in m.text for m in session.history)
        assert any("Resumo da conversa anterior" in m.text for m in session.history)
        assert estimate_messages(session.history) < 4000
        # nenhuma requisição enviada ao provedor passou da janela (com folga de calibração)
        for request in provider.requests:
            assert estimate_messages(request.messages) < 4000 * 1.25
        assert "compactado" in session.console.file.getvalue()  # type: ignore[attr-defined]

    async def test_compaction_uses_cheap_model_when_online(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        class Provider(ScriptedProvider):
            async def stream(self, request):  # type: ignore[no-untyped-def]
                if request.messages[0].text.startswith("Resuma a conversa"):
                    self.replies.insert(0, "RESUMO-LLM")
                async for chunk in super().stream(request):
                    yield chunk

        provider = Provider(["r" + "x" * 800] * 9 + ["final"] * 3)
        session = session_factory(provider)
        # o provedor falso reporta sempre 1000 tokens de prompt (calibração travada em 0,5)
        session.context_window = lambda: 1500  # type: ignore[method-assign]
        for i in range(8):
            await session.run_turn(f"p{i} " + "y" * 600)
        await session.run_turn("ATIVO")
        fast = session.router.tier_model(ComplexityTier.FAST)
        summarizing = [r for r in provider.requests if r.messages[0].text.startswith("Resuma a conversa")]
        assert summarizing and all(r.model == fast for r in summarizing)
        assert any("RESUMO-LLM" in m.text for m in session.history)

    async def test_manual_compact_is_async_and_persisted(self, session_factory) -> None:  # type: ignore[no-untyped-def]
        session = session_factory(ScriptedProvider([f"r{i}" for i in range(6)]))
        session.online = False
        for i in range(6):
            await session.run_turn(f"p{i}")
        message = await session.compact()
        assert "compactado" in message
        reloaded = session.sessions.load(session.session_id)
        assert reloaded[-1].kind == "compact"
