"""
O.R.I.O.N Facts Store (Sprint 3, v0.2.0)

Sphere 4 — project_decisions:
  Relational SQLite store for typed, anti-poisoned structured facts (ADRs,
  coding standards, project decisions).

Anti-Poisoning State Machine:
  CONFIRMED  → Set explicitly by the user. Immovable by agent inference.
  INFERRED   → Derived by the agent. May be promoted to CONFIRMED by the user.
  DEPRECATED → Marked obsolete. Never promoted back to CONFIRMED or INFERRED.

Key rule:
  An INFERRED fact CANNOT overwrite a key whose current status is CONFIRMED.
  An attempt to do so raises FactPoisoningAttempt.

ADR-004: Triple Memory Architecture
ADR-013: Anti-Poisoning State Machine
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

from orion.memory.models import FactCategory, FactEntry, FactStatus

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    key       TEXT    NOT NULL UNIQUE,
    value     TEXT    NOT NULL,
    category  TEXT    NOT NULL,
    status    TEXT    NOT NULL DEFAULT 'INFERRED',
    confidence REAL   NOT NULL DEFAULT 0.5,
    source    TEXT    NOT NULL DEFAULT 'agent',
    created_at TEXT   NOT NULL,
    updated_at TEXT   NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_status ON facts(status);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
"""


class FactPoisoningAttempt(Exception):
    """
    Raised when an INFERRED write attempts to overwrite a CONFIRMED fact.

    This is a deterministic hard-block — the operation is rejected and the
    confirmed fact remains intact.
    """

    def __init__(self, key: str, existing_status: FactStatus) -> None:
        super().__init__(
            f"Anti-poisoning block: cannot overwrite CONFIRMED key '{key}' "
            f"with an INFERRED fact. Current status: {existing_status.value}."
        )
        self.key = key
        self.existing_status = existing_status


class FactsStore:
    """
    Typed relational store for structured facts with anti-poisoning guarantees.

    Usage::

        store = FactsStore(db_path=Path(".orion/memory/facts.db"))
        await store.initialize()

        store.upsert(FactEntry(key="python_version", value="3.11",
                               category=FactCategory.INFRASTRUCTURE,
                               status=FactStatus.CONFIRMED))

        fact = store.get("python_version")
        facts = store.search(category=FactCategory.INFRASTRUCTURE)
        store.deprecate("python_version")
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Create the database and schema if they do not exist."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Enable WAL for concurrent read safety
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_CREATE_TABLE_SQL)
        self._conn.commit()
        logger.info("FactsStore initialised at %s", self._db_path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def upsert(self, fact: FactEntry) -> FactEntry:
        """
        Insert or update a fact, enforcing the anti-poisoning rule.

        Anti-Poisoning Rule:
            If a fact with the same ``key`` already exists and its status is
            CONFIRMED, an INFERRED write is deterministically blocked by raising
            ``FactPoisoningAttempt``.  CONFIRMED writes always succeed (they
            represent explicit user intent).

        Args:
            fact: The FactEntry to persist.

        Returns:
            The persisted FactEntry with its database ``id`` populated.

        Raises:
            FactPoisoningAttempt: If an INFERRED fact tries to overwrite CONFIRMED.
        """
        self._ensure_open()
        existing = self.get(fact.key)

        if existing is not None:
            # ──────────────────────────────────────────────────────────
            # Anti-Poisoning Guard
            # ──────────────────────────────────────────────────────────
            if (
                existing.status == FactStatus.CONFIRMED
                and fact.status == FactStatus.INFERRED
            ):
                logger.warning(
                    "FactPoisoningAttempt blocked: key='%s' is CONFIRMED; "
                    "INFERRED write rejected.",
                    fact.key,
                )
                raise FactPoisoningAttempt(fact.key, existing.status)

            # Reject any write to a DEPRECATED fact via INFERRED path
            if (
                existing.status == FactStatus.DEPRECATED
                and fact.status == FactStatus.INFERRED
            ):
                logger.warning(
                    "Write to DEPRECATED key '%s' via INFERRED path rejected.",
                    fact.key,
                )
                raise FactPoisoningAttempt(fact.key, existing.status)

        now_iso = datetime.utcnow().isoformat()
        created_at = now_iso if existing is None else (existing.created_at.isoformat() if isinstance(existing.created_at, datetime) else str(existing.created_at))

        assert self._conn is not None
        cursor = self._conn.execute(
            """
            INSERT INTO facts (key, value, category, status, confidence, source, created_at, updated_at)
            VALUES (:key, :value, :category, :status, :confidence, :source, :created_at, :updated_at)
            ON CONFLICT(key) DO UPDATE SET
                value      = excluded.value,
                category   = excluded.category,
                status     = excluded.status,
                confidence = excluded.confidence,
                source     = excluded.source,
                updated_at = excluded.updated_at
            """,
            {
                "key": fact.key,
                "value": fact.value,
                "category": fact.category.value,
                "status": fact.status.value,
                "confidence": fact.confidence,
                "source": fact.source,
                "created_at": created_at,
                "updated_at": now_iso,
            },
        )
        self._conn.commit()

        row_id = cursor.lastrowid if existing is None else (existing.id)
        return FactEntry(
            id=row_id,
            key=fact.key,
            value=fact.value,
            category=fact.category,
            status=fact.status,
            confidence=fact.confidence,
            source=fact.source,
        )

    def deprecate(self, key: str) -> bool:
        """
        Mark a fact as DEPRECATED.

        Once deprecated, a fact cannot be promoted back to CONFIRMED or INFERRED.

        Args:
            key: The fact key to deprecate.

        Returns:
            True if the fact was found and deprecated; False if not found.
        """
        self._ensure_open()
        assert self._conn is not None
        cursor = self._conn.execute(
            "UPDATE facts SET status = 'DEPRECATED', updated_at = ? WHERE key = ?",
            (datetime.utcnow().isoformat(), key),
        )
        self._conn.commit()
        found = cursor.rowcount > 0
        if found:
            logger.info("Fact '%s' deprecated.", key)
        else:
            logger.warning("deprecate(): key '%s' not found.", key)
        return found

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[FactEntry]:
        """
        Retrieve a single fact by key.

        Returns:
            FactEntry if found, None otherwise.
        """
        self._ensure_open()
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM facts WHERE key = ?", (key,)
        ).fetchone()
        return self._row_to_entry(row) if row else None

    def search(
        self,
        category: Optional[FactCategory] = None,
        status: Optional[FactStatus] = None,
        limit: int = 50,
    ) -> list[FactEntry]:
        """
        Query facts with optional filters on category and/or status.

        Args:
            category: Filter by FactCategory (optional).
            status:   Filter by FactStatus (optional).
            limit:    Maximum number of results (default 50).

        Returns:
            List of matching FactEntry objects, ordered by updated_at DESC.
        """
        self._ensure_open()
        assert self._conn is not None

        clauses: list[str] = []
        params: list[str | int] = []

        if category is not None:
            clauses.append("category = ?")
            params.append(category.value)

        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)

        rows = self._conn.execute(
            f"SELECT * FROM facts {where} ORDER BY updated_at DESC LIMIT ?",
            params,
        ).fetchall()

        return [self._row_to_entry(r) for r in rows]

    def count(self) -> int:
        """Return the total number of facts stored."""
        self._ensure_open()
        assert self._conn is not None
        return self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]

    def count_confirmed(self) -> int:
        """Return the number of CONFIRMED facts."""
        self._ensure_open()
        assert self._conn is not None
        return self._conn.execute(
            "SELECT COUNT(*) FROM facts WHERE status = 'CONFIRMED'"
        ).fetchone()[0]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_open(self) -> None:
        if self._conn is None:
            raise RuntimeError(
                "FactsStore is not initialised. Call initialize() first."
            )

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> FactEntry:
        return FactEntry(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            category=FactCategory(row["category"]),
            status=FactStatus(row["status"]),
            confidence=row["confidence"],
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
