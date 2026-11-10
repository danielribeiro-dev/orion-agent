"""
O.R.I.O.N — Auto-Recall (v0.5.0 Sprint 3, CA-03/DoD "recall dentro de 1500 tokens")

Liga o ``HybridRetriever`` (BM25 + vetorial, RRF) e o ``FactsStore`` ao turno: antes de cada
pedido, recupera fatos e episódios relevantes e devolve um bloco curto para o engine anexar
como dado (nunca instrução). Depois do turno, indexa o par pedido/resposta no vector store.

Degrada em silêncio: sem ``fastembed``/modelo, cai no BM25; qualquer falha desliga só o
recall (o turno nunca falha por memória). ``ORION_RECALL=0`` desliga tudo.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from orion.memory.facts_store import FactsStore
from orion.memory.hybrid_retriever import HybridRetriever
from orion.memory.models import FactStatus, HybridSearchResult, TimelineRecord, VectorRecord
from orion.memory.timeline import TimelineManager
from orion.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)

RECALL_TOKEN_BUDGET = 1_500
_FACTS_SHARE = 0.4
_SNIPPET_CHARS = 300
_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)
_CHARS_PER_TOKEN = 4

VectorFactory = Callable[[Path], VectorStore]

_MIN_SNIPPET_WORDS = 5
_MIN_TERM_LEN = 4
# Prompts de comando (slash/skills) não são conhecimento: não voltam como "memória".
_COMMAND_PROMPTS = ("destile a solução", "distill the solution")


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if len(w) >= _MIN_TERM_LEN}


def _is_noise(text: str, query: str) -> bool:
    """Descarta recall curto demais, de prompt de comando ou com pouca sobreposição com o pedido."""
    flat = " ".join(text.split())
    if len(flat.split()) < _MIN_SNIPPET_WORDS:
        return True
    if flat.lower().startswith(_COMMAND_PROMPTS):
        return True
    wanted = _terms(query)
    if not wanted:
        return False
    need = 2 if len(wanted) >= 3 else 1
    return len(wanted & _terms(flat)) < need


def _tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def fts_query(text: str, max_terms: int = 12) -> str:
    """Texto livre -> consulta FTS5 segura (termos entre aspas unidos por OR)."""
    seen: dict[str, None] = {}
    for word in _WORD.findall(text.lower()):
        seen.setdefault(word, None)
        if len(seen) >= max_terms:
            break
    return " OR ".join(f'"{w}"' for w in seen)


class _SafeTimeline:
    """Fachada do ``TimelineManager`` cuja busca léxica aceita texto livre."""

    def __init__(self, inner: TimelineManager) -> None:
        self._inner = inner

    async def search_lexical(self, query: str, limit: int = 20) -> list[TimelineRecord]:
        safe = fts_query(query)
        return await self._inner.search_lexical(safe, limit=limit) if safe else []


class AutoRecall:
    """Recall por turno e indexação pós-turno."""

    def __init__(
        self,
        db_path: Path,
        facts: FactsStore | None,
        *,
        enabled: bool = True,
        token_budget: int = RECALL_TOKEN_BUDGET,
        timeout_s: float = 8.0,
        vector_factory: VectorFactory | None = None,
    ) -> None:
        self._db_path = db_path
        self._facts = facts
        self._enabled = enabled
        self._budget = token_budget
        self._timeout = timeout_s
        self._vector_factory = vector_factory or (lambda path: VectorStore(path))
        self._model: Any = None  # modelo de embeddings reaproveitado entre turnos
        self._semantic = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ── Recall ──

    async def recall(self, query: str, session_id: str = "") -> str:
        """Bloco de memória relevante (<= orçamento) ou ``""``."""
        if not self._enabled or not query.strip():
            return ""
        try:
            return await asyncio.wait_for(self._recall(query, session_id), self._timeout)
        except Exception as exc:  # noqa: BLE001 - memória nunca derruba o turno
            logger.warning("AutoRecall: recall indisponível (%s).", exc)
            return ""

    def _fact_lines(self, query: str, budget: int) -> list[str]:
        if self._facts is None:
            return []
        words = {w for w in _WORD.findall(query.lower())}
        scored: list[tuple[int, int, Any]] = []
        for fact in self._facts.search(limit=10_000):
            if fact.status == FactStatus.DEPRECATED:
                continue
            haystack = f"{fact.key} {fact.value}".lower()
            hits = sum(1 for w in words if w in haystack)
            if hits:
                scored.append((hits, 1 if fact.status == FactStatus.CONFIRMED else 0, fact))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        lines: list[str] = []
        used = 0
        for _, _, fact in scored:
            line = f"- [fato {fact.status.value}] {fact.key} = {fact.value}"[:_SNIPPET_CHARS]
            cost = _tokens(line)
            if used + cost > budget:
                break
            lines.append(line)
            used += cost
        return lines

    async def _recall(self, query: str, session_id: str) -> str:
        fact_budget = int(self._budget * _FACTS_SHARE)
        fact_lines = self._fact_lines(query, fact_budget)
        remaining = self._budget - sum(_tokens(line) for line in fact_lines)

        episodes: list[str] = []
        if self._db_path.parent.is_dir() and remaining > 0:
            episodes = await self._episodes(query, session_id, remaining)
        if not fact_lines and not episodes:
            return ""
        return "\n".join(["Memória relevante (recuperada automaticamente):", *fact_lines, *episodes])

    async def retrieve(
        self, query: str, limit: int = 10, token_budget: int | None = None
    ) -> HybridSearchResult:
        """Busca híbrida (BM25 + vetorial; só BM25 se não houver embeddings).

        Mesma assinatura do ``HybridRetriever.retrieve``: serve de retriever ao tool ``recall``.
        """
        budget = token_budget if token_budget is not None else self._budget
        timeline = TimelineManager(self._db_path)
        vectors: VectorStore | None = None
        try:
            await timeline.initialize()
            retriever_vectors: Any = _NoVectors()
            if self._semantic:
                vectors = self._vector_factory(self._db_path)
                if self._model is not None:
                    vectors._model = self._model  # noqa: SLF001 - evita recarregar o ONNX a cada turno
                await vectors.initialize()
                retriever_vectors = vectors
            safe: Any = _SafeTimeline(timeline)
            try:
                result = await HybridRetriever(safe, retriever_vectors, token_budget=budget).retrieve(
                    query, limit=limit, token_budget=budget
                )
            except Exception as exc:  # noqa: BLE001 - sem modelo de embeddings: só BM25
                logger.info("AutoRecall: busca vetorial indisponível (%s); usando BM25.", exc)
                self._semantic = False
                result = await HybridRetriever(safe, _NoVectors(), token_budget=budget).retrieve(  # type: ignore[arg-type]
                    query, limit=limit, token_budget=budget
                )
            if vectors is not None and getattr(vectors, "_model", None) is not None:
                self._model = vectors._model  # noqa: SLF001
            return result
        finally:
            await _close(timeline)
            if vectors is not None:
                await _close(vectors)

    async def _episodes(self, query: str, session_id: str, budget: int) -> list[str]:
        result = await self.retrieve(query, limit=10, token_budget=budget)
        lines: list[str] = []
        used = 0
        for record in result.records:
            if isinstance(record, TimelineRecord):
                if record.session_id == session_id or record.event_type == "day_marker":
                    continue
                text, tag = record.content, "histórico"
            else:
                if session_id and record.metadata.get("session_id") == session_id:
                    continue
                text, tag = record.text, "episódio"
            if _is_noise(text, query):
                continue
            line = f"- [{tag}] " + " ".join(text.split())[:_SNIPPET_CHARS]
            cost = _tokens(line)
            if used + cost > budget:
                break
            lines.append(line)
            used += cost
        return lines

    # ── Indexação ──

    async def remember(self, text: str, session_id: str) -> None:
        """Indexa o par pedido/resposta para recalls futuros (best effort)."""
        if not self._enabled or not self._semantic or not text.strip():
            return
        vectors = self._vector_factory(self._db_path)
        try:
            if self._model is not None:
                vectors._model = self._model  # noqa: SLF001
            await vectors.initialize()
            await vectors.add(text[:2000], metadata={"session_id": session_id})
            self._model = getattr(vectors, "_model", None)
        except Exception as exc:  # noqa: BLE001
            logger.info("AutoRecall: indexação vetorial desligada (%s).", exc)
            self._semantic = False
        finally:
            await _close(vectors)


async def _close(store: Any) -> None:
    """Fecha o store mesmo com o banco corrompido (uma thread aiosqlite aberta trava o processo)."""
    try:
        await store.close()
    except Exception:  # noqa: BLE001
        conn = getattr(store, "_conn", None)
        if conn is not None:
            with contextlib.suppress(Exception):
                await conn.close()
            store._conn = None  # noqa: SLF001


class _NoVectors:
    """Substituto sem embeddings (apenas BM25)."""

    async def search_semantic(self, query: str, limit: int = 20) -> list[VectorRecord]:  # noqa: ARG002
        return []
