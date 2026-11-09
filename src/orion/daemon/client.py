"""Cliente IPC do daemon: chamadas JSON-RPC, stream de eventos e reconexão.

Usado por ``orion-agent attach``, ``/daemon`` e pelas tools (``daemon_control``, ``schedule_*``).
A aba flutuante e a voz (v0.6.0/v0.7.0) serão outros clientes deste mesmo contrato (ADR-034).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from orion.daemon import ipc


class DaemonUnavailable(ConnectionError):
    """Não há daemon ouvindo no socket."""


class DaemonClient:
    """Uma conexão com o daemon."""

    def __init__(self, path: Path, *, timeout_s: float = 30.0) -> None:
        self.path = path
        self.timeout_s = timeout_s
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._reader_task: asyncio.Task[None] | None = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> DaemonClient:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(self.path), limit=ipc.MAX_LINE_BYTES + 1), 5.0
            )
        except (OSError, TimeoutError) as exc:
            raise DaemonUnavailable(f"daemon indisponível em {self.path}: {exc}") from exc
        self._reader_task = asyncio.create_task(self._read_loop())
        return self

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader_task
        self._writer = None

    async def __aenter__(self) -> DaemonClient:
        return await self.connect()

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    break
                try:
                    message = ipc.decode(line)
                except ipc.IpcError:
                    continue
                if "id" in message and message.get("id") is not None:
                    future = self._pending.pop(int(message["id"]), None)
                    if future is None or future.done():
                        continue
                    if "error" in message:
                        err = message["error"] or {}
                        future.set_exception(
                            ipc.IpcError(int(err.get("code", ipc.INTERNAL_ERROR)), str(err.get("message", "")))
                        )
                    else:
                        future.set_result(message.get("result"))
                elif message.get("method") == "event":
                    params = message.get("params")
                    if isinstance(params, dict):
                        self._events.put_nowait(params)
        except (ConnectionError, OSError, ValueError):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(DaemonUnavailable("conexão com o daemon encerrada"))
            self._pending.clear()
            self._events.put_nowait(None)  # fim do stream

    async def call(self, method: str, params: dict[str, Any] | None = None, *, timeout_s: float | None = None) -> Any:
        if not self.connected:
            raise DaemonUnavailable("cliente não conectado")
        assert self._writer is not None
        req_id = next(self._ids)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        self._writer.write(ipc.encode(ipc.request(req_id, method, params)))
        await self._writer.drain()
        try:
            return await asyncio.wait_for(future, timeout_s or self.timeout_s)
        finally:
            self._pending.pop(req_id, None)

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Eventos publicados após ``subscribe``; termina quando a conexão cai."""
        while True:
            item = await self._events.get()
            if item is None:
                return
            yield item


async def call_once(path: Path, method: str, params: dict[str, Any] | None = None, *, timeout_s: float = 30.0) -> Any:
    """Conecta, chama um método e fecha."""
    async with DaemonClient(path, timeout_s=timeout_s) as client:
        return await client.call(method, params)


async def follow(
    path: Path,
    on_event: Callable[[dict[str, Any]], Awaitable[None] | None],
    *,
    client_name: str = "attach",
    on_state: Callable[[str], None] | None = None,
    stop: asyncio.Event | None = None,
    backoff_s: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0),
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    max_attempts: int | None = None,
) -> None:
    """Assina o stream e reconecta sozinho quando o daemon reinicia (detach não derruba nada).

    ``on_state`` recebe ``connected``/``disconnected``. Termina quando ``stop`` é sinalizado ou
    depois de ``max_attempts`` falhas seguidas.
    """
    stop = stop or asyncio.Event()
    failures = 0
    while not stop.is_set():
        try:
            client = await DaemonClient(path).connect()
        except DaemonUnavailable:
            failures += 1
            if max_attempts is not None and failures >= max_attempts:
                return
            await sleep(backoff_s[min(failures - 1, len(backoff_s) - 1)])
            continue
        failures = 0
        try:
            await client.call("subscribe", {"client": client_name})
            if on_state:
                on_state("connected")
            async for payload in client.events():
                outcome = on_event(payload)
                if asyncio.iscoroutine(outcome):
                    await outcome
                if stop.is_set():
                    break
        except (DaemonUnavailable, ipc.IpcError, TimeoutError):
            pass
        finally:
            await client.close()
            if on_state and not stop.is_set():
                on_state("disconnected")
