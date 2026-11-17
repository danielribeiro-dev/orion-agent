"""
O.R.I.O.N — Tools: enter_plan_mode / exit_plan_mode
O agente entra em modo plano (somente leitura) e só sai com aprovação explícita do Senhor.

ActionLevel: LEVEL_0 (a saída depende do modal de aprovação; entrar só RESTRINGE o agente)
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool


@dataclass(frozen=True)
class PresenceSteps:
    """Passos de faixa Presença que o plano pede para aprovar de uma vez (ADR-047 item 5)."""

    commands: tuple[str, ...] = field(default_factory=tuple)
    paths: tuple[str, ...] = field(default_factory=tuple)

    def __bool__(self) -> bool:
        return bool(self.commands or self.paths)


#: ``async (plan_markdown[, steps]) -> bool`` — True quando o Senhor aprova o plano.
PlanApprover = Callable[..., Awaitable[bool]]


def _accepts_steps(approver: Callable[..., Any]) -> bool:
    try:
        params = inspect.signature(approver).parameters.values()
    except (TypeError, ValueError):
        return False
    positional = [p for p in params if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
    return len(positional) >= 2 or any(p.kind == p.VAR_POSITIONAL for p in params)


class EnterPlanModeTool(BaseTool):
    name = "enter_plan_mode"
    description = (
        "Switch to plan mode: read-only exploration (every mutation is denied) to design an "
        "approach before touching code. Finish with exit_plan_mode to submit the plan."
    )
    input_schema = {"type": "object", "properties": {}}
    read_only = True

    def __init__(self, on_enter: Callable[[], None] | None = None) -> None:
        self._on_enter = on_enter

    async def run(self, **_: Any) -> RuntimeResult:
        if self._on_enter is None:
            return RuntimeResult.fail("enter_plan_mode: not available in this session.")
        self._on_enter()
        return RuntimeResult.ok(
            "Plan mode active: explore read-only, then call exit_plan_mode with the plan."
        )


class ExitPlanModeTool(BaseTool):
    name = "exit_plan_mode"
    description = (
        "Submit your plan (markdown) for the user's approval. Only callable in plan mode. "
        "On approval the session leaves plan mode and you may implement; on rejection stay in "
        "plan mode and revise. List high-risk steps (push to a protected branch, system units, "
        "sensitive files, data sent to a new host) in presence_commands/presence_paths: the user "
        "approves them once with the plan (valid 15 min). Irreversible (nuclear) steps are never "
        "covered and still need the user's verified presence."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "plan": {"type": "string", "minLength": 10, "description": "The plan, in markdown."},
            "presence_commands": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exact shell commands of high-risk steps (end with ' *' to allow extra args).",
            },
            "presence_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Files or folders of high-risk writes.",
            },
        },
        "required": ["plan"],
    }
    read_only = True

    def __init__(
        self, approver: PlanApprover | None = None, in_plan_mode: Callable[[], bool] | None = None
    ) -> None:
        self._approver = approver
        self._in_plan_mode = in_plan_mode

    async def run(
        self,
        plan: str,
        presence_commands: list[str] | None = None,
        presence_paths: list[str] | None = None,
        **_: Any,
    ) -> RuntimeResult:
        if self._approver is None:
            return RuntimeResult.fail("exit_plan_mode: not available in this session.")
        if self._in_plan_mode is not None and not self._in_plan_mode():
            return RuntimeResult.fail("exit_plan_mode: the session is not in plan mode.")
        steps = PresenceSteps(
            tuple(str(c) for c in presence_commands or () if str(c).strip()),
            tuple(str(p) for p in presence_paths or () if str(p).strip()),
        )
        approved = (
            await self._approver(plan, steps) if _accepts_steps(self._approver) else await self._approver(plan)
        )
        if not approved:
            return RuntimeResult.fail(
                "Plan not approved by the user. Stay in plan mode, ask what to change and revise.",
                approved=False,
            )
        return RuntimeResult.ok("Plan approved. Plan mode ended; you may implement it now.", approved=True)
