"""
O.R.I.O.N — Tools de agenda (v0.5.0 Sprint 7B, ADR-022/032)

``schedule_create`` (LEVEL_3: sempre confirmado), ``schedule_list`` (LEVEL_0) e
``schedule_delete`` (LEVEL_3). Gravam direto em ``~/.orion/schedules.db`` e avisam o daemon, se
estiver vivo, para recalcular o próximo despertar. A autonomia de um agendamento nunca passa da
autonomia atual da sessão; ação nuclear agendada continua exigindo step-up local, ou seja, é
negada (o disparo não tem humano). Projeto não confiável não cria agendamentos. Nenhuma delas é
entregue a subagents.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from orion.governance.pep import AutonomyMode, min_mode
from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.scheduler.cronspec import InvalidSpec, describe
from orion.scheduler.store import Schedule, ScheduleStore


async def notify_daemon(socket: Path | None) -> bool:
    """Pede ao daemon (se houver) para reler a agenda. Falha silenciosa."""
    from orion.daemon import ipc
    from orion.daemon.client import DaemonUnavailable, call_once

    with contextlib.suppress(DaemonUnavailable, ipc.IpcError, TimeoutError, OSError):
        await call_once(socket or ipc.socket_path(), "schedule.reload", timeout_s=3.0)
        return True
    return False


def _line(s: Schedule) -> str:
    when = s.next_run_at.astimezone().strftime("%d/%m %H:%M") if s.next_run_at else "—"
    what = s.command if s.action == "command" else s.prompt
    state = "ativo" if s.enabled else "desligado"
    return f"{s.id} · {state} · {describe(s.spec)} · próximo {when} · {s.runs} execuções · {str(what)[:70]}"


class _ScheduleTool(BaseTool):
    def __init__(
        self,
        home: Path,
        *,
        workspace: Path,
        autonomy: Callable[[], AutonomyMode],
        trusted: Callable[[], bool],
        daemon_enabled: Callable[[], bool],
        socket: Path | None = None,
    ) -> None:
        self._home = home
        self._workspace = workspace
        self._autonomy = autonomy
        self._trusted = trusted
        self._daemon_enabled = daemon_enabled
        self._socket = socket

    def _store(self) -> ScheduleStore:
        return ScheduleStore(self._home / "schedules.db")


class ScheduleCreateTool(_ScheduleTool):
    name = "schedule_create"
    description = (
        "Schedule a recurring or one-shot task run by the ORION daemon, even with no terminal open. "
        "spec: 5-field cron ('0 8 * * 1-5'), '@daily', an interval ('every 2h', min 1 minute) or an "
        "ISO datetime for a one-shot ('2026-11-10T08:00'). action 'prompt' runs a fresh agent "
        "session with the prompt (give it complete context); action 'command' runs a shell command. "
        "Runs have no human: anything needing confirmation is denied, so prefer read-only work. "
        "Set triage=true only for checks that depend on repository changes (skips the run when "
        "nothing changed). Confirm the exact time and wording with the user before calling."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "spec": {"type": "string", "minLength": 1},
            "prompt": {"type": "string"},
            "action": {"type": "string", "enum": ["prompt", "command"]},
            "command": {"type": "string"},
            "triage": {"type": "boolean"},
            "catchup": {"type": "string", "enum": ["skip", "run_once"]},
            "autonomy": {"type": "string", "enum": [m.value for m in AutonomyMode]},
            "budget_usd": {"type": "number", "exclusiveMinimum": 0, "maximum": 5},
        },
        "required": ["spec"],
    }

    async def run(self, **params: Any) -> RuntimeResult:
        if not self._trusted():
            return RuntimeResult.fail("this project's settings are not trusted; schedules cannot be created here")
        action = str(params.get("action") or "prompt")
        prompt = str(params.get("prompt") or "")
        command = params.get("command")
        if action == "prompt" and not prompt.strip():
            return RuntimeResult.fail("action 'prompt' needs a non-empty prompt")
        requested = AutonomyMode(str(params.get("autonomy") or AutonomyMode.SUPERVISED.value))
        autonomy = min_mode(requested, self._autonomy())  # nunca acima do configurado
        try:
            schedule = Schedule(
                spec=str(params["spec"]),
                prompt=prompt,
                action=action,  # type: ignore[arg-type]
                command=str(command) if command else None,
                triage=bool(params.get("triage", False)),
                catchup=str(params.get("catchup") or "skip"),  # type: ignore[arg-type]
                autonomy=autonomy,
                budget_usd=float(params.get("budget_usd") or 0.10),
                workspace=str(self._workspace),
                created_by="user",
            )
        except (InvalidSpec, ValueError) as exc:
            return RuntimeResult.fail(f"invalid schedule: {exc}")
        store = self._store()
        try:
            saved = await asyncio.to_thread(store.add, schedule)
        except ValueError as exc:
            return RuntimeResult.fail(str(exc))
        finally:
            store.close()
        live = await notify_daemon(self._socket)
        note = ""
        if not self._daemon_enabled():
            note = " The daemon is OFF: it will only run after the user enables it (/daemon enable)."
        elif not live:
            note = " The daemon is not running right now; it will catch up per 'catchup' when it starts."
        capped = f" Autonomy capped to {autonomy.value}." if autonomy != requested else ""
        return RuntimeResult.ok(f"Scheduled: {_line(saved)}.{capped}{note}", schedule_id=saved.id)


class ScheduleListTool(_ScheduleTool):
    name = "schedule_list"
    description = "List the daemon's schedules (id, state, when, next run, runs, task)."
    input_schema = {"type": "object", "properties": {}}
    read_only = True

    async def run(self, **params: Any) -> RuntimeResult:
        store = self._store()
        try:
            items = await asyncio.to_thread(store.list)
        finally:
            store.close()
        if not items:
            return RuntimeResult.ok("No schedules.")
        return RuntimeResult.ok("\n".join(_line(s) for s in items), count=len(items))


class ScheduleDeleteTool(_ScheduleTool):
    name = "schedule_delete"
    description = "Delete a schedule by id (see schedule_list)."
    input_schema = {
        "type": "object",
        "properties": {"schedule_id": {"type": "string", "minLength": 1}},
        "required": ["schedule_id"],
    }

    async def run(self, **params: Any) -> RuntimeResult:
        schedule_id = str(params["schedule_id"])
        store = self._store()
        try:
            removed = await asyncio.to_thread(store.delete, schedule_id)
        finally:
            store.close()
        if not removed:
            return RuntimeResult.fail(f"no schedule {schedule_id}")
        await notify_daemon(self._socket)
        return RuntimeResult.ok(f"Schedule {schedule_id} deleted.")
