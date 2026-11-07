"""
O.R.I.O.N — Cognitive Memory Tools (Sprint 3, v0.2.0)

The four cognitive tools that extend the agent's ReAct loop with structured
memory operations:

  1. MemorizeTool        — Persist a new or updated fact to the FactsStore.
  2. RecallTool          — Hybrid-retrieve relevant facts and timeline events.
  3. DeprecateFactTool   — Mark an obsolete fact as DEPRECATED.
  4. InspectEnvironmentTool — Snapshot current hardware telemetry (RAM/CPU/display).

Each tool conforms to the same interface as the 5 primitive native tools
(``supports(name) → bool``, ``execute(params) → RuntimeResult``) so they
plug seamlessly into the existing LocalRuntimeProvider + ReActEngine chain.

ADR-004: Triple Memory Architecture
ADR-013: 5-Sphere Cognitive Architecture
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from orion.memory.facts_store import FactPoisoningAttempt, FactsStore
from orion.memory.hybrid_retriever import HybridRetriever
from orion.memory.models import FactCategory, FactEntry, FactStatus
from orion.runtime.provider import RuntimeResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MemorizeTool
# ---------------------------------------------------------------------------


class MemorizeTool:
    """
    Persist a new or updated structured fact to the FactsStore.

    Tool name: ``memorize``

    Parameters (passed as a dict to execute):
        key         (str, required)  — Unique fact identifier (snake_case).
        value       (str, required)  — The fact's value.
        category    (str, required)  — One of: USER_PREFERENCE, PROJECT_ARCHITECTURE,
                                       CODING_STANDARD, INFRASTRUCTURE.
        status      (str, optional)  — CONFIRMED | INFERRED (default: INFERRED).
        confidence  (float, optional)— 0.0–1.0 (default: 0.5).
        source      (str, optional)  — "agent" | "user" | "file_sync" (default: "agent").
    """

    TOOL_NAME = "memorize"

    def __init__(self, facts_store: FactsStore) -> None:
        self._store = facts_store

    def supports(self, name: str) -> bool:
        return name == self.TOOL_NAME

    def execute(self, params: dict[str, Any]) -> RuntimeResult:
        """Persist the fact; returns success/failure RuntimeResult."""
        key = str(params.get("key", "")).strip()
        value = str(params.get("value", "")).strip()
        category_raw = str(params.get("category", "")).strip().upper()
        status_raw = str(params.get("status", "INFERRED")).strip().upper()
        confidence = float(params.get("confidence", 0.5))
        source = str(params.get("source", "agent")).strip()

        if not key:
            return RuntimeResult(success=False, error="'key' is required.")
        if not value:
            return RuntimeResult(success=False, error="'value' is required.")

        try:
            category = FactCategory(category_raw)
        except ValueError:
            valid = [c.value for c in FactCategory]
            return RuntimeResult(
                success=False,
                error=f"Invalid category '{category_raw}'. Valid: {valid}",
            )

        try:
            status = FactStatus(status_raw)
        except ValueError:
            valid_s = [s.value for s in FactStatus]
            return RuntimeResult(
                success=False,
                error=f"Invalid status '{status_raw}'. Valid: {valid_s}",
            )

        fact = FactEntry(
            key=key,
            value=value,
            category=category,
            status=status,
            confidence=max(0.0, min(1.0, confidence)),
            source=source,
        )

        try:
            saved = self._store.upsert(fact)
            return RuntimeResult(
                success=True,
                output=f"Fact '{saved.key}' ({saved.status.value}) persisted successfully.",
                metadata={"fact_id": saved.id, "key": saved.key, "status": saved.status.value},
            )
        except FactPoisoningAttempt as exc:
            return RuntimeResult(
                success=False,
                error=str(exc),
                metadata={"poisoning_attempt": True, "key": key},
            )


# ---------------------------------------------------------------------------
# RecallTool
# ---------------------------------------------------------------------------


class RecallTool:
    """
    Hybrid-retrieve relevant memory (BM25 + semantic RRF) from the FactsStore
    and Timeline.

    Tool name: ``recall``

    Parameters:
        query  (str, required)  — Natural language or keyword query.
        limit  (int, optional)  — Max results returned (default: 10).
    """

    TOOL_NAME = "recall"

    def __init__(
        self,
        facts_store: FactsStore,
        retriever: HybridRetriever | None = None,
    ) -> None:
        self._store = facts_store
        self._retriever = retriever

    def supports(self, name: str) -> bool:
        return name == self.TOOL_NAME

    def execute(self, params: dict[str, Any]) -> RuntimeResult:
        """Synchronous facts-only recall (no event loop needed)."""
        return self._build(params, hybrid_text="")

    async def run(self, **params: Any) -> RuntimeResult:
        """Async recall: facts + optional hybrid (BM25 + semantic) retrieval.

        The runtime prefers ``run`` over ``execute``, so this is the path used
        by the agent; it awaits the retriever on the running loop.
        """
        hybrid_text = ""
        query = str(params.get("query", "")).strip()
        if self._retriever is not None and query:
            limit = int(params.get("limit", 10))
            try:
                result = await self._retriever.retrieve(query, limit=limit)
                snippets = []
                for rec in result.records[:5]:
                    text = getattr(rec, "content", None) or getattr(rec, "text", "") or ""
                    snippets.append("  - " + " ".join(str(text).split())[:200])
                if snippets:
                    hybrid_text = (
                        f"\n[Hybrid retrieval: {len(result.records)} records, "
                        f"~{result.total_tokens_estimate} tokens]\n" + "\n".join(snippets)
                    )
            except Exception as exc:
                logger.warning("RecallTool hybrid retrieval failed: %s", exc)
        return self._build(params, hybrid_text=hybrid_text)

    def _build(self, params: dict[str, Any], hybrid_text: str) -> RuntimeResult:
        query = str(params.get("query", "")).strip()
        limit = int(params.get("limit", 10))

        if not query:
            return RuntimeResult(success=False, error="'query' is required for recall.")

        # Scan ALL facts, then rank by how many query words hit key/value.
        words = query.lower().split()
        scored = []
        for fact in self._store.search(limit=10_000):
            haystack = f"{fact.key} {fact.value}".lower()
            hits = sum(1 for w in words if w in haystack)
            if hits:
                scored.append((hits, fact))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        matched_facts = [f for _, f in scored[:limit]]

        if not matched_facts:
            return RuntimeResult(
                success=True,
                output=f"No facts found matching '{query}'.{hybrid_text}",
                metadata={"query": query, "count": 0},
            )

        lines = [f"Found {len(matched_facts)} fact(s) matching '{query}':"]
        for fact in matched_facts:
            lines.append(
                f"  [{fact.status.value}] {fact.key} = {fact.value} "
                f"(confidence: {int(fact.confidence * 100)}%, source: {fact.source})"
            )
        return RuntimeResult(
            success=True,
            output="\n".join(lines) + hybrid_text,
            metadata={"query": query, "count": len(matched_facts)},
        )


# ---------------------------------------------------------------------------
# DeprecateFactTool
# ---------------------------------------------------------------------------


class DeprecateFactTool:
    """
    Mark a fact as DEPRECATED in the FactsStore.

    Once deprecated, a fact can never be re-promoted to CONFIRMED or INFERRED.

    Tool name: ``deprecate_fact``

    Parameters:
        key  (str, required)  — The fact key to deprecate.
    """

    TOOL_NAME = "deprecate_fact"

    def __init__(self, facts_store: FactsStore) -> None:
        self._store = facts_store

    def supports(self, name: str) -> bool:
        return name == self.TOOL_NAME

    def execute(self, params: dict[str, Any]) -> RuntimeResult:
        key = str(params.get("key", "")).strip()
        if not key:
            return RuntimeResult(success=False, error="'key' is required.")

        found = self._store.deprecate(key)
        if found:
            return RuntimeResult(
                success=True,
                output=f"Fact '{key}' has been deprecated.",
                metadata={"key": key, "deprecated": True},
            )
        return RuntimeResult(
            success=False,
            error=f"Fact '{key}' not found in the store.",
            metadata={"key": key, "deprecated": False},
        )


# ---------------------------------------------------------------------------
# InspectEnvironmentTool
# ---------------------------------------------------------------------------


class InspectEnvironmentTool:
    """
    Capture a hardware telemetry snapshot (Sphere 3 — system_environment).

    Tool name: ``inspect_environment``

    Parameters:
        (none)  — No input parameters required.

    Returns:
        RAM free/total, CPU load, display mode, GPU name, headroom safety flag.
    """

    TOOL_NAME = "inspect_environment"

    def __init__(self, monitor: Any | None = None) -> None:
        if monitor is None:
            from orion.runtime.environment import EnvironmentMonitor

            self._monitor = EnvironmentMonitor()
        else:
            self._monitor = monitor

    def supports(self, name: str) -> bool:
        return name == self.TOOL_NAME

    def execute(self, params: dict[str, Any]) -> RuntimeResult:  # noqa: ARG002
        telemetry = self._monitor.snapshot()

        headroom_icon = "✅" if telemetry.headroom_safe else "⚠️"
        gpu_line = f"GPU      : {telemetry.gpu_name}" if telemetry.gpu_name else "GPU      : not detected"

        output = (
            f"[System Environment Snapshot]\n"
            f"RAM free : {telemetry.ram_free_gb:.2f} GB / {telemetry.ram_total_gb:.2f} GB total\n"
            f"CPU load : {telemetry.cpu_load_percent:.1f}%\n"
            f"Display  : {telemetry.display_mode}\n"
            f"{gpu_line}\n"
            f"Browser  : {headroom_icon} {'safe' if telemetry.headroom_safe else 'BLOCKED (< 1.5 GB free RAM)'}"
        )

        return RuntimeResult(
            success=True,
            output=output,
            metadata={
                "ram_free_gb": telemetry.ram_free_gb,
                "ram_total_gb": telemetry.ram_total_gb,
                "cpu_load_percent": telemetry.cpu_load_percent,
                "display_mode": telemetry.display_mode,
                "headroom_safe": telemetry.headroom_safe,
            },
        )
