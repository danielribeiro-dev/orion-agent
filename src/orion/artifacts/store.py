"""
O.R.I.O.N — ArtifactStore
Dual-storage manager: writes artifacts to global (~/.orion/brain/) and/or
local (.orion/artifacts/) paths, keeps an in-memory registry per session.
"""

from __future__ import annotations

import logging
from pathlib import Path

from orion.artifacts.models import Artifact, ArtifactMetadata, StorageScope
from orion.core.errors import ArtifactNotFoundError, ArtifactWriteError
from orion.config import PathsConfig

logger = logging.getLogger(__name__)


class ArtifactStore:
    """Manages creation, persistence and retrieval of ORION artifacts.

    Args:
        paths:      PathsConfig providing global_home and local_home roots.
        session_id: Session identifier used to namespace the global artifact dir.
    """

    def __init__(self, paths: PathsConfig, session_id: str) -> None:
        self._paths = paths
        self._session_id = session_id
        self._registry: dict[str, Artifact] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        *,
        filename: str,
        content: str,
        summary: str,
        session_id: str | None = None,
        user_facing: bool = True,
        request_feedback: bool = False,
        scope: StorageScope = StorageScope.BOTH,
    ) -> Artifact:
        """Create an artifact, persist it to disk and return the Artifact object.

        Args:
            filename:         Basename (e.g. "sprint_plan.md").
            content:          Raw markdown body.
            summary:          Multi-line human description.
            session_id:       Override session namespace (uses store's default if None).
            user_facing:      Surface to user in CLI.
            request_feedback: Show [Proceed] confirmation in CLI.
            scope:            Storage scope (GLOBAL / LOCAL / BOTH).

        Returns:
            The persisted Artifact with paths filled in.

        Raises:
            ArtifactWriteError: on filesystem errors.
        """
        meta = ArtifactMetadata(
            session_id=session_id or self._session_id,
            filename=filename,
            summary=summary,
            user_facing=user_facing,
            request_feedback=request_feedback,
            scope=scope,
        )
        artifact = Artifact(metadata=meta, content=content)
        artifact = self._persist(artifact)
        self._registry[artifact.artifact_id] = artifact
        logger.info("ArtifactStore: created artifact %s (%s)", filename, artifact.artifact_id)
        return artifact

    def get(self, artifact_id: str) -> Artifact:
        """Retrieve an artifact by its ID.

        Raises:
            ArtifactNotFoundError: if not found.
        """
        try:
            return self._registry[artifact_id]
        except KeyError:
            raise ArtifactNotFoundError(artifact_id)

    def list(self) -> list[Artifact]:
        """Return all artifacts registered in this session (newest first)."""
        return list(reversed(list(self._registry.values())))

    def list_user_facing(self) -> list[Artifact]:
        """Return only artifacts that should be surfaced in the CLI."""
        return [a for a in self.list() if a.metadata.user_facing]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, artifact: Artifact) -> Artifact:
        """Write artifact content to disk according to its scope.

        Returns a new (frozen) Artifact with global_path / local_path set.
        """
        scope = artifact.metadata.scope
        global_path: Path | None = None
        local_path: Path | None = None

        if scope in {StorageScope.GLOBAL, StorageScope.BOTH}:
            global_path = self._write_global(artifact)

        if scope in {StorageScope.LOCAL, StorageScope.BOTH}:
            local_path = self._write_local(artifact)

        # Rebuild with paths set (frozen model — must reconstruct)
        updated_meta = artifact.metadata.model_copy(
            update={"global_path": global_path, "local_path": local_path}
        )
        return artifact.model_copy(update={"metadata": updated_meta})

    def _write_global(self, artifact: Artifact) -> Path:
        dir_ = (
            self._paths.global_artifacts_dir
            / artifact.metadata.session_id
            / "artifacts"
        )
        return self._write_to(dir_, artifact)

    def _write_local(self, artifact: Artifact) -> Path:
        dir_ = self._paths.local_artifacts_dir
        return self._write_to(dir_, artifact)

    @staticmethod
    def _write_to(directory: Path, artifact: Artifact) -> Path:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / artifact.filename
            path.write_text(artifact.content, encoding="utf-8")
            logger.debug("ArtifactStore: wrote %s", path)
            return path
        except OSError as exc:
            raise ArtifactWriteError(
                f"Failed to write artifact {artifact.filename!r} to {directory}: {exc}"
            ) from exc
