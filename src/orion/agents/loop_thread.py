"""Loop asyncio persistente em thread dedicada (ADR-029).

O REPL roda ``asyncio.run`` por turno e destrói o loop ao final; uma task asyncio comum morreria
entre dois prompts. Aqui existe UM loop vivo numa thread daemon, que hospeda os subagents em
segundo plano. ``Ctrl+C`` no REPL cancela o turno, não este loop.

* :class:`ThreadExecutor` implementa ``ExecutorPort`` (``submit``/``cancel``). Cada execução copia
  o ``contextvars`` de quem a submeteu (``CURRENT_ACTION_ID`` etc.).
* :class:`NotificationQueue` implementa ``NotifierPort`` com uma fila thread-safe que o REPL drena
  antes de cada prompt e que a toolbar consulta. Término chega por evento: nada aqui chama o
  modelo enquanto se espera (zero token, ADR-022).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import contextvars
import logging
import queue
import threading
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from orion.agents.models import AgentEventEnvelope, AgentResult

logger = logging.getLogger(__name__)

T = TypeVar("T")


class NotificationQueue:
    """Fila thread-safe de eventos para o Senhor (``NotifierPort``)."""

    def __init__(self) -> None:
        self._queue: queue.Queue[AgentEventEnvelope] = queue.Queue()

    def notify(self, event: AgentEventEnvelope) -> None:
        self._queue.put(event)

    def drain(self) -> list[AgentEventEnvelope]:
        """Tudo o que chegou desde a última drenagem, na ordem de chegada."""
        events: list[AgentEventEnvelope] = []
        while True:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                return events

    def __len__(self) -> int:
        return self._queue.qsize()


class ExecutionHandle:
    """Alça de uma execução em segundo plano (``TaskHandle``)."""

    def __init__(self, agent_id: str, future: concurrent.futures.Future[AgentResult]) -> None:
        self.agent_id = agent_id
        self._future = future

    def done(self) -> bool:
        return self._future.done()

    async def wait(self) -> AgentResult:
        """Aguarda o término a partir de QUALQUER loop (propaga cancelamento/erros)."""
        return await asyncio.wrap_future(self._future)

    def result(self, timeout: float | None = None) -> AgentResult:
        """Versão bloqueante (para threads ou testes síncronos)."""
        return self._future.result(timeout)


class ThreadExecutor:
    """Executa corrotinas num loop asyncio persistente, em uma thread daemon."""

    def __init__(self, name: str = "orion-agents") -> None:
        self._name = name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._tasks: dict[str, asyncio.Task[AgentResult]] = {}
        self._stopping = False

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    @property
    def started(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Sobe a thread e o loop (idempotente)."""
        with self._lock:
            if self.started:
                return
            self._ready.clear()
            self._stopping = False
            self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
            self._thread.start()
        if not self._ready.wait(5.0):  # pragma: no cover - a thread sobe em milissegundos
            raise RuntimeError("ThreadExecutor: o loop não iniciou")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            with contextlib.suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    def shutdown(self, timeout: float = 5.0) -> None:
        """Cancela tudo, para o loop e junta a thread (cascata ao encerrar a sessão)."""
        if not self.started or self._loop is None:
            return
        self._stopping = True
        self.cancel_all(timeout=timeout)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout)

    # ------------------------------------------------------------------
    # ExecutorPort
    # ------------------------------------------------------------------

    def submit(
        self, coro_factory: Callable[[], Awaitable[AgentResult]], *, agent_id: str
    ) -> ExecutionHandle:
        """Agenda a execução; o ``contextvars`` do chamador é copiado para a task."""
        self.start()
        loop = self._loop
        assert loop is not None
        future: concurrent.futures.Future[AgentResult] = concurrent.futures.Future()
        context = contextvars.copy_context()

        def schedule() -> None:
            task = loop.create_task(self._wrap(coro_factory, agent_id, future))
            self._tasks[agent_id] = task

        loop.call_soon_threadsafe(schedule, context=context)
        return ExecutionHandle(agent_id, future)

    async def _wrap(
        self,
        coro_factory: Callable[[], Awaitable[AgentResult]],
        agent_id: str,
        future: concurrent.futures.Future[AgentResult],
    ) -> AgentResult:
        try:
            result = await coro_factory()
        except asyncio.CancelledError:
            future.cancel()
            raise
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            logger.exception("ThreadExecutor: execução %s falhou", agent_id)
            raise
        else:
            future.set_result(result)
            return result
        finally:
            self._tasks.pop(agent_id, None)

    async def cancel(self, agent_id: str) -> None:
        """Cancela uma execução e aguarda ela terminar de se desfazer."""
        await asyncio.get_running_loop().run_in_executor(None, self.cancel_sync, agent_id)

    def cancel_sync(self, agent_id: str, timeout: float = 5.0) -> bool:
        """Cancela e espera (bloqueante). ``False`` se não havia execução com esse id."""
        loop, task = self._loop, self._tasks.get(agent_id)
        if loop is None or task is None:
            return False
        done = threading.Event()

        def request_cancel() -> None:
            task.cancel()
            task.add_done_callback(lambda _t: done.set())

        loop.call_soon_threadsafe(request_cancel)
        done.wait(timeout)
        return True

    def cancel_all(self, timeout: float = 5.0) -> int:
        """Cancela todas as execuções; devolve quantas estavam ativas."""
        ids = list(self._tasks)
        for agent_id in ids:
            self.cancel_sync(agent_id, timeout)
        return len(ids)

    @property
    def running(self) -> list[str]:
        return sorted(self._tasks)

    # ------------------------------------------------------------------
    # Corrotinas auxiliares (agendadores, loops)
    # ------------------------------------------------------------------

    def run_coroutine(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """Roda uma corrotina qualquer no loop de fundo (usada pelo ``/loop``)."""
        self.start()
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def call_soon(self, callback: Callable[[], None]) -> None:
        self.start()
        assert self._loop is not None
        self._loop.call_soon_threadsafe(callback)
