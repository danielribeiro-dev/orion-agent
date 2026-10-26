"""
O.R.I.O.N — Memory File Syncer (Sprint 3, v0.2.0)

Bidirectional synchronisation between the FactsStore (SQLite) and the
human-readable `.orion/memory/MEMORY.md` file.

Design constraints:
  - MEMORY.md hard ceiling: 200 lines (oldest facts pruned when exceeded).
  - Format: markdown with structured sections per FactCategory.
  - Sync is one-way at runtime (SQLite → MEMORY.md); the file serves as a
    transparent audit / review surface for the developer.

ADR-004: Triple Memory Architecture
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from orion.memory.models import FactCategory, FactEntry, FactStatus

logger = logging.getLogger(__name__)

_MAX_LINES = 200
_MEMORY_FILENAME = "MEMORY.md"

# Section headers per category (display order)
_CATEGORY_ORDER = [
    FactCategory.USER_PREFERENCE,
    FactCategory.PROJECT_ARCHITECTURE,
    FactCategory.CODING_STANDARD,
    FactCategory.INFRASTRUCTURE,
]

_CATEGORY_LABELS: dict[FactCategory, str] = {
    FactCategory.USER_PREFERENCE: "👤 User Preferences",
    FactCategory.PROJECT_ARCHITECTURE: "🏛️ Project Architecture",
    FactCategory.CODING_STANDARD: "📐 Coding Standards",
    FactCategory.INFRASTRUCTURE: "⚙️ Infrastructure",
}

_STATUS_BADGE: dict[FactStatus, str] = {
    FactStatus.CONFIRMED: "✅ CONFIRMED",
    FactStatus.INFERRED: "🔵 INFERRED",
    FactStatus.DEPRECATED: "🚫 DEPRECATED",
}


class MemoryFileSyncer:
    """
    Keeps `.orion/memory/MEMORY.md` in sync with the FactsStore.

    Usage::

        syncer = MemoryFileSyncer(memory_dir=Path(".orion/memory"))
        syncer.write(facts)          # Render all facts → MEMORY.md
        syncer.prune_to_limit()      # Trim to 200-line ceiling
    """

    def __init__(self, memory_dir: Path) -> None:
        self._memory_dir = memory_dir
        self._memory_path: Path = memory_dir / _MEMORY_FILENAME

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self, facts: list[FactEntry]) -> Path:
        """
        Render *facts* into MEMORY.md, respecting the 200-line ceiling.

        Facts are grouped by category and rendered with status badges.
        If the rendered document would exceed 200 lines, the oldest
        DEPRECATED and INFERRED facts are pruned first.

        Args:
            facts: All facts to render (typically from FactsStore.search()).

        Returns:
            The path to the written MEMORY.md file.
        """
        self._memory_dir.mkdir(parents=True, exist_ok=True)

        # Sort facts: CONFIRMED first, then INFERRED, then DEPRECATED;
        # within each status, most-recently updated first.
        priority_order = {
            FactStatus.CONFIRMED: 0,
            FactStatus.INFERRED: 1,
            FactStatus.DEPRECATED: 2,
        }
        sorted_facts = sorted(
            facts,
            key=lambda f: (priority_order[f.status], -(f.updated_at.timestamp() if isinstance(f.updated_at, datetime) else 0)),
        )

        lines = self._render_lines(sorted_facts)

        # Hard ceiling enforcement: prune from the end
        if len(lines) > _MAX_LINES:
            lines = lines[:_MAX_LINES]
            lines.append("")
            lines.append(f"*(Truncated to {_MAX_LINES} lines — older facts pruned)*")
            logger.warning(
                "MEMORY.md exceeded %d-line ceiling; content was pruned.", _MAX_LINES
            )

        self._memory_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("MEMORY.md written: %d lines at %s", len(lines), self._memory_path)
        return self._memory_path

    def read(self) -> Optional[str]:
        """
        Read the current MEMORY.md contents.

        Returns:
            File content string, or None if the file does not exist.
        """
        if not self._memory_path.exists():
            return None
        return self._memory_path.read_text(encoding="utf-8")

    def line_count(self) -> int:
        """Return the current number of lines in MEMORY.md (0 if absent)."""
        if not self._memory_path.exists():
            return 0
        return len(self._memory_path.read_text(encoding="utf-8").splitlines())

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _render_lines(self, facts: list[FactEntry]) -> list[str]:
        """Build the full MEMORY.md line list from sorted facts."""
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = [
            "# 🧠 O.R.I.O.N — Memory Ledger",
            "",
            f"> Last synced: {now_str}",
            "",
        ]

        # Group by category
        by_category: dict[FactCategory, list[FactEntry]] = {
            cat: [] for cat in _CATEGORY_ORDER
        }
        for fact in facts:
            by_category[fact.category].append(fact)

        for category in _CATEGORY_ORDER:
            category_facts = by_category[category]
            if not category_facts:
                continue

            label = _CATEGORY_LABELS[category]
            lines.append(f"## {label}")
            lines.append("")

            for fact in category_facts:
                badge = _STATUS_BADGE[fact.status]
                confidence_pct = int(fact.confidence * 100)
                lines.append(f"- **{fact.key}**: `{fact.value}`")
                lines.append(f"  - Status: {badge} · Confidence: {confidence_pct}% · Source: `{fact.source}`")

            lines.append("")

        return lines
