"""
O.R.I.O.N — Tools de tasks em segundo plano (Sprint 6B)
``task_create``, ``task_list``, ``task_get``, ``task_stop`` e ``send_message``.

ActionLevel: ``task_create``/``task_get``/``send_message`` LEVEL_1, ``task_list`` LEVEL_0,
``task_stop`` LEVEL_2. Disparar uma task não amplia privilégio: o filho roda sob o teto do PEP
do pai, exatamente como em foreground. Nenhuma delas é entregue a subagents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

if TYPE_CHECKING:
    from orion.agents.runner import ParentHandle
    from orion.agents.tasks import TaskManager


def _line(rec: Any) -> str:
    return (
        f"{rec.task_id} · {rec.status.value} · {rec.agent} · ${rec.cost_usd:.4f} · "
        f"{rec.goal[:80]}"
    )


class TaskCreateTool(BaseTool):
    name = "task_create"
    description = (
        "Start a subagent in the BACKGROUND and return immediately with a task_id. You will be told "
        "when it finishes; do not poll or wait. Use it for long, independent work (a broad audit, a "
        "slow investigation) while you keep helping the user. Same rules as 'task': give a complete "
        "goal and context, the subagent has no human to ask and never exceeds your permissions. "
        "Read the result with task_get, or open its ref://."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "agent": {"type": "string", "description": "Agent type (default 'general-purpose')."},
            "goal": {"type": "string", "minLength": 1, "description": "Complete, self-contained objective."},
            "context": {"type": "string", "description": "Context the subagent needs (it starts with none)."},
            "output_schema": {"type": "object", "description": "Optional JSON Schema for the final answer."},
            "resume": {"type": "string", "description": "agent_id of a partial subagent to continue."},
        },
        "required": ["goal"],
    }
    read_only = True

    def __init__(self, manager: TaskManager, parent: ParentHandle) -> None:
        self._manager = manager
        self._parent = parent

    async def run(self, **params: Any) -> RuntimeResult:
        from orion.agents.runner import TaskRequest

        request = TaskRequest(
            agent=str(params.get("agent") or "general-purpose"),
            goal=str(params["goal"]),
            context=str(params.get("context") or ""),
            output_schema=params.get("output_schema"),
            resume=params.get("resume"),
        )
        rec = self._manager.start(request, self._parent)
        return RuntimeResult.ok(
            f"Started {rec.task_id} ({rec.agent}) in the background. You will be notified when it "
            "finishes; keep working on something else.",
            task_id=rec.task_id,
            agent_id=rec.agent_id,
        )


class TaskListTool(BaseTool):
    name = "task_list"
    description = "List the background tasks of this session (id, status, agent, cost, goal)."
    input_schema = {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "running", "done", "failed", "cancelled", "interrupted"],
            }
        },
    }
    read_only = True

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    async def run(self, **params: Any) -> RuntimeResult:
        from orion.agents.models import TaskStatus

        status = TaskStatus(params["status"]) if params.get("status") else None
        records = self._manager.list(status=status)
        if not records:
            return RuntimeResult.ok("(no background tasks)", count=0)
        return RuntimeResult.ok("\n".join(_line(r) for r in records), count=len(records))


class TaskGetTool(BaseTool):
    name = "task_get"
    description = (
        "Show one background task: status, cost, a short summary of its result and the ref:// of the "
        "full result (open it with read_file)."
    )
    input_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "string", "minLength": 1}},
        "required": ["task_id"],
    }
    read_only = True

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    async def run(self, **params: Any) -> RuntimeResult:
        rec = self._manager.get(str(params["task_id"]))
        if rec is None:
            return RuntimeResult.fail(f"task_get: unknown task '{params['task_id']}'")
        lines = [_line(rec)]
        if rec.summary:
            lines.append(rec.summary)
        if rec.ref:
            lines.append(f"full result: {rec.ref}")
        if rec.error and rec.status.value != "done":
            lines.append(f"error: {rec.error}")
        if rec.resumable:
            lines.append(f"resumable: task_create(resume='{rec.agent_id}', goal='...')")
        return RuntimeResult.ok("\n".join(lines), status=rec.status.value)


class TaskStopTool(BaseTool):
    name = "task_stop"
    description = "Cancel a running background task of this session."
    input_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "string", "minLength": 1}},
        "required": ["task_id"],
    }

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    async def run(self, **params: Any) -> RuntimeResult:
        import asyncio

        task_id = str(params["task_id"])
        stopped = await asyncio.get_running_loop().run_in_executor(None, self._manager.stop, task_id)
        if not stopped:
            return RuntimeResult.fail(f"task_stop: '{task_id}' is not a running task of this session")
        return RuntimeResult.ok(f"Cancelled {task_id}.")


class SendMessageTool(BaseTool):
    name = "send_message"
    description = (
        "Send a message to a RUNNING background subagent (a correction, new information). It reads "
        "it before its next model call. A finished task cannot receive messages: resume it instead."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "minLength": 1},
            "message": {"type": "string", "minLength": 1},
        },
        "required": ["task_id", "message"],
    }
    read_only = True

    def __init__(self, manager: TaskManager) -> None:
        self._manager = manager

    async def run(self, **params: Any) -> RuntimeResult:
        problem = self._manager.send_message(str(params["task_id"]), str(params["message"]))
        if problem is not None:
            return RuntimeResult.fail(f"send_message: {problem}")
        return RuntimeResult.ok("Message delivered; the subagent reads it before its next model call.")
