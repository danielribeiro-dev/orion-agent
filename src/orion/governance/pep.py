"""
O.R.I.O.N — Policy Enforcement Point (PEP)
Deterministic gatekeeper that intercepts every Action before execution.

Reference: docs/architecture/GOVERNANCE_PEP.md

Modes:
  SUPERVISED    (default for v0.1.0): LEVEL_2+ actions require [Y/n].
  WORKSPACE_AUTO: LEVEL_2 inside workspace auto-approved; LEVEL_3 still gated.
  FULLY_AUTO    : All actions auto-approved (LEVEL_3 still blocks sudo).

Safety invariants that are NEVER bypassed regardless of mode:
  - 'sudo' in any run_command invocation always requires explicit confirmation
    (unless already trusted via CommandTrustLedger).
  - Paths outside the WorkspaceScope are always denied for mutating tools.
  - NUCLEAR_DESTRUCTIVE commands always trigger OS authentication popup.
  - SAFE_HOLDING state blocks all mutations until the frontier model recovers
    (ONLY applies when SAFE_HOLDING was triggered by a model failure, NOT
     when the user deliberately chose a light model as their daily driver).

Sprint 4 additions (v0.3.0):
  - CircuitBreaker integration: blocks mutations in SAFE_HOLDING state.
  - CommandTrustLedger integration: known-safe commands skip prompt in auto.
  - NuclearSafetyGate integration: NUCLEAR_DESTRUCTIVE always auth-gated.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from enum import Enum
from typing import Any, Optional

from orion.core.events import Action
from orion.governance.audit import AuditLogger
from orion.governance.nuclear import (
    BlastRadius,
    BlastRadiusClassifier,
    NuclearAuthDenied,
    NuclearSafetyGate,
)
from orion.governance.permissions import (
    ActionLevel,
    WorkspaceScope,
    is_dynamic_mutating,
    tool_action_level,
)
from orion.governance.trust_ledger import CommandTrustLedger

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
        action_confirm : Optional async or sync callable receiving (action, level)
                         for structured dialogs. Returns bool, or a dict of edited
                         params, which pass the static safety checks again before
                         being approved. Takes precedence over ``confirm``.
        trust_ledger   : Optional CommandTrustLedger for capability caching.
                         If provided, known-safe commands skip prompts in auto.
        nuclear_gate   : Optional NuclearSafetyGate. If provided, NUCLEAR_DESTRUCTIVE
                         commands trigger OS authentication popup.
        circuit_breaker: Optional CircuitBreaker instance. If provided, mutations
                         are blocked when the breaker is in SAFE_HOLDING state
                         (i.e., frontier model failed externally — NOT when the
                         user deliberately chose a light model as daily driver).
    """

    def __init__(
        self,
        scope: Optional[WorkspaceScope] = None,
        mode: AutonomyMode = AutonomyMode.SUPERVISED,
        audit_logger: Optional[AuditLogger] = None,
        confirm: Optional[ConfirmCallback] = None,
        action_confirm: Optional[Callable[[Action, ActionLevel], Any]] = None,
        trust_ledger: Optional[CommandTrustLedger] = None,
        nuclear_gate: Optional[NuclearSafetyGate] = None,
        circuit_breaker: Optional[Any] = None,  # CircuitBreaker (avoid circular import)
    ) -> None:
        self._scope = scope or WorkspaceScope.default()
        self._mode = mode
        self._audit = audit_logger or AuditLogger()
        self._confirm = confirm if confirm is not None else _default_confirm
        self._action_confirm = action_confirm
        self._edited_params: dict[str, dict[str, Any]] = {}
        self._trust_ledger = trust_ledger
        self._nuclear_gate = nuclear_gate or NuclearSafetyGate()
        self._circuit_breaker = circuit_breaker  # Optional[CircuitBreaker]
        self._blast_classifier = BlastRadiusClassifier()

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

    def attach_circuit_breaker(self, circuit_breaker: Any) -> None:
        """Attaches a CircuitBreaker instance to the PEP.

        The PEP will block mutations when the breaker is in SAFE_HOLDING.

        IMPORTANT: SAFE_HOLDING only blocks mutations when the frontier model
        failed externally. If the user deliberately chose a light model
        (circuit_breaker.intentional_lite_mode == True), mutations are NOT
        blocked — the user has full access to all tools.

        Args:
            circuit_breaker: CircuitBreaker instance to attach.
        """
        self._circuit_breaker = circuit_breaker
        logger.info(
            "PEP: CircuitBreaker attached (intentional_lite_mode=%s, state=%s)",
            getattr(circuit_breaker, "intentional_lite_mode", "unknown"),
            getattr(circuit_breaker, "state", "unknown"),
        )

    async def evaluate(self, action: Action) -> bool:
        """Gate the given Action through the policy.

        Evaluation order:
          1. Safe Holding check (circuit breaker): blocks mutations if in
             SAFE_HOLDING due to frontier model failure (NOT if user chose
             a light model deliberately).
          2. Nuclear Safety Gate: NUCLEAR_DESTRUCTIVE commands always require
             OS authentication, regardless of autonomy mode.
          3. Static safety invariants: sudo, path scope.
          4. Trust Ledger lookup: known-safe commands skip prompt in auto mode.
          5. Autonomy mode gating: LEVEL_2/LEVEL_3 policy.

        Returns:
            True  if the action is approved and should proceed.
            False if the user explicitly rejected a confirmation prompt.

        Raises:
            ActionDenied  if the action is structurally blocked by policy
                          (e.g. path outside workspace, safe holding violation,
                           nuclear auth denied).
        """
        level = self._effective_level(action)
        params = dict(action.params)

        # ── 1. Static safety invariants (never bypassed, zero prompt) ────
        self._assert_no_sudo(action, level)
        self._assert_path_scope(action, level)

        # ── 2. SAFE_HOLDING check (HIGHEST priority for code safety) ────
        # Only blocks if SAFE_HOLDING was caused by an external model failure,
        # NOT if the user intentionally chose a light model as their daily driver.
        self._assert_safe_holding(action, level)

        # ── 3. Nuclear Safety Gate (always enforced in all modes) ───────
        # NUCLEAR_DESTRUCTIVE commands require OS authentication in ALL modes.
        await self._assert_nuclear_safe(action, level)

        # ── 4. LEVEL_0: pure informative — no audit, no gate ─────────────
        if level == ActionLevel.LEVEL_0:
            return True

        # ── 5. LEVEL_1: passive read — audit only ────────────────────────
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

        # ── 6. LEVEL_2 / LEVEL_3: apply autonomy mode + trust ledger ────
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

    def take_edited_params(self, action_id: str) -> Optional[dict[str, Any]]:
        """Return (and clear) params the human edited while approving *action_id*."""
        return self._edited_params.pop(action_id, None)

    def record_action_success(self, action: Action, exit_code: int = 0) -> None:
        """Records a successful action in the Trust Ledger (if applicable).

        Should be called after a run_command action completes successfully.
        Nuclear commands are NEVER recorded in the trust ledger.

        Args:
            action: The Action that was executed successfully.
            exit_code: Exit code of the command (0 = success).
        """
        if self._trust_ledger is None:
            return
        if action.tool != "run_command":
            return

        cmd = str(action.params.get("command", ""))
        if not cmd:
            return

        # Never record nuclear commands in the trust ledger
        if self._blast_classifier.is_nuclear(cmd):
            return

        self._trust_ledger.record_success(cmd, exit_code=exit_code)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _effective_level(self, action: Action) -> ActionLevel:
        """Derive ActionLevel from the tool registry (ignores engine hint)."""
        return tool_action_level(action.tool)

    def _assert_safe_holding(self, action: Action, level: ActionLevel) -> None:
        """Block mutations if circuit breaker is in SAFE_HOLDING state.

        CRITICAL DISTINCTION:
        SAFE_HOLDING only blocks when ALL of these are true simultaneously:
          1. The circuit_breaker state is SAFE_HOLDING
          2. The frontier model failed due to an EXTERNAL cause (API, network,
             budget) — NOT because the user chose a light model intentionally.
          3. circuit_breaker.intentional_lite_mode is False.

        If the user deliberately set a light model as their daily driver
        (intentional_lite_mode=True), this check is a NO-OP and the user
        has full tool access as normal.

        Args:
            action: Action to check.
            level: ActionLevel of the action.

        Raises:
            ActionDenied: If SAFE_HOLDING is active due to a model failure.
        """
        if self._circuit_breaker is None:
            return

        # Check if mutation blocking is active.
        # is_mutation_blocked() returns False if intentional_lite_mode=True,
        # so this entire check is a no-op for intentional light model users.
        if not self._circuit_breaker.is_mutation_blocked():
            return

        # Only block LEVEL_2+ (mutations and commands)
        if level < ActionLevel.LEVEL_2:
            return

        # Import here to avoid circular import
        from orion.gateway.circuit_breaker import MUTATING_TOOLS, SafeHoldingViolation

        if action.tool in MUTATING_TOOLS or is_dynamic_mutating(action.tool):
            try:
                self._circuit_breaker.assert_mutation_allowed(action.tool)
            except SafeHoldingViolation as exc:
                self._audit.log_denied(
                    action_id=action.event_id,
                    tool=action.tool,
                    params=dict(action.params),
                    level=level,
                    reason=f"safe_holding: {exc.reason.value}",
                )
                raise ActionDenied(
                    action.event_id,
                    action.tool,
                    str(exc),
                ) from exc

    async def _assert_nuclear_safe(self, action: Action, level: ActionLevel) -> None:
        """Run Nuclear Safety Gate for LEVEL_3 run_command actions.

        NUCLEAR_DESTRUCTIVE commands trigger OS authentication in ALL modes.
        This invariant cannot be bypassed by any configuration.

        Args:
            action: Action to check.
            level: ActionLevel of the action.

        Raises:
            ActionDenied: If nuclear authentication was denied.
        """
        # Only applies to run_command
        if action.tool != "run_command":
            return
        if level < ActionLevel.LEVEL_3:
            return

        cmd = str(action.params.get("command", ""))
        if not cmd:
            return

        blast = self._blast_classifier.classify(cmd)
        if blast != BlastRadius.NUCLEAR_DESTRUCTIVE:
            return

        # Nuclear command detected — run OS authentication challenge
        logger.warning(
            "PEP: NUCLEAR command detected — '%s'. Launching OS auth challenge.",
            cmd[:80],
        )

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                self._nuclear_gate.challenge,
                cmd,
            )
        except Exception as exc:
            logger.exception("PEP: NuclearSafetyGate challenge raised unexpectedly.")
            raise ActionDenied(
                action.event_id,
                action.tool,
                f"Nuclear auth challenge failed with exception: {exc}",
            ) from exc

        if not result.authorized:
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=dict(action.params),
                level=level,
                reason=f"nuclear_auth_denied:{result.method_used}",
            )
            raise ActionDenied(
                action.event_id,
                action.tool,
                f"Nuclear operation denied. Authentication cancelled or failed "
                f"(method: {result.method_used}). Command: {cmd[:80]}",
            )

        logger.warning(
            "PEP: Nuclear command AUTHORIZED by user (method=%s, duration=%.1fs): '%s'",
            result.method_used,
            result.duration_seconds,
            cmd[:80],
        )

    def _assert_no_sudo(self, action: Action, level: ActionLevel) -> None:
        """Block sudo commands unless trusted or mode/level allows.

        In SUPERVISED mode: sudo always denied (must use FULLY_AUTO).
        In WORKSPACE_AUTO: sudo at LEVEL_3 goes to confirmation prompt.
        In FULLY_AUTO: sudo is allowed (gated by trust ledger / user confirm).
        """
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
        """Apply autonomy-mode gating logic for LEVEL_2 / LEVEL_3.

        In auto modes, consults the Trust Ledger before prompting.
        Known-safe commands run without user interruption.
        """
        cmd: str = str(action.params.get("command", "")) if action.tool == "run_command" else ""

        # ── Trust Ledger shortcut (WORKSPACE_AUTO / FULLY_AUTO only) ────
        if self._trust_ledger and cmd and self._mode != AutonomyMode.SUPERVISED:
            lookup = self._trust_ledger.lookup(cmd)
            if lookup.is_trusted:
                logger.debug(
                    "PEP: TrustLedger HIT — '%s' is trusted, skipping prompt.",
                    cmd[:60],
                )
                return True

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
        if self._action_confirm is not None:
            decision = self._action_confirm(action, level)
            if inspect.isawaitable(decision):
                decision = await decision
            if isinstance(decision, dict):
                edited = action.model_copy(update={"params": decision})
                self._assert_no_sudo(edited, level)
                self._assert_path_scope(edited, level)
                await self._assert_nuclear_safe(edited, level)
                self._edited_params[action.event_id] = decision
                return True
            return bool(decision)

        level_label = f"LEVEL_{level}"
        prompt = (
            f"\n!  O.R.I.O.N wants to execute a {level_label} action:\n"
            f"   Tool   : {action.tool}\n"
            f"   Params : {action.params}\n"
            f"Approve?"
        )
        result = self._confirm(prompt)
        if asyncio.iscoroutine(result):
            return bool(await result)
        return bool(result)
