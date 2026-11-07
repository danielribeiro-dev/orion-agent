"""
O.R.I.O.N — Checkpoint Synthesis (Sprint 4, v0.2.0)

Generates concise, 3 to 5 line executive synthesis records for merged branches
or major operational milestones to be back-propagated into the Main Timeline.

ADR-011: Context Branches & Checkpoint Synthesis
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

logger = logging.getLogger(__name__)


def synthesize_checkpoint(
    branch_name: str,
    actions_summary: Sequence[str],
    modified_files: Sequence[str],
    outcome: str = "Merged successfully",
) -> str:
    """
    Synthesize an executive checkpoint of 3 to 5 lines.

    Lines:
      1. Header with branch name and status
      2. Summary of key accomplishments (1-2 lines)
      3. Modified artifacts / files
      4. Outcome verification / test status
    """
    files_str = ", ".join(modified_files[:5]) if modified_files else "none"
    if len(modified_files) > 5:
        files_str += f" (+{len(modified_files) - 5} more)"

    milestones_str = (
        "; ".join(actions_summary[:3])
        if actions_summary
        else "Completed planned branch tasks"
    )

    lines = [
        f"📍 [CHECKPOINT: branch '{branch_name}']",
        f"  • Accomplished : {milestones_str}",
        f"  • Files touched: {files_str}",
        f"  • Outcome      : {outcome}",
    ]

    result = "\n".join(lines)
    logger.debug("Synthesized checkpoint for '%s':\n%s", branch_name, result)
    return result
