"""
Tests — FactsStore (Sprint 3, v0.2.0)

Validates:
  - Basic CRUD operations
  - Anti-poisoning state machine (INFERRED cannot overwrite CONFIRMED)
  - DEPRECATED facts cannot be overwritten via INFERRED path
  - deprecate() finaliser
  - search() with category and status filters
"""

from __future__ import annotations

import pytest

from orion.memory.facts_store import FactPoisoningAttempt, FactsStore
from orion.memory.models import FactCategory, FactEntry, FactStatus


@pytest.fixture
def store(tmp_path):
    """Provide a fresh, initialised FactsStore backed by a temp DB."""
    s = FactsStore(db_path=tmp_path / "facts.db")
    s.initialize()
    yield s
    s.close()


def _fact(
    key: str,
    value: str = "test_value",
    category: FactCategory = FactCategory.INFRASTRUCTURE,
    status: FactStatus = FactStatus.INFERRED,
    confidence: float = 0.7,
    source: str = "agent",
) -> FactEntry:
    return FactEntry(
        key=key,
        value=value,
        category=category,
        status=status,
        confidence=confidence,
        source=source,
    )


# ---------------------------------------------------------------------------
# Basic operations
# ---------------------------------------------------------------------------


class TestBasicCRUD:
    def test_upsert_and_get(self, store):
        fact = _fact("python_version", "3.11", status=FactStatus.CONFIRMED)
        saved = store.upsert(fact)

        assert saved.key == "python_version"
        assert saved.status == FactStatus.CONFIRMED
        assert saved.id is not None

        retrieved = store.get("python_version")
        assert retrieved is not None
        assert retrieved.value == "3.11"

    def test_get_nonexistent_returns_none(self, store):
        assert store.get("nonexistent_key") is None

    def test_count_empty(self, store):
        assert store.count() == 0

    def test_count_after_inserts(self, store):
        store.upsert(_fact("key1"))
        store.upsert(_fact("key2"))
        assert store.count() == 2

    def test_count_confirmed(self, store):
        store.upsert(_fact("k1", status=FactStatus.CONFIRMED))
        store.upsert(_fact("k2", status=FactStatus.INFERRED))
        assert store.count_confirmed() == 1

    def test_upsert_updates_existing_inferred(self, store):
        store.upsert(_fact("db_engine", "sqlite", status=FactStatus.INFERRED))
        updated = store.upsert(_fact("db_engine", "postgres", status=FactStatus.INFERRED))
        assert updated.value == "postgres"
        # count should still be 1 (upsert, not insert)
        assert store.count() == 1


# ---------------------------------------------------------------------------
# Anti-Poisoning State Machine — KEY TEST SCENARIOS
# ---------------------------------------------------------------------------


class TestAntiPoisoning:
    def test_inferred_cannot_overwrite_confirmed(self, store):
        """TEST 1 (spec): INFERRED write on CONFIRMED key → FactPoisoningAttempt."""
        store.upsert(_fact("arch_decision", "microservices", status=FactStatus.CONFIRMED))

        inferred_attempt = _fact("arch_decision", "monolith", status=FactStatus.INFERRED)

        with pytest.raises(FactPoisoningAttempt) as exc_info:
            store.upsert(inferred_attempt)

        assert exc_info.value.key == "arch_decision"
        assert exc_info.value.existing_status == FactStatus.CONFIRMED

        # The confirmed fact must remain intact
        intact = store.get("arch_decision")
        assert intact is not None
        assert intact.value == "microservices"
        assert intact.status == FactStatus.CONFIRMED

    def test_confirmed_can_overwrite_inferred(self, store):
        """A CONFIRMED write on an INFERRED key is always allowed (user intent)."""
        store.upsert(_fact("db_engine", "sqlite", status=FactStatus.INFERRED))
        store.upsert(_fact("db_engine", "postgres", status=FactStatus.CONFIRMED))

        fact = store.get("db_engine")
        assert fact is not None
        assert fact.value == "postgres"
        assert fact.status == FactStatus.CONFIRMED

    def test_confirmed_can_overwrite_confirmed(self, store):
        """User may update their own CONFIRMED fact."""
        store.upsert(_fact("python_version", "3.11", status=FactStatus.CONFIRMED, source="user"))
        store.upsert(_fact("python_version", "3.12", status=FactStatus.CONFIRMED, source="user"))

        fact = store.get("python_version")
        assert fact is not None
        assert fact.value == "3.12"

    def test_inferred_cannot_overwrite_deprecated(self, store):
        """INFERRED write on DEPRECATED key is also blocked."""
        store.upsert(_fact("old_feature", "enabled", status=FactStatus.CONFIRMED))
        store.deprecate("old_feature")

        with pytest.raises(FactPoisoningAttempt):
            store.upsert(_fact("old_feature", "re-enabled", status=FactStatus.INFERRED))

        fact = store.get("old_feature")
        assert fact is not None
        assert fact.status == FactStatus.DEPRECATED

    def test_poisoning_attempt_does_not_corrupt_store(self, store):
        """After a blocked poisoning attempt, store state is unchanged."""
        store.upsert(_fact("critical_setting", "locked", status=FactStatus.CONFIRMED))
        initial_count = store.count()

        try:
            store.upsert(_fact("critical_setting", "unlocked", status=FactStatus.INFERRED))
        except FactPoisoningAttempt:
            pass

        assert store.count() == initial_count
        fact = store.get("critical_setting")
        assert fact is not None
        assert fact.value == "locked"


# ---------------------------------------------------------------------------
# Deprecation
# ---------------------------------------------------------------------------


class TestDeprecation:
    def test_deprecate_existing(self, store):
        store.upsert(_fact("legacy_key"))
        result = store.deprecate("legacy_key")

        assert result is True
        fact = store.get("legacy_key")
        assert fact is not None
        assert fact.status == FactStatus.DEPRECATED

    def test_deprecate_nonexistent_returns_false(self, store):
        assert store.deprecate("does_not_exist") is False

    def test_deprecate_idempotent(self, store):
        store.upsert(_fact("key"))
        store.deprecate("key")
        result = store.deprecate("key")
        # Second call: row exists but rowcount may be 1 (no status change needed — still returns True)
        # The fact remains DEPRECATED
        fact = store.get("key")
        assert fact is not None
        assert fact.status == FactStatus.DEPRECATED


# ---------------------------------------------------------------------------
# Search / Filtering
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_all(self, store):
        store.upsert(_fact("k1", category=FactCategory.INFRASTRUCTURE))
        store.upsert(_fact("k2", category=FactCategory.CODING_STANDARD))
        results = store.search()
        assert len(results) == 2

    def test_search_by_category(self, store):
        store.upsert(_fact("k1", category=FactCategory.INFRASTRUCTURE))
        store.upsert(_fact("k2", category=FactCategory.CODING_STANDARD))

        infra = store.search(category=FactCategory.INFRASTRUCTURE)
        assert len(infra) == 1
        assert infra[0].key == "k1"

    def test_search_by_status(self, store):
        store.upsert(_fact("k1", status=FactStatus.CONFIRMED))
        store.upsert(_fact("k2", status=FactStatus.INFERRED))

        confirmed = store.search(status=FactStatus.CONFIRMED)
        assert len(confirmed) == 1
        assert confirmed[0].key == "k1"

    def test_search_combined_filter(self, store):
        store.upsert(
            _fact("k1", category=FactCategory.INFRASTRUCTURE, status=FactStatus.CONFIRMED)
        )
        store.upsert(
            _fact("k2", category=FactCategory.INFRASTRUCTURE, status=FactStatus.INFERRED)
        )
        store.upsert(
            _fact("k3", category=FactCategory.CODING_STANDARD, status=FactStatus.CONFIRMED)
        )

        results = store.search(
            category=FactCategory.INFRASTRUCTURE, status=FactStatus.CONFIRMED
        )
        assert len(results) == 1
        assert results[0].key == "k1"

    def test_search_limit(self, store):
        for i in range(10):
            store.upsert(_fact(f"key_{i}"))
        results = store.search(limit=5)
        assert len(results) == 5


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_requires_initialization(self, tmp_path):
        """FactsStore operations raise RuntimeError if not initialised."""
        uninitialised = FactsStore(db_path=tmp_path / "uninit.db")
        with pytest.raises(RuntimeError, match="not initialised"):
            uninitialised.get("any")
