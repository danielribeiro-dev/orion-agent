"""Persistência das agendas em SQLite (stdlib, WAL, arquivo 0600) e lock exclusivo do daemon.

Datas são gravadas em UTC com formato fixo, então a ordenação textual coincide com a cronológica.
Todo SQL é parametrizado. O banco vive somente no caminho recebido (``~/.orion/`` em produção).
"""

from __future__ import annotations

import builtins
import fcntl
import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import IO, Literal

from pydantic import BaseModel, Field, field_validator

from orion.governance.pep import AutonomyMode
from orion.scheduler.cronspec import next_fire, validate_spec

MAX_SCHEDULES = 50
_TS = "%Y-%m-%dT%H:%M:%S.%f+00:00"

RunStatus = Literal["ok", "failed", "denied", "skipped", "missed"]


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _enc(value: datetime | None) -> str | None:
    return value.astimezone(UTC).strftime(_TS) if value else None


class Schedule(BaseModel):
    """Uma agenda persistente (cron, intervalo ou disparo único)."""

    id: str = Field(default_factory=lambda: f"sch_{uuid.uuid4().hex[:8]}")
    spec: str
    prompt: str = ""
    action: Literal["prompt", "command"] = "prompt"
    command: str | None = None
    agent: str = "general-purpose"
    autonomy: AutonomyMode = AutonomyMode.SUPERVISED
    triage: bool = True
    catchup: Literal["skip", "run_once"] = "skip"
    workspace: str
    enabled: bool = True
    budget_usd: float = Field(default=0.10, gt=0, le=5.0)
    created_by: str = "user"
    created_at: datetime = Field(default_factory=_now)
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: str = ""
    last_summary: str = ""
    runs: int = 0

    @field_validator("spec")
    @classmethod
    def _check_spec(cls, value: str) -> str:
        return validate_spec(value)

    @field_validator("created_at", "next_run_at", "last_run_at")
    @classmethod
    def _utc(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    def model_post_init(self, _context: object) -> None:
        if self.action == "command" and not self.command:
            raise ValueError("`command` é obrigatório quando action == 'command'")


class ScheduleRun(BaseModel):
    """Registro de uma execução (ou omissão) de uma agenda."""

    schedule_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    detail: str = ""
    cost_usd: float = 0.0


class SchedulerLocked(RuntimeError):
    """Outro processo já detém o lock do agendador."""


class SchedulerLock:
    """Lock exclusivo (``flock``) que garante um único daemon por arquivo de lock."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._fh: IO[str] | None = None

    def acquire(self) -> None:
        if self._fh is not None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        fh = os.fdopen(fd, "r+")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.close()
            raise SchedulerLocked(f"Agendador já em execução ({self._path})") from exc
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> SchedulerLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules (
    id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL,
    next_run_at TEXT,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_schedules_due ON schedules(enabled, next_run_at);
CREATE TABLE IF NOT EXISTS schedule_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_schedule ON schedule_runs(schedule_id, id);
"""


class ScheduleStore:
    """Repositório SQLite das agendas e do histórico de execuções."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if not db_path.exists():
            os.close(os.open(db_path, os.O_CREAT | os.O_WRONLY, 0o600))
        self._lock = threading.Lock()
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def add(self, s: Schedule) -> Schedule:
        with self._lock:
            row = self._db.execute("SELECT COUNT(*) FROM schedules").fetchone()
            if int(row[0]) >= MAX_SCHEDULES:
                raise ValueError(f"Limite de {MAX_SCHEDULES} agendas atingido")
            if s.next_run_at is None and s.enabled:
                s.next_run_at = next_fire(s.spec, _now())
            self._db.execute(
                "INSERT INTO schedules (id, enabled, next_run_at, created_at, data) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    s.id,
                    int(s.enabled),
                    _enc(s.next_run_at),
                    _enc(s.created_at),
                    s.model_dump_json(),
                ),
            )
            self._db.commit()
        return s

    def get(self, schedule_id: str) -> Schedule | None:
        with self._lock:
            row = self._db.execute(
                "SELECT data FROM schedules WHERE id = ?", (schedule_id,)
            ).fetchone()
        return Schedule.model_validate_json(row[0]) if row else None

    def list(self, *, enabled_only: bool = False) -> builtins.list[Schedule]:
        sql = "SELECT data FROM schedules"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at, id"
        with self._lock:
            rows = self._db.execute(sql).fetchall()
        return [Schedule.model_validate_json(r[0]) for r in rows]

    def update(self, s: Schedule) -> None:
        with self._lock:
            self._db.execute(
                "UPDATE schedules SET enabled = ?, next_run_at = ?, data = ? WHERE id = ?",
                (int(s.enabled), _enc(s.next_run_at), s.model_dump_json(), s.id),
            )
            self._db.commit()

    def delete(self, schedule_id: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
            self._db.execute("DELETE FROM schedule_runs WHERE schedule_id = ?", (schedule_id,))
            self._db.commit()
        return cur.rowcount > 0

    def due(self, now: datetime) -> builtins.list[Schedule]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM schedules WHERE enabled = 1 AND next_run_at IS NOT NULL "
                "AND next_run_at <= ? ORDER BY next_run_at, id",
                (_enc(now),),
            ).fetchall()
        return [Schedule.model_validate_json(r[0]) for r in rows]

    def next_due_at(self) -> datetime | None:
        with self._lock:
            row = self._db.execute(
                "SELECT MIN(next_run_at) FROM schedules "
                "WHERE enabled = 1 AND next_run_at IS NOT NULL"
            ).fetchone()
        if not row or row[0] is None:
            return None
        return datetime.strptime(row[0], _TS).replace(tzinfo=UTC)

    def record_run(self, run: ScheduleRun) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO schedule_runs (schedule_id, started_at, data) VALUES (?, ?, ?)",
                (run.schedule_id, _enc(run.started_at), run.model_dump_json()),
            )
            self._db.commit()

    def runs(self, schedule_id: str, limit: int = 20) -> builtins.list[ScheduleRun]:
        with self._lock:
            rows = self._db.execute(
                "SELECT data FROM schedule_runs WHERE schedule_id = ? ORDER BY id DESC LIMIT ?",
                (schedule_id, limit),
            ).fetchall()
        return [ScheduleRun.model_validate_json(r[0]) for r in rows]

    def close(self) -> None:
        with self._lock:
            self._db.close()
