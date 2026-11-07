"""
Tests for the PEP (PolicyEnforcementPoint) — Sprint 3.

Coverage:
  - ActionLevel classification via tool_action_level()
  - WorkspaceScope path guard
  - PEP.evaluate() → LEVEL_0 auto-approved (no audit)
  - PEP.evaluate() → LEVEL_1 auto-approved with audit entry
  - PEP.evaluate() → LEVEL_2 in SUPERVISED mode: confirm=True → approved
  - PEP.evaluate() → LEVEL_2 in SUPERVISED mode: confirm=False → denied
  - PEP.evaluate() → LEVEL_2 in WORKSPACE_AUTO mode: auto-approved
  - PEP.evaluate() → LEVEL_3 in WORKSPACE_AUTO mode: still gated
  - PEP.evaluate() → LEVEL_3 in FULLY_AUTO mode: auto-approved
  - PEP raises ActionDenied for sudo in non-FULLY_AUTO mode
  - PEP raises ActionDenied for path outside workspace (LEVEL_2)
  - AuditLogger writes append-only JSON-Lines records
  - AuditLogger.log_denied writes denial record
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion.core.events import Action, RiskLevel
from orion.governance.audit import AuditLogger
from orion.governance.pep import ActionDenied, AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import (
    ActionLevel,
    WorkspaceScope,
    tool_action_level,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_audit(tmp_path: Path) -> Path:
    """Return a temp path for audit log."""
    return tmp_path / "audit.log"


@pytest.fixture()
def audit(tmp_audit: Path) -> AuditLogger:
    return AuditLogger(log_path=tmp_audit)


@pytest.fixture()
def workspace(tmp_path: Path) -> WorkspaceScope:
    return WorkspaceScope(roots=[tmp_path])


def _pep(
    workspace: WorkspaceScope,
    audit: AuditLogger,
    mode: AutonomyMode = AutonomyMode.SUPERVISED,
    confirm: bool = True,
) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(
        scope=workspace,
        mode=mode,
        audit_logger=audit,
        confirm=lambda _: confirm,
    )


def _action(tool: str, params: dict | None = None) -> Action:
    return Action(tool=tool, params=params or {}, risk_level=RiskLevel.SAFE)


# ─────────────────────────────────────────────────────────────────────────────
# tool_action_level
# ─────────────────────────────────────────────────────────────────────────────


def test_tool_levels_known_tools() -> None:
    assert tool_action_level("read_file") == ActionLevel.LEVEL_1
    assert tool_action_level("search_files") == ActionLevel.LEVEL_1
    assert tool_action_level("write_file") == ActionLevel.LEVEL_2
    assert tool_action_level("edit_file") == ActionLevel.LEVEL_2
    assert tool_action_level("run_command") == ActionLevel.LEVEL_3


def test_tool_levels_unknown_tool_defaults_to_level3() -> None:
    assert tool_action_level("nonexistent_tool") == ActionLevel.LEVEL_3


# ─────────────────────────────────────────────────────────────────────────────
# WorkspaceScope
# ─────────────────────────────────────────────────────────────────────────────


def test_workspace_scope_allows_inside(tmp_path: Path) -> None:
    scope = WorkspaceScope(roots=[tmp_path])
    child = tmp_path / "src" / "main.py"
    assert scope.is_allowed(child)


def test_workspace_scope_denies_outside(tmp_path: Path) -> None:
    scope = WorkspaceScope(roots=[tmp_path])
    assert not scope.is_allowed(Path("/etc/passwd"))


def test_workspace_scope_assert_allowed_raises(tmp_path: Path) -> None:
    scope = WorkspaceScope(roots=[tmp_path])
    with pytest.raises(PermissionError, match="outside the authorised workspace"):
        scope.assert_allowed("/etc/shadow")


def test_workspace_scope_add_root(tmp_path: Path) -> None:
    other = tmp_path / "other"
    scope = WorkspaceScope(roots=[tmp_path])
    scope.add_root(other)
    assert scope.is_allowed(other / "file.txt")


# ─────────────────────────────────────────────────────────────────────────────
# PEP — LEVEL_0
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_level0_auto_approved_no_audit(
    workspace: WorkspaceScope, audit: AuditLogger, tmp_audit: Path
) -> None:
    pep = _pep(workspace, audit)
    # Create a fake LEVEL_0 action (not in tool registry → defaults to LEVEL_3,
    # so we test via mode FULLY_AUTO to avoid gating; or we create a direct
    # method call with a tool mapped to LEVEL_0 by patching TOOL_LEVELS)
    from orion.governance import permissions as perms_mod

    original = dict(perms_mod.TOOL_LEVELS)
    perms_mod.TOOL_LEVELS["fake_info"] = ActionLevel.LEVEL_0
    try:
        action = _action("fake_info")
        approved = await pep.evaluate(action)
        assert approved is True
        # No audit record for LEVEL_0
        assert not tmp_audit.exists() or tmp_audit.read_text() == ""
    finally:
        perms_mod.TOOL_LEVELS.clear()
        perms_mod.TOOL_LEVELS.update(original)


# ─────────────────────────────────────────────────────────────────────────────
# PEP — LEVEL_1
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_level1_auto_approved_with_audit(
    workspace: WorkspaceScope, audit: AuditLogger, tmp_audit: Path
) -> None:
    pep = _pep(workspace, audit)
    action = _action("read_file", {"path": "/tmp/x.txt"})
    approved = await pep.evaluate(action)
    assert approved is True
    # Audit record written
    records = [json.loads(l) for l in tmp_audit.read_text().splitlines() if l]
    assert len(records) == 1
    assert records[0]["tool"] == "read_file"
    assert records[0]["result_status"] == "success"
    assert records[0]["user_authorized"] is False


# ─────────────────────────────────────────────────────────────────────────────
# PEP — LEVEL_2 supervised
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_level2_supervised_confirm_true(
    tmp_path: Path, audit: AuditLogger
) -> None:
    workspace = WorkspaceScope(roots=[tmp_path])
    pep = _pep(workspace, audit, mode=AutonomyMode.SUPERVISED, confirm=True)
    action = _action("write_file", {"path": str(tmp_path / "out.txt"), "content": "x"})
    approved = await pep.evaluate(action)
    assert approved is True


@pytest.mark.asyncio
async def test_pep_level2_supervised_confirm_false(
    tmp_path: Path, audit: AuditLogger, tmp_audit: Path
) -> None:
    workspace = WorkspaceScope(roots=[tmp_path])
    pep = _pep(workspace, audit, mode=AutonomyMode.SUPERVISED, confirm=False)
    action = _action("write_file", {"path": str(tmp_path / "out.txt"), "content": "x"})
    approved = await pep.evaluate(action)
    assert approved is False
    # Denial audit record
    records = [json.loads(l) for l in tmp_audit.read_text().splitlines() if l]
    assert records[-1]["result_status"] == "denied"
    assert records[-1]["denial_reason"] == "user_rejected"


# ─────────────────────────────────────────────────────────────────────────────
# PEP — LEVEL_2 workspace_auto
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_level2_workspace_auto_approved(
    tmp_path: Path, audit: AuditLogger
) -> None:
    workspace = WorkspaceScope(roots=[tmp_path])
    pep = _pep(workspace, audit, mode=AutonomyMode.WORKSPACE_AUTO, confirm=False)
    action = _action("edit_file", {"path": str(tmp_path / "f.py"), "target": "x", "replacement": "y"})
    approved = await pep.evaluate(action)
    assert approved is True  # LEVEL_2 auto-approved in workspace_auto


@pytest.mark.asyncio
async def test_pep_level3_workspace_auto_still_gated(
    tmp_path: Path, audit: AuditLogger
) -> None:
    workspace = WorkspaceScope(roots=[tmp_path])
    pep = _pep(workspace, audit, mode=AutonomyMode.WORKSPACE_AUTO, confirm=False)
    action = _action("run_command", {"command": "ls"})
    approved = await pep.evaluate(action)
    assert approved is False  # LEVEL_3 still gated → user said no


# ─────────────────────────────────────────────────────────────────────────────
# PEP — FULLY_AUTO
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_fully_auto_level3_approved(
    workspace: WorkspaceScope, audit: AuditLogger
) -> None:
    pep = _pep(workspace, audit, mode=AutonomyMode.FULLY_AUTO)
    action = _action("run_command", {"command": "echo hello"})
    approved = await pep.evaluate(action)
    assert approved is True


# ─────────────────────────────────────────────────────────────────────────────
# PEP — sudo invariant
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_sudo_raises_action_denied_in_supervised(
    workspace: WorkspaceScope, audit: AuditLogger
) -> None:
    pep = _pep(workspace, audit, mode=AutonomyMode.SUPERVISED, confirm=True)
    action = _action("run_command", {"command": "sudo rm -rf /"})
    with pytest.raises(ActionDenied, match="sudo"):
        await pep.evaluate(action)


@pytest.mark.asyncio
async def test_pep_sudo_raises_action_denied_in_workspace_auto(
    workspace: WorkspaceScope, audit: AuditLogger
) -> None:
    pep = _pep(workspace, audit, mode=AutonomyMode.WORKSPACE_AUTO, confirm=True)
    action = _action("run_command", {"command": "sudo apt update"})
    with pytest.raises(ActionDenied, match="sudo"):
        await pep.evaluate(action)


# ─────────────────────────────────────────────────────────────────────────────
# PEP — path outside workspace
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_path_outside_workspace_denied(
    tmp_path: Path, audit: AuditLogger
) -> None:
    workspace = WorkspaceScope(roots=[tmp_path])
    pep = _pep(workspace, audit, mode=AutonomyMode.FULLY_AUTO)
    action = _action("write_file", {"path": "/etc/malicious.conf", "content": "x"})
    with pytest.raises(ActionDenied, match="outside the authorised workspace"):
        await pep.evaluate(action)


# ─────────────────────────────────────────────────────────────────────────────
# AuditLogger
# ─────────────────────────────────────────────────────────────────────────────


def test_audit_logger_creates_file_and_appends(tmp_audit: Path) -> None:
    logger = AuditLogger(log_path=tmp_audit)
    logger.log(
        action_id="abc-123",
        tool="read_file",
        params={"path": "/x"},
        level=1,
        user_authorized=False,
        result_status="success",
    )
    logger.log(
        action_id="def-456",
        tool="write_file",
        params={"path": "/y"},
        level=2,
        user_authorized=True,
        result_status="success",
    )
    lines = tmp_audit.read_text().splitlines()
    assert len(lines) == 2
    r1 = json.loads(lines[0])
    assert r1["action_id"] == "abc-123"
    assert r1["tool"] == "read_file"
    r2 = json.loads(lines[1])
    assert r2["action_id"] == "def-456"


def test_audit_logger_log_denied(tmp_audit: Path) -> None:
    logger = AuditLogger(log_path=tmp_audit)
    logger.log_denied(
        action_id="xyz-789",
        tool="run_command",
        params={"command": "rm -rf /"},
        level=3,
        reason="sudo_detected",
    )
    record = json.loads(tmp_audit.read_text().strip())
    assert record["result_status"] == "denied"
    assert record["denial_reason"] == "sudo_detected"
    assert record["user_authorized"] is False


def test_audit_logger_survives_non_serialisable_params(tmp_audit: Path) -> None:
    logger = AuditLogger(log_path=tmp_audit)
    logger.log(
        action_id="zzz",
        tool="run_command",
        params={"obj": object()},  # non-serialisable
        level=3,
        user_authorized=False,
        result_status="pending",
    )
    record = json.loads(tmp_audit.read_text().strip())
    assert "obj" in record["params"]  # repr() fallback


# ─────────────────────────────────────────────────────────────────────────────
# AutonomyMode switching
# ─────────────────────────────────────────────────────────────────────────────


def test_pep_set_mode(workspace: WorkspaceScope, audit: AuditLogger) -> None:
    pep = PolicyEnforcementPoint(scope=workspace, audit_logger=audit)
    assert pep.mode == AutonomyMode.SUPERVISED
    pep.set_mode(AutonomyMode.FULLY_AUTO)
    assert pep.mode == AutonomyMode.FULLY_AUTO


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 4: CircuitBreaker & SafeHolding Integration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_blocks_mutations_when_safe_holding_active(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """When a frontier model fails externally and safe holding triggers,
    PEP must block mutating actions (write_file, edit_file, run_command)."""
    from orion.gateway.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, FailureReason
    from orion.gateway.models import ComplexityTier

    workspace = WorkspaceScope(roots=[tmp_path])
    cb = CircuitBreaker(
        primary_model_id="anthropic/claude-sonnet-4-5",
        primary_model_tier=ComplexityTier.HEAVY,
        config=CircuitBreakerConfig(failure_threshold=1),
    )
    cb.record_failure(FailureReason.RATE_LIMIT)
    assert cb.is_mutation_blocked() is True

    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        mode=AutonomyMode.FULLY_AUTO,
        circuit_breaker=cb,
    )

    action_write = _action("write_file", {"path": str(tmp_path / "test.py"), "content": "x"})
    with pytest.raises(ActionDenied, match="SAFE HOLDING"):
        await pep.evaluate(action_write)


@pytest.mark.asyncio
async def test_pep_allows_read_operations_during_safe_holding(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """Read-only actions (read_file, search_files) must remain allowed
    even when SAFE_HOLDING is active, so the agent can inspect context."""
    from orion.gateway.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, FailureReason
    from orion.gateway.models import ComplexityTier

    workspace = WorkspaceScope(roots=[tmp_path])
    cb = CircuitBreaker(
        primary_model_id="anthropic/claude-sonnet-4-5",
        primary_model_tier=ComplexityTier.HEAVY,
        config=CircuitBreakerConfig(failure_threshold=1),
    )
    cb.record_failure(FailureReason.RATE_LIMIT)

    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        mode=AutonomyMode.FULLY_AUTO,
        circuit_breaker=cb,
    )

    action_read = _action("read_file", {"path": str(tmp_path / "test.py")})
    approved = await pep.evaluate(action_read)
    assert approved is True


@pytest.mark.asyncio
async def test_pep_allows_mutations_when_user_intentionally_uses_lite_model(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """CRITICAL SAFETY INVARIANT:
    If the user chose a lite model as their everyday driver (intentional_lite_mode=True),
    the system must NEVER block tools or think it's in SAFE_HOLDING.
    The user must have full tool access."""
    from orion.gateway.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, FailureReason
    from orion.gateway.models import ComplexityTier

    workspace = WorkspaceScope(roots=[tmp_path])
    cb = CircuitBreaker(
        primary_model_id="google/gemini-2.0-flash-lite",
        primary_model_tier=ComplexityTier.FAST,
        config=CircuitBreakerConfig(failure_threshold=1),
        intentional_lite_mode=True,  # User's intentional choice
    )
    cb.record_failure(FailureReason.RATE_LIMIT)

    assert cb.is_mutation_blocked() is False

    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        mode=AutonomyMode.FULLY_AUTO,
        circuit_breaker=cb,
    )

    action_write = _action("write_file", {"path": str(tmp_path / "test.py"), "content": "x"})
    approved = await pep.evaluate(action_write)
    assert approved is True


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 4: CommandTrustLedger Integration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_trust_ledger_auto_approves_known_safe_command(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """A known-safe command recorded in TrustLedger bypasses confirmation in WORKSPACE_AUTO."""
    from orion.governance.trust_ledger import CommandTrustLedger

    workspace = WorkspaceScope(roots=[tmp_path])
    trust_ledger = CommandTrustLedger(db_path=tmp_path / "test_trust.db")
    trust_ledger.record_success("npm test")

    # In WORKSPACE_AUTO, LEVEL_3 usually prompts; with trust_ledger hit, it should approve
    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        mode=AutonomyMode.WORKSPACE_AUTO,
        confirm=lambda _: False,  # would deny if prompted
        trust_ledger=trust_ledger,
    )

    action = _action("run_command", {"command": "npm test"})
    approved = await pep.evaluate(action)
    assert approved is True


@pytest.mark.asyncio
async def test_pep_trust_ledger_still_prompts_in_supervised(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """In SUPERVISED mode, TrustLedger does not bypass confirmation — user must confirm."""
    from orion.governance.trust_ledger import CommandTrustLedger

    workspace = WorkspaceScope(roots=[tmp_path])
    trust_ledger = CommandTrustLedger(db_path=tmp_path / "test_trust.db")
    trust_ledger.record_success("npm test")

    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        mode=AutonomyMode.SUPERVISED,
        confirm=lambda _: False,  # user rejects
        trust_ledger=trust_ledger,
    )

    action = _action("run_command", {"command": "npm test"})
    approved = await pep.evaluate(action)
    assert approved is False


def test_pep_record_action_success_skips_nuclear(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """Nuclear commands must NEVER be recorded into the trust ledger."""
    from orion.governance.trust_ledger import CommandTrustLedger

    workspace = WorkspaceScope(roots=[tmp_path])
    trust_ledger = CommandTrustLedger(db_path=tmp_path / "test_trust.db")
    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        trust_ledger=trust_ledger,
    )

    action_nuclear = _action("run_command", {"command": "rm -rf /tmp/test"})
    pep.record_action_success(action_nuclear, exit_code=0)

    # Must NOT be in the ledger
    assert trust_ledger.lookup("rm -rf /tmp/test").is_trusted is False


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 4: NuclearSafetyGate Integration
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pep_nuclear_gate_blocks_destructive_in_fully_auto(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """Even in FULLY_AUTO mode, a NUCLEAR_DESTRUCTIVE command triggers OS authentication.
    If auth is denied, PEP raises ActionDenied."""
    from unittest.mock import patch

    from orion.governance.nuclear import BlastRadius, NuclearChallengeResult, NuclearSafetyGate

    workspace = WorkspaceScope(roots=[tmp_path])
    nuclear_gate = NuclearSafetyGate()

    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        mode=AutonomyMode.FULLY_AUTO,
        nuclear_gate=nuclear_gate,
    )

    action = _action("run_command", {"command": "rm -rf /tmp/important_data"})

    with patch.object(nuclear_gate, "challenge") as mock_challenge:
        mock_challenge.return_value = NuclearChallengeResult(
            authorized=False,
            method_used="zenity",
            duration_seconds=1.0,
            command_pattern="rm -rf /tmp/important_data",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
        )
        with pytest.raises(ActionDenied, match="Nuclear operation denied"):
            await pep.evaluate(action)


@pytest.mark.asyncio
async def test_pep_nuclear_gate_allows_destructive_when_authenticated(
    tmp_path: Path, audit: AuditLogger
) -> None:
    """If user authenticates in OS challenge, nuclear command proceeds."""
    from unittest.mock import patch

    from orion.governance.nuclear import BlastRadius, NuclearChallengeResult, NuclearSafetyGate

    workspace = WorkspaceScope(roots=[tmp_path])
    nuclear_gate = NuclearSafetyGate()

    pep = PolicyEnforcementPoint(
        scope=workspace,
        audit_logger=audit,
        mode=AutonomyMode.FULLY_AUTO,
        nuclear_gate=nuclear_gate,
    )

    action = _action("run_command", {"command": "rm -rf /tmp/clean_cache"})

    with patch.object(nuclear_gate, "challenge") as mock_challenge:
        mock_challenge.return_value = NuclearChallengeResult(
            authorized=True,
            method_used="zenity",
            duration_seconds=1.2,
            command_pattern="rm -rf /tmp/clean_cache",
            blast_radius=BlastRadius.NUCLEAR_DESTRUCTIVE,
        )
        approved = await pep.evaluate(action)
        assert approved is True
