"""
Tests — Cognitive Memory Tools (Sprint 3, v0.2.0)

Validates TEST 6 (spec): memorize, recall, deprecate_fact, inspect_environment
work correctly within the ReAct tool interface.

Tests:
  - MemorizeTool: persist facts, anti-poisoning block, invalid params
  - RecallTool: keyword search, empty result, missing query
  - DeprecateFactTool: deprecate existing, missing key
  - InspectEnvironmentTool: snapshot returned with metadata
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from orion.memory.facts_store import FactsStore
from orion.memory.models import FactCategory, FactEntry, FactStatus
from orion.memory.tools import (
    DeprecateFactTool,
    InspectEnvironmentTool,
    MemorizeTool,
    RecallTool,
)
from orion.runtime.environment import EnvironmentMonitor
from orion.runtime.provider import RuntimeResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path) -> FactsStore:
    s = FactsStore(db_path=tmp_path / "tools_test.db")
    s.initialize()
    yield s
    s.close()


@pytest.fixture
def memorize_tool(store) -> MemorizeTool:
    return MemorizeTool(facts_store=store)


@pytest.fixture
def recall_tool(store) -> RecallTool:
    return RecallTool(facts_store=store)


@pytest.fixture
def deprecate_tool(store) -> DeprecateFactTool:
    return DeprecateFactTool(facts_store=store)


# ---------------------------------------------------------------------------
# MemorizeTool
# ---------------------------------------------------------------------------


class TestMemorizeTool:
    def test_supports_memorize(self, memorize_tool):
        assert memorize_tool.supports("memorize") is True
        assert memorize_tool.supports("recall") is False

    def test_persist_inferred_fact(self, memorize_tool, store):
        result = memorize_tool.execute({
            "key": "python_version",
            "value": "3.11",
            "category": "INFRASTRUCTURE",
            "status": "INFERRED",
        })
        assert result.success is True
        assert "python_version" in result.output

        fact = store.get("python_version")
        assert fact is not None
        assert fact.value == "3.11"
        assert fact.status == FactStatus.INFERRED

    def test_persist_confirmed_fact(self, memorize_tool, store):
        result = memorize_tool.execute({
            "key": "db_engine",
            "value": "postgres",
            "category": "INFRASTRUCTURE",
            "status": "CONFIRMED",
            "confidence": "0.99",
            "source": "user",
        })
        assert result.success is True
        fact = store.get("db_engine")
        assert fact is not None
        assert fact.status == FactStatus.CONFIRMED
        assert fact.source == "user"

    def test_anti_poisoning_block(self, memorize_tool, store):
        """Memorize INFERRED on a CONFIRMED key → failure (poisoning blocked)."""
        # First, store a CONFIRMED fact
        memorize_tool.execute({
            "key": "arch",
            "value": "microservices",
            "category": "PROJECT_ARCHITECTURE",
            "status": "CONFIRMED",
        })

        # Attempt to overwrite with INFERRED
        result = memorize_tool.execute({
            "key": "arch",
            "value": "monolith",
            "category": "PROJECT_ARCHITECTURE",
            "status": "INFERRED",
        })

        assert result.success is False
        assert "poisoning" in result.error.lower() or "confirmed" in result.error.lower()
        assert result.metadata.get("poisoning_attempt") is True

        # Confirmed value must remain intact
        fact = store.get("arch")
        assert fact is not None
        assert fact.value == "microservices"

    def test_missing_key_param(self, memorize_tool):
        result = memorize_tool.execute({
            "value": "some_value",
            "category": "INFRASTRUCTURE",
        })
        assert result.success is False
        assert "key" in result.error.lower()

    def test_missing_value_param(self, memorize_tool):
        result = memorize_tool.execute({
            "key": "some_key",
            "category": "INFRASTRUCTURE",
        })
        assert result.success is False
        assert "value" in result.error.lower()

    def test_invalid_category(self, memorize_tool):
        result = memorize_tool.execute({
            "key": "k",
            "value": "v",
            "category": "INVALID_CATEGORY",
        })
        assert result.success is False
        assert "category" in result.error.lower()

    def test_invalid_status(self, memorize_tool):
        result = memorize_tool.execute({
            "key": "k",
            "value": "v",
            "category": "INFRASTRUCTURE",
            "status": "MAYBE",
        })
        assert result.success is False

    def test_confidence_clamped_to_range(self, memorize_tool, store):
        result = memorize_tool.execute({
            "key": "clamped_key",
            "value": "v",
            "category": "INFRASTRUCTURE",
            "confidence": "2.5",  # > 1.0, should clamp to 1.0
        })
        assert result.success is True
        fact = store.get("clamped_key")
        assert fact is not None
        assert fact.confidence <= 1.0

    def test_metadata_contains_fact_key(self, memorize_tool):
        result = memorize_tool.execute({
            "key": "my_key",
            "value": "my_value",
            "category": "CODING_STANDARD",
        })
        assert result.success is True
        assert result.metadata.get("key") == "my_key"


# ---------------------------------------------------------------------------
# RecallTool
# ---------------------------------------------------------------------------


class TestRecallTool:
    def test_supports_recall(self, recall_tool):
        assert recall_tool.supports("recall") is True
        assert recall_tool.supports("memorize") is False

    def test_recall_finds_matching_fact(self, recall_tool, store):
        store.upsert(FactEntry(
            key="python_version",
            value="3.11",
            category=FactCategory.INFRASTRUCTURE,
            status=FactStatus.CONFIRMED,
        ))
        result = recall_tool.execute({"query": "python"})

        assert result.success is True
        assert "python_version" in result.output
        assert result.metadata.get("count") == 1

    def test_recall_no_results(self, recall_tool):
        result = recall_tool.execute({"query": "nonexistent_xyz_987"})
        assert result.success is True
        assert result.metadata.get("count") == 0
        assert "No facts found" in result.output

    def test_recall_missing_query(self, recall_tool):
        result = recall_tool.execute({})
        assert result.success is False
        assert "query" in result.error.lower()

    def test_recall_returns_multiple_facts(self, recall_tool, store):
        store.upsert(FactEntry(
            key="python_linter",
            value="ruff",
            category=FactCategory.CODING_STANDARD,
            status=FactStatus.CONFIRMED,
        ))
        store.upsert(FactEntry(
            key="python_version",
            value="3.11",
            category=FactCategory.INFRASTRUCTURE,
            status=FactStatus.CONFIRMED,
        ))
        result = recall_tool.execute({"query": "python"})
        assert result.success is True
        assert result.metadata.get("count") == 2

    def test_recall_limit_param(self, recall_tool, store):
        for i in range(5):
            store.upsert(FactEntry(
                key=f"key_{i}",
                value=str(i),
                category=FactCategory.INFRASTRUCTURE,
                status=FactStatus.INFERRED,
            ))
        result = recall_tool.execute({"query": "key", "limit": 3})
        # count should be at most 3 (depends on keyword match)
        assert result.success is True


# ---------------------------------------------------------------------------
# DeprecateFactTool
# ---------------------------------------------------------------------------


class TestDeprecateFactTool:
    def test_supports_deprecate_fact(self, deprecate_tool):
        assert deprecate_tool.supports("deprecate_fact") is True

    def test_deprecate_existing_fact(self, deprecate_tool, store):
        store.upsert(FactEntry(
            key="old_lib",
            value="requests",
            category=FactCategory.INFRASTRUCTURE,
            status=FactStatus.CONFIRMED,
        ))
        result = deprecate_tool.execute({"key": "old_lib"})

        assert result.success is True
        assert "old_lib" in result.output
        assert result.metadata.get("deprecated") is True

        fact = store.get("old_lib")
        assert fact is not None
        assert fact.status == FactStatus.DEPRECATED

    def test_deprecate_nonexistent_key(self, deprecate_tool):
        result = deprecate_tool.execute({"key": "does_not_exist"})
        assert result.success is False
        assert result.metadata.get("deprecated") is False

    def test_deprecate_missing_key_param(self, deprecate_tool):
        result = deprecate_tool.execute({})
        assert result.success is False
        assert "key" in result.error.lower()


# ---------------------------------------------------------------------------
# InspectEnvironmentTool
# ---------------------------------------------------------------------------


class TestInspectEnvironmentTool:
    def test_supports_inspect_environment(self):
        tool = InspectEnvironmentTool()
        assert tool.supports("inspect_environment") is True
        assert tool.supports("memorize") is False

    def test_snapshot_returns_success(self):
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(8.0 * 1024 ** 3)
        mock_mem.total = int(16.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=10.0):
                monitor._psutil_available = True
                tool = InspectEnvironmentTool(monitor=monitor)
                result = tool.execute({})

        assert result.success is True
        assert "RAM" in result.output or "ram" in result.output.lower()

    def test_metadata_has_expected_keys(self):
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(4.0 * 1024 ** 3)
        mock_mem.total = int(8.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=5.0):
                monitor._psutil_available = True
                tool = InspectEnvironmentTool(monitor=monitor)
                result = tool.execute({})

        assert "ram_free_gb" in result.metadata
        assert "ram_total_gb" in result.metadata
        assert "cpu_load_percent" in result.metadata
        assert "display_mode" in result.metadata
        assert "headroom_safe" in result.metadata

    def test_headroom_unsafe_reflected_in_output(self):
        monitor = EnvironmentMonitor()
        mock_mem = MagicMock()
        mock_mem.available = int(0.5 * 1024 ** 3)
        mock_mem.total = int(4.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=80.0):
                monitor._psutil_available = True
                tool = InspectEnvironmentTool(monitor=monitor)
                result = tool.execute({})

        assert result.metadata.get("headroom_safe") is False
        assert "BLOCKED" in result.output

    def test_accepts_empty_params(self):
        """Tool accepts {} or any dict — no params needed."""
        tool = InspectEnvironmentTool()
        mock_mem = MagicMock()
        mock_mem.available = int(4.0 * 1024 ** 3)
        mock_mem.total = int(8.0 * 1024 ** 3)

        with patch("psutil.virtual_memory", return_value=mock_mem):
            with patch("psutil.cpu_percent", return_value=0.0):
                result = tool.execute({})

        assert isinstance(result, RuntimeResult)
        assert result.success is True


class TestRecallRegressions:
    """Bugs found in the Sprint 5 review of RecallTool."""

    def test_match_beyond_first_page_is_found(self, store):
        # Old code fetched `limit` newest facts and only then filtered.
        store.upsert(FactEntry(key="needle_fact", value="x", category=FactCategory.INFRASTRUCTURE,
                               status=FactStatus.CONFIRMED))
        for i in range(15):
            store.upsert(FactEntry(key=f"noise_{i}", value="y", category=FactCategory.INFRASTRUCTURE,
                                   status=FactStatus.CONFIRMED))
        result = RecallTool(facts_store=store).execute({"query": "needle", "limit": 3})
        assert result.metadata["count"] == 1 and "needle_fact" in result.output

    def test_multi_word_query_ranks_by_hits(self, store):
        store.upsert(FactEntry(key="python_linter", value="ruff", category=FactCategory.CODING_STANDARD,
                               status=FactStatus.CONFIRMED))
        store.upsert(FactEntry(key="python_version", value="3.11", category=FactCategory.INFRASTRUCTURE,
                               status=FactStatus.CONFIRMED))
        result = RecallTool(facts_store=store).execute({"query": "python ruff"})
        assert result.output.index("python_linter") < result.output.index("python_version")

    async def test_async_run_uses_hybrid_retriever_on_running_loop(self, store):
        from types import SimpleNamespace

        rec = SimpleNamespace(content="decided to use  ruff\nfor lint")

        class FakeRetriever:
            async def retrieve(self, query, limit=20):
                return SimpleNamespace(records=[rec], total_tokens_estimate=7)

        tool = RecallTool(facts_store=store, retriever=FakeRetriever())
        result = await tool.run(query="lint")
        assert "Hybrid retrieval: 1 records" in result.output
        assert "decided to use ruff for lint" in result.output

    async def test_async_run_survives_retriever_failure(self, store):
        class Boom:
            async def retrieve(self, query, limit=20):
                raise RuntimeError("down")

        result = await RecallTool(facts_store=store, retriever=Boom()).run(query="zzz")
        assert result.success is True and "No facts found" in result.output
