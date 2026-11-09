"""ThreadExecutor (loop persistente em thread, ADR-029) e a fila de notificações."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator

import pytest

from orion.agents.loop_thread import NotificationQueue, ThreadExecutor
from orion.agents.models import AgentEventEnvelope, AgentResult
from orion.core.events import CURRENT_ACTION_ID
from tests.agent_helpers import wait_until


def _result(agent_id: str = "agent_1", text: str = "ok") -> AgentResult:
    return AgentResult(agent_id=agent_id, status="ok", summary=text, ref="ref://agents/agent_1/result.md")


@pytest.fixture
def executor() -> Iterator[ThreadExecutor]:
    ex = ThreadExecutor()
    yield ex
    ex.shutdown(timeout=3)


async def test_runs_in_a_dedicated_thread_and_handle_is_awaitable(executor: ThreadExecutor) -> None:
    seen: list[str] = []

    async def work() -> AgentResult:
        seen.append(threading.current_thread().name)
        return _result(text="feito")

    handle = executor.submit(work, agent_id="agent_1")
    result = await handle.wait()
    assert result.summary == "feito" and handle.done()
    assert seen == ["orion-agents"] and threading.current_thread().name != "orion-agents"
    assert handle.result(1).summary == "feito"


def test_work_outlives_the_loop_that_submitted_it(executor: ThreadExecutor) -> None:
    """O REPL faz asyncio.run por turno e destrói o loop; a task em segundo plano segue viva."""
    gate = threading.Event()

    async def slow() -> AgentResult:
        while not gate.is_set():
            await asyncio.sleep(0.005)
        return _result(text="terminou depois")

    async def one_turn() -> object:
        return executor.submit(slow, agent_id="agent_1")

    handle = asyncio.run(one_turn())  # esse loop já foi fechado quando a próxima linha roda
    assert not handle.done()
    gate.set()
    assert handle.result(3).summary == "terminou depois"


async def test_contextvars_are_copied_into_the_task(executor: ThreadExecutor) -> None:
    seen: list[str | None] = []

    async def work() -> AgentResult:
        seen.append(CURRENT_ACTION_ID.get())
        return _result()

    token = CURRENT_ACTION_ID.set("action-123")
    try:
        await executor.submit(work, agent_id="agent_1").wait()
    finally:
        CURRENT_ACTION_ID.reset(token)
    assert seen == ["action-123"]


async def test_cancel_stops_a_running_execution(executor: ThreadExecutor) -> None:
    started = threading.Event()
    cancelled = threading.Event()

    async def forever() -> AgentResult:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return _result()

    handle = executor.submit(forever, agent_id="agent_1")
    await wait_until(started.is_set)
    assert executor.running == ["agent_1"]
    await executor.cancel("agent_1")
    assert cancelled.is_set() and handle.done() and executor.running == []
    with pytest.raises(asyncio.CancelledError):
        await handle.wait()
    assert executor.cancel_sync("nope") is False


async def test_errors_reach_the_handle(executor: ThreadExecutor) -> None:
    async def boom() -> AgentResult:
        raise RuntimeError("falhou")

    handle = executor.submit(boom, agent_id="agent_1")
    with pytest.raises(RuntimeError, match="falhou"):
        await handle.wait()


async def test_shutdown_cancels_everything_and_can_restart() -> None:
    ex = ThreadExecutor()
    started = threading.Event()

    async def forever() -> AgentResult:
        started.set()
        await asyncio.sleep(60)
        return _result()

    handle = ex.submit(forever, agent_id="agent_1")
    await wait_until(started.is_set)
    ex.shutdown(timeout=3)
    assert handle.done() and not ex.started
    ex.shutdown()  # idempotente

    async def again() -> AgentResult:
        return _result(text="de novo")

    assert ex.submit(again, agent_id="agent_2").result(3).summary == "de novo"
    ex.shutdown(timeout=3)


async def test_run_coroutine_and_call_soon(executor: ThreadExecutor) -> None:
    async def add() -> int:
        return 2 + 3

    assert executor.run_coroutine(add()).result(3) == 5
    fired = threading.Event()
    executor.call_soon(fired.set)
    await wait_until(fired.is_set)


def test_notification_queue_is_ordered_and_thread_safe() -> None:
    queue = NotificationQueue()

    def producer(base: int) -> None:
        for i in range(50):
            queue.notify(AgentEventEnvelope(agent_id=f"a{base}-{i}", session_id="s", kind="x"))

    threads = [threading.Thread(target=producer, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(queue) == 200
    events = queue.drain()
    assert len(events) == 200 and len(queue) == 0 and queue.drain() == []
    for n in range(4):  # a ordem relativa de cada produtor se mantém
        mine = [e.agent_id for e in events if e.agent_id.startswith(f"a{n}-")]
        assert mine == [f"a{n}-{i}" for i in range(50)]
