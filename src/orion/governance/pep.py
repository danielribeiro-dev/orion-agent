"""
O.R.I.O.N — Policy Enforcement Point (PEP)
Deterministic gatekeeper that intercepts every Action before execution.

Reference: docs/architecture/GOVERNANCE_PEP.md

Modes:
  SUPERVISED    (default for v0.1.0): LEVEL_2+ actions require [Y/n].
  WORKSPACE_AUTO: LEVEL_2 inside workspace auto-approved; LEVEL_3 still gated.
  FULLY_AUTO    : All actions auto-approved (LEVEL_3 still blocks sudo).

Safety invariants that are NEVER bypassed regardless of mode:
  - 'sudo' in any run_command invocation always requires explicit confirmation.
  - Paths outside the WorkspaceScope are always denied for mutating tools.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

from orion.core.events import Action
from orion.governance.audit import AuditLogger
from orion.governance.permissions import ActionLevel, WorkspaceScope, tool_action_level

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Autonomy modes
# ---------------------------------------------------------------------------


class AutonomyMode(str, Enum):
    """Configurable autonomy level for the PEP."""

    SUPERVISED = "supervised"
    WORKSPACE_AUTO = "workspace_auto"
    FULLY_AUTO = "fully_auto"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ActionDenied(Exception):
    """Raised by the PEP when an action is blocked."""

    def __init__(self, action_id: str, tool: str, reason: str) -> None:
        self.action_id = action_id
        self.tool = tool
        self.reason = reason
        super().__init__(f"Action '{tool}' [{action_id}] denied: {reason}")


# ---------------------------------------------------------------------------
# Confirmation callback type
# ---------------------------------------------------------------------------

# A callable that receives (prompt: str) and returns True (approved) / False.
# Defaults to the built-in synchronous stdin prompt wrapped in an async shim.
ConfirmCallback = Any  # Callable[[str], bool | Awaitable[bool]]


def _default_confirm(prompt: str) -> bool:  # pragma: no cover
    """Synchronous stdin confirmation for interactive sessions."""
    answer = input(f"\n{prompt} [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")


# ---------------------------------------------------------------------------
# PolicyEnforcementPoint
# ---------------------------------------------------------------------------


class PolicyEnforcementPoint:
    """Intercepts Actions, evaluates policy, and either approves or denies.

    Args:
        scope          : WorkspaceScope defining authorised filesystem paths.
        mode           : Autonomy mode (default: SUPERVISED).
        audit_logger   : Optional AuditLogger; one is created if not provided.
        confirm        : Async or sync callable for human confirmation prompts.
                         Must accept (prompt: str) and return bool.
                         Defaults to stdin prompt.
    """

    def __init__(
        self,
        scope: WorkspaceScope | None = None,
        mode: AutonomyMode = AutonomyMode.SUPERVISED,
        audit_logger: AuditLogger | None = None,
        confirm: ConfirmCallback | None = None,
    ) -> None:
        self._scope = scope or WorkspaceScope.default()
        self._mode = mode
        self._audit = audit_logger or AuditLogger()
        self._confirm = confirm or _default_confirm

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> AutonomyMode:
        return self._mode

    @property
    def scope(self) -> WorkspaceScope:
        return self._scope

    def set_mode(self, mode: AutonomyMode) -> None:
        """Switch autonomy mode at runtime."""
        logger.info("PEP: autonomy mode changed %s → %s", self._mode, mode)
        self._mode = mode

    async def evaluate(self, action: Action) -> bool:
        """Gate the given Action through the policy.

        Returns:
            True  if the action is approved and should proceed.
            False if the user explicitly rejected a confirmation prompt.

        Raises:
            ActionDenied  if the action is structurally blocked by policy
                          (e.g. path outside workspace, sudo in supervised mode).
        """
        level = self._effective_level(action)
        params = dict(action.params)

        # ── Static safety invariants (never bypassed) ──────────────────
        self._assert_no_sudo(action)
        self._assert_path_scope(action, level)

        # ── LEVEL_0: pure informative — no audit, no gate ──────────────
        if level == ActionLevel.LEVEL_0:
            return True

        # ── LEVEL_1: passive read — audit only ──────────────────────────
        if level == ActionLevel.LEVEL_1:
            self._audit.log(
                action_id=action.event_id,
                tool=action.tool,
                params=params,
                level=level,
                user_authorized=False,
                result_status="success",
            )
            return True

        # ── LEVEL_2 / LEVEL_3: apply autonomy mode logic ────────────────
        approved = await self._gate(action, level)

        if not approved:
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=params,
                level=level,
                reason="user_rejected",
            )
            return False

        self._audit.log(
            action_id=action.event_id,
            tool=action.tool,
            params=params,
            level=level,
            user_authorized=(level >= ActionLevel.LEVEL_2),
            result_status="pending",
        )
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_level(self, action: Action) -> ActionLevel:
        """Derive ActionLevel from the tool registry (ignores engine hint)."""
        return tool_action_level(action.tool)

    def _assert_no_sudo(self, action: Action) -> None:
        """Block sudo commands unless the mode is FULLY_AUTO with confirmation."""
        cmd: str = str(action.params.get("command", ""))
        if "sudo" in cmd.split() or cmd.strip().startswith("sudo"):
            if self._mode != AutonomyMode.FULLY_AUTO:
                raise ActionDenied(
                    action.event_id,
                    action.tool,
                    "sudo usage requires FULLY_AUTO mode with explicit human confirmation.",
                )

    def _assert_path_scope(self, action: Action, level: ActionLevel) -> None:
        """Deny mutating actions targeting paths outside the workspace."""
        if level < ActionLevel.LEVEL_2:
            return  # reads are not restricted to workspace
        path: str | None = str(action.params.get("path", "")) or None
        if path:
            try:
                self._scope.assert_allowed(path)
            except PermissionError as exc:
                raise ActionDenied(action.event_id, action.tool, str(exc)) from exc

    async def _gate(self, action: Action, level: ActionLevel) -> bool:
        """Apply autonomy-mode gating logic for LEVEL_2 / LEVEL_3."""
        if self._mode == AutonomyMode.SUPERVISED:
            return await self._ask_user(action, level)

        if self._mode == AutonomyMode.WORKSPACE_AUTO:
            if level == ActionLevel.LEVEL_2:
                return True  # auto-approved inside workspace
            return await self._ask_user(action, level)  # LEVEL_3 still gated

        # FULLY_AUTO
        return True

    async def _ask_user(self, action: Action, level: ActionLevel) -> bool:
        """Display confirmation prompt and return the human's decision."""
        level_label = f"LEVEL_{level}"
        prompt = (
            f"\n⚠️  O.R.I.O.N wants to execute a {level_label} action:\n"
            f"   Tool   : {action.tool}\n"
            f"   Params : {action.params}\n"
            f"Approve?"
        )
        result = self._confirm(prompt)
        if asyncio.iscoroutine(result):
            return bool(await result)
        return bool(result)
