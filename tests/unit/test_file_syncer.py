"""
Tests — MemoryFileSyncer (Sprint 3 & 4, v0.2.0)

Validates:
  - Writing facts to MEMORY.md with category grouping and status badges.
  - 200-line ceiling enforcement and pruning.
  - Reading MEMORY.md content and line counting.
  - Graceful handling of missing files.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from orion.memory.file_syncer import MemoryFileSyncer, _MAX_LINES
from orion.memory.models import FactCategory, FactEntry, FactStatus


def _create_fact(
    key: str,
    value: str = "val",
    category: FactCategory = FactCategory.CODING_STANDARD,
    status: FactStatus = FactStatus.CONFIRMED,
    confidence: float = 0.9,
    source: str = "user",
) -> FactEntry:
    return FactEntry(
        key=key,
        value=value,
        category=category,
        status=status,
        confidence=confidence,
        source=source,
    )


class TestMemoryFileSyncer:
    def test_write_and_read_facts(self, tmp_path):
        syncer = MemoryFileSyncer(memory_dir=tmp_path / "memory")
        facts = [
            _create_fact("python_version", "3.11", FactCategory.INFRASTRUCTURE, FactStatus.CONFIRMED),
            _create_fact("code_style", "PEP8", FactCategory.CODING_STANDARD, FactStatus.INFERRED),
            _create_fact("user_alias", "Chief", FactCategory.USER_PREFERENCE, FactStatus.CONFIRMED),
            _create_fact("architecture", "Clean", FactCategory.PROJECT_ARCHITECTURE, FactStatus.CONFIRMED),
        ]

        target_file = syncer.write(facts)
        assert target_file.is_file()

        content = syncer.read()
        assert content is not None
        assert "O.R.I.O.N — Memory Ledger" in content
        assert "python_version" in content
        assert "code_style" in content
        assert "user_alias" in content
        assert "architecture" in content

        lines = syncer.line_count()
        assert lines > 0
        assert lines <= _MAX_LINES

    def test_read_missing_file_returns_none(self, tmp_path):
        syncer = MemoryFileSyncer(memory_dir=tmp_path / "nonexistent")
        assert syncer.read() is None
        assert syncer.line_count() == 0

    def test_max_lines_pruning(self, tmp_path):
        """When rendered lines exceed 200, output is truncated to 200 lines."""
        syncer = MemoryFileSyncer(memory_dir=tmp_path / "memory")

        # Create many facts to exceed 200 lines (each fact generates 2-3 lines)
        facts = [
            _create_fact(f"fact_key_{i}", f"value_{i}", FactCategory.INFRASTRUCTURE, FactStatus.INFERRED)
            for i in range(120)
        ]

        syncer.write(facts)
        lines = syncer.line_count()

        # Should be strictly capped around 200 lines
        assert lines <= _MAX_LINES + 2
        content = syncer.read()
        assert content is not None
        assert "Truncated" in content
