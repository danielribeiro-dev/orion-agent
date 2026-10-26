"""
Testes unitários — CostLedger (v0.3.0 Sprint 3)

Cobre:
- Inicialização e criação do schema WAL
- record_turn_cost: gravação atômica, cálculo correto de custos
- Desconto de cache tokens
- daily_summary: agregação por dia
- list_records: consulta com filtro de data
- spent_today_usd: atalho de custo diário
- total_spent_usd: total histórico
- Modelos locais (custo zero)
- usd_to_brl: conversão e setter
- record_turn_cost_async: versão assíncrona
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from orion.gateway.ledger import CostCalculator, CostLedger, CostRecord, DailySummary
from orion.gateway.models import ComplexityTier, ProviderName, TokenUsage
from orion.gateway.registry import ModelRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_ledger(tmp_path: Path) -> CostLedger:
    """CostLedger isolado em diretório temporário."""
    return CostLedger(db_path=tmp_path / "test_metrics.db")


@pytest.fixture
def registry() -> ModelRegistry:
    return ModelRegistry()


@pytest.fixture
def calculator(registry: ModelRegistry) -> CostCalculator:
    return CostCalculator(registry=registry, usd_to_brl=5.7)


@pytest.fixture
def usage_standard() -> TokenUsage:
    """Uso padrão: 1000 tokens de prompt, 500 de completion, sem cache."""
    return TokenUsage(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=0,
        total_tokens=1500,
    )


@pytest.fixture
def usage_with_cache() -> TokenUsage:
    """Uso com cache: 1000 tokens de prompt, 700 cacheados, 500 de completion."""
    return TokenUsage(
        prompt_tokens=1000,
        completion_tokens=500,
        cached_tokens=700,
        total_tokens=1500,
    )


# ---------------------------------------------------------------------------
# CostCalculator — testes de cálculo puro
# ---------------------------------------------------------------------------


class TestCostCalculator:
    def test_compute_no_cache(self, calculator: CostCalculator) -> None:
        """Custo sem cache: soma de input + output ao preço cheio."""
        # google/gemini-2.0-flash: input=$0.1/M, output=$0.4/M
        usage = TokenUsage(
            prompt_tokens=1_000_000,
            completion_tokens=1_000_000,
            cached_tokens=0,
            total_tokens=2_000_000,
        )
        cost_usd, cost_brl = calculator.compute("google/gemini-2.0-flash", usage)
        # 1M * $0.1 + 1M * $0.4 = $0.5
        assert abs(cost_usd - 0.5) < 1e-6
        assert abs(cost_brl - 0.5 * 5.7) < 1e-4

    def test_compute_with_full_cache(self, calculator: CostCalculator) -> None:
        """Custo com todos os tokens cacheados no prompt."""
        # anthropic/claude-haiku-3-5: input=$0.8/M, output=$4.0/M
        usage = TokenUsage(
            prompt_tokens=1_000_000,
            completion_tokens=0,
            cached_tokens=1_000_000,  # 100% cacheados
            total_tokens=1_000_000,
        )
        cost_usd, _ = calculator.compute("anthropic/claude-haiku-3-5", usage)
        # 0 tokens não-cacheados × $0.8 + 1M cacheados × $0.8 × 0.1 = $0.08
        assert abs(cost_usd - 0.08) < 1e-6

    def test_compute_partial_cache(self, calculator: CostCalculator) -> None:
        """Custo com cache parcial no prompt."""
        # google/gemini-2.0-flash: input=$0.1/M, output=$0.4/M
        usage = TokenUsage(
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            cached_tokens=600_000,
            total_tokens=1_500_000,
        )
        cost_usd, _ = calculator.compute("google/gemini-2.0-flash", usage)
        # billable_input = 400_000 não-cacheados
        # custo_input = 400_000 × $0.1/M + 600_000 × $0.1/M × 0.1
        # = 0.04 + 0.006 = $0.046
        # custo_output = 500_000 × $0.4/M = $0.2
        # total = $0.246
        assert abs(cost_usd - 0.246) < 1e-6

    def test_local_model_zero_cost(self, calculator: CostCalculator) -> None:
        """Modelos locais têm custo zero."""
        usage = TokenUsage(
            prompt_tokens=10_000,
            completion_tokens=5_000,
            cached_tokens=0,
            total_tokens=15_000,
        )
        cost_usd, cost_brl = calculator.compute("qwen2.5-coder:7b", usage)
        assert cost_usd == 0.0
        assert cost_brl == 0.0

    def test_compute_unknown_model_raises(self, calculator: CostCalculator) -> None:
        """Modelo desconhecido deve levantar KeyError."""
        usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        with pytest.raises(KeyError, match="not found in registry"):
            calculator.compute("unknown/model-xyz", usage)

    def test_usd_to_brl_setter_valid(self, calculator: CostCalculator) -> None:
        """Setter de taxa de câmbio atualiza o valor."""
        calculator.usd_to_brl = 6.0
        assert calculator.usd_to_brl == 6.0

    def test_usd_to_brl_setter_invalid(self, calculator: CostCalculator) -> None:
        """Setter de taxa de câmbio rejeita valores não-positivos."""
        with pytest.raises(ValueError):
            calculator.usd_to_brl = 0.0
        with pytest.raises(ValueError):
            calculator.usd_to_brl = -1.5

    def test_cached_tokens_excess_clamped(self, calculator: CostCalculator) -> None:
        """cached_tokens > prompt_tokens não deve resultar em custo negativo."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            cached_tokens=9999,  # absurdo — não deve ser negativo
            total_tokens=150,
        )
        cost_usd, _ = calculator.compute("google/gemini-2.0-flash", usage)
        assert cost_usd >= 0.0


# ---------------------------------------------------------------------------
# CostLedger — schema e inicialização
# ---------------------------------------------------------------------------


class TestCostLedgerInit:
    def test_creates_db_file(self, tmp_path: Path) -> None:
        """Deve criar o arquivo SQLite ao primeiro uso."""
        db_path = tmp_path / "sub" / "metrics.db"
        assert not db_path.exists()
        ledger = CostLedger(db_path=db_path)
        ledger._init_db()
        assert db_path.exists()

    def test_db_path_property(self, tmp_ledger: CostLedger, tmp_path: Path) -> None:
        """db_path expõe o caminho correto."""
        assert tmp_ledger.db_path == tmp_path / "test_metrics.db"

    def test_schema_idempotent(self, tmp_ledger: CostLedger) -> None:
        """Chamar _init_db múltiplas vezes não deve levantar erros."""
        tmp_ledger._init_db()
        tmp_ledger._init_db()
        tmp_ledger._initialized = False
        tmp_ledger._init_db()

    def test_custom_usd_to_brl(self, tmp_path: Path) -> None:
        """Taxa de câmbio personalizada é aplicada ao calculador."""
        ledger = CostLedger(db_path=tmp_path / "m.db", usd_to_brl=6.5)
        assert ledger.usd_to_brl == 6.5

    def test_usd_to_brl_setter(self, tmp_ledger: CostLedger) -> None:
        """Atualização da taxa de câmbio em tempo de execução."""
        tmp_ledger.usd_to_brl = 5.9
        assert tmp_ledger.usd_to_brl == 5.9


# ---------------------------------------------------------------------------
# CostLedger — record_turn_cost
# ---------------------------------------------------------------------------


class TestRecordTurnCost:
    def test_returns_cost_record(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """Deve retornar um CostRecord válido."""
        record = tmp_ledger.record_turn_cost(
            provider=ProviderName.OPENROUTER,
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        assert isinstance(record, CostRecord)
        assert record.provider == "openrouter"
        assert record.model == "google/gemini-2.0-flash"
        assert record.cost_usd >= 0.0
        assert record.cost_brl >= 0.0

    def test_record_id_is_uuid(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """ID do registro deve ser um UUID válido."""
        record = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        # Verificar que é UUID válido
        parsed = uuid.UUID(record.id)
        assert str(parsed) == record.id

    def test_record_timestamp_utc(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """Timestamp deve estar em UTC."""
        before = datetime.now(timezone.utc)
        record = tmp_ledger.record_turn_cost(
            provider=ProviderName.OPENROUTER,
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        after = datetime.now(timezone.utc)
        assert before <= record.timestamp <= after

    def test_record_routing_and_complexity(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """routing_mode e complexity_level são gravados corretamente."""
        record = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
            routing_mode="fixed",
            complexity=ComplexityTier.HEAVY,
        )
        assert record.routing_mode == "fixed"
        assert record.complexity_level == "heavy"

    def test_record_with_task_id(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """task_id opcional deve ser gravado."""
        record = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
            task_id="task-abc-123",
        )
        assert record.task_id == "task-abc-123"

    def test_record_latency(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """latency_ms é gravada corretamente."""
        record = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
            latency_ms=342.5,
        )
        assert record.latency_ms == 342.5

    def test_cache_discount_applied(
        self, tmp_ledger: CostLedger, usage_with_cache: TokenUsage
    ) -> None:
        """Tokens cacheados devem ter custo menor que tokens normais."""
        record_no_cache = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=TokenUsage(
                prompt_tokens=1000,
                completion_tokens=500,
                cached_tokens=0,
                total_tokens=1500,
            ),
        )
        record_with_cache = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_with_cache,
        )
        # Com cache, custo deve ser menor
        assert record_with_cache.cost_usd < record_no_cache.cost_usd

    def test_local_model_zero_cost(self, tmp_ledger: CostLedger) -> None:
        """Modelos locais têm custo USD e BRL iguais a zero."""
        usage = TokenUsage(
            prompt_tokens=5000,
            completion_tokens=2000,
            cached_tokens=0,
            total_tokens=7000,
        )
        record = tmp_ledger.record_turn_cost(
            provider=ProviderName.OLLAMA,
            model="qwen2.5-coder:7b",
            usage=usage,
        )
        assert record.cost_usd == 0.0
        assert record.cost_brl == 0.0

    def test_string_provider_accepted(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """provider pode ser string além de ProviderName enum."""
        record = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        assert record.provider == "openrouter"

    def test_string_complexity_accepted(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """complexity pode ser string além de ComplexityTier enum."""
        record = tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
            complexity="fast",
        )
        assert record.complexity_level == "fast"

    def test_multiple_records_persisted(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """Múltiplos registros são persistidos individualmente."""
        for _ in range(5):
            tmp_ledger.record_turn_cost(
                provider="openrouter",
                model="google/gemini-2.0-flash",
                usage=usage_standard,
            )
        records = tmp_ledger.list_records()
        assert len(records) == 5


# ---------------------------------------------------------------------------
# CostLedger — record_turn_cost_async
# ---------------------------------------------------------------------------


class TestRecordTurnCostAsync:
    @pytest.mark.asyncio
    async def test_async_record_returns_cost_record(self, tmp_ledger: CostLedger) -> None:
        """Versão async deve retornar CostRecord válido."""
        usage = TokenUsage(
            prompt_tokens=500,
            completion_tokens=200,
            cached_tokens=0,
            total_tokens=700,
        )
        record = await tmp_ledger.record_turn_cost_async(
            provider=ProviderName.OPENROUTER,
            model="anthropic/claude-haiku-3-5",
            usage=usage,
        )
        assert isinstance(record, CostRecord)
        assert record.model == "anthropic/claude-haiku-3-5"
        assert record.cost_usd > 0.0

    @pytest.mark.asyncio
    async def test_async_record_persisted(self, tmp_ledger: CostLedger) -> None:
        """Registro assíncrono deve aparecer na consulta daily_summary."""
        usage = TokenUsage(
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            cached_tokens=0,
            total_tokens=1_500_000,
        )
        await tmp_ledger.record_turn_cost_async(
            provider=ProviderName.OPENROUTER,
            model="google/gemini-2.0-flash",
            usage=usage,
        )
        summary = tmp_ledger.daily_summary()
        assert summary.total_turns == 1
        assert summary.total_cost_usd > 0.0

    @pytest.mark.asyncio
    async def test_async_daily_summary(self, tmp_ledger: CostLedger) -> None:
        """daily_summary_async retorna o mesmo resultado que daily_summary."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            cached_tokens=0,
            total_tokens=150,
        )
        await tmp_ledger.record_turn_cost_async(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage,
        )
        sync_result = tmp_ledger.daily_summary()
        async_result = await tmp_ledger.daily_summary_async()
        assert sync_result.total_turns == async_result.total_turns
        assert abs(sync_result.total_cost_usd - async_result.total_cost_usd) < 1e-10


# ---------------------------------------------------------------------------
# CostLedger — daily_summary
# ---------------------------------------------------------------------------


class TestDailySummary:
    def test_empty_ledger_zero_summary(self, tmp_ledger: CostLedger) -> None:
        """Ledger vazio retorna summary com zeros."""
        summary = tmp_ledger.daily_summary()
        assert summary.total_cost_usd == 0.0
        assert summary.total_cost_brl == 0.0
        assert summary.total_turns == 0

    def test_summary_accumulates_costs(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """Custo total acumula múltiplos registros."""
        tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        summary = tmp_ledger.daily_summary()
        assert summary.total_turns == 2
        assert summary.total_prompt_tokens == usage_standard.prompt_tokens * 2
        assert summary.total_completion_tokens == usage_standard.completion_tokens * 2

    def test_summary_for_specific_date(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """Consulta por data específica retorna apenas registros daquele dia."""
        # Gravar registro hoje
        tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        today = datetime.now(timezone.utc).date()
        yesterday = date(today.year, today.month, max(1, today.day - 1))

        summary_today = tmp_ledger.daily_summary(day=today)
        summary_yesterday = tmp_ledger.daily_summary(day=yesterday)

        assert summary_today.total_turns == 1
        assert summary_yesterday.total_turns == 0

    def test_summary_date_field(self, tmp_ledger: CostLedger) -> None:
        """DailySummary.date deve refletir a data consultada."""
        target = date(2025, 6, 15)
        summary = tmp_ledger.daily_summary(day=target)
        assert summary.date == target

    def test_summary_brl_consistent(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """cost_brl deve ser consistente com cost_usd × taxa."""
        ledger = CostLedger(
            db_path=tmp_ledger.db_path,
            usd_to_brl=6.0,
        )
        ledger.record_turn_cost(
            provider="openrouter",
            model="google/gemini-2.0-flash",
            usage=usage_standard,
        )
        summary = ledger.daily_summary()
        # Verificar proporcionalidade aproximada (pode divergir por arredondamento)
        if summary.total_cost_usd > 0:
            ratio = summary.total_cost_brl / summary.total_cost_usd
            assert abs(ratio - 6.0) < 0.01


# ---------------------------------------------------------------------------
# CostLedger — spent_today_usd e total_spent_usd
# ---------------------------------------------------------------------------


class TestSpentQueries:
    def test_spent_today_empty(self, tmp_ledger: CostLedger) -> None:
        """spent_today_usd retorna 0.0 para ledger vazio."""
        assert tmp_ledger.spent_today_usd() == 0.0

    def test_spent_today_after_record(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """spent_today_usd retorna valor positivo após registro."""
        tmp_ledger.record_turn_cost(
            provider="openrouter",
            model="anthropic/claude-haiku-3-5",
            usage=usage_standard,
        )
        assert tmp_ledger.spent_today_usd() > 0.0

    def test_total_spent_empty(self, tmp_ledger: CostLedger) -> None:
        """total_spent_usd retorna 0.0 para ledger vazio."""
        assert tmp_ledger.total_spent_usd() == 0.0

    def test_total_spent_accumulates(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """total_spent_usd acumula múltiplos registros."""
        for _ in range(3):
            tmp_ledger.record_turn_cost(
                provider="openrouter",
                model="google/gemini-2.0-flash",
                usage=usage_standard,
            )
        total = tmp_ledger.total_spent_usd()
        today = tmp_ledger.spent_today_usd()
        assert total == today  # todos os registros são de hoje
        assert total > 0.0


# ---------------------------------------------------------------------------
# CostLedger — list_records
# ---------------------------------------------------------------------------


class TestListRecords:
    def test_list_empty(self, tmp_ledger: CostLedger) -> None:
        """Ledger vazio retorna lista vazia."""
        assert tmp_ledger.list_records() == []

    def test_list_returns_correct_count(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """list_records retorna o número correto de registros."""
        for _ in range(4):
            tmp_ledger.record_turn_cost(
                provider="openrouter",
                model="google/gemini-2.0-flash",
                usage=usage_standard,
            )
        assert len(tmp_ledger.list_records()) == 4

    def test_list_respects_limit(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """list_records deve respeitar o parâmetro limit."""
        for _ in range(10):
            tmp_ledger.record_turn_cost(
                provider="openrouter",
                model="google/gemini-2.0-flash",
                usage=usage_standard,
            )
        assert len(tmp_ledger.list_records(limit=3)) == 3

    def test_list_descending_order(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """Registros são retornados em ordem cronológica decrescente."""
        for _ in range(3):
            tmp_ledger.record_turn_cost(
                provider="openrouter",
                model="google/gemini-2.0-flash",
                usage=usage_standard,
            )
        records = tmp_ledger.list_records()
        timestamps = [r.timestamp for r in records]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_list_fields_preserved(
        self, tmp_ledger: CostLedger, usage_standard: TokenUsage
    ) -> None:
        """Todos os campos do registro são corretamente recuperados."""
        original = tmp_ledger.record_turn_cost(
            provider=ProviderName.OPENROUTER,
            model="google/gemini-2.0-flash",
            usage=usage_standard,
            routing_mode="fixed",
            complexity=ComplexityTier.FAST,
            task_id="test-task-1",
            latency_ms=123.45,
        )
        retrieved = tmp_ledger.list_records()[0]
        assert retrieved.id == original.id
        assert retrieved.model == original.model
        assert retrieved.routing_mode == original.routing_mode
        assert retrieved.complexity_level == original.complexity_level
        assert retrieved.task_id == original.task_id
        assert retrieved.latency_ms == original.latency_ms
        assert abs(retrieved.cost_usd - original.cost_usd) < 1e-10
