"""
O.R.I.O.N — Governance Permissions
Defines ActionLevel risk tiers and WorkspaceScope path guards.

Reference: docs/architecture/GOVERNANCE_PEP.md
"""

from __future__ import annotations

import os
from enum import IntEnum
from pathlib import Path


class ActionLevel(IntEnum):
    """Static risk classification for every registered tool.

    LEVEL_0  — Informative / in-memory: no side-effects.
               Executes immediately without logging.
    LEVEL_1  — Passive read: read_file, search_files, status queries.
               Executes with audit log entry.
    LEVEL_2  — Project mutation: write_file, edit_file inside workspace.
               Requires explicit [Y/n] confirmation in Supervised Mode.
    LEVEL_3  — Critical system: run_command (arbitrary shell), file deletion,
               network changes.
               Requires explicit confirmation with full command display.
    """

    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 2
    LEVEL_3 = 3


# Static mapping: tool name → default ActionLevel
TOOL_LEVELS: dict[str, ActionLevel] = {
    "read_file": ActionLevel.LEVEL_1,
    "search_files": ActionLevel.LEVEL_1,
    "write_file": ActionLevel.LEVEL_2,
    "edit_file": ActionLevel.LEVEL_2,
    "run_command": ActionLevel.LEVEL_3,
}


def tool_action_level(tool_name: str) -> ActionLevel:
    """Return the ActionLevel for a given tool name.

    Unknown tools default to LEVEL_3 (safest assumption).
    """
    return TOOL_LEVELS.get(tool_name, ActionLevel.LEVEL_3)


class WorkspaceScope:
    """Restricts filesystem operations to a set of authorised root paths.

    Any path that resolves outside every authorised root is rejected.
    The check is canonical-path-based to prevent symlink traversal.
    """

    def __init__(self, roots: list[Path] | None = None) -> None:
        if roots is None:
            roots = [Path.cwd()]
        self._roots: list[Path] = [r.resolve() for r in roots]

    @classmethod
    def default(cls) -> "WorkspaceScope":
        """Return a scope anchored at the current working directory."""
        return cls([Path.cwd()])

    def is_allowed(self, path: Path | str) -> bool:
        """Return True if *path* is inside at least one authorised root."""
        target = Path(path).resolve()
        return any(self._is_inside(target, root) for root in self._roots)

    @staticmethod
    def _is_inside(target: Path, root: Path) -> bool:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            return False

    def assert_allowed(self, path: Path | str) -> None:
        """Raise PermissionError if *path* is outside every authorised root."""
        if not self.is_allowed(path):
            raise PermissionError(
                f"Path '{path}' is outside the authorised workspace. "
                f"Allowed roots: {[str(r) for r in self._roots]}"
            )

    def add_root(self, path: Path | str) -> None:
        """Extend the scope with an additional authorised root."""
        self._roots.append(Path(path).resolve())

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def __repr__(self) -> str:  # pragma: no cover
        return f"WorkspaceScope(roots={[str(r) for r in self._roots]})"
