"""
Unit tests for src/orion/artifacts/models.py and store.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orion.artifacts.models import Artifact, ArtifactMetadata, StorageScope
from orion.artifacts.store import ArtifactStore
from orion.core.errors import ArtifactNotFoundError
from orion.config import PathsConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> ArtifactStore:
    """ArtifactStore backed by a tmp_path for full isolation."""
    paths = PathsConfig(
        global_home=tmp_path / "global_orion",
        local_home=tmp_path / "local_orion",
    )
    return ArtifactStore(paths=paths, session_id="test-session-123")


# ---------------------------------------------------------------------------
# ArtifactMetadata
# ---------------------------------------------------------------------------


class TestArtifactMetadata:
    def test_auto_generates_artifact_id(self) -> None:
        m = ArtifactMetadata(
            session_id="s1",
            filename="plan.md",
            summary="A plan",
        )
        assert m.artifact_id != ""
        assert len(m.artifact_id) == 36  # UUID format

    def test_default_flags(self) -> None:
        m = ArtifactMetadata(session_id="s1", filename="f.md", summary="s")
        assert m.user_facing is True
        assert m.request_feedback is False
        assert m.scope == StorageScope.BOTH

    def test_frozen(self) -> None:
        m = ArtifactMetadata(session_id="s1", filename="f.md", summary="s")
        with pytest.raises(Exception):
            m.filename = "other.md"  # type: ignore[misc]

    def test_paths_default_none(self) -> None:
        m = ArtifactMetadata(session_id="s1", filename="f.md", summary="s")
        assert m.global_path is None
        assert m.local_path is None


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


class TestArtifact:
    def test_artifact_id_delegates(self) -> None:
        m = ArtifactMetadata(session_id="s", filename="x.md", summary="x")
        a = Artifact(metadata=m, content="# Hello")
        assert a.artifact_id == m.artifact_id

    def test_filename_delegates(self) -> None:
        m = ArtifactMetadata(session_id="s", filename="report.md", summary="r")
        a = Artifact(metadata=m, content="body")
        assert a.filename == "report.md"


# ---------------------------------------------------------------------------
# ArtifactStore — creation and retrieval
# ---------------------------------------------------------------------------


class TestArtifactStoreCreate:
    def test_create_returns_artifact(self, store: ArtifactStore) -> None:
        art = store.create(
            filename="plan.md",
            content="# Sprint Plan\nDo things.",
            summary="Sprint 2 plan document.",
        )
        assert isinstance(art, Artifact)
        assert art.filename == "plan.md"
        assert "Sprint Plan" in art.content

    def test_create_assigns_session_id(self, store: ArtifactStore) -> None:
        art = store.create(filename="x.md", content="c", summary="s")
        assert art.metadata.session_id == "test-session-123"

    def test_create_with_custom_session_id(self, store: ArtifactStore) -> None:
        art = store.create(
            filename="x.md", content="c", summary="s", session_id="override"
        )
        assert art.metadata.session_id == "override"

    def test_created_artifact_in_registry(self, store: ArtifactStore) -> None:
        art = store.create(filename="a.md", content="c", summary="s")
        assert store.get(art.artifact_id) is art

    def test_get_nonexistent_raises(self, store: ArtifactStore) -> None:
        with pytest.raises(ArtifactNotFoundError):
            store.get("nonexistent-id")

    def test_list_returns_all(self, store: ArtifactStore) -> None:
        store.create(filename="a.md", content="a", summary="s")
        store.create(filename="b.md", content="b", summary="s")
        assert len(store.list()) == 2

    def test_list_newest_first(self, store: ArtifactStore) -> None:
        a1 = store.create(filename="first.md", content="1", summary="s")
        a2 = store.create(filename="second.md", content="2", summary="s")
        listed = store.list()
        assert listed[0].artifact_id == a2.artifact_id
        assert listed[1].artifact_id == a1.artifact_id

    def test_list_user_facing_filters(self, store: ArtifactStore) -> None:
        store.create(filename="visible.md", content="v", summary="s", user_facing=True)
        store.create(filename="hidden.md", content="h", summary="s", user_facing=False)
        visible = store.list_user_facing()
        assert len(visible) == 1
        assert visible[0].filename == "visible.md"


# ---------------------------------------------------------------------------
# ArtifactStore — filesystem
# ---------------------------------------------------------------------------


class TestArtifactStoreFilesystem:
    def test_global_file_created(self, store: ArtifactStore, tmp_path: Path) -> None:
        art = store.create(
            filename="output.md",
            content="# Output",
            summary="s",
            scope=StorageScope.GLOBAL,
        )
        assert art.metadata.global_path is not None
        assert art.metadata.global_path.exists()
        assert art.metadata.global_path.read_text() == "# Output"

    def test_local_file_created(self, store: ArtifactStore, tmp_path: Path) -> None:
        art = store.create(
            filename="local.md",
            content="local content",
            summary="s",
            scope=StorageScope.LOCAL,
        )
        assert art.metadata.local_path is not None
        assert art.metadata.local_path.exists()

    def test_both_files_created(self, store: ArtifactStore) -> None:
        art = store.create(
            filename="dual.md",
            content="dual",
            summary="s",
            scope=StorageScope.BOTH,
        )
        assert art.metadata.global_path is not None
        assert art.metadata.local_path is not None
        assert art.metadata.global_path.exists()
        assert art.metadata.local_path.exists()

    def test_global_path_not_set_for_local_scope(self, store: ArtifactStore) -> None:
        art = store.create(
            filename="l.md", content="c", summary="s", scope=StorageScope.LOCAL
        )
        assert art.metadata.global_path is None

    def test_local_path_not_set_for_global_scope(self, store: ArtifactStore) -> None:
        art = store.create(
            filename="g.md", content="c", summary="s", scope=StorageScope.GLOBAL
        )
        assert art.metadata.local_path is None

    def test_file_content_matches(self, store: ArtifactStore) -> None:
        content = "# Hello\n\nThis is **markdown**.\n"
        art = store.create(
            filename="content.md",
            content=content,
            summary="s",
            scope=StorageScope.GLOBAL,
        )
        assert art.metadata.global_path is not None
        assert art.metadata.global_path.read_text(encoding="utf-8") == content

    def test_directories_created_automatically(
        self, store: ArtifactStore, tmp_path: Path
    ) -> None:
        art = store.create(
            filename="nested.md", content="c", summary="s", scope=StorageScope.BOTH
        )
        assert art.metadata.global_path is not None
        assert art.metadata.global_path.parent.is_dir()
        assert art.metadata.local_path is not None
        assert art.metadata.local_path.parent.is_dir()


# ---------------------------------------------------------------------------
# request_feedback flag
# ---------------------------------------------------------------------------


class TestRequestFeedback:
    def test_request_feedback_stored_in_metadata(self, store: ArtifactStore) -> None:
        art = store.create(
            filename="plan.md",
            content="# Plan",
            summary="s",
            request_feedback=True,
        )
        assert art.metadata.request_feedback is True

    def test_request_feedback_default_false(self, store: ArtifactStore) -> None:
        art = store.create(filename="x.md", content="c", summary="s")
        assert art.metadata.request_feedback is False
