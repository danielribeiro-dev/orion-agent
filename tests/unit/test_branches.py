"""
Tests — Context Branch Manager & Checkpoint Synthesis (Sprint 4, v0.2.0)

Validates:
  - Teste 4 (spec): Branch merge generates a 3-5 line executive summary
    on Main Timeline and archives detailed event log to disk.
  - Branch creation, isolation, and switching.
  - Slug validation for branch names.
  - Error handling: merging 'main' into 'main', non-existent branch.
  - Checkpoint synthesis formatting.
"""

from __future__ import annotations

import json

import pytest

from orion.memory.timeline import TimelineManager
from orion.timeline.branch_manager import BranchError, BranchManager
from orion.timeline.checkpoint_synthesis import synthesize_checkpoint


@pytest.fixture
async def timeline_manager(tmp_path):
    tm = TimelineManager(db_path=tmp_path / "timeline.db")
    await tm.initialize()
    yield tm
    await tm.close()


# ---------------------------------------------------------------------------
# Test 4 (spec): Merge generates 3-5 lines on Main Timeline & archives to disk
# ---------------------------------------------------------------------------


class TestBranchMergeAndArchive:
    @pytest.mark.asyncio
    async def test_merge_synthesizes_checkpoint_and_archives(
        self, timeline_manager, tmp_path
    ):
        """
        Teste 4 (spec): Merge de branch gera resumo executivo de 3 a 5 linhas
        na Main Timeline e arquiva o log detalhado em disco.
        """
        archive_dir = tmp_path / "archive"
        manager = BranchManager(timeline=timeline_manager, archive_dir=archive_dir)

        # 1. Create branch
        manager.create_branch("refactor-auth")
        assert manager.active_branch == "refactor-auth"

        # 2. Record actions inside branch
        manager.record_event(
            content="Read src/orion/auth.py and analyzed HMAC logic",
            event_type="action",
            source="agent",
            files=["src/orion/auth.py"],
        )
        manager.record_event(
            content="Implemented Ed25519 signature verification",
            event_type="action",
            source="agent",
            files=["src/orion/crypto.py"],
        )
        manager.record_event(
            content="Ran pytest tests/unit/test_auth.py (12 passed)",
            event_type="action",
            source="agent",
            files=["tests/unit/test_auth.py"],
        )

        # 3. Merge branch
        checkpoint = await manager.merge_branch(
            "refactor-auth", outcome="12 unit tests passed"
        )

        # Verify executive synthesis is between 3 and 5 lines
        lines = [line for line in checkpoint.splitlines() if line.strip()]
        assert 3 <= len(lines) <= 5, (
            f"Expected checkpoint between 3 and 5 lines, got {len(lines)} lines:\n{checkpoint}"
        )
        assert "refactor-auth" in checkpoint
        assert "src/orion/auth.py" in checkpoint
        assert "12 unit tests passed" in checkpoint

        # Verify active branch returned to main
        assert manager.active_branch == "main"
        assert "refactor-auth" not in manager.list_branches()

        # Verify checkpoint event was committed to Main Timeline
        events = await timeline_manager.get_recent_history(limit=10)
        assert any(
            e.event_type == "checkpoint" and "refactor-auth" in e.content
            for e in events
        )

        # Verify detailed log archived to disk
        archive_files = list(archive_dir.glob("refactor-auth_*.json"))
        assert len(archive_files) == 1
        archived_data = json.loads(archive_files[0].read_text(encoding="utf-8"))
        assert archived_data["branch_name"] == "refactor-auth"
        assert archived_data["total_events"] == 3
        assert "src/orion/auth.py" in archived_data["modified_files"]


# ---------------------------------------------------------------------------
# Branch Management & Isolation
# ---------------------------------------------------------------------------


class TestBranchIsolation:
    def test_create_and_switch_branch(self, tmp_path):
        manager = BranchManager(archive_dir=tmp_path / "archive")
        assert manager.active_branch == "main"

        manager.create_branch("feature-metrics")
        assert manager.active_branch == "feature-metrics"
        assert "feature-metrics" in manager.list_branches()

        manager.switch_branch("main")
        assert manager.active_branch == "main"

    def test_invalid_branch_name_raises(self, tmp_path):
        manager = BranchManager(archive_dir=tmp_path / "archive")
        with pytest.raises(BranchError):
            manager.create_branch("Invalid_Branch_Name")

        with pytest.raises(BranchError):
            manager.create_branch("double--hyphen")

    def test_switch_nonexistent_branch_raises(self, tmp_path):
        manager = BranchManager(archive_dir=tmp_path / "archive")
        with pytest.raises(BranchError, match="does not exist"):
            manager.switch_branch("ghost-branch")

    @pytest.mark.asyncio
    async def test_merge_main_raises(self, tmp_path):
        manager = BranchManager(archive_dir=tmp_path / "archive")
        with pytest.raises(BranchError, match="Cannot merge 'main'"):
            await manager.merge_branch("main")


# ---------------------------------------------------------------------------
# Checkpoint Synthesis Formatting
# ---------------------------------------------------------------------------


class TestCheckpointSynthesis:
    def test_synthesize_checkpoint_format(self):
        summary = synthesize_checkpoint(
            branch_name="database-migration",
            actions_summary=["Added alembic migration", "Updated User table"],
            modified_files=["migrations/001.py", "src/models/user.py"],
            outcome="Schema migrated clean",
        )
        lines = summary.splitlines()
        assert len(lines) == 4
        assert "database-migration" in lines[0]
        assert "Accomplished" in lines[1]
        assert "Files touched" in lines[2]
        assert "Outcome" in lines[3]
