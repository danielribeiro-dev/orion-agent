"""
O.R.I.O.N — Tools: enter_plan_mode / exit_plan_mode
O agente entra em modo plano (somente leitura) e só sai com aprovação explícita do Senhor.

ActionLevel: LEVEL_0 (a saída depende do modal de aprovação; entrar só RESTRINGE o agente)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

#: ``async (plan_markdown) -> bool`` — True quando o Senhor aprova o plano.
PlanApprover = Callable[[str], Awaitable[bool]]


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
        "plan mode and revise."
    )
    input_schema = {
        "type": "object",
        "properties": {"plan": {"type": "string", "minLength": 10, "description": "The plan, in markdown."}},
        "required": ["plan"],
    }
    read_only = True

    def __init__(
        self, approver: PlanApprover | None = None, in_plan_mode: Callable[[], bool] | None = None
    ) -> None:
        self._approver = approver
        self._in_plan_mode = in_plan_mode

    async def run(self, plan: str, **_: Any) -> RuntimeResult:
        if self._approver is None:
            return RuntimeResult.fail("exit_plan_mode: not available in this session.")
        if self._in_plan_mode is not None and not self._in_plan_mode():
            return RuntimeResult.fail("exit_plan_mode: the session is not in plan mode.")
        if not await self._approver(plan):
            return RuntimeResult.fail(
                "Plan not approved by the user. Stay in plan mode, ask what to change and revise.",
                approved=False,
            )
        return RuntimeResult.ok("Plan approved. Plan mode ended; you may implement it now.", approved=True)
