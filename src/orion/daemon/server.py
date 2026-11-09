"""Servidor IPC do daemon: socket Unix 0600, ``SO_PEERCRED`` e stream de eventos (ADR-032).

Os métodos são registrados como corrotinas ``handler(params, conn) -> resultado``. ``subscribe``
é embutido: a conexão passa a receber os eventos publicados com :meth:`IpcServer.publish`.
Cada assinante tem uma fila limitada; quem não lê perde os eventos mais antigos, nunca trava o
daemon. Nada aqui chama modelo: em idle o servidor só espera em ``accept``/``readline``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import stat
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from orion.daemon import ipc

logger = logging.getLogger(__name__)

_QUEUE_MAX = 1000


class Connection:
    """Um cliente conectado."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, uid: int) -> None:
        self.reader = reader
        self.writer = writer
        self.uid = uid
        self.subscribed = False
        self.client_name = ""
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAX)
        self._write_lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        async with self._write_lock:
            self.writer.write(ipc.encode(message))
            await self.writer.drain()

    def offer(self, payload: dict[str, Any]) -> None:
        """Enfileira um evento; cheia, descarta o mais antigo."""
        if self.queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.queue.get_nowait()
        self.queue.put_nowait(payload)


Handler = Callable[[dict[str, Any], Connection], Awaitable[Any]]


class IpcServer:
    """Servidor JSON-RPC em socket Unix, restrito ao UID do dono."""

    def __init__(self, path: Path, *, uid: int | None = None) -> None:
        self.path = path
        self.uid = os.getuid() if uid is None else uid
        self._handlers: dict[str, Handler] = {}
        self._server: asyncio.base_events.Server | None = None
        self._connections: set[Connection] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.rejected_peers = 0

    # ------------------------------------------------------------------

    def register(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    @property
    def methods(self) -> list[str]:
        return sorted([*self._handlers, "subscribe", "unsubscribe"])

    @property
    def subscriber_count(self) -> int:
        return sum(1 for c in self._connections if c.subscribed)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if len(os.fsencode(self.path)) > ipc.MAX_SOCKET_PATH:
            raise RuntimeError(
                f"caminho do socket longo demais para AF_UNIX ({self.path}); defina XDG_RUNTIME_DIR"
            )
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        if self.path.exists() or self.path.is_symlink():
            if await self._alive():
                raise RuntimeError(f"já existe um daemon ouvindo em {self.path}")
            self.path.unlink()
        old_umask = os.umask(0o177)  # o socket nasce 0600, sem janela de corrida
        try:
            self._server = await asyncio.start_unix_server(
                self._serve, path=str(self.path), limit=ipc.MAX_LINE_BYTES + 1
            )
        finally:
            os.umask(old_umask)
        os.chmod(self.path, 0o600)

    async def _alive(self) -> bool:
        if not stat.S_ISSOCK(self.path.lstat().st_mode):
            return False
        try:
            _r, w = await asyncio.wait_for(asyncio.open_unix_connection(str(self.path)), 1.0)
        except (OSError, TimeoutError):
            return False
        w.close()
        with contextlib.suppress(Exception):
            await w.wait_closed()
        return True

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            for conn in list(self._connections):
                conn.writer.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        with contextlib.suppress(FileNotFoundError):
            self.path.unlink()

    # ------------------------------------------------------------------

    def publish(self, payload: dict[str, Any]) -> None:
        """Entrega um evento a todos os assinantes (seguro a partir de qualquer thread)."""
        loop = self._loop
        if loop is None:
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._fanout(payload)
        else:
            loop.call_soon_threadsafe(self._fanout, payload)

    def _fanout(self, payload: dict[str, Any]) -> None:
        for conn in self._connections:
            if conn.subscribed:
                conn.offer(payload)

    # ------------------------------------------------------------------

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        sock = writer.get_extra_info("socket")
        try:
            uid = ipc.peer_uid(sock) if sock is not None else -1
        except (OSError, AttributeError):
            uid = -1
        if uid != self.uid:
            self.rejected_peers += 1
            logger.warning("daemon: conexão recusada de uid %s", uid)
            writer.close()
            return
        conn = Connection(reader, writer, uid)
        self._connections.add(conn)
        pump = asyncio.create_task(self._pump(conn))
        try:
            while True:
                try:
                    line = await reader.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    await conn.send(ipc.error(None, ipc.PARSE_ERROR, "mensagem grande demais"))
                    break
                if not line:
                    break
                if not line.strip():
                    continue
                asyncio.create_task(self._dispatch(conn, line))
        except (ConnectionError, OSError):
            pass
        finally:
            pump.cancel()
            self._connections.discard(conn)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    async def _pump(self, conn: Connection) -> None:
        with contextlib.suppress(ConnectionError, OSError, asyncio.CancelledError):
            while True:
                payload = await conn.queue.get()
                await conn.send(ipc.event(payload))

    async def _dispatch(self, conn: Connection, line: bytes) -> None:
        req_id: Any = None
        notification = False
        try:
            message = ipc.decode(line)
            req_id = message.get("id")
            notification = "id" not in message
            method = message.get("method")
            params = message.get("params") or {}
            if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
                raise ipc.IpcError(ipc.INVALID_REQUEST, "requisição JSON-RPC 2.0 inválida")
            if not isinstance(params, dict):
                raise ipc.IpcError(ipc.INVALID_PARAMS, "params precisa ser um objeto")
            value = await self._call(conn, method, params)
        except ipc.IpcError as exc:
            reply = ipc.error(req_id, exc.code, exc.message)
        except Exception as exc:  # um handler com bug nunca derruba o daemon
            logger.exception("daemon: falha no método")
            reply = ipc.error(req_id, ipc.INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        else:
            reply = ipc.result(req_id, value)
        if notification and "error" not in reply:
            return  # notificação válida do cliente: sem resposta (JSON-RPC 2.0)
        with contextlib.suppress(ConnectionError, OSError):
            await conn.send(reply)

    async def _call(self, conn: Connection, method: str, params: dict[str, Any]) -> Any:
        if method == "subscribe":
            conn.subscribed = True
            conn.client_name = str(params.get("client", ""))[:40]
            return {"subscribed": True, "protocol": ipc.PROTOCOL_VERSION}
        if method == "unsubscribe":
            conn.subscribed = False
            return {"subscribed": False}
        handler = self._handlers.get(method)
        if handler is None:
            raise ipc.IpcError(ipc.METHOD_NOT_FOUND, f"método desconhecido: {method}")
        return await handler(params, conn)
