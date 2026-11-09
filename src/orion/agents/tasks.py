"""Tasks em segundo plano: registro persistente (SQLite) e gerente (ADR-029).

``SqliteTaskStore`` guarda o estado em ``~/.orion/tasks.db`` (WAL, 100% parametrizado). Ele
sobrevive a reinícios: o que estava "em execução" quando o processo morreu vira ``interrupted``
na próxima abertura (a checagem usa o ``pid`` do dono, então duas sessões vivas não se atropelam).

``TaskManager`` dispara :class:`~orion.agents.runner.AgentRunner` num :class:`ThreadExecutor` e
**avisa por evento** quando termina: nenhuma chamada ao modelo acontece enquanto se espera
(zero token em idle, ADR-022). Os filhos rodam sob o teto do pai exatamente como em foreground.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sqlite3
import threading
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from orion.agents.budget import AggregateBudget
from orion.agents.loop_thread import ExecutionHandle, ThreadExecutor
from orion.agents.models import (
    AgentEventEnvelope,
    AgentResult,
    TaskRecord,
    TaskStatus,
)
from orion.agents.ports import NotifierPort, TaskStorePort
from orion.agents.runner import AgentRunner, ParentHandle, TaskRequest

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id    TEXT PRIMARY KEY,
    owner      TEXT NOT NULL,
    agent      TEXT NOT NULL,
    agent_id   TEXT NOT NULL DEFAULT '',
    goal       TEXT NOT NULL,
    status     TEXT NOT NULL,
    origin     TEXT NOT NULL DEFAULT 'subagent',
    model_tier TEXT NOT NULL DEFAULT '',
    model_used TEXT NOT NULL DEFAULT '',
    ref        TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL DEFAULT '',
    cost_usd   REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    error      TEXT,
    resumable  INTEGER NOT NULL DEFAULT 0,
    pid        INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_owner ON tasks(owner);
"""

_COLUMNS = (
    "task_id, owner, agent, agent_id, goal, status, origin, model_tier, model_used, ref, "
    "summary, cost_usd, created_at, updated_at, error, resumable, pid"
)


class SqliteTaskStore:
    """``TaskStorePort`` em SQLite (uma conexão curta por operação, seguro entre threads)."""

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = threading.Lock()
        self._ready = False

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        with self._init_lock:
            if not self._ready:
                boot = sqlite3.connect(self._path, timeout=10)
                try:
                    boot.execute("PRAGMA journal_mode=WAL;")
                    boot.executescript(_DDL)
                    boot.commit()
                finally:
                    boot.close()
                with contextlib.suppress(OSError):
                    os.chmod(self._path, 0o600)
                self._ready = True
        conn = sqlite3.connect(self._path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # -- TaskStorePort ---------------------------------------------------

    def upsert(self, rec: TaskRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO tasks ({_COLUMNS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rec.task_id,
                    rec.owner,
                    rec.agent,
                    rec.agent_id,
                    rec.goal,
                    rec.status.value,
                    rec.origin,
                    rec.model_tier,
                    rec.model_used,
                    rec.ref,
                    rec.summary,
                    rec.cost_usd,
                    rec.created_at.isoformat(),
                    rec.updated_at.isoformat(),
                    rec.error,
                    int(rec.resumable),
                    rec.pid,
                ),
            )

    def get(self, task_id: str) -> TaskRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                f"SELECT {_COLUMNS} FROM tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        return self._record(row) if row else None

    def list(self, *, status: TaskStatus | None = None, owner: str | None = None) -> list[TaskRecord]:
        query = f"SELECT {_COLUMNS} FROM tasks"
        clauses: list[str] = []
        params: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC, task_id"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._record(r) for r in rows]

    @staticmethod
    def _record(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            owner=row["owner"],
            agent=row["agent"],
            agent_id=row["agent_id"],
            goal=row["goal"],
            status=TaskStatus(row["status"]),
            origin=row["origin"],
            model_tier=row["model_tier"],
            model_used=row["model_used"],
            ref=row["ref"],
            summary=row["summary"],
            cost_usd=row["cost_usd"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error=row["error"],
            resumable=bool(row["resumable"]),
            pid=row["pid"],
        )


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, só não é nosso
    return True


def _task_status(result: AgentResult) -> TaskStatus:
    if result.status == "error":
        return TaskStatus.FAILED
    if result.status == "cancelled":
        return TaskStatus.CANCELLED
    return TaskStatus.DONE  # ok, parciais retomáveis e schema_invalid têm resultado em disco


class TaskManager:
    """Dispara, acompanha, cancela e notifica subagents em segundo plano."""

    def __init__(
        self,
        *,
        store: TaskStorePort,
        executor: ThreadExecutor,
        runner: AgentRunner,
        notifier: NotifierPort,
        owner: str,
        on_result: Callable[[AgentResult, TaskRecord], None] | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self._store = store
        self._executor = executor
        self._runner = runner
        self._notifier = notifier
        self.owner = owner
        self._on_result = on_result
        self._on_change = on_change
        self._pid = os.getpid()
        self._live: dict[str, TaskRecord] = {}
        self._handles: dict[str, ExecutionHandle] = {}
        self._lock = threading.Lock()
        self.recover()

    # ------------------------------------------------------------------
    # Recuperação após reinício
    # ------------------------------------------------------------------

    def recover(self) -> int:
        """Marca como ``interrupted`` o que ficou em andamento num processo que já morreu."""
        count = 0
        active = [
            r for r in self._store.list() if r.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
        ]
        for rec in active:
            if rec.pid == self._pid and rec.task_id in self._live:
                continue
            if _pid_alive(rec.pid) and rec.pid != self._pid:
                continue  # outra sessão viva é dona
            self._store.upsert(
                rec.model_copy(
                    update={
                        "status": TaskStatus.INTERRUPTED,
                        "updated_at": datetime.now(UTC),
                        "error": "o processo terminou antes da conclusão",
                    }
                )
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def start(self, request: TaskRequest, parent: ParentHandle) -> TaskRecord:
        """Registra e dispara a task em segundo plano; devolve o registro imediatamente."""
        agent_id = request.resume or f"agent_{uuid.uuid4().hex[:10]}"
        rec = TaskRecord(
            task_id=f"task_{uuid.uuid4().hex[:8]}",
            owner=self.owner,
            agent=request.agent,
            agent_id=agent_id,
            goal=request.goal[:500],
            status=TaskStatus.RUNNING,
            origin=request.origin,
            pid=self._pid,
        )
        self._store.upsert(rec)
        with self._lock:
            self._live[rec.task_id] = rec
        self._changed()
        handle = self._executor.submit(lambda: self._run(rec, request, parent), agent_id=agent_id)
        self._handles[rec.task_id] = handle
        return rec

    async def wait(self, task_id: str) -> AgentResult | None:
        """Aguarda o término (de qualquer loop). ``None`` se foi cancelada ou falhou."""
        handle = self._handles.get(task_id)
        if handle is None:
            return None
        try:
            return await handle.wait()
        except asyncio.CancelledError:
            if handle.done():  # cancelaram a task, não quem espera
                return None
            raise
        except Exception:
            return None

    async def _run(self, rec: TaskRecord, request: TaskRequest, parent: ParentHandle) -> AgentResult:
        deps = self._runner.deps
        aggregate = AggregateBudget(deps.limits().aggregate_budget_usd, parent=deps.daily)
        try:
            result = await self._runner.run_one(
                request, parent, aggregate, agent_id=rec.agent_id, publish=False
            )
        except asyncio.CancelledError:
            self._finish(rec, status=TaskStatus.CANCELLED, error="cancelada", kind="task.cancelled")
            raise
        except Exception as exc:
            logger.exception("TaskManager: task %s falhou", rec.task_id)
            self._finish(rec, status=TaskStatus.FAILED, error=f"{type(exc).__name__}: {exc}", kind="task.failed")
            raise
        status = _task_status(result)
        kind = {
            TaskStatus.DONE: "task.completed",
            TaskStatus.FAILED: "task.failed",
            TaskStatus.CANCELLED: "task.cancelled",
        }.get(status, "task.completed")
        self._finish(rec, status=status, result=result, kind=kind)
        return result

    def _finish(
        self,
        rec: TaskRecord,
        *,
        status: TaskStatus,
        kind: str,
        result: AgentResult | None = None,
        error: str | None = None,
    ) -> None:
        update: dict[str, object] = {"status": status, "updated_at": datetime.now(UTC), "error": error}
        if result is not None:
            update.update(
                model_used=result.model_used,
                ref=result.ref,
                summary=result.summary[:2000],
                cost_usd=result.usage.cost_usd,
                resumable=result.resumable,
                error=result.error,
            )
        final = rec.model_copy(update=update)
        self._store.upsert(final)
        with self._lock:
            self._live.pop(rec.task_id, None)
        if result is not None and self._on_result is not None:
            try:
                self._on_result(result, final)
            except Exception:  # pragma: no cover - contabilidade nunca derruba a task
                logger.exception("TaskManager: on_result falhou")
        self._notifier.notify(
            AgentEventEnvelope(
                agent_id=rec.agent_id,
                parent_id=None,
                session_id=self.owner,
                origin=rec.origin,
                kind=kind,
                payload={
                    "task_id": rec.task_id,
                    "agent": rec.agent,
                    "status": result.status if result is not None else status.value,
                    "summary": (result.summary if result is not None else (error or ""))[:400],
                    "ref": result.ref if result is not None else "",
                    "cost_usd": result.usage.cost_usd if result is not None else 0.0,
                    "resumable": final.resumable,
                },
            )
        )
        self._changed()

    def _changed(self) -> None:
        if self._on_change is not None:
            with contextlib.suppress(Exception):
                self._on_change()

    # ------------------------------------------------------------------
    # Consulta e controle
    # ------------------------------------------------------------------

    def get(self, task_id: str) -> TaskRecord | None:
        return self._store.get(task_id)

    def list(self, *, status: TaskStatus | None = None, mine: bool = True) -> list[TaskRecord]:
        records = self._store.list(status=status)
        return [r for r in records if r.owner == self.owner] if mine else records

    def active_count(self) -> int:
        with self._lock:
            return len(self._live)

    def stop(self, task_id: str, timeout: float = 5.0) -> bool:
        """Cancela uma task desta sessão. ``False`` se não existe, é de outra sessão ou já terminou."""
        with self._lock:
            rec = self._live.get(task_id)
        if rec is None:
            return False
        return self._executor.cancel_sync(rec.agent_id, timeout)

    def stop_all(self, timeout: float = 5.0) -> int:
        with self._lock:
            ids = list(self._live)
        return sum(1 for task_id in ids if self.stop(task_id, timeout))

    def send_message(self, task_id: str, text: str) -> str | None:
        """Entrega *text* ao filho (lida entre os turnos dele). Devolve o motivo se não entregou."""
        rec = self._store.get(task_id)
        if rec is None:
            return f"tarefa desconhecida: {task_id}"
        if rec.owner != self.owner:
            return "a tarefa pertence a outra sessão"
        if rec.status != TaskStatus.RUNNING:
            hint = (
                f" Ela é retomável: task_create(resume='{rec.agent_id}', goal='...')."
                if rec.resumable
                else ""
            )
            return f"a tarefa não está em execução ({rec.status.value}).{hint}"
        if not self._runner.deps.inbox.post(rec.agent_id, text):
            return "a tarefa ainda não abriu a caixa de entrada; tente de novo em instantes"
        return None

    def shutdown(self, timeout: float = 5.0) -> int:
        """Cascata ao encerrar a sessão: cancela tudo e para o loop de fundo."""
        cancelled = self.stop_all(timeout)
        self._executor.shutdown(timeout)
        return cancelled
