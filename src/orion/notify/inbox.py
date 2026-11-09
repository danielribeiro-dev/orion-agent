"""Inbox do daemon: livro-razão dos itens pendentes do Senhor (ADR-032).

Guarda mensagens, aprovações e alertas com estado (``pending|resolved|expired|read``), a fila do
resumo agrupado (digest) e o log de feedback que alimenta a memória viva (ADR-027). Usa ``sqlite3``
da stdlib em modo WAL, arquivo 0600; todo SQL é parametrizado.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import os
import sqlite3
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from orion.notify.models import FeedbackEvent, NotifyAction, OutgoingMessage

InboxStatus = Literal["pending", "resolved", "expired", "read"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    priority TEXT NOT NULL,
    actions TEXT NOT NULL,
    origin TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    resolution TEXT,
    resolved_by TEXT,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status, created_at);
CREATE TABLE IF NOT EXISTS held (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    signal TEXT NOT NULL,
    channel TEXT NOT NULL,
    rule_key TEXT,
    at TEXT NOT NULL
);
"""

_COLUMNS = (
    "id, kind, title, body, priority, actions, origin, status, created_at, expires_at, "
    "resolution, resolved_by, payload"
)

#: Intervalo de releitura do banco em ``wait_resolution`` (resolução vinda de outro processo).
_POLL_S = 1.0


class InboxItem(BaseModel):
    """Um item do Inbox."""

    id: str
    kind: str
    title: str
    body: str = ""
    priority: str = "normal"
    actions: builtins.list[NotifyAction] = Field(default_factory=builtins.list)
    origin: str = "daemon"
    status: InboxStatus = "pending"
    created_at: datetime
    expires_at: datetime | None = None
    resolution: str | None = None
    resolved_by: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


class Inbox:
    """Livro-razão persistente de itens pendentes, com espera assíncrona por resolução."""

    def __init__(self, db_path: Path, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._path = Path(db_path)
        self._clock = clock
        self._lock = threading.RLock()
        self._waiters: dict[str, builtins.list[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            fd = os.open(self._path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
        os.chmod(self._path, 0o600)
        self._db = sqlite3.connect(str(self._path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # ------------------------------------------------------------------ itens

    def add(self, msg: OutgoingMessage, *, status: InboxStatus = "pending") -> None:
        """Registra a mensagem (substitui item de mesmo id ainda não resolvido)."""
        expires = (
            (msg.created_at + timedelta(seconds=msg.ttl_s)).isoformat()
            if msg.ttl_s is not None
            else None
        )
        with self._lock:
            self._db.execute(
                f"INSERT OR REPLACE INTO items ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    msg.id,
                    msg.kind,
                    msg.title,
                    msg.body,
                    msg.priority,
                    json.dumps([a.model_dump() for a in msg.actions]),
                    msg.origin,
                    status,
                    msg.created_at.isoformat(),
                    expires,
                    None,
                    None,
                    json.dumps(msg.payload, default=str),
                ),
            )
            self._db.commit()

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> InboxItem:
        return InboxItem(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            body=row["body"],
            priority=row["priority"],
            actions=[NotifyAction(**a) for a in json.loads(row["actions"])],
            origin=row["origin"],
            status=row["status"],
            created_at=_parse(row["created_at"]),
            expires_at=_parse(row["expires_at"]) if row["expires_at"] else None,
            resolution=row["resolution"],
            resolved_by=row["resolved_by"],
            payload=json.loads(row["payload"]),
        )

    def get(self, item_id: str) -> InboxItem | None:
        with self._lock:
            row = self._db.execute(
                f"SELECT {_COLUMNS} FROM items WHERE id = ?", (item_id,)
            ).fetchone()
        return self._row_to_item(row) if row else None

    def list(self, *, status: InboxStatus | None = None, limit: int = 50) -> builtins.list[InboxItem]:
        """Itens mais recentes primeiro, opcionalmente filtrados por estado."""
        with self._lock:
            if status is None:
                rows = self._db.execute(
                    f"SELECT {_COLUMNS} FROM items ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = self._db.execute(
                    f"SELECT {_COLUMNS} FROM items WHERE status = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def pending_count(self) -> int:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM items WHERE status = 'pending'").fetchone()
        return int(row[0])

    def mark_read(self, item_id: str) -> None:
        """Marca como lido (só afeta itens ainda pendentes)."""
        with self._lock:
            self._db.execute(
                "UPDATE items SET status = 'read' WHERE id = ? AND status = 'pending'", (item_id,)
            )
            self._db.commit()

    def resolve(self, item_id: str, action_id: str, channel: str) -> bool:
        """Resolve uma única vez. False se ausente, já resolvido ou expirado."""
        with self._lock:
            row = self._db.execute(
                "SELECT status, expires_at FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            if row is None or row["status"] in ("resolved", "expired"):
                return False
            if row["expires_at"] and _parse(row["expires_at"]) <= self._clock():
                self._db.execute("UPDATE items SET status = 'expired' WHERE id = ?", (item_id,))
                self._db.commit()
                self._wake(item_id)
                return False
            self._db.execute(
                "UPDATE items SET status = 'resolved', resolution = ?, resolved_by = ? "
                "WHERE id = ?",
                (action_id, channel, item_id),
            )
            self._db.commit()
        self._wake(item_id)
        return True

    def expire(self, item_id: str) -> bool:
        """Expira um item pendente (TTL esgotado). False se já não estava pendente."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE items SET status = 'expired' WHERE id = ? AND status = 'pending'",
                (item_id,),
            )
            self._db.commit()
            changed = cur.rowcount > 0
        if changed:
            self._wake(item_id)
        return changed

    def expire_due(self, now: datetime) -> builtins.list[str]:
        """Expira todos os pendentes cujo ``expires_at`` já passou; devolve os ids."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, expires_at FROM items WHERE status = 'pending' "
                "AND expires_at IS NOT NULL"
            ).fetchall()
            due = [r["id"] for r in rows if _parse(r["expires_at"]) <= now]
            for item_id in due:
                self._db.execute("UPDATE items SET status = 'expired' WHERE id = ?", (item_id,))
            self._db.commit()
        for item_id in due:
            self._wake(item_id)
        return due

    # ------------------------------------------------------------------ espera

    def _wake(self, item_id: str) -> None:
        with self._lock:
            waiters = self._waiters.pop(item_id, [])
        for loop, event in waiters:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:  # loop já fechado
                continue

    async def wait_resolution(self, item_id: str, timeout_s: float) -> InboxItem | None:
        """Espera o item sair de ``pending`` por resolução ou expiração; None no timeout."""
        loop = asyncio.get_running_loop()
        event = asyncio.Event()
        with self._lock:
            self._waiters.setdefault(item_id, []).append((loop, event))
        deadline = loop.time() + timeout_s
        try:
            while True:
                item = self.get(item_id)
                if item is not None and item.status in ("resolved", "expired"):
                    return item
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return None
                try:
                    await asyncio.wait_for(event.wait(), timeout=min(remaining, _POLL_S))
                    event.clear()
                except TimeoutError:
                    continue
        finally:
            with self._lock:
                lst = self._waiters.get(item_id)
                if lst is not None:
                    lst[:] = [w for w in lst if w[1] is not event]
                    if not lst:
                        self._waiters.pop(item_id, None)

    # ------------------------------------------------------------------ digest

    def hold(self, msg: OutgoingMessage) -> None:
        """Guarda a mensagem para o próximo resumo agrupado."""
        with self._lock:
            self._db.execute("INSERT INTO held (message) VALUES (?)", (msg.model_dump_json(),))
            self._db.commit()

    def take_held(self) -> builtins.list[OutgoingMessage]:
        """Remove e devolve as mensagens seguradas, em ordem de chegada."""
        with self._lock:
            rows = self._db.execute("SELECT seq, message FROM held ORDER BY seq").fetchall()
            self._db.execute("DELETE FROM held")
            self._db.commit()
        return [OutgoingMessage.model_validate_json(r["message"]) for r in rows]

    # ---------------------------------------------------------------- feedback

    def record_feedback(self, ev: FeedbackEvent) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO feedback (message_id, signal, channel, rule_key, at) "
                "VALUES (?,?,?,?,?)",
                (ev.message_id, ev.signal, ev.channel, ev.rule_key, ev.at.isoformat()),
            )
            self._db.commit()

    def feedback(self, limit: int = 100) -> builtins.list[FeedbackEvent]:
        """Feedback mais recente primeiro."""
        with self._lock:
            rows = self._db.execute(
                "SELECT message_id, signal, channel, rule_key, at FROM feedback "
                "ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            FeedbackEvent(
                message_id=r["message_id"],
                signal=r["signal"],
                channel=r["channel"],
                rule_key=r["rule_key"],
                at=_parse(r["at"]),
            )
            for r in rows
        ]
