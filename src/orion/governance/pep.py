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

Faixas (v0.5.3 Sprint 2, ADR-046/047): além do nível por tool, cada ação recebe uma faixa por raio
de destruição e reversibilidade (``bands.py``). A blocklist nega em qualquer modo; Nuclear exige
presença verificada; no modo ``auto`` (WORKSPACE_AUTO) Livre passa, Classificada vai ao
classificador em dois estágios, Presença pergunta (ou usa um grant de plano). Deleções e
sobrescritas são fotografadas antes (``reversibility.py``). Sem humano, Presença e Nuclear viram
pendência na Inbox; num subagent, Presença volta ao agente pai.

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any

from orion.core.events import Action
from orion.governance.audit import AuditLogger
from orion.governance.bands import (
    Band,
    BandContext,
    BandVerdict,
    classify_action,
    is_external_content_tool,
)
from orion.governance.classifier import (
    ClassifierRequest,
    ClassifierVerdict,
    Decision,
    RiskClassifier,
    RiskClassifierPort,
)
from orion.governance.grants import GrantStore, IntentGrant
from orion.governance.nuclear import (
    BlastRadiusClassifier,
    NuclearSafetyGate,
)
from orion.governance.paths import (
    is_protected_state_path,
    is_secret_path,
    is_sensitive_path,
    zone_of,
)
from orion.governance.permissions import (
    ActionLevel,
    WorkspaceScope,
    is_dynamic_mutating,
    tool_action_level,
)
from orion.governance.reversibility import (
    ReversibilityEngine,
    Snapshot,
    SnapshotError,
    SnapshotPlan,
)
from orion.governance.rules import RuleMatch, RuleSet
from orion.governance.trust_ledger import CommandCanonicalizer, CommandTrustLedger

__all__ = [
    "ActionDeferred",
    "ActionDenied",
    "AutonomyMode",
    "Escalation",
    "PendingAction",
    "PolicyEnforcementPoint",
    "REMEMBERABLE_ESCALATIONS",
    "Rejection",
    "is_protected_state_path",
    "is_secret_path",
    "is_sensitive_path",
    "min_mode",
]

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Autonomy modes
# ---------------------------------------------------------------------------


class AutonomyMode(StrEnum):
    """Configurable autonomy level for the PEP.

    v0.5.3 (ADR-046): ``ask`` = SUPERVISED (pergunta toda mutação), ``auto`` = WORKSPACE_AUTO
    (decide por faixa; padrão novo da TUI), ``full`` = FULLY_AUTO (sem estágio 2; Presença vira
    Classificada). Nenhum modo toca Nuclear nem a blocklist.
    """

    SUPERVISED = "supervised"
    WORKSPACE_AUTO = "workspace_auto"
    FULLY_AUTO = "fully_auto"
    ASK = "supervised"
    AUTO = "workspace_auto"
    FULL = "fully_auto"

    @classmethod
    def _missing_(cls, value: object) -> AutonomyMode | None:
        aliases = {
            "ask": cls.SUPERVISED,
            "manual": cls.SUPERVISED,
            "plan": cls.SUPERVISED,
            "auto": cls.WORKSPACE_AUTO,
            "accept-edits": cls.WORKSPACE_AUTO,
            "full": cls.FULLY_AUTO,
        }
        return aliases.get(str(value).strip().lower())


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


class ActionDeferred(ActionDenied):
    """Sem humano: a ação virou pendência na Inbox (ADR-046 item 6). Não roda agora."""

    def __init__(self, action_id: str, tool: str, reason: str, pending_id: str = "") -> None:
        self.pending_id = pending_id
        super().__init__(action_id, tool, reason)


@dataclass(frozen=True)
class PendingAction:
    """Pendência entregue ao Senhor quando não há ninguém para responder agora."""

    action_id: str
    tool: str
    params: dict[str, Any]
    band: Band
    reason: str
    agent_id: str | None = None

    @property
    def summary(self) -> str:
        subject = self.params.get("command") or self.params.get("path") or ""
        return f"{self.tool}: {str(subject)[:300]}" if subject else self.tool


#: Recebe a pendência; devolve o id dela na Inbox (ou None). Pode ser síncrono ou assíncrono.
DeferralSink = Callable[[PendingAction], Any]

#: Negações automáticas (classificador) antes de devolver a decisão ao Senhor.
MAX_CONSECUTIVE_DENIALS = 3
MAX_SESSION_DENIALS = 20


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


_READ_TOOLS = frozenset({"read_file", "grep", "search_files"})
_WRITE_TOOLS = frozenset({"write_file", "edit_file", "notebook_edit"})


_SUDO_RE = re.compile(r"(?:^|[\s;&|(`])sudo(?:\s|$)")

#: Escaladas que o Senhor pode transformar em "sempre" (regra allow local).
REMEMBERABLE_ESCALATIONS = frozenset({"outside_workspace"})


@dataclass(frozen=True)
class Escalation:
    """Motivo pelo qual a ação exige confirmação explícita do Senhor."""

    kind: str  # "sudo" | "outside_workspace" | "sensitive_path"
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
        reversibility: ReversibilityEngine | None = None,
        classifier: RiskClassifierPort | None = None,
        orion_home: Path | None = None,
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
        self._pending_kinds: dict[str, frozenset[str]] = {}
        self._approval_sources: dict[str, str] = {}
        # ── Faixas (v0.5.3 Sprint 2) ──
        self._orion_home = orion_home
        self._reversibility = reversibility
        self._classifier: RiskClassifierPort | None = classifier
        self._user_messages: Callable[[], Sequence[str]] | None = None
        self._grants = GrantStore()
        self._deferral: DeferralSink | None = None
        self._contaminated = False
        self._known_hosts: set[str] = set()
        self._action_hosts: dict[str, tuple[str, ...]] = {}
        self._plans: dict[str, SnapshotPlan] = {}
        self._snapshots: dict[str, Snapshot] = {}
        self._denials_consecutive = 0
        self._denials_total = 0
        self.session_id: str | None = None
        self._current_branch: Callable[[Path], str | None] | None = None
        self._root_devices: Callable[[], frozenset[str]] | None = None
        self._protected_branches: tuple[str, ...] | None = None

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

    def peek_escalation_kinds(self, action_id: str) -> frozenset[str]:
        """Kinds of the escalation being asked for *action_id* (empty if ordinary)."""
        return self._pending_kinds.get(action_id, frozenset())

    @property
    def nuclear_gate(self) -> NuclearSafetyGate:
        return self._nuclear_gate

    @property
    def trust_ledger(self) -> CommandTrustLedger | None:
        return self._trust_ledger

    def attach_trust_ledger(self, ledger: CommandTrustLedger | None) -> None:
        """Liga o Command Trust Ledger (ADR-017, ADR-046 item 7). Subagents nunca o recebem."""
        if self._ceiling is None:
            self._trust_ledger = ledger

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

    # ------------------------------------------------------------------
    # Faixas, classificador, grants, reversibilidade (v0.5.3 Sprint 2)
    # ------------------------------------------------------------------

    def _root(self) -> PolicyEnforcementPoint:
        """O PEP da sessão (o pai mais alto): dono de grants, contaminação e contadores."""
        pep = self
        while pep._ceiling is not None:
            pep = pep._ceiling
        return pep

    def attach_reversibility(self, engine: ReversibilityEngine | None) -> None:
        """Liga o motor de snapshot (``~/.orion/trash``). Subagents usam o do pai."""
        self._reversibility = engine

    @property
    def reversibility(self) -> ReversibilityEngine | None:
        if self._reversibility is None and self._ceiling is not None:
            return self._ceiling.reversibility
        return self._reversibility

    def attach_classifier(self, classifier: RiskClassifierPort | None) -> None:
        """Liga o classificador de dois estágios (o estágio 2 só existe com modelo)."""
        self._classifier = classifier

    @property
    def classifier(self) -> RiskClassifierPort:
        if self._classifier is not None:
            return self._classifier
        if self._ceiling is not None:
            return self._ceiling.classifier
        return RiskClassifier(ledger=self._trust_ledger)

    def set_user_messages(self, provider: Callable[[], Sequence[str]] | None) -> None:
        """Fonte das mensagens do Senhor (única entrada do classificador além da chamada)."""
        self._user_messages = provider

    def user_messages(self) -> tuple[str, ...]:
        root = self._root()
        if root._user_messages is None:
            return ()
        try:
            return tuple(str(m) for m in root._user_messages())
        except Exception:  # noqa: BLE001
            return ()

    def set_deferral(self, sink: DeferralSink | None) -> None:
        """Sem humano: para onde vão as pendências de Presença e Nuclear (Inbox)."""
        self._deferral = sink

    def configure_bands(
        self,
        *,
        current_branch: Callable[[Path], str | None] | None = None,
        root_devices: Callable[[], frozenset[str]] | None = None,
        protected_branches: Sequence[str] | None = None,
    ) -> None:
        """Ajustes do classificador de faixas (branches protegidas e resolvedores injetáveis)."""
        if current_branch is not None:
            self._current_branch = current_branch
        if root_devices is not None:
            self._root_devices = root_devices
        if protected_branches is not None:
            self._protected_branches = tuple(protected_branches)

    @property
    def grants(self) -> GrantStore:
        return self._root()._grants

    def issue_grant(self, *, commands: Sequence[str] = (), paths: Sequence[str] = (), note: str = "") -> IntentGrant | None:
        """Aprovação por intenção (plano aprovado com passos de Presença), TTL de 15 min."""
        grant = self.grants.issue(commands=commands, paths=paths, note=note)
        if grant is not None:
            self._audit.log(
                action_id=f"grant_{grant.id}",
                tool="exit_plan_mode",
                params={"commands": list(grant.commands), "paths": list(grant.paths)},
                level=ActionLevel.LEVEL_0,
                user_authorized=True,
                result_status="success",
                decision_source=f"grant:{grant.id}",
            )
        return grant

    @property
    def contaminated(self) -> bool:
        return self._root()._contaminated

    def mark_contaminated(self) -> None:
        """A sessão leu conteúdo externo (web/MCP): exfiltração passa a exigir presença."""
        self._root()._contaminated = True

    def take_snapshot(self, action_id: str) -> Snapshot | None:
        """Snapshot feito antes de *action_id* (consumido uma vez pelo runtime)."""
        return self._snapshots.pop(action_id, None)

    def band_context(self, cwd: str | None = None) -> BandContext:
        root = self._root()
        hosts = set(root._known_hosts)
        for message in self.user_messages():
            hosts.update(h.lower() for h in _HOST_RE.findall(message))
        ctx = BandContext(
            scope=self._scope,
            orion_home=self._orion_home or (root._orion_home if root is not self else None),
            contaminated=root._contaminated,
            known_hosts=frozenset(hosts),
            current_branch=self._current_branch or root._current_branch,
            root_devices=self._root_devices or root._root_devices,
        )
        protected = self._protected_branches or root._protected_branches
        if protected:
            ctx.protected_branches = protected
        if cwd:
            ctx.cwd = ctx.resolve(cwd)
        return ctx

    def band_of(self, action: Action) -> BandVerdict:
        """Faixa final da ação: classificação + plano de snapshot (sem gravar nada)."""
        verdict, _plan = self._band(action)
        return verdict

    def _band(self, action: Action) -> tuple[BandVerdict, SnapshotPlan | None]:
        params = dict(action.params)
        ctx = self.band_context(str(params.get("cwd", "") or "") or None)
        verdict = classify_action(action.tool, params, ctx)
        if verdict.blocked or not verdict.ops:
            return verdict, None
        if verdict.band >= Band.NUCLEAR:
            return verdict, None
        engine = self.reversibility
        if engine is None:
            return verdict.raised(Band.NUCLEAR, "deleção/sobrescrita sem snapshot possível", "no_snapshot"), None
        try:
            plan = engine.plan(verdict.ops)
        except Exception as exc:  # noqa: BLE001 - plano falho = sem snapshot
            logger.warning("PEP: plano de snapshot falhou: %s", exc)
            return verdict.raised(Band.NUCLEAR, "deleção/sobrescrita sem snapshot possível", "no_snapshot"), None
        if plan.unresolved or verdict.unresolved:
            raised = verdict.band.up()
            verdict = replace(
                verdict.raised(raised, f"{verdict.reason}; alvos não resolvidos (sobe uma faixa)", "unresolved"),
                stage1_allow=False,
            )
        for target in plan.files:
            zone = zone_of(
                target,
                in_scope=self._scope.is_allowed(target),
                home=ctx.home,
                orion_home=ctx.orion_home or ctx.home / ".orion",
            )
            from orion.governance.bands import _band_for_zone

            band, blocked, rule = _band_for_zone(zone)
            if blocked:
                return replace(verdict, blocked=True, band=Band.NUCLEAR, reason=f"alvo protegido: {target}", rule=rule), None
            if band > max(verdict.band, Band.CLASSIFICADA):
                verdict = verdict.raised(band, f"alvo em zona {zone.value}: {target}", rule)
        if plan.bytes > engine.action_cap:
            verdict = verdict.raised(Band.NUCLEAR, f"snapshot de {_human_bytes(plan.bytes)} acima do teto", "snapshot_over_cap")
            return verdict, None
        if plan.regenerable_bytes > engine.action_cap:
            verdict = verdict.raised(Band.PRESENCA, "apaga pastas regeneráveis grandes (recuperáveis, sem snapshot)", "regenerable_over_cap")
        return verdict, plan

    def _audit_band_denial(self, action: Action, level: ActionLevel, verdict: BandVerdict, reason: str) -> None:
        self._audit.log_denied(
            action_id=action.event_id,
            tool=action.tool,
            params=dict(action.params),
            level=level,
            reason=reason,
            decision_source=f"band:{verdict.band.label}",
        )

    def _assert_not_blocked(self, action: Action, level: ActionLevel, verdict: BandVerdict) -> None:
        """Blocklist e segredos: negados em qualquer modo, por qualquer regra ou hook."""
        if not verdict.blocked:
            return
        self._audit.log_denied(
            action_id=action.event_id,
            tool=action.tool,
            params=dict(action.params),
            level=level,
            reason=verdict.rule,
            decision_source="band:blocklist",
        )
        raise ActionDenied(
            action.event_id,
            action.tool,
            f"blocked ({verdict.reason}). This never runs in any mode; do not retry or work around it.",
        )

    async def _defer(self, action: Action, level: ActionLevel, verdict: BandVerdict) -> None:
        """Sem humano: Presença/Nuclear viram pendência na Inbox (nunca execução)."""
        sink = self._deferral
        pending = PendingAction(
            action_id=action.event_id,
            tool=action.tool,
            params=dict(action.params),
            band=verdict.band,
            reason=verdict.reason,
            agent_id=self._agent_id,
        )
        pending_id = ""
        if sink is not None:
            try:
                outcome = sink(pending)
                if inspect.isawaitable(outcome):
                    outcome = await outcome
                pending_id = str(outcome or "")
            except Exception:  # noqa: BLE001 - Inbox indisponível vira negação comum
                logger.exception("PEP: falha ao registrar pendência na Inbox")
                sink = None
        if sink is None:
            self._audit_band_denial(action, level, verdict, f"escalation_no_human:{verdict.reason}")
            raise ActionDenied(
                action.event_id,
                action.tool,
                f"requires the Senhor's presence ({verdict.band.label}: {verdict.reason}) but no human is available",
            )
        self._audit_band_denial(action, level, verdict, f"deferred_inbox:{pending_id or '-'}")
        raise ActionDeferred(
            action.event_id,
            action.tool,
            f"deferred to the Senhor's Inbox ({verdict.band.label}: {verdict.reason}). It did NOT run; "
            "continue without this step and mention it in your report.",
            pending_id,
        )

    async def _presence(
        self, action: Action, level: ActionLevel, verdict: BandVerdict, escalations: list[Escalation]
    ) -> tuple[bool, str]:
        """Faixa Presença: grant do plano, pai (subagent), Inbox (sem humano) ou o Senhor."""
        grant = self.grants.match(action.tool, dict(action.params), verdict.band)
        if grant is not None:
            return True, f"grant:{grant.id}"
        if self._ceiling is not None:
            self._audit_band_denial(action, level, verdict, f"presence_to_parent:{verdict.reason}")
            raise ActionDenied(
                action.event_id,
                action.tool,
                f"needs the Senhor's presence ({verdict.reason}); a subagent cannot ask. Stop and report "
                "this exact step back to the parent agent, which can ask the Senhor.",
            )
        if not self._interactive:
            await self._defer(action, level, verdict)
        extra = [Escalation("presence", f"faixa presença: {verdict.reason}")]
        approved = await self._escalate(action, level, [*escalations, *extra])
        return approved, "user_escalation"

    async def _classified(
        self,
        action: Action,
        level: ActionLevel,
        verdict: BandVerdict,
        match: RuleMatch | None,
        escalations: list[Escalation],
    ) -> tuple[bool, str]:
        """Faixa Classificada no modo ``auto``: regra allow, estágio 1, estágio 2, o Senhor.

        Regra ``allow`` nunca libera ``sudo`` (invariante do v0.5.0); o classificador pode.
        Aprovação do Senhor numa escalada só do classificador conta como aprovação comum
        (``user``): o ledger aprende e o "sempre" grava regra.
        """
        if match is not None and match.effect == "allow" and not verdict.sudo:
            return True, "rule"
        request = ClassifierRequest(
            tool=action.tool,
            params=dict(action.params),
            verdict=verdict,
            user_messages=self.user_messages(),
            contaminated=self.contaminated,
        )
        try:
            result: ClassifierVerdict = await self.classifier.classify(request)
        except Exception as exc:  # noqa: BLE001 - classificador falho = escalate
            logger.warning("PEP: classificador falhou: %s", exc)
            result = ClassifierVerdict(Decision.ESCALATE, verdict.band, "classificador falhou", "none")
        source = f"classifier:{result.stage}"
        if result.decision == Decision.ALLOW:
            return True, source
        if result.band >= Band.PRESENCA:
            raised = verdict.raised(result.band, result.reason, f"classifier:{result.stage}")
            return await self._presence(action, level, raised, escalations)
        root = self._root()
        if result.decision == Decision.DENY:
            root._denials_consecutive += 1
            root._denials_total += 1
            too_many = (
                root._denials_consecutive >= MAX_CONSECUTIVE_DENIALS
                or root._denials_total >= MAX_SESSION_DENIALS
            )
            if not (too_many and self._interactive):
                self._rejection_reasons[action.event_id] = (
                    f"the risk classifier denied this ({result.reason}). This is not the Senhor's "
                    "decision; explain the goal and propose a safer alternative, or ask the Senhor."
                )
                return False, source
            root._denials_consecutive = 0
            reason = f"o classificador negou {MAX_CONSECUTIVE_DENIALS}+ vezes: {result.reason}"
            approved = await self._escalate(action, level, [*escalations, Escalation("classifier", reason)])
            return approved, "user" if not escalations else "user_escalation"
        reason = f"classificador: {result.reason}"
        approved = await self._escalate(action, level, [*escalations, Escalation("classifier", reason)])
        return approved, "user" if not escalations else "user_escalation"

    def _take_snapshot(self, action: Action, verdict: BandVerdict, plan: SnapshotPlan | None) -> Snapshot | None:
        edited = self._edited_params.get(action.event_id)
        if edited is not None:
            verdict, plan = self._band(action.model_copy(update={"params": edited}))
        engine = self.reversibility
        if plan is None or engine is None or plan.empty or verdict.band >= Band.NUCLEAR:
            return None
        command = str((edited or action.params).get("command", "") or (edited or action.params).get("path", ""))
        try:
            snap = engine.snapshot(plan, command=command or action.tool, session_id=self._root().session_id)
        except SnapshotError as exc:
            self._audit_band_denial(action, tool_action_level(action.tool), verdict, f"snapshot_failed:{exc}")
            raise ActionDenied(
                action.event_id,
                action.tool,
                f"could not snapshot the targets before running ({exc}); the action would not be "
                "reversible, so it was not run.",
            ) from exc
        if snap is not None:
            self._snapshots[action.event_id] = snap
        return snap

    async def evaluate(self, action: Action) -> bool:
        """Gate the given Action through the policy.

        Evaluation order:
          1. Safe Holding check (circuit breaker): hard block of mutations.
          2. Protected state, blocklist and secrets: denied in every mode.
          3. Band ``NUCLEAR``: verified presence (polkit/PAM); no human = Inbox.
          4. Declarative rules: a matching ``deny`` blocks.
          5. Read-only (plan mode): anything that mutates is refused.
          6. Pure reads (Livre, no mutation) pass in every mode.
          7. Mode: ``ask`` asks; ``full`` approves; ``auto`` decides by band (Livre passes,
             Classificada goes to the classifier, Presença asks or uses a plan grant).
          8. Snapshot of deletions/overwrites before returning True.

        Returns:
            True  if the action is approved and should proceed.
            False if the user, the classifier or plan mode refused it.

        Raises:
            ActionDenied  if the action is structurally blocked; ``ActionDeferred`` when it became
                          a pending item in the Senhor's Inbox.
        """
        level = self._effective_level(action)
        params = dict(action.params)

        self._assert_safe_holding(action, level)
        self._assert_not_protected_state(action, level)
        verdict, plan = self._band(action)
        self._assert_not_blocked(action, level, verdict)
        nuclear = await self._assert_nuclear_safe(action, level, verdict)

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

        mutating = level >= ActionLevel.LEVEL_2 and (verdict.mutates or verdict.band >= Band.CLASSIFICADA)
        if self.read_only and mutating:
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

        # Leitura pura passa sem pergunta, salvo no modo ``ask`` (que pergunta tudo acima de LEVEL_1).
        free_read = not mutating and not escalations and (self.mode != AutonomyMode.SUPERVISED or self.read_only)
        livre = verdict.band == Band.LIVRE
        if not forced_ask and livre and (level <= ActionLevel.LEVEL_1 or free_read):
            if level >= ActionLevel.LEVEL_1:
                self._audit.log(
                    action_id=action.event_id,
                    tool=action.tool,
                    params=params,
                    level=level,
                    user_authorized=False,
                    result_status="success",
                    decision_source="band:livre" if level > ActionLevel.LEVEL_1 else "mode",
                )
            self._note_hosts(action, verdict)
            return True

        mode = self.mode
        if nuclear is not None and not forced_ask and (not escalations or mode != AutonomyMode.SUPERVISED):
            # A presença verificada (polkit/PAM) já é o consentimento do Senhor para este ato:
            # perguntar "y/n" de novo seria ritual vazio (ADR-048).
            approved, source = True, "user"
        elif forced_ask:
            approved = await self._ask_user(action, level)
            source = "user"
        elif mode == AutonomyMode.SUPERVISED:
            if escalations:
                approved = await self._escalate(action, level, escalations)
                source = "user_escalation"
            else:
                approved, source = await self._gate(action, level, match)
        elif mode == AutonomyMode.FULLY_AUTO:
            confined = [e for e in escalations if e.kind == "outside_workspace" and self._cwd_confined]
            if confined:
                approved = await self._escalate(action, level, confined)
                source = "user_escalation"
            else:
                approved, source = True, "mode"
        else:
            approved, source = await self._decide_auto(action, level, verdict, match, escalations)

        if not approved:
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=params,
                level=level,
                reason="classifier_denied" if source.startswith("classifier") else "user_rejected",
                decision_source=source,
            )
            return False

        root = self._root()
        root._denials_consecutive = 0
        snap = self._take_snapshot(action, verdict, plan)
        self._approval_sources[action.event_id] = source
        if nuclear is not None:
            source = f"nuclear_stepup:{nuclear}+{source}"
        if snap is not None:
            source = f"{source}+snapshot:{snap.id}"
        self._note_hosts(action, verdict)
        self._audit.log(
            action_id=action.event_id,
            tool=action.tool,
            params=params,
            level=level,
            user_authorized=(source.startswith("user") or nuclear is not None),
            result_status="pending",
            decision_source=source,
        )
        return True

    async def _decide_auto(
        self,
        action: Action,
        level: ActionLevel,
        verdict: BandVerdict,
        match: RuleMatch | None,
        escalations: list[Escalation],
    ) -> tuple[bool, str]:
        """Modo ``auto`` (ADR-046): a faixa decide; sudo e "fora do escopo" vão ao classificador."""
        confined = [e for e in escalations if e.kind == "outside_workspace" and self._cwd_confined]
        if confined:
            return await self._escalate(action, level, confined), "user_escalation"
        sensitive = [e for e in escalations if e.kind == "sensitive_path"]
        band = verdict.band
        if sensitive and band < Band.PRESENCA:
            verdict = verdict.raised(Band.PRESENCA, sensitive[0].reason, "zone:sensitive")
            band = verdict.band
        if band == Band.LIVRE:
            return True, "band:livre"
        if band >= Band.PRESENCA:
            return await self._presence(action, level, verdict, sensitive)
        others = [e for e in escalations if e.kind in ("outside_workspace", "sudo")]
        return await self._classified(action, level, verdict, match, others)

    def _note_hosts(self, action: Action, verdict: BandVerdict) -> None:
        if verdict.outbound_hosts:
            self._action_hosts[action.event_id] = verdict.outbound_hosts

    def _assert_not_protected_state(self, action: Action, level: ActionLevel) -> None:
        """Escritas do agente em arquivos de governança de ``~/.orion`` são sempre negadas.

        Leituras de segredos (``.env``, chaves, ``secrets/``) também.
        """
        if action.tool in _READ_TOOLS:
            raw = str(action.params.get("path", ""))
            if raw and is_secret_path(raw):
                self._audit.log_denied(
                    action_id=action.event_id,
                    tool=action.tool,
                    params=dict(action.params),
                    level=level,
                    reason="protected_secret",
                    decision_source="mode",
                )
                raise ActionDenied(
                    action.event_id,
                    action.tool,
                    f"'{raw}' contém segredos do ORION; o agente não os lê.",
                )
            return
        if action.tool not in _WRITE_TOOLS:
            return
        raw = str(action.params.get("path", ""))
        if not raw or not is_protected_state_path(raw):
            return
        self._audit.log_denied(
            action_id=action.event_id,
            tool=action.tool,
            params=dict(action.params),
            level=level,
            reason="protected_governance_file",
            decision_source="mode",
        )
        raise ActionDenied(
            action.event_id,
            action.tool,
            f"'{raw}' é estado de governança do ORION; o agente não o altera. "
            "Peça ao Senhor para editar o arquivo manualmente.",
        )

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
        """Close the "pending" audit record with the execution outcome.

        Também alimenta a sessão contaminada (ADR-049): hosts contatados antes de qualquer
        conteúdo externo viram conhecidos; o resultado de web/MCP contamina a sessão.
        """
        hosts = self._action_hosts.pop(action_id, ())
        if success:
            root = self._root()
            if not root._contaminated:
                root._known_hosts.update(h for h in hosts if h and h != "?")
            if is_external_content_tool(tool):
                root._contaminated = True
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

        Called after a run_command completes. Only what the Senhor approved (or a ledger hit
        refreshing itself) is learned; nuclear, compound and destructive commands never are.

        Args:
            action: The Action that was executed successfully.
            exit_code: Exit code of the command (0 = success).
        """
        source = self._approval_sources.pop(action.event_id, "")
        if self._trust_ledger is None or action.tool != "run_command" or exit_code != 0:
            return
        if source not in ("user", "ledger", "classifier:ledger"):
            return

        cmd = str(action.params.get("command", ""))
        if not cmd or not CommandCanonicalizer.is_trustable(cmd):
            return

        # Never record nuclear commands in the trust ledger
        if self._blast_classifier.is_nuclear(cmd):
            return

        try:
            self._trust_ledger.record_success(cmd, exit_code=exit_code)
        except Exception:  # noqa: BLE001 - ledger indisponível nunca derruba a tool
            logger.warning("PEP: trust ledger indisponível; comando não aprendido.", exc_info=True)

    def forget_approval(self, action_id: str) -> None:
        """Descarta a origem da aprovação de uma ação que não terminou bem."""
        self._approval_sources.pop(action_id, None)

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

    async def _assert_nuclear_safe(
        self, action: Action, level: ActionLevel, verdict: BandVerdict | None = None
    ) -> str | None:
        """Faixa Nuclear: presença verificada do Senhor em TODOS os modos (ADR-046/048).

        Vale para qualquer tool (comando, escrita em ``~/.ssh`` ou ``/etc``, tool sem faixa). Sem
        humano: num subagent é negado; na sessão sem terminal vira pendência na Inbox.

        Raises:
            ActionDenied: If nuclear authentication was denied or no human is available.
        """
        if verdict is None:
            verdict, _plan = self._band(action)
        if verdict.blocked or verdict.band < Band.NUCLEAR:
            return None
        cmd = str(action.params.get("command", "") or "")
        if not cmd:
            subject = action.params.get("path") or action.params.get("url") or ""
            cmd = f"{action.tool} {subject}".strip()

        if not self._interactive:
            if self._ceiling is None and self._deferral is not None:
                await self._defer(action, level, verdict)
            # Sem humano para o desafio do SO: nuclear nunca é contornado, é negado.
            self._audit.log_denied(
                action_id=action.event_id,
                tool=action.tool,
                params=dict(action.params),
                level=level,
                reason="nuclear_no_human",
                decision_source="band:nuclear",
            )
            raise ActionDenied(
                action.event_id,
                action.tool,
                "nuclear operation requires the Senhor's OS authentication but no human is "
                f"available ({verdict.reason}). Command: {cmd[:80]}",
            )

        logger.warning("PEP: faixa NUCLEAR (%s) — '%s'. Desafio do SO.", verdict.rule, cmd[:80])
        try:
            result = await self._nuclear_gate.challenge_async(cmd, required=True)
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
                reason=f"nuclear_stepup:failed:{result.method_used}",
                decision_source="band:nuclear",
            )
            raise ActionDenied(
                action.event_id,
                action.tool,
                f"Nuclear operation denied ({verdict.reason}). Authentication cancelled or failed "
                f"(method: {result.method_used}). Command: {cmd[:80]}",
            )

        logger.warning(
            "PEP: Nuclear AUTHORIZED by user (method=%s, duration=%.1fs): '%s'",
            result.method_used,
            result.duration_seconds,
            cmd[:80],
        )
        return str(result.method_used)

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
            if path and action.tool in _WRITE_TOOLS and is_sensitive_path(path):
                found.append(
                    Escalation("sensitive_path", f"altera arquivo sensível do Senhor: {path}")
                )
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
        self._pending_kinds[action.event_id] = frozenset(e.kind for e in escalations)
        try:
            approved = await self._ask_user(action, level)
        finally:
            self._pending_escalations.pop(action.event_id, None)
            self._pending_kinds.pop(action.event_id, None)
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
        if (
            self._trust_ledger
            and cmd
            and mode != AutonomyMode.SUPERVISED
            and CommandCanonicalizer.is_trustable(cmd)
        ):
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
        edited_verdict, _plan = self._band(edited)
        self._assert_not_blocked(edited, level, edited_verdict)
        original_verdict, _ = self._band(action)
        if original_verdict.band < Band.NUCLEAR:
            await self._assert_nuclear_safe(edited, level, edited_verdict)
        known = {e.kind for e in self._escalations(action, level)}
        fresh = [e for e in self._escalations(edited, level) if e.kind not in known]
        if fresh and not await self._escalate(edited, level, fresh):
            return False
        self._edited_params[action.event_id] = decision
        return True


_HOST_RE = re.compile(r"(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?=[/:\s?#]|$)", re.IGNORECASE)


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.1f} {unit}".replace(".", ",")
        value /= 1024
    return f"{size} B"  # pragma: no cover
