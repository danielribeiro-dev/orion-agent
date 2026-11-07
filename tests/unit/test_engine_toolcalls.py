"""v0.5.0 Sprint 2 — loop agêntico nativo: tool_use/tool_result, paralelismo, cancelamento (CA-02)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from orion.core.engine import (
    CANCELLED_MESSAGE,
    CONTINUE_MESSAGE,
    REFUSAL_MESSAGE,
    ModelTurn,
    ReActEngine,
)
from orion.core.errors import TurnBudgetExceeded
from orion.core.event_bus import EventBus
from orion.core.events import ActionEmitted, Observation, TurnCancelledEvent
from orion.core.state import AgentState
from orion.gateway.models import ContentBlock, LLMMessage, MessageRole
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint, Rejection
from orion.governance.permissions import WorkspaceScope
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.runtime.provider import BaseRuntimeProvider, RuntimeResult
from tests.llm_script import ScriptedLLM, say, tool_results, use, uses


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


@pytest.fixture()
def runtime(workspace: Path, tmp_path: Path) -> LocalRuntimeProvider:
    scope = WorkspaceScope([workspace])
    pep = PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO)
    return LocalRuntimeProvider(pep=pep, scope=scope)


def engine_for(llm: Any, runtime: BaseRuntimeProvider | None, bus: EventBus | None = None, **kw: Any) -> ReActEngine:
    return ReActEngine(event_bus=bus or EventBus(), llm=llm, runtime=runtime, max_turns=kw.pop("max_turns", 8), **kw)


class TestMultipleTools:
    async def test_several_tools_in_one_response(self, runtime: LocalRuntimeProvider, workspace: Path) -> None:
        (workspace / "a.txt").write_text("AAA")
        (workspace / "b.txt").write_text("BBB")
        llm = ScriptedLLM(
            uses(("read_file", {"path": str(workspace / "a.txt")}), ("read_file", {"path": str(workspace / "b.txt")})),
            say("lidos"),
        )
        answer = await engine_for(llm, runtime).run("leia")
        assert answer == "lidos"
        results = tool_results(llm.requests[1][-1])
        assert len(results) == 2
        assert "AAA" in str(results[0].content)
        assert "BBB" in str(results[1].content)
        # ids casam com os tool_use, na ordem em que o modelo pediu
        assert [r.tool_use_id for r in results] == [b.id for b in llm.requests[1][-2].blocks if b.type == "tool_use"]

    async def test_tools_are_exposed_with_schemas(self, runtime: LocalRuntimeProvider) -> None:
        llm = ScriptedLLM(say("oi"))
        await engine_for(llm, runtime).run("x")
        specs = {t.name: t for t in llm.tools[0]}
        assert {"read_file", "write_file", "edit_file", "run_command", "search_files"} <= set(specs)
        assert specs["edit_file"].input_schema["required"] == ["path", "target"]
        assert [t.name for t in llm.tools[0]] == sorted(specs)

    async def test_text_before_tool_is_not_part_of_the_answer(self, runtime: LocalRuntimeProvider, workspace: Path) -> None:
        (workspace / "a.txt").write_text("A")
        llm = ScriptedLLM(use("read_file", {"path": str(workspace / "a.txt")}, text="Vou ler. "), say("Feito."))
        assert await engine_for(llm, runtime).run("x") == "Feito."


class TestValidation:
    async def test_missing_required_param_returns_error_result(self, runtime: LocalRuntimeProvider) -> None:
        llm = ScriptedLLM(use("edit_file", {"path": "x"}), say("ok"))
        await engine_for(llm, runtime).run("x")
        result = tool_results(llm.requests[1][-1])[0]
        assert result.is_error
        assert "target" in str(result.content)

    async def test_wrong_type_returns_error_result(self, runtime: LocalRuntimeProvider) -> None:
        llm = ScriptedLLM(use("read_file", {"path": 42}), say("ok"))
        await engine_for(llm, runtime).run("x")
        assert tool_results(llm.requests[1][-1])[0].is_error

    async def test_invalid_params_never_reach_the_pep(self, workspace: Path) -> None:
        scope = WorkspaceScope([workspace])
        pep = PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO)
        calls: list[str] = []
        original = pep.evaluate

        async def spy(action: Any) -> Any:
            calls.append(action.tool)
            return await original(action)

        pep.evaluate = spy  # type: ignore[method-assign]
        runtime = LocalRuntimeProvider(pep=pep, scope=scope)
        llm = ScriptedLLM(use("write_file", {"path": "x"}), say("ok"))
        await engine_for(llm, runtime).run("x")
        assert calls == []

    async def test_unknown_tool_is_an_error_result(self, runtime: LocalRuntimeProvider) -> None:
        llm = ScriptedLLM(use("inexistente", {}), say("ok"))
        answer = await engine_for(llm, runtime).run("x")
        assert answer == "ok"
        result = tool_results(llm.requests[1][-1])[0]
        assert result.is_error
        assert "unknown tool" in str(result.content)

    async def test_mutating_tool_goes_through_the_pep(self, workspace: Path) -> None:
        scope = WorkspaceScope([workspace])
        pep = PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO)
        seen: list[str] = []
        original = pep.evaluate

        async def spy(action: Any) -> Any:
            seen.append(action.tool)
            return await original(action)

        pep.evaluate = spy  # type: ignore[method-assign]
        runtime = LocalRuntimeProvider(pep=pep, scope=scope)
        target = workspace / "n.txt"
        llm = ScriptedLLM(use("write_file", {"path": str(target), "content": "oi"}), say("ok"))
        await engine_for(llm, runtime).run("x")
        assert seen == ["write_file"]
        assert target.read_text() == "oi"

    async def test_pep_denial_is_an_error_result(self, workspace: Path, tmp_path: Path) -> None:
        scope = WorkspaceScope([workspace])
        pep = PolicyEnforcementPoint(scope=scope, mode=AutonomyMode.FULLY_AUTO)
        runtime = LocalRuntimeProvider(pep=pep, scope=scope)
        outside = tmp_path / "fora.txt"
        llm = ScriptedLLM(use("write_file", {"path": str(outside), "content": "x"}), say("ok"))
        await engine_for(llm, runtime).run("x")
        assert tool_results(llm.requests[1][-1])[0].is_error
        assert not outside.exists()

    async def test_failed_command_returns_its_output(self, runtime: LocalRuntimeProvider) -> None:
        """F-06: o modelo precisa ver o traceback quando o comando sai com código != 0."""
        cmd = "echo TRACEBACK_VISIVEL; exit 3"
        llm = ScriptedLLM(use("run_command", {"command": cmd}), say("ok"))
        await engine_for(llm, runtime).run("x")
        result = tool_results(llm.requests[1][-1])[0]
        assert result.is_error
        text = str(result.content)
        assert "exited with code 3" in text
        assert "TRACEBACK_VISIVEL" in text

    async def test_plan_mode_rejection_is_not_reported_as_user_rejection(self, workspace: Path) -> None:
        """F-02: a negação do modo plano deve dizer o motivo real."""
        scope = WorkspaceScope([workspace])
        pep = PolicyEnforcementPoint(
            scope=scope,
            mode=AutonomyMode.SUPERVISED,
            action_confirm=lambda action, level: Rejection("plan mode is read-only"),
        )
        runtime = LocalRuntimeProvider(pep=pep, scope=scope)
        llm = ScriptedLLM(use("write_file", {"path": str(workspace / "x.txt"), "content": "x"}), say("ok"))
        await engine_for(llm, runtime).run("x")
        text = str(tool_results(llm.requests[1][-1])[0].content)
        assert "plan mode is read-only" in text
        assert "user rejected" not in text
        assert not (workspace / "x.txt").exists()


class SlowRuntime(BaseRuntimeProvider):
    """Runtime falso que mede concorrência: leituras dormem, escritas registram a ordem."""

    def __init__(self, read_only: set[str]) -> None:
        self.read_only = read_only
        self.running = 0
        self.max_running = 0
        self.order: list[str] = []

    def supports(self, tool: str) -> bool:
        return True

    def is_read_only(self, tool: str) -> bool:
        return tool in self.read_only

    async def execute(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
        self.running += 1
        self.max_running = max(self.max_running, self.running)
        self.order.append(f"start:{params.get('id')}")
        await asyncio.sleep(0.05)
        self.order.append(f"end:{params.get('id')}")
        self.running -= 1
        return RuntimeResult.ok(f"{tool}:{params.get('id')}")


class TestParallelism:
    async def test_read_only_tools_run_in_parallel(self) -> None:
        rt = SlowRuntime(read_only={"read_file"})
        llm = ScriptedLLM(uses(*[("read_file", {"id": i}) for i in range(3)]), say("ok"))
        await engine_for(llm, rt).run("x")
        assert rt.max_running == 3

    async def test_mutating_tools_run_in_series(self) -> None:
        rt = SlowRuntime(read_only=set())
        llm = ScriptedLLM(uses(*[("write_file", {"id": i}) for i in range(3)]), say("ok"))
        await engine_for(llm, rt).run("x")
        assert rt.max_running == 1
        assert rt.order == ["start:0", "end:0", "start:1", "end:1", "start:2", "end:2"]

    async def test_mutation_is_a_barrier_between_reads(self) -> None:
        rt = SlowRuntime(read_only={"read_file"})
        llm = ScriptedLLM(
            uses(
                ("read_file", {"id": "r1"}),
                ("read_file", {"id": "r2"}),
                ("write_file", {"id": "w"}),
                ("read_file", {"id": "r3"}),
            ),
            say("ok"),
        )
        await engine_for(llm, rt).run("x")
        assert rt.order.index("end:r1") < rt.order.index("start:w")
        assert rt.order.index("end:r2") < rt.order.index("start:w")
        assert rt.order.index("end:w") < rt.order.index("start:r3")

    async def test_results_keep_the_model_order(self) -> None:
        rt = SlowRuntime(read_only={"read_file"})
        llm = ScriptedLLM(uses(*[("read_file", {"id": i}) for i in range(4)]), say("ok"))
        await engine_for(llm, rt).run("x")
        contents = [str(r.content) for r in tool_results(llm.requests[1][-1])]
        assert [c.split("read_file:")[1].split("\n")[0] for c in contents] == ["0", "1", "2", "3"]

    async def test_events_are_emitted_per_call(self) -> None:
        bus = EventBus()
        rt = SlowRuntime(read_only={"read_file"})
        llm = ScriptedLLM(uses(("read_file", {"id": 1}), ("read_file", {"id": 2})), say("ok"))
        await engine_for(llm, rt, bus).run("x")
        assert len(bus.history_of(ActionEmitted)) == 2
        assert len(bus.history_of(Observation)) == 2

    async def test_real_runtime_classifies_read_only_by_pep_level(self, runtime: LocalRuntimeProvider) -> None:
        assert runtime.is_read_only("read_file")
        assert runtime.is_read_only("search_files")
        assert not runtime.is_read_only("write_file")
        assert not runtime.is_read_only("run_command")
        assert not runtime.is_read_only("inexistente")


class TestStopReasons:
    async def test_max_tokens_continues_and_joins_text(self) -> None:
        llm = ScriptedLLM(say("parte um, ", stop_reason="max_tokens"), say("parte dois."))
        answer = await engine_for(llm, None).run("x")
        assert answer == "parte um, parte dois."
        assert llm.requests[1][-1].content == CONTINUE_MESSAGE
        assert [m.role for m in llm.requests[1]] == [MessageRole.USER, MessageRole.ASSISTANT, MessageRole.USER]

    async def test_max_tokens_continuation_is_bounded(self) -> None:
        llm = ScriptedLLM(say("x", stop_reason="max_tokens"), repeat=True)
        answer = await engine_for(llm, None, max_turns=20).run("x")
        assert answer == "xxxx"  # 1 + 3 continuações
        assert len(llm.requests) == 4

    async def test_refusal_is_reported(self) -> None:
        llm = ScriptedLLM(ModelTurn([ContentBlock.of_text("não posso")], "refusal"))
        answer = await engine_for(llm, None).run("x")
        assert answer.endswith(REFUSAL_MESSAGE)
        assert "não posso" in answer

    async def test_empty_response_does_not_poison_the_conversation(self) -> None:
        llm = ScriptedLLM(ModelTurn([], "end_turn"))
        engine = engine_for(llm, None)
        assert await engine.run("x") == ""
        assert [m.role for m in engine.messages] == [MessageRole.USER]

    async def test_turn_budget_counts_model_calls(self, runtime: LocalRuntimeProvider) -> None:
        llm = ScriptedLLM(use("search_files", {}), repeat=True)
        with pytest.raises(TurnBudgetExceeded):
            await engine_for(llm, runtime, max_turns=3).run("x")
        assert len(llm.requests) == 3


class HangingRuntime(BaseRuntimeProvider):
    def __init__(self) -> None:
        self.started = asyncio.Event()

    def supports(self, tool: str) -> bool:
        return True

    def is_read_only(self, tool: str) -> bool:
        return tool == "read_file"

    async def execute(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
        self.started.set()
        await asyncio.sleep(60)
        return RuntimeResult.ok("never")


class TestCancellation:
    async def test_cancel_closes_pending_tool_use_with_synthetic_result(self) -> None:
        bus = EventBus()
        rt = HangingRuntime()
        llm = ScriptedLLM(uses(("read_file", {}), ("write_file", {})), say("nunca"))
        engine = engine_for(llm, rt, bus)
        task = asyncio.create_task(engine.run("x"))
        await rt.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        messages = engine.messages
        assert messages[-2].role == MessageRole.ASSISTANT
        results = tool_results(messages[-1])
        assert len(results) == 2
        assert all(r.is_error and r.content == CANCELLED_MESSAGE for r in results)
        assert [r.tool_use_id for r in results] == [b.id for b in messages[-2].blocks if b.type == "tool_use"]
        assert len(bus.history_of(TurnCancelledEvent)) == 1
        assert engine.state == AgentState.IDLE

    async def test_conversation_stays_valid_for_the_next_turn(self) -> None:
        rt = HangingRuntime()
        llm = ScriptedLLM(use("write_file", {}), say("retomando"))
        engine = engine_for(llm, rt)
        task = asyncio.create_task(engine.run("primeiro"))
        await rt.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        llm2 = ScriptedLLM(say("retomando"))
        answer = await engine_for(llm2, None).run("segundo", history=engine.messages)
        assert answer == "retomando"
        roles = [m.role for m in llm2.requests[0]]
        assert roles == [MessageRole.USER, MessageRole.ASSISTANT, MessageRole.USER, MessageRole.USER]

    async def test_cancel_during_the_model_call_keeps_history_consistent(self) -> None:
        started = asyncio.Event()

        async def slow_llm(**_: Any) -> ModelTurn:
            started.set()
            await asyncio.sleep(60)
            return say("never")

        engine = engine_for(slow_llm, None)
        task = asyncio.create_task(engine.run("x"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [m.role for m in engine.messages] == [MessageRole.USER]


class TestStubRuntime:
    async def test_without_runtime_tool_use_gets_a_stub_observation(self) -> None:
        llm = ScriptedLLM(use("read_file", {"path": "/x"}), say("ok"))
        await engine_for(llm, None).run("x")
        assert "[stub]" in str(tool_results(llm.requests[1][-1])[0].content)

    async def test_runtime_exception_becomes_error_result(self) -> None:
        class Boom(BaseRuntimeProvider):
            def supports(self, tool: str) -> bool:
                return True

            async def execute(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
                raise RuntimeError("explodiu")

        llm = ScriptedLLM(use("read_file", {}), say("ok"))
        assert await engine_for(llm, Boom()).run("x") == "ok"
        result = tool_results(llm.requests[1][-1])[0]
        assert result.is_error
        assert "explodiu" in str(result.content)


def test_messages_are_independent_copies() -> None:
    engine = engine_for(ScriptedLLM(say("a")), None)
    assert engine.messages == []
    msgs: list[LLMMessage] = engine.messages
    msgs.append(LLMMessage(role=MessageRole.USER, content="x"))
    assert engine.messages == []
