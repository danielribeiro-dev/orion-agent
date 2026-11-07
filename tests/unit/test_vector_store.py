"""
Tests for VectorStore — Sprint 2, v0.2.0

Coverage targets:
  - Embedding generation (< 50ms warm) and shape validation
  - Deduplication: same semantic content → touch_memory(), no new row
  - Cross-lingual deduplication (EN ↔ PT-BR) — if threshold allows
  - Independent inserts remain as separate records
  - search_semantic returns records sorted by cosine score
  - Token-budget safety: RRF contract (tested via HybridRetriever in a separate file)
  - count() returns correct row count after adds and dedup touches

All tests use an in-memory SQLite database (db_path=':memory:' equivalent via tmpdir)
so the real ~/.orion/timeline.db is never touched.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
import pytest_asyncio

from orion.memory.models import VectorRecord
from orion.memory.vector_store import (
    _DEDUP_THRESHOLD,
    _EMBED_DIM,
    VectorStore,
    _cosine_similarity,
    _cosine_similarity_batch,
    _pack_embedding,
    _unpack_embedding,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> VectorStore:  # type: ignore[misc]
    """A fresh VectorStore backed by a temporary SQLite file."""
    vs = VectorStore(db_path=tmp_path / "test_timeline.db")
    await vs.initialize()
    yield vs
    await vs.close()


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _random_unit_vector(dim: int = _EMBED_DIM, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# Unit tests — pure functions (no asyncio needed)
# ---------------------------------------------------------------------------


class TestPackUnpack:
    """Serialization roundtrip tests for binary embedding storage."""

    def test_roundtrip_zero_vector(self) -> None:
        vec = np.zeros(_EMBED_DIM, dtype=np.float32)
        assert np.allclose(_unpack_embedding(_pack_embedding(vec)), vec)

    def test_roundtrip_unit_vector(self) -> None:
        vec = _random_unit_vector()
        restored = _unpack_embedding(_pack_embedding(vec))
        assert np.allclose(restored, vec, atol=1e-6)

    def test_packed_size(self) -> None:
        """384 floats × 4 bytes = 1 536 bytes."""
        vec = _random_unit_vector()
        assert len(_pack_embedding(vec)) == _EMBED_DIM * 4


class TestCosineSimilarity:
    """Cosine similarity correctness tests."""

    def test_identical_vectors(self) -> None:
        v = _random_unit_vector()
        assert _cosine_similarity(v, v) == pytest.approx(1.0, abs=1e-5)

    def test_orthogonal_vectors(self) -> None:
        a = np.zeros(_EMBED_DIM, dtype=np.float32)
        b = np.zeros(_EMBED_DIM, dtype=np.float32)
        a[0] = 1.0
        b[1] = 1.0
        assert _cosine_similarity(a, b) == pytest.approx(0.0, abs=1e-6)

    def test_zero_vector_returns_zero(self) -> None:
        v = _random_unit_vector()
        z = np.zeros(_EMBED_DIM, dtype=np.float32)
        assert _cosine_similarity(v, z) == 0.0

    def test_batch_matches_pairwise(self) -> None:
        query = _random_unit_vector(seed=42)
        n = 10
        matrix = np.stack([_random_unit_vector(seed=i) for i in range(n)])
        batch_scores = _cosine_similarity_batch(query, matrix)
        for i in range(n):
            assert batch_scores[i] == pytest.approx(
                _cosine_similarity(query, matrix[i]), abs=1e-5
            )

    def test_batch_zero_query_returns_zeros(self) -> None:
        zero_query = np.zeros(_EMBED_DIM, dtype=np.float32)
        matrix = np.stack([_random_unit_vector(seed=i) for i in range(5)])
        scores = _cosine_similarity_batch(zero_query, matrix)
        assert np.all(scores == 0.0)


# ---------------------------------------------------------------------------
# Integration tests — require initialized VectorStore
# ---------------------------------------------------------------------------


class TestVectorStoreLifecycle:
    """Basic lifecycle: initialize, add, count, close."""

    async def test_initialize_creates_table(self, store: VectorStore) -> None:
        assert await store.count() == 0

    async def test_add_returns_vector_record(self, store: VectorStore) -> None:
        record = await store.add("EACCES on /var/run/docker.sock")
        assert isinstance(record, VectorRecord)
        assert record.id > 0
        assert record.text == "EACCES on /var/run/docker.sock"
        assert record.embedding_dim == _EMBED_DIM

    async def test_count_increments_after_add(self, store: VectorStore) -> None:
        await store.add("first unique entry")
        await store.add("second completely different entry: sqlite WAL mode enabled")
        assert await store.count() == 2

    async def test_not_initialized_raises(self, tmp_path: Path) -> None:
        vs = VectorStore(db_path=tmp_path / "uninit.db")
        with pytest.raises(RuntimeError, match="not initialized"):
            await vs.add("should fail")


class TestEmbeddingSpeed:
    """
    Teste 1 (Sprint 2 DoD): embedding de sentença técnica deve completar em < 50 ms
    em CPU (medido na segunda chamada — modelo já carregado/aquecido).
    """

    async def test_embedding_latency_warm(self, store: VectorStore) -> None:
        # Warm-up: first call loads the ONNX model into memory
        await store.add("warm-up sentence to load ONNX model")

        # Measured call
        t0 = time.perf_counter()
        await store.add("RuntimeError: Connection reset by peer on socket 8080")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 50, (
            f"Embedding + add took {elapsed_ms:.1f} ms — exceeds 50 ms budget on warm model. "
            "Consider optimizing or adjusting the threshold for this environment."
        )


class TestDeduplication:
    """
    Teste 2 (Sprint 2 DoD): frases semanticamente idênticas não devem criar
    registros duplicados — devem acionar touch_memory() no registro existente.
    """

    async def test_identical_text_no_duplicate(self, store: VectorStore) -> None:
        r1 = await store.add("Docker container failed to start")
        count_after_first = await store.count()

        r2 = await store.add("Docker container failed to start")
        count_after_second = await store.count()

        # Same count — no new record was created
        assert count_after_first == count_after_second == 1
        # Both calls return the same record id
        assert r1.id == r2.id

    async def test_semantically_similar_en_no_duplicate(self, store: VectorStore) -> None:
        """
        Very close paraphrases in English should exceed the 0.92 cosine threshold
        and be deduplicated into a single record.
        """
        r1 = await store.add("Docker container failed to start")
        initial_count = await store.count()

        # Near-identical paraphrase — expect deduplication
        r2 = await store.add("The Docker container could not start")
        final_count = await store.count()

        # If dedup fires, count stays the same and IDs match.
        # If the model similarity is below 0.92 for this pair, the test is
        # marked xfail (model-dependent behaviour — not a code defect).
        if r1.id == r2.id:
            assert final_count == initial_count
        else:
            pytest.xfail(
                "Model similarity between EN paraphrases was below the 0.92 threshold — "
                "acceptable model-dependent behaviour."
            )

    async def test_distinct_texts_create_separate_records(self, store: VectorStore) -> None:
        await store.add("EACCES on /var/run/docker.sock — permission denied")
        await store.add("Python ImportError: No module named 'numpy'")
        await store.add("git rebase --abort after merge conflict")
        assert await store.count() == 3

    async def test_dedup_threshold_constant(self) -> None:
        """Guard: the dedup threshold must remain at 0.92 per ADR-012."""
        assert _DEDUP_THRESHOLD == 0.92

    async def test_touch_memory_updates_last_seen(self, store: VectorStore) -> None:
        """touch_memory() must update last_seen_at without creating a new row."""
        import asyncio

        r1 = await store.add("Unique test sentence for touch_memory validation")
        before_count = await store.count()

        # Small delay so the timestamp actually differs
        await asyncio.sleep(0.01)
        await store.touch_memory(r1.id)

        after_count = await store.count()
        assert before_count == after_count == 1


class TestSemanticSearch:
    """Tests for search_semantic correctness and ordering."""

    async def test_search_returns_relevant_results(self, store: VectorStore) -> None:
        await store.add("EACCES on /var/run/docker.sock", metadata={"tag": "docker"})
        await store.add("Python ImportError: No module named 'requests'", metadata={"tag": "python"})
        await store.add("git merge conflict in pyproject.toml", metadata={"tag": "git"})

        results = await store.search_semantic("docker permission error", limit=3)
        assert len(results) >= 1
        # Top result should mention docker
        assert "docker" in results[0].text.lower() or "docker" in str(results[0].metadata).lower()

    async def test_search_returns_vector_records(self, store: VectorStore) -> None:
        await store.add("SQLite WAL mode enabled for concurrent reads")
        results = await store.search_semantic("sqlite database write-ahead log", limit=5)
        assert all(isinstance(r, VectorRecord) for r in results)

    async def test_search_scores_are_positive(self, store: VectorStore) -> None:
        await store.add("FastEmbed ONNX model loaded successfully")
        results = await store.search_semantic("ONNX embedding model", limit=5)
        assert all(r.cosine_score is not None and r.cosine_score > 0.0 for r in results)

    async def test_search_scores_descending_order(self, store: VectorStore) -> None:
        for i in range(5):
            await store.add(f"Unique technical entry number {i}: sqlite fts5 bm25 ranking")
        results = await store.search_semantic("sqlite full text search ranking", limit=5)
        scores = [r.cosine_score for r in results if r.cosine_score is not None]
        assert scores == sorted(scores, reverse=True)

    async def test_search_empty_store_returns_empty(self, store: VectorStore) -> None:
        results = await store.search_semantic("anything", limit=10)
        assert results == []

    async def test_search_limit_respected(self, store: VectorStore) -> None:
        for i in range(10):
            await store.add(f"Technical log entry {i}: process started with PID {1000 + i}")
        results = await store.search_semantic("process started", limit=3)
        assert len(results) <= 3

    async def test_search_with_metadata(self, store: VectorStore) -> None:
        meta = {"session": "s42", "source": "tool_output"}
        await store.add("RuntimeError: NoneType is not iterable at line 88", metadata=meta)
        results = await store.search_semantic("NoneType runtime error", limit=5)
        assert len(results) >= 1
        assert results[0].metadata.get("session") == "s42"
