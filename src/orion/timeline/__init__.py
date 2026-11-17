"""
O.R.I.O.N — Timeline & Session Management (Sprint 4, v0.2.0)

Timeline enhancements:
  - ContextCompactor: auto-compaction and /compact command
  - CheckpointSynthesis: 3-5 line executive summary generation

ADR-011: Context Branches & Dynamic Compactor. Desde a v0.5.3 (ADR-051) as branches são
threads persistidas em ``orion.sessions`` (``/branch``, ``/merge``, ``session_branch``).
"""

from orion.timeline.checkpoint_synthesis import synthesize_checkpoint
from orion.timeline.compactor import ContextCompactor, TurnData

__all__ = [
    "ContextCompactor",
    "TurnData",
    "synthesize_checkpoint",
]
