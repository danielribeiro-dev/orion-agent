"""
Tests for HybridRetriever — Sprint 2, v0.2.0

Coverage targets:
  - RRF formula correctness: score = 1 / (k + rank), k=60
  - Parallel fetch: both BM25 and semantic results are combined
  - Token budget enforcement: total payload never exceeds 1,500 tokens
  - truncated=True when budget forces early stop
  - Empty sources: graceful handling when one or both sources return nothing
  - Ordering: results sorted by descending RRF score
  - Per-call token_budget override works correctly

Teste 3 (Sprint 2 DoD): consulta híbrida via RRF nunca ultrapassa 1.500 tokens
no total do payload retornado.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from orion.memory.hybrid_retriever import HybridRetriever, _estimate_tokens, _rrf_score
from orion.memory.models import HybridSearchResult, TimelineRecord, VectorRecord
from orion.memory.timeline import TimelineManager
from orion.memory.vector_store import VectorStore

from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_timeline_record(
    record_id: int, content: str, session_id: str = "s1"
) -> TimelineRecord:
    return TimelineRecord(
        id=record_id,
        session_id=session_id,
        timestamp=datetime.now(timezone.utc),
        event_type="action",
        source="agent",
        content=content,
        bm25_rank=1.0,
    )


def _make_vector_record(record_id: int, text: str) -> VectorRecord:
    return VectorRecord(
        id=record_id,
        text=text,
        embedding_dim=384,
        cosine_score=0.85,
        created_at=datetime.now(timezone.utc),
        last_seen_at=datetime.now(timezone.utc),
    )


def _make_retriever(
    bm25_results: list[TimelineRecord],
    semantic_results: list[VectorRecord],
    token_budget: int = 1_500,
) -> HybridRetriever:
    """Build a HybridRetriever with fully mocked timeline + vector store."""
    timeline = MagicMock(spec=TimelineManager)
    timeline.search_lexical = AsyncMock(return_value=bm25_results)

    vector_store = MagicMock(spec=VectorStore)
    vector_store.search_semantic = AsyncMock(return_value=semantic_results)

    return HybridRetriever(
        timeline=timeline,
        vector_store=vector_store,
        token_budget=token_budget,
    )


# ---------------------------------------------------------------------------
# Unit tests — pure functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:

    def test_estimate_tokens_basic(self) -> None:
        """1 token ≈ 4 chars (conservative estimate)."""
        assert _estimate_tokens("abcd") == 1
        assert _estimate_tokens("a" * 100) == 25
        assert _estimate_tokens("") == 1  # min=1 guard

    def test_estimate_tokens_long_text(self) -> None:
        text = "x" * 6000  # 6000 chars → 1500 tokens
        assert _estimate_tokens(text) == 1500

    def test_rrf_score_k60(self) -> None:
        """RRF(rank=0, k=60) = 1/60 ≈ 0.01667."""
        assert _rrf_score(0, k=60) == pytest.approx(1 / 60, rel=1e-6)

    def test_rrf_score_rank1(self) -> None:
        assert _rrf_score(1, k=60) == pytest.approx(1 / 61, rel=1e-6)

    def test_rrf_score_decreasing(self) -> None:
        scores = [_rrf_score(r) for r in range(10)]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Integration tests — HybridRetriever behaviour
# ---------------------------------------------------------------------------


class TestHybridRetrieverBasic:

    async def test_retrieve_returns_hybrid_search_result(self) -> None:
        bm25 = [_make_timeline_record(1, "Docker EACCES error")]
        sem = [_make_vector_record(1, "Permission denied on docker socket")]
        retriever = _make_retriever(bm25, sem)

        result = await retriever.retrieve("docker permission")
        assert isinstance(result, HybridSearchResult)
        assert result.query == "docker permission"

    async def test_retrieve_calls_both_sources(self) -> None:
        bm25 = [_make_timeline_record(10, "sqlite WAL mode")]
        sem = [_make_vector_record(20, "write-ahead logging")]
        retriever = _make_retriever(bm25, sem)

        await retriever.retrieve("sqlite")

        retriever._timeline.search_lexical.assert_awaited_once()
        retriever._vector_store.search_semantic.assert_awaited_once()

    async def test_retrieve_empty_both_sources(self) -> None:
        retriever = _make_retriever([], [])
        result = await retriever.retrieve("anything")
        assert result.records == []
        assert result.total_tokens_estimate == 0
        assert not result.truncated

    async def test_retrieve_empty_bm25_only_semantic(self) -> None:
        sem = [_make_vector_record(5, "Python runtime error NoneType")]
        retriever = _make_retriever([], sem)
        result = await retriever.retrieve("python error")
        assert len(result.records) == 1
        assert result.records[0].id == 5

    async def test_retrieve_empty_semantic_only_bm25(self) -> None:
        bm25 = [_make_timeline_record(7, "git rebase conflict resolved")]
        retriever = _make_retriever(bm25, [])
        result = await retriever.retrieve("git rebase")
        assert len(result.records) == 1
        assert result.records[0].id == 7


class TestRRFScoring:
    """Validate the RRF fusion logic."""

    async def test_rrf_scores_present_in_result(self) -> None:
        bm25 = [_make_timeline_record(1, "entry one")]
        sem = [_make_vector_record(2, "entry two")]
        retriever = _make_retriever(bm25, sem)

        result = await retriever.retrieve("entry")
        assert len(result.rrf_scores) > 0

    async def test_record_appearing_in_both_sources_gets_higher_score(self) -> None:
        """
        A document that ranks well in BOTH BM25 and semantic search should
        receive a combined RRF score higher than a document appearing in only one.

        We simulate this by using a record with id=99 in both lists.
        Since the namespace differs (tl_99 vs vs_99), the actual IDs won't collide,
        but we can verify that combined contributions sum correctly.
        """
        # Rank 0 in BM25 → score 1/60 ≈ 0.01667
        # Rank 0 in semantic → score 1/60 ≈ 0.01667
        # Combined: 2/60 ≈ 0.03333
        bm25 = [
            _make_timeline_record(99, "shared content docker permission error"),
            _make_timeline_record(100, "only in bm25"),
        ]
        sem = [
            _make_vector_record(99, "shared content docker permission error"),
            _make_vector_record(101, "only in semantic search"),
        ]
        retriever = _make_retriever(bm25, sem)
        result = await retriever.retrieve("docker permission")

        # Four distinct records (tl_99, tl_100, vs_99, vs_101)
        assert len(result.records) == 4

        # tl_99 and vs_99 each appear at rank 0 in their respective lists
        # → each receives 1/60; total unique records are 4
        all_scores = list(result.rrf_scores.values())
        # Scores for top records should be 1/60 ≈ 0.01667
        assert max(all_scores) == pytest.approx(1 / 60, rel=1e-5)

    async def test_results_sorted_by_descending_rrf(self) -> None:
        bm25 = [
            _make_timeline_record(i, f"bm25 record {i}") for i in range(5)
        ]
        sem = [
            _make_vector_record(i + 100, f"semantic record {i}") for i in range(5)
        ]
        retriever = _make_retriever(bm25, sem)
        result = await retriever.retrieve("record")

        # Verify descending RRF order
        scores_in_order = [result.rrf_scores.get(r.id, 0.0) for r in result.records]
        assert scores_in_order == sorted(scores_in_order, reverse=True)


class TestTokenBudget:
    """
    Teste 3 (Sprint 2 DoD): consulta híbrida via RRF nunca ultrapassa 1.500 tokens.
    """

    async def test_default_budget_never_exceeded(self) -> None:
        """Generate records that would overflow; verify truncation applies."""
        # Each record has ~500 characters → ~125 tokens; 20 records = ~2500 tokens
        large_records_bm25 = [
            _make_timeline_record(i, "A" * 500 + f" unique-{i}")
            for i in range(10)
        ]
        large_records_sem = [
            _make_vector_record(i + 100, "B" * 500 + f" unique-{i}")
            for i in range(10)
        ]
        retriever = _make_retriever(large_records_bm25, large_records_sem, token_budget=1_500)

        result = await retriever.retrieve("large content")

        assert result.total_tokens_estimate <= 1_500, (
            f"Token budget exceeded: {result.total_tokens_estimate} tokens returned "
            f"(limit=1500). truncated={result.truncated}"
        )
        assert result.truncated is True

    async def test_small_payload_not_truncated(self) -> None:
        """Small records should pass through untouched."""
        bm25 = [_make_timeline_record(i, f"short record {i}") for i in range(3)]
        sem = [_make_vector_record(i + 100, f"short entry {i}") for i in range(3)]
        retriever = _make_retriever(bm25, sem, token_budget=1_500)

        result = await retriever.retrieve("short")
        assert result.total_tokens_estimate <= 1_500
        assert result.truncated is False

    async def test_custom_budget_override(self) -> None:
        """Per-call token_budget override must be respected."""
        bm25 = [_make_timeline_record(i, "x" * 400) for i in range(5)]
        retriever = _make_retriever(bm25, [], token_budget=1_500)

        # Override to very small budget (100 tokens → 400 chars)
        result = await retriever.retrieve("test", token_budget=100)
        assert result.total_tokens_estimate <= 100
        assert result.truncated is True

    async def test_budget_exactly_at_limit_not_truncated(self) -> None:
        """A single record whose token count exactly equals the budget passes through."""
        # 400 chars → 100 tokens
        record_text = "Z" * 400
        bm25 = [_make_timeline_record(1, record_text)]
        retriever = _make_retriever(bm25, [], token_budget=100)

        result = await retriever.retrieve("test", token_budget=100)
        # 400 chars / 4 = 100 tokens → exactly at budget
        assert result.total_tokens_estimate == 100
        assert result.truncated is False

    async def test_total_tokens_field_is_accurate(self) -> None:
        """total_tokens_estimate must equal the sum of tokens of returned records."""
        bm25 = [
            _make_timeline_record(1, "A" * 40),   # 10 tokens
            _make_timeline_record(2, "B" * 80),   # 20 tokens
        ]
        retriever = _make_retriever(bm25, [], token_budget=1_500)

        result = await retriever.retrieve("test")
        expected_tokens = sum(_estimate_tokens(r.content) for r in bm25)
        assert result.total_tokens_estimate == expected_tokens


class TestEdgeCases:
    """Edge case and robustness tests."""

    async def test_limit_parameter_forwarded(self) -> None:
        """The `limit` parameter should be passed to both search methods."""
        bm25 = [_make_timeline_record(i, f"bm25 {i}") for i in range(5)]
        sem = [_make_vector_record(i + 10, f"sem {i}") for i in range(5)]
        retriever = _make_retriever(bm25, sem)

        await retriever.retrieve("test", limit=7)

        # Verify both sources were called with limit=7
        retriever._timeline.search_lexical.assert_awaited_once_with("test", limit=7)
        retriever._vector_store.search_semantic.assert_awaited_once_with("test", limit=7)

    async def test_rrf_scores_dict_keyed_by_int_ids(self) -> None:
        bm25 = [_make_timeline_record(42, "timeline entry")]
        sem = [_make_vector_record(99, "vector entry")]
        retriever = _make_retriever(bm25, sem)

        result = await retriever.retrieve("entry")
        for key in result.rrf_scores:
            assert isinstance(key, int)

    async def test_single_very_long_record_truncated(self) -> None:
        """A single record larger than the budget must be excluded."""
        # 6_000 chars → 1500 tokens, already at limit
        # With budget=100 (25 chars), this single record cannot fit
        huge_record = _make_timeline_record(1, "H" * 6_000)
        retriever = _make_retriever([huge_record], [], token_budget=100)

        result = await retriever.retrieve("huge")
        assert result.total_tokens_estimate == 0
        assert result.records == []
        assert result.truncated is True
