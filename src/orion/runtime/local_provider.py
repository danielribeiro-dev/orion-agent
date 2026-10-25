"""
O.R.I.O.N — Local Runtime Provider
Orchestrates the 5 native primitive tools and integrates with the PEP.

Dispatch flow:
  LocalRuntimeProvider.execute(tool, params)
      └─► PEP.evaluate(action)            ← governance gate
              ├── approved → tool.run(**params) → RuntimeResult
              └── denied  → RuntimeResult.fail("ActionDenied")
"""

from __future__ import annotations

import logging
from typing import Any

from orion.core.events import Action, RiskLevel
from orion.governance.pep import ActionDenied, AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope
from orion.runtime.provider import BaseRuntimeProvider, RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.runtime.tools.edit_file import EditFileTool
from orion.runtime.tools.read_file import ReadFileTool
from orion.runtime.tools.run_command import RunCommandTool
from orion.runtime.tools.search_files import SearchFilesTool
from orion.runtime.tools.write_file import WriteFileTool

logger = logging.getLogger(__name__)

_RISK_MAP: dict[str, RiskLevel] = {
    "read_file": RiskLevel.SAFE,
    "search_files": RiskLevel.SAFE,
    "write_file": RiskLevel.CONTROLLED,
    "edit_file": RiskLevel.CONTROLLED,
    "run_command": RiskLevel.CRITICAL,
}


class LocalRuntimeProvider(BaseRuntimeProvider):
    """Concrete runtime that executes the 5 native tools on the local OS.

    Args:
        pep   : PolicyEnforcementPoint instance. Created with default config
                (SUPERVISED mode) if not provided.
        scope : WorkspaceScope for path validation.
    """

    def __init__(
        self,
        pep: PolicyEnforcementPoint | None = None,
        scope: WorkspaceScope | None = None,
    ) -> None:
        self._scope = scope or WorkspaceScope.default()
        self._pep = pep or PolicyEnforcementPoint(scope=self._scope)

        self._tools: dict[str, BaseTool] = {
            t.name: t
            for t in [
                RunCommandTool(),
                ReadFileTool(),
                WriteFileTool(),
                EditFileTool(),
                SearchFilesTool(),
            ]
        }

    # ------------------------------------------------------------------
    # BaseRuntimeProvider contract
    # ------------------------------------------------------------------

    def supports(self, tool: str) -> bool:
        return tool in self._tools

    async def execute(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
        """PEP-gate then dispatch *tool* with *params*.

        The PEP always runs first. If an action is denied (user says no or
        policy blocks it), a failed RuntimeResult is returned immediately
        without touching the OS.
        """
        if not self.supports(tool):
            return RuntimeResult.fail(
                f"LocalRuntimeProvider: unknown tool '{tool}'. "
                f"Available: {sorted(self._tools)}"
            )

        risk = _RISK_MAP.get(tool, RiskLevel.CRITICAL)
        action = Action(tool=tool, params=params, risk_level=risk)

        # ── Governance gate ──────────────────────────────────────────────
        try:
            approved = await self._pep.evaluate(action)
        except ActionDenied as exc:
            return RuntimeResult.fail(
                f"PEP denied '{tool}': {exc.reason}",
                action_id=exc.action_id,
                denied=True,
            )

        if not approved:
            return RuntimeResult.fail(
                f"PEP: user rejected execution of '{tool}'.",
                denied=True,
            )

        # ── Execute ──────────────────────────────────────────────────────
        impl = self._tools[tool]
        try:
            result = await impl.run(**params)
        except Exception as exc:
            logger.exception("LocalRuntimeProvider: unhandled error in tool '%s'", tool)
            return RuntimeResult.fail(f"'{tool}' raised an unexpected error: {exc}")

        # Update audit log with final result status
        if hasattr(self._pep, "_audit"):
            pass  # audit already written by PEP; future: update status

        return result

    # ------------------------------------------------------------------
    # Direct tool access (bypasses PEP — use only in tests / trusted paths)
    # ------------------------------------------------------------------

    async def execute_direct(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
        """Execute *tool* WITHOUT going through the PEP.

        WARNING: This method bypasses all governance checks.
        It is intended exclusively for unit tests and trusted internal calls.
        """
        if not self.supports(tool):
            return RuntimeResult.fail(f"LocalRuntimeProvider: unknown tool '{tool}'.")
        impl = self._tools[tool]
        return await impl.run(**params)

    @property
    def pep(self) -> PolicyEnforcementPoint:
        return self._pep

    @property
    def scope(self) -> WorkspaceScope:
        return self._scope
