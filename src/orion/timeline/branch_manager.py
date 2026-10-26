"""
O.R.I.O.N — Context Branch Manager (Sprint 4, v0.2.0)

Context Branching & Checkpoint Archiving:
  - Contextual isolation via `/branch <slug>` to prevent debugging/exploratory
    noise from polluting the main operational timeline.
  - Synthesis on `/merge`: compresses branch turns into a 3-5 line executive checkpoint
    and commits it to the Main Timeline.
  - Detailed branch event logs are persisted to an archive directory
    (`~/.orion/timeline/archive/`).

ADR-011: Context Branches & Dynamic Compactor
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from orion.memory.timeline import TimelineManager
from orion.timeline.checkpoint_synthesis import synthesize_checkpoint

logger = logging.getLogger(__name__)

_DEFAULT_ARCHIVE_DIR = Path.home() / ".orion" / "timeline" / "archive"
_BRANCH_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class BranchError(Exception):
    """Raised when an invalid branch operation is attempted."""


class ContextBranch:
    """Represents an isolated contextual workspace branch."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.created_at = datetime.now(UTC)
        self.events: list[dict[str, Any]] = []
        self.actions_summary: list[str] = []
        self.modified_files: set[str] = set()

    def record(
        self,
        content: str,
        event_type: str = "action",
        source: str = "agent",
        files: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an event within this branch."""
        event_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event_type": event_type,
            "source": source,
            "content": content,
            "metadata": metadata or {},
        }
        self.events.append(event_entry)

        if files:
            self.modified_files.update(files)

        # Track meaningful action summaries
        if content and len(self.actions_summary) < 10:
            summary_snippet = content.splitlines()[0][:100]
            if summary_snippet not in self.actions_summary:
                self.actions_summary.append(summary_snippet)

    def to_archive_payload(self) -> dict[str, Any]:
        """Generate full JSON payload for archiving."""
        return {
            "branch_name": self.name,
            "created_at": self.created_at.isoformat(),
            "total_events": len(self.events),
            "modified_files": sorted(list(self.modified_files)),
            "actions_summary": self.actions_summary,
            "events": self.events,
        }


class BranchManager:
    """
    Coordinates context branch lifecycle, switching, merging, and archiving.
    """

    def __init__(
        self,
        timeline: Optional[TimelineManager] = None,
        archive_dir: Optional[Path] = None,
    ) -> None:
        self.timeline = timeline
        self.archive_dir = archive_dir or _DEFAULT_ARCHIVE_DIR
        self._active_branch_name: str = "main"
        self._branches: dict[str, ContextBranch] = {
            "main": ContextBranch("main")
        }

    @property
    def active_branch(self) -> str:
        """Name of the currently active context branch."""
        return self._active_branch_name

    def list_branches(self) -> list[str]:
        """Return names of all existing context branches."""
        return sorted(list(self._branches.keys()))

    def create_branch(self, name: str) -> str:
        """
        Create and switch to a new context branch.

        Validates branch name format (lowercase alphanumeric and hyphens).
        """
        name = name.strip()
        if not _BRANCH_NAME_PATTERN.match(name):
            raise BranchError(
                f"Invalid branch name '{name}'. Only lowercase letters, digits, "
                "and single hyphens are allowed (e.g. 'refactor-auth')."
            )

        if name not in self._branches:
            self._branches[name] = ContextBranch(name)
            logger.info("Created new context branch: '%s'", name)

        self._active_branch_name = name
        return name

    def switch_branch(self, name: str) -> None:
        """Switch to an existing context branch."""
        name = name.strip()
        if name not in self._branches:
            raise BranchError(f"Branch '{name}' does not exist.")
        self._active_branch_name = name
        logger.info("Switched to context branch: '%s'", name)

    def record_event(
        self,
        content: str,
        event_type: str = "action",
        source: str = "agent",
        files: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Record an event in the currently active branch."""
        branch = self._branches[self._active_branch_name]
        branch.record(
            content=content,
            event_type=event_type,
            source=source,
            files=files,
            metadata=metadata,
        )

    async def merge_branch(
        self,
        branch_name: Optional[str] = None,
        outcome: str = "Merged successfully",
    ) -> str:
        """
        Merge a context branch into the Main Timeline.

        1. Synthesizes a 3 to 5 line executive checkpoint.
        2. Publishes the checkpoint to Main Timeline (if timeline is configured).
        3. Archives detailed event logs to disk.
        4. Switches active branch back to 'main'.

        Returns:
            The synthesized checkpoint text.
        """
        target_name = branch_name or self._active_branch_name
        if target_name == "main":
            raise BranchError("Cannot merge 'main' into itself.")

        branch = self._branches.get(target_name)
        if not branch:
            raise BranchError(f"Branch '{target_name}' not found for merging.")

        # 1. Synthesize 3-5 line checkpoint
        checkpoint = synthesize_checkpoint(
            branch_name=target_name,
            actions_summary=branch.actions_summary,
            modified_files=sorted(list(branch.modified_files)),
            outcome=outcome,
        )

        # 2. Publish to Main Timeline
        if self.timeline is not None:
            await self.timeline.append_event(
                session_id="main",
                event_type="checkpoint",
                source="system",
                content=checkpoint,
                metadata={
                    "branch": target_name,
                    "event_count": len(branch.events),
                },
            )

        # 3. Archive detailed log to disk
        self._archive_branch(branch)

        # 4. Remove branch and switch to main
        del self._branches[target_name]
        self._active_branch_name = "main"

        logger.info("Branch '%s' merged into main and archived.", target_name)
        return checkpoint

    def _archive_branch(self, branch: ContextBranch) -> Path:
        """Save branch execution payload to JSON archive."""
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        archive_file = self.archive_dir / f"{branch.name}_{timestamp}.json"
        archive_file.write_text(
            json.dumps(branch.to_archive_payload(), indent=2), encoding="utf-8"
        )
        logger.debug("Archived branch '%s' to %s", branch.name, archive_file)
        return archive_file
