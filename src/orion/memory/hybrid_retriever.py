"""
O.R.I.O.N Hybrid Retriever — Reciprocal Rank Fusion (Sprint 2, v0.2.0)

Fuses BM25 lexical results (FTS5) and cosine semantic results (FastEmbed)
using the Reciprocal Rank Fusion algorithm with k=60, subject to a strict
token budget of < 1,500 tokens for the final injection payload.

Formula: RRF(d) = Σ_{m ∈ M} 1 / (k + r_m(d))  where k = 60

ADR-004: Triple Memory Architecture
ADR-012: FastEmbed bge-small-en-v1.5 & RRF Hybrid Fusion
"""

from __future__ import annotations

from orion.memory.models import HybridSearchResult, TimelineRecord, VectorRecord
from orion.memory.timeline import TimelineManager
from orion.memory.vector_store import VectorStore

_RRF_K = 60
_DEFAULT_TOKEN_BUDGET = 1_500
# Rough token estimate: 1 token ≈ 4 characters (conservative for English/code)
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    """Conservative token count estimate: len(text) / 4 characters per token."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _rrf_score(rank: int, k: int = _RRF_K) -> float:
    """Single-method RRF contribution: 1 / (k + rank)."""
    return 1.0 / (k + rank)


class HybridRetriever:
    """
    Fuses BM25 (lexical) and semantic (cosine) search results via RRF.

    Usage:
        retriever = HybridRetriever(timeline=tm, vector_store=vs)
        result = await retriever.retrieve("EACCES docker permission", limit=20)
        print(result.records)  # Fused, ranked, budget-trimmed results
    """

    def __init__(
        self,
        timeline: TimelineManager,
        vector_store: VectorStore,
        rrf_k: int = _RRF_K,
        token_budget: int = _DEFAULT_TOKEN_BUDGET,
    ) -> None:
        self._timeline = timeline
        self._vector_store = vector_store
        self._rrf_k = rrf_k
        self._token_budget = token_budget

    async def retrieve(
        self,
        query: str,
        limit: int = 20,
        token_budget: int | None = None,
    ) -> HybridSearchResult:
        """
        Execute parallel BM25 + semantic search and fuse results via RRF.

        Args:
            query: The search query string.
            limit: Maximum number of candidates to fetch per source before fusion.
            token_budget: Override the instance-level token budget for this call.

        Returns:
            HybridSearchResult with fused records ordered by RRF score,
            truncated to fit within the token budget.
        """
        budget = token_budget if token_budget is not None else self._token_budget

        # Fetch candidates from both sources in parallel
        # (asyncio.gather is used for conceptual clarity; in practice aiosqlite
        # uses a thread pool so these are not truly concurrent)
        import asyncio

        bm25_results, semantic_results = await asyncio.gather(
            self._timeline.search_lexical(query, limit=limit),
            self._vector_store.search_semantic(query, limit=limit),
        )

        # Build unified id → record map and accumulate RRF scores
        # Timeline records use negative IDs to avoid collision with VectorRecord IDs
        record_map: dict[str, TimelineRecord | VectorRecord] = {}
        rrf_scores: dict[str, float] = {}

        for rank, record in enumerate(bm25_results):
            key = f"tl_{record.id}"
            record_map[key] = record
            rrf_scores[key] = rrf_scores.get(key, 0.0) + _rrf_score(rank, self._rrf_k)

        for rank, record in enumerate(semantic_results):
            key = f"vs_{record.id}"
            record_map[key] = record
            rrf_scores[key] = rrf_scores.get(key, 0.0) + _rrf_score(rank, self._rrf_k)

        # Sort by descending RRF score
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)

        # Apply token budget — greedy truncation by score order
        selected_records: list[TimelineRecord | VectorRecord] = []
        selected_keys: list[str] = []
        total_tokens = 0
        truncated = False

        for key in sorted_keys:
            record = record_map[key]
            content = record.content if isinstance(record, TimelineRecord) else record.text
            tokens = _estimate_tokens(content)

            if total_tokens + tokens > budget:
                truncated = True
                break

            selected_records.append(record)
            selected_keys.append(key)
            total_tokens += tokens

        # Build numeric score map for the response (keyed by record id)
        numeric_scores = {
            int(key.split("_", 1)[1]): rrf_scores[key] for key in selected_keys
        }

        return HybridSearchResult(
            query=query,
            records=selected_records,
            total_tokens_estimate=total_tokens,
            rrf_scores=numeric_scores,
            truncated=truncated,
        )


# ---------------------------------------------------------------------------
# Type alias fix — Optional not in scope at module level in Python 3.11 style
# ---------------------------------------------------------------------------
