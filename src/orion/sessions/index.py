"""
O.R.I.O.N — Índice de sessões ``~/.orion/sessions.db`` (v0.5.3 Sprint 3, ADR-051)

Os JSONL continuam sendo o transcript; este índice guarda o que se busca: tipo
(``daily``/``thread``), título (provisório ou do Senhor), daily de origem, pai, workspace,
datas, contagem de pedidos e cartão. FTS5 sobre título e cartão (sem acento: ``sessao``
acha ``sessão``). Atualizado a cada turno, sem reler arquivos.

A migração dos JSONL da v0.5.2 (e das branches arquivadas em ``timeline/archive``) é
idempotente e faz backup em ``~/.orion/backup/v0.5.2/`` antes de indexar.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, time, tzinfo
from pathlib import Path
from typing import Any, Literal

from orion.sessions.clock import daily_id_for, is_daily_id, local_day, parse_hhmm, parse_iso
from orion.sessions.query import SessionQuery, fts_expression

logger = logging.getLogger(__name__)

SessionKind = Literal["daily", "thread"]
TitleSource = Literal["auto", "user"]
TITLE_MAX = 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('daily', 'thread')),
    title TEXT NOT NULL DEFAULT '',
    title_source TEXT NOT NULL DEFAULT 'auto' CHECK (title_source IN ('auto', 'user')),
    daily_id TEXT,
    parent_id TEXT,
    workspace TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    turn_count INTEGER NOT NULL DEFAULT 0,
    card_json TEXT,
    local_date TEXT NOT NULL,
    opening TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_local_date ON sessions(local_date);
CREATE INDEX IF NOT EXISTS idx_sessions_daily ON sessions(daily_id);
CREATE INDEX IF NOT EXISTS idx_sessions_workspace ON sessions(workspace, updated_at);
CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts USING fts5(
    id UNINDEXED, title, card, tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_COLUMNS = (
    "id, kind, title, title_source, daily_id, parent_id, workspace, created_at, updated_at, "
    "closed_at, turn_count, card_json, local_date, opening"
)


def provisional_title(text: str) -> str:
    """Título provisório determinístico: o primeiro pedido, até 60 caracteres, sem cortar palavra."""
    flat = " ".join(text.split())
    if len(flat) <= TITLE_MAX:
        return flat
    cut = flat[:TITLE_MAX]
    space = cut.rfind(" ")
    return (cut[:space] if space > TITLE_MAX // 2 else cut).rstrip(" ,.;:-")


def card_text(card: dict[str, Any] | None) -> str:
    """Texto indexável do cartão (valores, não chaves)."""
    if not card:
        return ""
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(card)
    return " ".join(parts)


@dataclass(frozen=True)
class SessionRecord:
    """Uma linha do índice."""

    id: str
    kind: SessionKind
    title: str
    title_source: TitleSource
    daily_id: str | None
    parent_id: str | None
    workspace: str | None
    created_at: str
    updated_at: str
    closed_at: str | None
    turn_count: int
    card: dict[str, Any] | None
    local_date: str
    opening: str | None = None

    @property
    def display_title(self) -> str:
        if self.title:
            return self.title
        return f"Daily {self.local_date}" if self.kind == "daily" else "(sem título)"

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SessionRecord:
        card = json.loads(row["card_json"]) if row["card_json"] else None
        return cls(
            id=row["id"],
            kind=row["kind"],
            title=row["title"],
            title_source=row["title_source"],
            daily_id=row["daily_id"],
            parent_id=row["parent_id"],
            workspace=row["workspace"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            turn_count=row["turn_count"],
            card=card,
            local_date=row["local_date"],
            opening=row["opening"],
        )


@dataclass
class MigrationReport:
    sessions: int = 0
    branches: int = 0
    backed_up: int = 0

    def summary(self) -> str:
        return f"{self.sessions} sessão(ões) e {self.branches} branch(es) indexadas"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SessionIndex:
    """``sessions.db``: leitura e escrita parametrizadas, seguro entre threads e processos (WAL)."""

    def __init__(self, db_path: Path, *, day_starts_at: str | time = "04:00", tz: tzinfo | None = None) -> None:
        self.db_path = db_path
        self.starts_at = day_starts_at if isinstance(day_starts_at, time) else parse_hhmm(day_starts_at)
        self.tz = tz
        self._lock = threading.RLock()
        db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fresh = not db_path.exists()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        if fresh:
            os.chmod(db_path, 0o600)
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    # ── Datas ──

    def day_of(self, iso: str) -> str:
        return local_day(parse_iso(iso), self.starts_at, self.tz).isoformat()

    # ── Escrita ──

    def register(
        self,
        session_id: str,
        kind: SessionKind,
        *,
        title: str = "",
        title_source: TitleSource = "auto",
        daily_id: str | None = None,
        parent_id: str | None = None,
        workspace: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
        turn_count: int = 0,
        card: dict[str, Any] | None = None,
        closed_at: str | None = None,
        opening: str | None = None,
    ) -> SessionRecord:
        """Cria a linha se não existir (idempotente) e devolve o estado atual."""
        created = created_at or _now()
        local_date = session_id[len("daily-") :] if is_daily_id(session_id) else self.day_of(created)
        with self._tx() as conn:
            cursor = conn.execute(
                f"INSERT OR IGNORE INTO sessions ({_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    kind,
                    title,
                    title_source,
                    daily_id,
                    parent_id,
                    workspace,
                    created,
                    updated_at or created,
                    closed_at,
                    turn_count,
                    json.dumps(card, ensure_ascii=False) if card else None,
                    local_date,
                    opening,
                ),
            )
            if cursor.rowcount:
                self._reindex(conn, session_id, title, card)
        record = self.get(session_id)
        assert record is not None
        return record

    @staticmethod
    def _reindex(conn: sqlite3.Connection, session_id: str, title: str, card: dict[str, Any] | None) -> None:
        conn.execute("DELETE FROM sessions_fts WHERE id = ?", (session_id,))
        conn.execute(
            "INSERT INTO sessions_fts (id, title, card) VALUES (?, ?, ?)",
            (session_id, title, card_text(card)),
        )

    def _refresh_fts(self, conn: sqlite3.Connection, session_id: str) -> None:
        row = conn.execute("SELECT title, card_json FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is not None:
            card = json.loads(row["card_json"]) if row["card_json"] else None
            self._reindex(conn, session_id, row["title"], card)

    def record_turn(self, session_id: str, text: str, *, at: str | None = None) -> None:
        """Um pedido do Senhor: conta, atualiza a data e dá título provisório se ainda não houver."""
        moment = at or _now()
        with self._tx() as conn:
            conn.execute(
                "UPDATE sessions SET turn_count = turn_count + 1, updated_at = ? WHERE id = ?",
                (moment, session_id),
            )
            title = provisional_title(text)
            cursor = conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ? AND title = '' AND title_source = 'auto' AND kind = 'thread'",
                (title, session_id),
            )
            if cursor.rowcount:
                self._refresh_fts(conn, session_id)

    def touch(self, session_id: str, *, at: str | None = None) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (at or _now(), session_id))

    def rename(self, session_id: str, title: str) -> bool:
        """``/rename``: título do Senhor, nunca mais sobrescrito pelo automático."""
        clean = " ".join(title.split())
        if not clean:
            return False
        with self._tx() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET title = ?, title_source = 'user' WHERE id = ?", (clean, session_id)
            )
            if cursor.rowcount:
                self._refresh_fts(conn, session_id)
            return bool(cursor.rowcount)

    def set_auto_title(self, session_id: str, title: str) -> bool:
        """Título automático (Mordomo, Sprint 4): ignorado quando o Senhor já deu um."""
        clean = " ".join(title.split())
        with self._tx() as conn:
            cursor = conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ? AND title_source = 'auto'", (clean, session_id)
            )
            if cursor.rowcount:
                self._refresh_fts(conn, session_id)
            return bool(cursor.rowcount)

    def set_card(self, session_id: str, card: dict[str, Any] | None) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE sessions SET card_json = ? WHERE id = ?",
                (json.dumps(card, ensure_ascii=False) if card else None, session_id),
            )
            self._refresh_fts(conn, session_id)

    def close_session(self, session_id: str, *, card: dict[str, Any] | None = None, at: str | None = None) -> None:
        with self._tx() as conn:
            conn.execute(
                "UPDATE sessions SET closed_at = COALESCE(closed_at, ?) WHERE id = ?", (at or _now(), session_id)
            )
        if card is not None:
            self.set_card(session_id, card)

    def reopen(self, session_id: str) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE sessions SET closed_at = NULL WHERE id = ?", (session_id,))

    def set_opening(self, session_id: str, opening: str) -> None:
        with self._tx() as conn:
            conn.execute("UPDATE sessions SET opening = ? WHERE id = ?", (opening, session_id))

    # ── Leitura ──

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            row = self._conn.execute(f"SELECT {_COLUMNS} FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return SessionRecord.from_row(row) if row is not None else None

    def children(self, daily_id: str) -> list[SessionRecord]:
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM sessions WHERE daily_id = ? AND id != ? ORDER BY created_at",
                (daily_id, daily_id),
            ).fetchall()
        return [SessionRecord.from_row(r) for r in rows]

    def open_dailies_before(self, daily_id: str) -> list[SessionRecord]:
        """Dailies ainda abertas de dias anteriores (fecham na virada)."""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_COLUMNS} FROM sessions WHERE kind = 'daily' AND closed_at IS NULL AND id < ? ORDER BY id",
                (daily_id,),
            ).fetchall()
        return [SessionRecord.from_row(r) for r in rows]

    def latest_daily_before(self, daily_id: str) -> SessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {_COLUMNS} FROM sessions WHERE kind = 'daily' AND id < ? ORDER BY id DESC LIMIT 1",
                (daily_id,),
            ).fetchone()
        return SessionRecord.from_row(row) if row is not None else None

    def resolve(self, prefix: str) -> list[str]:
        """Ids que começam com ``prefix`` (``/resume ab12``, ``--resume daily-2026-11-16``)."""
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM sessions WHERE id LIKE ? ESCAPE '\\' ORDER BY id", (escaped + "%",)
            ).fetchall()
        return [r["id"] for r in rows]

    def search(self, query: SessionQuery | None = None, *, limit: int = 200, include_empty: bool = False) -> list[SessionRecord]:
        """Sessões que casam com o filtro, da mais recente para a mais antiga."""
        query = query or SessionQuery()
        where: list[str] = []
        params: list[Any] = []
        if not include_empty:
            where.append("s.turn_count > 0")
        if query.date_from is not None:
            where.append("s.local_date >= ?")
            params.append(query.date_from.isoformat())
        if query.date_to is not None:
            where.append("s.local_date <= ?")
            params.append(query.date_to.isoformat())
        if query.kind:
            where.append("s.kind = ?")
            params.append(query.kind)
        if query.workspace:
            where.append("s.workspace = ?")
            params.append(query.workspace)
        if query.workspace_name:
            where.append("s.workspace LIKE ? ESCAPE '\\'")
            escaped = query.workspace_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        expression = fts_expression(query.terms)
        if query.terms and not expression:
            return []
        if expression:
            where.append("s.id IN (SELECT id FROM sessions_fts WHERE sessions_fts MATCH ?)")
            params.append(expression)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        columns = ", ".join(f"s.{c.strip()}" for c in _COLUMNS.split(","))
        sql = f"SELECT {columns} FROM sessions s {clause} ORDER BY s.updated_at DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            try:
                rows = self._conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError as exc:  # expressão FTS inválida: nada casa
                logger.debug("SessionIndex: busca inválida (%s)", exc)
                return []
        return [SessionRecord.from_row(r) for r in rows]

    # ── Metadados do índice ──

    def meta(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM index_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row is not None else None

    def set_meta(self, key: str, value: str) -> None:
        with self._tx() as conn:
            conn.execute(
                "INSERT INTO index_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # ── Migração (v0.5.2 -> v0.5.3) ──

    def migrate(self, home: Path) -> MigrationReport:
        """Indexa JSONL e branches arquivadas ainda não indexados; idempotente."""
        from orion.sessions.transcript import TranscriptEntry, user_turns

        report = MigrationReport()
        sessions_root = home / "sessions"
        archive_dir = home / "timeline" / "archive"
        if self.meta("backup_v0.5.2") is None:
            report.backed_up = _backup(home, sessions_root, archive_dir)
            self.set_meta("backup_v0.5.2", _now())
        if sessions_root.is_dir():
            for path in sorted(sessions_root.glob("*/*.jsonl")):
                if self.get(path.stem) is not None:
                    continue
                entries: list[TranscriptEntry] = []
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        entries.append(TranscriptEntry.model_validate_json(line))
                    except ValueError:
                        continue
                if not entries:
                    continue
                turns = user_turns(entries)
                workspace = next(
                    (str(e.meta.get("workspace")) for e in entries if e.kind == "meta" and e.meta and e.meta.get("workspace")),
                    None,
                )
                daily = is_daily_id(path.stem)
                created = entries[0].ts
                self.register(
                    path.stem,
                    "daily" if daily else "thread",
                    title=provisional_title(turns[0].preview) if turns and not daily else "",
                    daily_id=path.stem if daily else daily_id_for(local_day(parse_iso(created), self.starts_at, self.tz)),
                    workspace=None if daily else workspace,
                    created_at=created,
                    updated_at=entries[-1].ts,
                    turn_count=len(turns),
                )
                report.sessions += 1
        if archive_dir.is_dir():
            for path in sorted(archive_dir.glob("*.json")):
                session_id = f"branch-{path.stem}"
                if self.get(session_id) is not None:
                    continue
                if _migrate_branch(self, sessions_root, path, session_id):
                    report.branches += 1
        self.set_meta("migrated_v0.5.2", _now())
        return report


def _backup(home: Path, sessions_root: Path, archive_dir: Path) -> int:
    """Copia transcripts e branches arquivadas para ``backup/v0.5.2`` (sem sobrescrever)."""
    target = home / "backup" / "v0.5.2"
    copied = 0
    for source_root, name, pattern in ((sessions_root, "sessions", "*/*.jsonl"), (archive_dir, "timeline-archive", "*.json")):
        if not source_root.is_dir():
            continue
        for path in source_root.glob(pattern):
            destination = target / name / path.relative_to(source_root)
            if destination.exists():
                continue
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copy2(path, destination)
            copied += 1
    if copied:
        os.chmod(target, 0o700)
    return copied


def _migrate_branch(index: SessionIndex, sessions_root: Path, path: Path, session_id: str) -> bool:
    """Branch arquivada da v0.2.0 -> thread fechada, com transcript mínimo para o ``/resume``."""
    from orion.gateway.models import LLMMessage, MessageRole
    from orion.sessions.transcript import TranscriptEntry

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    name = str(payload.get("branch_name") or path.stem)
    created = str(payload.get("created_at") or _now())
    actions = [str(a) for a in payload.get("actions_summary") or []][:10]
    files = [str(f) for f in payload.get("modified_files") or []][:20]
    card = {"branch": name, "actions": actions, "files": files}
    summary = f"Branch arquivada '{name}'."
    if actions:
        summary += "\nAções: " + "; ".join(actions)
    if files:
        summary += "\nArquivos: " + ", ".join(files)
    transcript = sessions_root / "archive" / f"{session_id}.jsonl"
    transcript.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not transcript.exists():
        lines = [
            TranscriptEntry.of_meta(session_id=session_id, migrated_from=str(path)).model_copy(update={"index": 0, "ts": created}),
            TranscriptEntry.of_compact(
                [
                    LLMMessage(role=MessageRole.USER, content=summary),
                    LLMMessage(role=MessageRole.ASSISTANT, content="Entendido."),
                ]
            ).model_copy(update={"index": 1, "ts": created}),
        ]
        fd = os.open(transcript, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.writelines(e.model_dump_json(exclude_none=True) + "\n" for e in lines)
    index.register(
        session_id,
        "thread",
        title=provisional_title(name.replace("-", " ")),
        daily_id=daily_id_for(local_day(parse_iso(created), index.starts_at, index.tz)),
        created_at=created,
        turn_count=1,
        card=card,
        closed_at=created,
    )
    return True
