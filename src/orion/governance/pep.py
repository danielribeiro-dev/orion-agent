"""
O.R.I.O.N — Policy Enforcement Point (PEP)
Deterministic gatekeeper that intercepts every Action before execution.

Reference: docs/architecture/GOVERNANCE_PEP.md

Modes:
  SUPERVISED    (default for v0.1.0): LEVEL_2+ actions require [Y/n].
  WORKSPACE_AUTO: LEVEL_2 inside workspace auto-approved; LEVEL_3 still gated.
  FULLY_AUTO    : All actions auto-approved (LEVEL_3 still blocks sudo).

Safety invariants that are NEVER bypassed regardless of mode, rule or hook:
  - NUCLEAR_DESTRUCTIVE commands always trigger OS authentication popup.
  - SAFE_HOLDING state blocks all mutations until the frontier model recovers
    (ONLY applies when SAFE_HOLDING was triggered by a model failure, NOT
     when the user deliberately chose a light model as their daily driver).

Escalations (v0.5.0 Sprint 5): 'sudo' and paths outside the workspace no longer
hard-block. They ESCALATE to a one-shot confirmation that shows the exact
command and the reason. They are never persisted as "always allow" (sudo) and
never approved by a rule or hook. With no human available (``interactive=False``:
hooks, subagents, scheduled jobs, daemon) an escalation is DENIED.

Subagents (v0.5.0 Sprint 6, ADR-028): a child PEP is built with ``for_subagent`` and
runs UNDER the parent's ceiling. Privilege only decreases: the effective mode is
``min(parent, child)``, the parent's ``deny`` and ``ask`` rules also apply to the child,
``allow`` rules and the Trust Ledger are never inherited, the child can never ask a human
(every ``ask`` and every nuclear challenge is DENIED) and the parent's SAFE_HOLDING and
plan-mode restrictions apply live.

Declarative rules (``governance/rules.py``): deny > ask > allow. A deny rule
blocks; an ask rule forces a confirmation; an allow rule only skips the prompt
where the mode would have asked, never overriding the invariants above.

Sprint 4 additions (v0.3.0):
  - CircuitBreaker integration: blocks mutations in SAFE_HOLDING state.
  - CommandTrustLedger integration: known-safe commands skip prompt in auto.
  - NuclearSafetyGate integration: NUCLEAR_DESTRUCTIVE always auth-gated.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from orion.core.events import Action
from orion.governance.audit import AuditLogger
from orion.governance.nuclear import (
    BlastRadius,
    BlastRadiusClassifier,
    NuclearSafetyGate,
)
from orion.governance.permissions import (
    ActionLevel,
    WorkspaceScope,
    is_dynamic_mutating,
    tool_action_level,
)
from orion.governance.rules import RuleMatch, RuleSet
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


_MODE_RANK: dict[AutonomyMode, int] = {
    AutonomyMode.SUPERVISED: 0,
    AutonomyMode.WORKSPACE_AUTO: 1,
    AutonomyMode.FULLY_AUTO: 2,
}


def min_mode(a: AutonomyMode, b: AutonomyMode) -> AutonomyMode:
    """The less autonomous of two modes (privilege only decreases)."""
    return a if _MODE_RANK[a] <= _MODE_RANK[b] else b


#: Tools whose ``cwd``/``path`` must stay inside the scope of a confined (subagent) PEP.
_CWD_SCOPED_TOOLS = frozenset({"run_command", "glob", "grep", "search_files"})


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


@dataclass(frozen=True)
class Rejection:
    """Recusa que não veio do usuário (ex.: modo plano); *reason* chega ao modelo."""

    reason: str


_SUDO_RE = re.compile(r"(?:^|[\s;&|(`])sudo(?:\s|$)")


@dataclass(frozen=True)
class Escalation:
    """Motivo pelo qual a ação exige confirmação explícita do Senhor."""

    kind: str  # "sudo" | "outside_workspace"
    reason: str


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
        scope: WorkspaceScope | None = None,
        mode: AutonomyMode = AutonomyMode.SUPERVISED,
        audit_logger: AuditLogger | None = None,
        confirm: ConfirmCallback | None = None,
        action_confirm: Callable[[Action, ActionLevel], Any] | None = None,
        trust_ledger: CommandTrustLedger | None = None,
        nuclear_gate: NuclearSafetyGate | None = None,
        circuit_breaker: Any | None = None,  # CircuitBreaker (avoid circular import)
        rules: RuleSet | None = None,
        interactive: bool = True,
        ceiling: PolicyEnforcementPoint | None = None,
        agent_id: str | None = None,
    ) -> None:
        self._ceiling = ceiling
        self._agent_id = agent_id
        self._scope = scope or WorkspaceScope.default()
        self._mode = mode
        self._audit = audit_logger or AuditLogger()
        self._confirm = confirm if confirm is not None else _default_confirm
        self._action_confirm = action_confirm
        self._edited_params: dict[str, dict[str, Any]] = {}
        self._rejection_reasons: dict[str, str] = {}
        self._trust_ledger = trust_ledger
        self._nuclear_gate = nuclear_gate or NuclearSafetyGate()
        self._circuit_breaker = circuit_breaker  # Optional[CircuitBreaker]
        self._blast_classifier = BlastRadiusClassifier()
        self._rules = rules
        self._interactive = interactive
        if ceiling is not None:
            # Sob teto: nunca há humano, nunca há trust ledger (nada de "allow" herdado) e o
            # safe-holding do pai vale para o filho.
            self._interactive = False
            self._trust_ledger = None
            if self._circuit_breaker is None:
                self._circuit_breaker = ceiling._circuit_breaker
        self._read_only = False
        self._cwd_confined = False
        self._confine_reads = False
        self._pending_escalations: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @classmethod
    def for_subagent(
        cls,
        parent: PolicyEnforcementPoint,
        *,
        agent_id: str,
        scope: WorkspaceScope | None = None,
        mode: AutonomyMode | None = None,
        audit_logger: AuditLogger | None = None,
        confine_reads: bool = False,
    ) -> PolicyEnforcementPoint:
        """PEP of a child agent, under *parent*'s ceiling (ADR-028).

        ``mode`` can only lower the autonomy: the stored mode is ``min(parent, mode)``
        and the parent's CURRENT mode keeps capping it afterwards. ``confine_reads`` (isolated
        workspaces) also denies read tools whose ``path`` leaves the child's scope.
        """
        requested = parent.mode if mode is None else min_mode(mode, parent.mode)
        pep = cls(
            scope=scope or parent.scope,
            mode=requested,
            audit_logger=audit_logger or parent._audit.with_agent(agent_id),
            confirm=lambda _prompt: False,  # defesa em profundidade: nunca aprova
            ceiling=parent,
            agent_id=agent_id,
        )
        pep._cwd_confined = True
        pep._confine_reads = confine_reads
        return pep

    @property
    def agent_id(self) -> str | None:
        return self._agent_id

    @property
    def ceiling(self) -> PolicyEnforcementPoint | None:
        return self._ceiling

    @property
    def interactive(self) -> bool:
        return self._interactive

    @property
    def mode(self) -> AutonomyMode:
        """Effective mode: the child can never exceed its parent's current mode."""
        if self._ceiling is not None:
            return min_mode(self._mode, self._ceiling.mode)
        return self._mode

    @property
    def scope(self) -> WorkspaceScope:
        return self._scope

    def set_mode(self, mode: AutonomyMode) -> None:
        """Switch autonomy mode at runtime (a child is still capped by its parent)."""
        logger.info("PEP: autonomy mode changed %s → %s", self._mode, mode)
        self._mode = mode

    @property
    def rules(self) -> RuleSet | None:
        return self._rules

    def set_rules(self, rules: RuleSet | None) -> None:
        """Replace the declarative rule set (settings reloaded, "always allow" saved)."""
        self._rules = rules

    def set_interactive(self, interactive: bool) -> None:
        """False when no human can answer (hooks, subagents, jobs, daemon)."""
        if self._ceiling is not None and interactive:
            raise ValueError("a subagent PEP can never be interactive")
        self._interactive = interactive

    @property
    def read_only(self) -> bool:
        """Plan mode, own or inherited from the parent (live)."""
        return self._read_only or (self._ceiling is not None and self._ceiling.read_only)

    def set_read_only(self, read_only: bool) -> None:
        """Plan mode: every LEVEL_2+ action is refused, whatever the rules say."""
        self._read_only = read_only

    def peek_escalation(self, action_id: str) -> str | None:
        """Reason of the escalation being asked for *action_id* (None if ordinary)."""
        return self._pending_escalations.get(action_id)

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
          1. Safe Holding check (circuit breaker): hard block of mutations.
          2. Nuclear Safety Gate: NUCLEAR_DESTRUCTIVE always needs OS auth.
          3. Declarative rules: a matching ``deny`` blocks.
          4. Read-only (plan mode): LEVEL_2+ refused.
          5. Escalations (sudo, outside workspace): one-shot confirmation.
          6. ``ask`` rule, Trust Ledger, ``allow`` rule and autonomy mode.

        Returns:
            True  if the action is approved and should proceed.
            False if the user (or plan mode) refused it.

        Raises:
            ActionDenied  if the action is structurally blocked (safe holding,
                          nuclear auth denied, deny rule, escalation with no
                          human available).
        """
        level = self._effective_level(action)
        params = dict(action.params)

        self._assert_safe_holding(action, level)
        await self._assert_nuclear_safe(action, level)

        match = self._match_rule(action)
        if match is not None and match.effect == "deny":
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=params,
                level=level,
                reason=f"rule_deny:{match.rule}",
                decision_source="rule",
            )
            raise ActionDenied(
                action.event_id, action.tool, f"blocked by deny rule '{match.rule}'"
            )

        if self.read_only and level >= ActionLevel.LEVEL_2:
            self._rejection_reasons[action.event_id] = (
                "plan mode is read-only; this is not a user rejection. "
                "Call exit_plan_mode with a plan to get approval before mutating."
            )
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=params,
                level=level,
                reason="plan_mode_read_only",
                decision_source="mode",
            )
            return False

        escalations = self._escalations(action, level)
        forced_ask = match is not None and match.effect == "ask"

        if escalations and level <= ActionLevel.LEVEL_1 and self._cwd_confined:
            # Tools de leitura de um subagent com ``cwd`` fora do escopo: sem humano, nega.
            await self._escalate(action, level, escalations)

        if level <= ActionLevel.LEVEL_1 and not forced_ask:
            if level == ActionLevel.LEVEL_1:
                self._audit.log(
                    action_id=action.event_id,
                    tool=action.tool,
                    params=params,
                    level=level,
                    user_authorized=False,
                    result_status="success",
                    decision_source="mode",
                )
            return True

        if escalations:
            approved = await self._escalate(action, level, escalations)
            source = "user_escalation"
        elif forced_ask:
            approved = await self._ask_user(action, level)
            source = "user"
        else:
            approved, source = await self._gate(action, level, match)

        if not approved:
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=params,
                level=level,
                reason="user_rejected",
                decision_source=source,
            )
            return False

        self._audit.log(
            action_id=action.event_id,
            tool=action.tool,
            params=params,
            level=level,
            user_authorized=(source.startswith("user")),
            result_status="pending",
            decision_source=source,
        )
        return True

    def record_hook_denial(self, action: Action, reason: str) -> None:
        """Audit a PreToolUse hook that blocked *action* before it reached the PEP."""
        self._audit.log_denied(
            action_id=action.event_id,
            tool=action.tool,
            params=dict(action.params),
            level=self._effective_level(action),
            reason=f"hook_block:{reason[:200]}",
            decision_source="hook",
        )

    def record_result(self, action_id: str, tool: str, success: bool, detail: str = "") -> None:
        """Close the "pending" audit record with the execution outcome."""
        self._audit.log_result(
            action_id=action_id,
            tool=tool,
            status="success" if success else "error",
            detail=detail,
        )

    def take_rejection_reason(self, action_id: str) -> str | None:
        """Motivo de uma recusa não-humana (consumido uma vez)."""
        return self._rejection_reasons.pop(action_id, None)

    def take_edited_params(self, action_id: str) -> dict[str, Any] | None:
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

        if not self._interactive:
            # Sem humano para o desafio do SO: nuclear nunca é contornado, é negado.
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=dict(action.params),
                level=level,
                reason="nuclear_no_human",
                decision_source="mode",
            )
            raise ActionDenied(
                action.event_id,
                action.tool,
                "nuclear operation requires the Senhor's OS authentication but no human is "
                f"available. Command: {cmd[:80]}",
            )

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

    def _match_rule(self, action: Action) -> RuleMatch | None:
        own = (
            self._rules.match(action.tool, dict(action.params), self._scope.roots)
            if self._rules is not None
            else None
        )
        if self._ceiling is None:
            return own
        # Sob teto: deny/ask do pai se somam; allow do pai NUNCA é herdado.
        inherited = self._ceiling._match_rule(action)
        if inherited is not None and inherited.effect == "allow":
            inherited = None
        for candidate in (own, inherited):
            if candidate is not None and candidate.effect == "deny":
                return candidate
        for candidate in (own, inherited):
            if candidate is not None and candidate.effect == "ask":
                return candidate
        return own

    def _escalations(self, action: Action, level: ActionLevel) -> list[Escalation]:
        """Reasons this action needs the Senhor's explicit, one-shot confirmation."""
        found: list[Escalation] = []
        cmd = str(action.params.get("command", ""))
        if cmd and _SUDO_RE.search(cmd) and self.mode != AutonomyMode.FULLY_AUTO:
            found.append(Escalation("sudo", "usa sudo (privilégios de administrador)"))
        if self._cwd_confined and action.tool in _CWD_SCOPED_TOOLS:
            cwd = str(action.params.get("cwd", "")) or None
            if cwd:
                try:
                    self._scope.assert_allowed(cwd)
                except PermissionError:
                    found.append(Escalation("outside_workspace", f"cwd fora do workspace: {cwd}"))
        if self._confine_reads and (action.tool in _CWD_SCOPED_TOOLS or action.tool == "read_file"):
            read_path = str(action.params.get("path", "")) or None
            if read_path:
                try:
                    self._scope.assert_allowed(read_path)
                except PermissionError:
                    found.append(
                        Escalation("outside_workspace", f"leitura fora do workspace isolado: {read_path}")
                    )
        if level >= ActionLevel.LEVEL_2:
            path = str(action.params.get("path", "")) or None
            if path:
                try:
                    self._scope.assert_allowed(path)
                except PermissionError:
                    covered = self._rules is not None and self._rules.allows_outside(
                        action.tool, dict(action.params), self._scope.roots
                    )
                    if not covered:
                        found.append(
                            Escalation("outside_workspace", f"caminho fora do workspace: {path}")
                        )
        return found

    async def _escalate(
        self, action: Action, level: ActionLevel, escalations: list[Escalation]
    ) -> bool:
        """Ask the Senhor once; with nobody to ask, deny (never approve by default)."""
        reasons = "; ".join(e.reason for e in escalations)
        if not self._interactive:
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=dict(action.params),
                level=level,
                reason=f"escalation_no_human:{reasons}",
                decision_source="mode",
            )
            raise ActionDenied(
                action.event_id,
                action.tool,
                f"requires the Senhor's confirmation ({reasons}) but no human is available",
            )
        self._pending_escalations[action.event_id] = reasons
        try:
            approved = await self._ask_user(action, level)
        finally:
            self._pending_escalations.pop(action.event_id, None)
        if not approved and action.event_id not in self._rejection_reasons:
            self._rejection_reasons[action.event_id] = (
                f"the Senhor declined the escalation ({reasons}). Explain what you needed it "
                "for and propose an alternative that does not require it."
            )
        return approved

    async def _gate(
        self, action: Action, level: ActionLevel, match: RuleMatch | None
    ) -> tuple[bool, str]:
        """Apply rule/trust/autonomy-mode gating for LEVEL_2 / LEVEL_3.

        Returns ``(approved, decision_source)``.
        """
        cmd: str = str(action.params.get("command", "")) if action.tool == "run_command" else ""

        if match is not None and match.effect == "allow":
            return True, "rule"

        # ── Trust Ledger shortcut (WORKSPACE_AUTO / FULLY_AUTO only) ────
        mode = self.mode
        if self._trust_ledger and cmd and mode != AutonomyMode.SUPERVISED:
            lookup = self._trust_ledger.lookup(cmd)
            if lookup.is_trusted:
                logger.debug(
                    "PEP: TrustLedger HIT — '%s' is trusted, skipping prompt.",
                    cmd[:60],
                )
                return True, "ledger"

        if mode == AutonomyMode.SUPERVISED:
            return await self._ask_user(action, level), "user"

        if mode == AutonomyMode.WORKSPACE_AUTO:
            if level == ActionLevel.LEVEL_2:
                return True, "mode"  # auto-approved inside workspace
            return await self._ask_user(action, level), "user"  # LEVEL_3 still gated

        # FULLY_AUTO
        return True, "mode"

    async def _ask_user(self, action: Action, level: ActionLevel) -> bool:
        """Display confirmation prompt and return the human's decision.

        With no human available (subagents, jobs, daemon) EVERY ask is denied (ADR-028):
        the denial reaches the model as an ordinary tool error, so the child carries on.
        """
        if not self._interactive:
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=dict(action.params),
                level=level,
                reason="ask_no_human",
                decision_source="mode",
            )
            raise ActionDenied(
                action.event_id,
                action.tool,
                "requires the Senhor's confirmation but no human is available "
                "(parent may not grant it to subagents); use a read-only alternative "
                "or report back what you needed",
            )
        if self._action_confirm is not None:
            decision = self._action_confirm(action, level)
            if inspect.isawaitable(decision):
                decision = await decision
            if isinstance(decision, Rejection):
                self._rejection_reasons[action.event_id] = decision.reason
                return False
            if isinstance(decision, dict):
                return await self._accept_edit(action, level, decision)
            return bool(decision)

        level_label = f"LEVEL_{level}"
        why = self._pending_escalations.get(action.event_id)
        prompt = (
            f"\n!  O.R.I.O.N wants to execute a {level_label} action:\n"
            f"   Tool   : {action.tool}\n"
            f"   Params : {action.params}\n"
            + (f"   Escalation: {why}\n" if why else "")
            + "Approve?"
        )
        result = self._confirm(prompt)
        if asyncio.iscoroutine(result):
            return bool(await result)
        return bool(result)

    async def _accept_edit(
        self, action: Action, level: ActionLevel, decision: dict[str, Any]
    ) -> bool:
        """Re-check parameters the human edited while approving.

        Deny rules and the nuclear gate apply again. A NEW escalation introduced
        by the edit (e.g. adding sudo) asks again with its reason shown.
        """
        edited = action.model_copy(update={"params": decision})
        edited_match = self._match_rule(edited)
        if edited_match is not None and edited_match.effect == "deny":
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=dict(decision),
                level=level,
                reason=f"rule_deny:{edited_match.rule}",
                decision_source="rule",
            )
            raise ActionDenied(
                action.event_id, action.tool, f"blocked by deny rule '{edited_match.rule}'"
            )
        await self._assert_nuclear_safe(edited, level)
        known = {e.kind for e in self._escalations(action, level)}
        fresh = [e for e in self._escalations(edited, level) if e.kind not in known]
        if fresh and not await self._escalate(edited, level, fresh):
            return False
        self._edited_params[action.event_id] = decision
        return True
