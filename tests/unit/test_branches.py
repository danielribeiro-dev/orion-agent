"""
Tests — Checkpoint Synthesis (Sprint 4, v0.2.0)

As branches em RAM deram lugar a threads persistidas na v0.5.3 (ADR-051); o comportamento de
``/branch`` e ``/merge`` é coberto em ``test_session_branch.py``.
"""

from __future__ import annotations

from orion.timeline.checkpoint_synthesis import synthesize_checkpoint

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
