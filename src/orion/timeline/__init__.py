"""
O.R.I.O.N — Timeline & Session Management (Sprint 4, v0.2.0)

Timeline enhancements:
  - ContextCompactor: auto-compaction and /compact command
  - BranchManager: contextual workspace branching (/branch, /merge)
  - CheckpointSynthesis: 3-5 line executive summary generation

ADR-011: Context Branches & Dynamic Compactor
"""

from orion.timeline.branch_manager import BranchError, BranchManager, ContextBranch
from orion.timeline.checkpoint_synthesis import synthesize_checkpoint
from orion.timeline.compactor import ContextCompactor, TurnData

__all__ = [
    "ContextCompactor",
    "TurnData",
    "BranchManager",
    "ContextBranch",
    "BranchError",
    "synthesize_checkpoint",
]
