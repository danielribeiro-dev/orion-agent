"""
O.R.I.O.N Vector Store — FastEmbed ONNX Local Embeddings (Sprint 2, v0.2.0)

Implements the Semantic Layer of the Triple Memory Architecture using:
  - fastembed: lightweight ONNX Runtime wrapper (no PyTorch required)
  - Model: bge-small-en-v1.5 (384 dimensions, < 130MB, pure CPU inference)
  - Deduplication: cosine similarity >= 0.92 → touch existing record instead of inserting
  - Storage: SQLite table `vector_embeddings` with binary float serialization

ADR-004: Triple Memory Architecture
ADR-012: FastEmbed bge-small-en-v1.5 & RRF Hybrid Fusion
"""

from __future__ import annotations

import json
import struct
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiosqlite
import numpy as np

from orion.memory.models import VectorRecord

if TYPE_CHECKING:
    pass

_DEFAULT_DB_PATH = Path.home() / ".orion" / "timeline.db"
_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
_EMBED_DIM = 384
_DEDUP_THRESHOLD = 0.92  # Cosine similarity threshold for deduplication

_VECTOR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS vector_embeddings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    embedding    BLOB    NOT NULL,
    metadata_json TEXT   NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL,
    last_seen_at TEXT    NOT NULL
);
"""


def _pack_embedding(embedding: np.ndarray) -> bytes:
    """Serialize a float32 numpy array to bytes (little-endian)."""
    return struct.pack(f"<{len(embedding)}f", *embedding.astype(np.float32).tolist())


def _unpack_embedding(data: bytes) -> np.ndarray:
    """Deserialize bytes back to a float32 numpy array."""
    n = len(data) // 4  # 4 bytes per float32
    return np.array(struct.unpack(f"<{n}f", data), dtype=np.float32)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two L2-normalized vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _cosine_similarity_batch(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """
    Compute cosine similarity between *query* (1D) and every row in *matrix* (2D).
    Vectorised with NumPy — O(n) dot products in a single BLAS call.
    """
    query_norm = np.linalg.norm(query)
    if query_norm == 0.0:
        return np.zeros(len(matrix))
    row_norms = np.linalg.norm(matrix, axis=1)
    # Avoid division by zero for zero-magnitude rows
    row_norms = np.where(row_norms == 0.0, 1.0, row_norms)
    scores: np.ndarray = (matrix @ query) / (row_norms * query_norm)
    return scores


class VectorStore:
    """
    Async vector store backed by SQLite with FastEmbed ONNX local embeddings.

    Usage:
        store = VectorStore()
        await store.initialize()
        record = await store.add("EACCES on /var/run/docker.sock", metadata={"session": "s1"})
        results = await store.search_semantic("permission denied docker", limit=5)
        await store.close()
    """

    def __init__(self, db_path: Path = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._model: Any | None = None  # fastembed.TextEmbedding (lazy loaded)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the SQLite connection and create the vector_embeddings table."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(_VECTOR_SCHEMA_SQL)
        await self._conn.commit()

    def _get_model(self) -> Any:
        """Lazy-load the FastEmbed model on first use (downloads on first call)."""
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=_EMBED_MODEL)
        return self._model

    async def close(self) -> None:
        """Close the SQLite connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    async def add(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
    ) -> VectorRecord:
        """
        Add a text chunk to the vector store.

        If a semantically similar entry already exists (cosine_sim >= 0.92),
        performs a touch_memory() update instead of inserting a duplicate.

        Returns the VectorRecord (either new or the existing one that was touched).
        """
        if self._conn is None:
            raise RuntimeError("VectorStore not initialized. Call await initialize() first.")

        embedding = self._embed(text)
        existing = await self._find_duplicate(embedding)

        if existing is not None:
            await self.touch_memory(existing.id)
            return existing

        now = datetime.now(UTC).isoformat()
        meta_json = json.dumps(metadata or {})
        blob = _pack_embedding(embedding)

        async with self._conn.execute(
            """
            INSERT INTO vector_embeddings (text, embedding, metadata_json, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (text, blob, meta_json, now, now),
        ) as cursor:
            row_id = cursor.lastrowid

        await self._conn.commit()
        return VectorRecord(
            id=row_id,  # type: ignore[arg-type]
            text=text,
            embedding_dim=_EMBED_DIM,
            metadata=metadata or {},
            created_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )

    async def touch_memory(self, record_id: int) -> None:
        """Update last_seen_at for an existing record (deduplication touch)."""
        if self._conn is None:
            raise RuntimeError("VectorStore not initialized.")

        now = datetime.now(UTC).isoformat()
        await self._conn.execute(
            "UPDATE vector_embeddings SET last_seen_at = ? WHERE id = ?",
            (now, record_id),
        )
        await self._conn.commit()

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    async def search_semantic(
        self, query: str, limit: int = 20
    ) -> list[VectorRecord]:
        """
        Encode *query* and return the top *limit* records by cosine similarity.
        Uses vectorised NumPy dot-products for efficiency.
        """
        if self._conn is None:
            raise RuntimeError("VectorStore not initialized.")

        query_emb = self._embed(query)

        rows = await self._conn.execute_fetchall(
            "SELECT id, text, embedding, metadata_json, created_at, last_seen_at FROM vector_embeddings"
        )
        if not rows:
            return []

        ids = [row["id"] for row in rows]
        texts = [row["text"] for row in rows]
        metas = [json.loads(row["metadata_json"]) for row in rows]
        timestamps_created = [row["created_at"] for row in rows]
        timestamps_seen = [row["last_seen_at"] for row in rows]
        matrix = np.array(
            [_unpack_embedding(row["embedding"]) for row in rows], dtype=np.float32
        )

        scores = _cosine_similarity_batch(query_emb, matrix)
        top_indices = np.argsort(scores)[::-1][:limit]

        return [
            VectorRecord(
                id=ids[i],
                text=texts[i],
                embedding_dim=_EMBED_DIM,
                cosine_score=float(scores[i]),
                metadata=metas[i],
                created_at=datetime.fromisoformat(timestamps_created[i]),
                last_seen_at=datetime.fromisoformat(timestamps_seen[i]),
            )
            for i in top_indices
            if scores[i] > 0.0
        ]

    async def count(self) -> int:
        """Return the total number of stored embeddings."""
        if self._conn is None:
            raise RuntimeError("VectorStore not initialized.")

        rows = await self._conn.execute_fetchall("SELECT COUNT(*) AS cnt FROM vector_embeddings")
        return int(rows[0]["cnt"])  # type: ignore[index]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> np.ndarray:
        """Encode a single text string using the FastEmbed ONNX model."""
        model = self._get_model()
        embeddings = list(model.embed([text]))
        return np.array(embeddings[0], dtype=np.float32)

    async def _find_duplicate(self, embedding: np.ndarray) -> VectorRecord | None:
        """
        Check if any existing vector has cosine_sim >= 0.92 with *embedding*.
        Returns the most similar existing VectorRecord, or None.
        """
        if self._conn is None:
            raise RuntimeError("VectorStore not initialized.")

        rows = list(
            await self._conn.execute_fetchall(
                "SELECT id, text, embedding, metadata_json, created_at, last_seen_at FROM vector_embeddings"
            )
        )
        if not rows:
            return None

        ids = [row["id"] for row in rows]
        matrix = np.array(
            [_unpack_embedding(row["embedding"]) for row in rows], dtype=np.float32
        )
        scores = _cosine_similarity_batch(embedding, matrix)
        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])

        if best_score >= _DEDUP_THRESHOLD:
            row = rows[best_idx]
            return VectorRecord(
                id=ids[best_idx],
                text=row["text"],
                embedding_dim=_EMBED_DIM,
                cosine_score=best_score,
                metadata=json.loads(row["metadata_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                last_seen_at=datetime.fromisoformat(row["last_seen_at"]),
            )
        return None
