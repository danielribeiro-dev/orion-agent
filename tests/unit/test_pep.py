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

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

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
