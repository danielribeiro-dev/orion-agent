"""Protocolo IPC do daemon (ADR-032): JSON-RPC 2.0 em socket Unix, uma mensagem por linha.

* O socket vive em ``$XDG_RUNTIME_DIR/orion/daemon.sock`` (diretório 0700, socket 0600); sem
  ``XDG_RUNTIME_DIR`` cai em ``~/.orion/run/``. Nunca há TCP.
* Toda conexão é autenticada por ``SO_PEERCRED``: só o mesmo UID do daemon conversa com ele.
* Requisição: ``{"jsonrpc": "2.0", "id": 1, "method": "status", "params": {}}``.
* Evento (notificação JSON-RPC, sem ``id``): ``{"jsonrpc": "2.0", "method": "event",
  "params": {...}}``. O payload é um ``AgentEventEnvelope`` serializado ou um evento de sink
  (``orion.tui.sink``); clientes futuros (aba, voz) consomem o mesmo stream (ADR-034).
"""

from __future__ import annotations

import json
import os
import socket
import struct
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 1_048_576
SOCKET_NAME = "daemon.sock"
#: ``sun_path`` tem 108 bytes no Linux, contando o NUL final.
MAX_SOCKET_PATH = 107

# Códigos JSON-RPC 2.0
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
#: Específico do ORION: o pedido foi negado pela governança.
DENIED = -32001


class IpcError(Exception):
    """Erro devolvido pelo daemon (ou de transporte, com ``code`` ``INTERNAL_ERROR``)."""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


def runtime_dir(home: Path | None = None) -> Path:
    """Diretório do socket: ``$XDG_RUNTIME_DIR/orion`` ou ``~/.orion/run``."""
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg and Path(xdg).is_dir():
        return Path(xdg) / "orion"
    return (home or Path.home() / ".orion") / "run"


def socket_path(home: Path | None = None) -> Path:
    return runtime_dir(home) / SOCKET_NAME


def peer_uid(sock: Any) -> int:
    """``sock``: ``socket.socket`` ou o ``TransportSocket`` do asyncio."""
    # UID do processo do outro lado (SO_PEERCRED: pid, uid, gid).
    raw = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    _pid, uid, _gid = struct.unpack("3i", raw)
    return int(uid)


def encode(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=False, default=str) + "\n").encode()


def decode(line: bytes) -> dict[str, Any]:
    """Uma linha -> objeto JSON. Levanta :class:`IpcError` (``PARSE_ERROR``) se inválida."""
    if len(line) > MAX_LINE_BYTES:
        raise IpcError(PARSE_ERROR, "mensagem grande demais")
    try:
        data = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IpcError(PARSE_ERROR, f"JSON inválido: {exc}") from exc
    if not isinstance(data, dict):
        raise IpcError(INVALID_REQUEST, "a mensagem precisa ser um objeto")
    return data


def request(req_id: int, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def result(req_id: Any, value: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": value}


def error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def event(payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": "event", "params": payload}
