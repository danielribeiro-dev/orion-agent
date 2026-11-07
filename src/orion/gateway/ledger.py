"""
O.R.I.O.N — Cost Ledger (v0.3.0 Sprint 3)

Livro-razão financeiro local de consumo computacional.

Persiste em SQLite WAL em ~/.orion/metrics.db, registrando o custo
exato de cada turno em USD e BRL com suporte a desconto de cache.

Referência de design: ADR-009 (Ledger de Custos no CLI).
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from datetime import date as date_type
from pathlib import Path

from pydantic import BaseModel, Field

from orion.gateway.models import ComplexityTier, ProviderName, TokenUsage
from orion.gateway.registry import ModelRegistry

# ---------------------------------------------------------------------------
# Contratos de Dados
# ---------------------------------------------------------------------------


class CostRecord(BaseModel):
    """Registro de custo de um único turno de inferência."""

    model_config = {"frozen": True}

    id: str = Field(description="UUID do registro")
    timestamp: datetime = Field(description="Instante UTC do registro")
    provider: str = Field(description="Provedor de inferência (ex: 'openrouter')")
    model: str = Field(description="ID canônico do modelo")
    routing_mode: str = Field(description="Modo de roteamento: 'auto' ou 'fixed'")
    complexity_level: str = Field(description="Tier de complexidade: 'fast', 'balanced' ou 'heavy'")
    prompt_tokens: int = Field(ge=0, description="Tokens de prompt enviados")
    completion_tokens: int = Field(ge=0, description="Tokens gerados")
    cached_tokens: int = Field(ge=0, description="Tokens lidos do cache (custo reduzido)")
    cache_write_tokens: int = Field(default=0, ge=0, description="Tokens escritos no cache (custo maior)")
    cost_usd: float = Field(ge=0.0, description="Custo total calculado em USD")
    cost_brl: float = Field(ge=0.0, description="Custo total convertido em BRL")
    task_id: str | None = Field(default=None, description="ID externo do turno/task")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Latência da chamada em ms")


class DailySummary(BaseModel):
    """Resumo de custo agregado para um dia específico."""

    model_config = {"frozen": True}

    date: date_type = Field(description="Data do resumo (UTC)")
    total_cost_usd: float = Field(ge=0.0, description="Custo total do dia em USD")
    total_cost_brl: float = Field(ge=0.0, description="Custo total do dia em BRL")
    total_turns: int = Field(ge=0, description="Número de turnos registrados no dia")
    total_prompt_tokens: int = Field(ge=0, description="Tokens de prompt totais do dia")
    total_completion_tokens: int = Field(ge=0, description="Tokens de completion totais do dia")
    total_cached_tokens: int = Field(ge=0, description="Tokens em cache totais do dia")


# ---------------------------------------------------------------------------
# Constante de desconto de cache
# ---------------------------------------------------------------------------

# Desconto padrão para prompt caching (tokens em cache são cobrados a ~10%
# do preço normal de input — prática comum em Anthropic e OpenAI).
DEFAULT_CACHE_DISCOUNT = 0.1

# Escrita no cache de prompt (TTL de 5 min) custa 1,25x o input normal (Anthropic).
DEFAULT_CACHE_WRITE_MULTIPLIER = 1.25


# ---------------------------------------------------------------------------
# Cost Calculator (puro — sem I/O)
# ---------------------------------------------------------------------------


class CostCalculator:
    """Calcula custos de inferência com base em preços por milhão de tokens.

    Leva em conta o desconto de tokens cacheados.
    Thread-safe e sem estado mutável.
    """

    def __init__(
        self,
        registry: ModelRegistry,
        usd_to_brl: float = 5.7,
        cache_discount: float = DEFAULT_CACHE_DISCOUNT,
    ) -> None:
        """
        Args:
            registry: ModelRegistry com preços por modelo.
            usd_to_brl: Taxa de conversão USD → BRL. Padrão: 5.70.
            cache_discount: Fração do custo input aplicada a tokens cacheados.
                            Padrão: 0.10 (10% do preço normal).
        """
        self._registry = registry
        self._usd_to_brl = usd_to_brl
        self._cache_discount = cache_discount

    @property
    def usd_to_brl(self) -> float:
        """Taxa de conversão atual USD → BRL."""
        return self._usd_to_brl

    @usd_to_brl.setter
    def usd_to_brl(self, value: float) -> None:
        if value <= 0.0:
            raise ValueError(f"usd_to_brl deve ser positivo, recebido: {value}")
        self._usd_to_brl = value

    def compute(
        self,
        model_id: str,
        usage: TokenUsage,
    ) -> tuple[float, float]:
        """Calcula custo em (USD, BRL) para um conjunto de uso de tokens.

        Os tokens cacheados são cobrados a ``cache_discount`` do custo de input.
        Os tokens não-cacheados de prompt são cobrados ao preço cheio de input.

        Args:
            model_id: ID canônico do modelo no registry.
            usage: Uso de tokens do turno.

        Returns:
            Tupla (cost_usd, cost_brl).

        Raises:
            KeyError: Se model_id não for encontrado no registry.
        """
        spec = self._registry.require(model_id)

        # prompt_tokens é o total de entrada (inclui cache lido e escrito)
        billable_input = max(0, usage.prompt_tokens - usage.cached_tokens - usage.cache_write_tokens)
        read_price_m = (
            spec.cache_read_cost_m
            if spec.cache_read_cost_m is not None
            else spec.cost_input_m * self._cache_discount
        )

        cost_usd = (
            billable_input * spec.cost_input_m / 1_000_000
            + usage.cached_tokens * read_price_m / 1_000_000
            + usage.cache_write_tokens
            * spec.cost_input_m
            * DEFAULT_CACHE_WRITE_MULTIPLIER
            / 1_000_000
            + usage.completion_tokens * spec.cost_output_m / 1_000_000
        )
        cost_brl = cost_usd * self._usd_to_brl
        return round(cost_usd, 8), round(cost_brl, 6)


# ---------------------------------------------------------------------------
# Cost Ledger — persistência SQLite WAL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS token_ledger (
    id               TEXT    PRIMARY KEY,
    timestamp        TEXT    NOT NULL,
    provider         TEXT    NOT NULL,
    model            TEXT    NOT NULL,
    routing_mode     TEXT    NOT NULL,
    complexity_level TEXT    NOT NULL,
    prompt_tokens    INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens    INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd         REAL    NOT NULL DEFAULT 0.0,
    cost_brl         REAL    NOT NULL DEFAULT 0.0,
    task_id          TEXT,
    latency_ms       REAL    NOT NULL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON token_ledger(timestamp);
CREATE INDEX IF NOT EXISTS idx_ledger_model     ON token_ledger(model);
CREATE INDEX IF NOT EXISTS idx_ledger_date      ON token_ledger(substr(timestamp, 1, 10));
"""


class CostLedger:
    """Livro-razão de custos baseado em SQLite WAL.

    Armazena um registro atômico por turno de inferência.
    Suporte a consultas de custo diário e agregação histórica.

    Uso:
        ledger = CostLedger()  # usa ~/.orion/metrics.db por padrão
        await ledger.record_turn_cost(...)
        summary = await ledger.daily_summary()
    """

    def __init__(
        self,
        db_path: Path | None = None,
        registry: ModelRegistry | None = None,
        usd_to_brl: float = 5.7,
        cache_discount: float = DEFAULT_CACHE_DISCOUNT,
    ) -> None:
        """
        Args:
            db_path: Caminho para o arquivo SQLite. Padrão: ~/.orion/metrics.db.
            registry: ModelRegistry para lookup de preços.
            usd_to_brl: Taxa de conversão USD → BRL.
            cache_discount: Fração do custo input aplicado a tokens cacheados.
        """
        if db_path is None:
            db_path = Path.home() / ".orion" / "metrics.db"
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._registry = registry or ModelRegistry()
        self._calculator = CostCalculator(
            registry=self._registry,
            usd_to_brl=usd_to_brl,
            cache_discount=cache_discount,
        )
        self._lock = threading.Lock()
        self._initialized = False

    # ── Inicialização ────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Cria o schema se não existir. Thread-safe via lock."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            conn = sqlite3.connect(str(self._db_path))
            try:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.executescript(_DDL)
                # Migração v0.5.0: bancos antigos não têm cache_write_tokens
                cols = {r[1] for r in conn.execute("PRAGMA table_info(token_ledger)")}
                if "cache_write_tokens" not in cols:
                    conn.execute(
                        "ALTER TABLE token_ledger ADD COLUMN "
                        "cache_write_tokens INTEGER NOT NULL DEFAULT 0"
                    )
                conn.commit()
            finally:
                conn.close()
            self._initialized = True

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager que entrega uma conexão SQLite com WAL ativo."""
        self._init_db()
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ── Propriedades ─────────────────────────────────────────────────────────

    @property
    def usd_to_brl(self) -> float:
        """Taxa de conversão USD → BRL do calculador."""
        return self._calculator.usd_to_brl

    @usd_to_brl.setter
    def usd_to_brl(self, value: float) -> None:
        self._calculator.usd_to_brl = value

    @property
    def db_path(self) -> Path:
        """Caminho do arquivo SQLite."""
        return self._db_path

    # ── Gravação ─────────────────────────────────────────────────────────────

    def record_turn_cost(
        self,
        provider: ProviderName | str,
        model: str,
        usage: TokenUsage,
        routing_mode: str = "auto",
        complexity: ComplexityTier | str = ComplexityTier.BALANCED,
        task_id: str | None = None,
        latency_ms: float = 0.0,
    ) -> CostRecord:
        """Grava uma linha atômica no livro-razão e retorna o registro criado.

        O custo é calculado com base nos preços do ModelRegistry, aplicando
        desconto para tokens cacheados.

        Args:
            provider: Provedor de inferência (ProviderName ou string).
            model: ID canônico do modelo no registry.
            usage: Uso de tokens do turno.
            routing_mode: Modo de roteamento ('auto' ou 'fixed').
            complexity: Tier de complexidade do turno.
            task_id: Identificador externo do turno/task (opcional).
            latency_ms: Latência da chamada em milissegundos.

        Returns:
            CostRecord com os dados gravados.
        """
        cost_usd, cost_brl = self._calculator.compute(model_id=model, usage=usage)

        record = CostRecord(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            provider=str(provider.value if isinstance(provider, ProviderName) else provider),
            model=model,
            routing_mode=routing_mode,
            complexity_level=str(complexity.value if isinstance(complexity, ComplexityTier) else complexity),
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cached_tokens=usage.cached_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            cost_usd=cost_usd,
            cost_brl=cost_brl,
            task_id=task_id,
            latency_ms=latency_ms,
        )
        self._insert(record)
        return record

    async def record_turn_cost_async(
        self,
        provider: ProviderName | str,
        model: str,
        usage: TokenUsage,
        routing_mode: str = "auto",
        complexity: ComplexityTier | str = ComplexityTier.BALANCED,
        task_id: str | None = None,
        latency_ms: float = 0.0,
    ) -> CostRecord:
        """Versão assíncrona de record_turn_cost (executa em thread pool)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.record_turn_cost(
                provider=provider,
                model=model,
                usage=usage,
                routing_mode=routing_mode,
                complexity=complexity,
                task_id=task_id,
                latency_ms=latency_ms,
            ),
        )

    def _insert(self, record: CostRecord) -> None:
        """Insere o registro no banco de forma atômica."""
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO token_ledger (
                    id, timestamp, provider, model, routing_mode, complexity_level,
                    prompt_tokens, completion_tokens, cached_tokens, cache_write_tokens,
                    cost_usd, cost_brl, task_id, latency_ms
                ) VALUES (
                    :id, :timestamp, :provider, :model, :routing_mode, :complexity_level,
                    :prompt_tokens, :completion_tokens, :cached_tokens, :cache_write_tokens,
                    :cost_usd, :cost_brl, :task_id, :latency_ms
                )
                """,
                {
                    "id": record.id,
                    "timestamp": record.timestamp.isoformat(),
                    "provider": record.provider,
                    "model": record.model,
                    "routing_mode": record.routing_mode,
                    "complexity_level": record.complexity_level,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "cached_tokens": record.cached_tokens,
                    "cache_write_tokens": record.cache_write_tokens,
                    "cost_usd": record.cost_usd,
                    "cost_brl": record.cost_brl,
                    "task_id": record.task_id,
                    "latency_ms": record.latency_ms,
                },
            )

    # ── Consultas ────────────────────────────────────────────────────────────

    def daily_summary(self, day: date_type | None = None) -> DailySummary:
        """Retorna o resumo de custos de um dia específico (padrão: hoje UTC).

        Args:
            day: Data para agregar. Se None, usa hoje em UTC.

        Returns:
            DailySummary com totais de custo e tokens do dia.
        """
        if day is None:
            day = datetime.now(UTC).date()

        date_prefix = day.isoformat()  # "YYYY-MM-DD"

        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(cost_usd), 0.0)         AS total_cost_usd,
                    COALESCE(SUM(cost_brl), 0.0)         AS total_cost_brl,
                    COUNT(*)                              AS total_turns,
                    COALESCE(SUM(prompt_tokens), 0)      AS total_prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0)  AS total_completion_tokens,
                    COALESCE(SUM(cached_tokens), 0)      AS total_cached_tokens
                FROM token_ledger
                WHERE substr(timestamp, 1, 10) = ?
                """,
                (date_prefix,),
            ).fetchone()

        return DailySummary(
            date=day,
            total_cost_usd=row["total_cost_usd"],
            total_cost_brl=row["total_cost_brl"],
            total_turns=row["total_turns"],
            total_prompt_tokens=row["total_prompt_tokens"],
            total_completion_tokens=row["total_completion_tokens"],
            total_cached_tokens=row["total_cached_tokens"],
        )

    async def daily_summary_async(self, day: date_type | None = None) -> DailySummary:
        """Versão assíncrona de daily_summary."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.daily_summary(day))

    def spent_today_usd(self) -> float:
        """Atalho: retorna o custo total de hoje em USD."""
        return self.daily_summary().total_cost_usd

    def list_records(
        self,
        day: date_type | None = None,
        limit: int = 100,
    ) -> list[CostRecord]:
        """Lista registros individuais de um dia (padrão: hoje).

        Args:
            day: Data para filtrar. Se None, usa hoje em UTC.
            limit: Máximo de registros retornados.

        Returns:
            Lista de CostRecord em ordem cronológica decrescente.
        """
        if day is None:
            day = datetime.now(UTC).date()
        date_prefix = day.isoformat()

        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM token_ledger
                WHERE substr(timestamp, 1, 10) = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (date_prefix, limit),
            ).fetchall()

        return [
            CostRecord(
                id=row["id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                provider=row["provider"],
                model=row["model"],
                routing_mode=row["routing_mode"],
                complexity_level=row["complexity_level"],
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                cached_tokens=row["cached_tokens"],
                cache_write_tokens=row["cache_write_tokens"],
                cost_usd=row["cost_usd"],
                cost_brl=row["cost_brl"],
                task_id=row["task_id"],
                latency_ms=row["latency_ms"],
            )
            for row in rows
        ]

    def total_spent_usd(self) -> float:
        """Retorna o custo histórico total de todos os dias em USD."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM token_ledger"
            ).fetchone()
        return row["total"]
