"""
Testes unitários — BudgetGuard (v0.3.0 Sprint 3)

Cobre:
- Inicialização e validações do BudgetGuard
- BudgetStatus: cálculo de percentual, limit_reached, warning_triggered
- check(): passagem normal, aviso de 85%, bloqueio a 100%
- BudgetExceededError: atributos e mensagem
- BudgetWarningEvent: formato de string
- on_warning callback
- Modelos locais ignoram limite (is_local_model=True)
- daily_budget_usd=0.0 desativa o limite
- update_budget(): atualização em tempo de execução
- reset_warning_state()
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from orion.gateway.budget import (
    BudgetExceededError,
    BudgetGuard,
    BudgetStatus,
    BudgetWarningEvent,
)
from orion.gateway.ledger import CostLedger
from orion.gateway.models import ProviderName, TokenUsage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_ledger(tmp_path: Path) -> CostLedger:
    """Ledger isolado em diretório temporário."""
    return CostLedger(db_path=tmp_path / "test_metrics.db")


def make_guard(
    ledger: CostLedger,
    daily_budget_usd: float = 2.0,
    warning_threshold_pct: float = 85.0,
    on_warning=None,
) -> BudgetGuard:
    return BudgetGuard(
        ledger=ledger,
        daily_budget_usd=daily_budget_usd,
        warning_threshold_pct=warning_threshold_pct,
        on_warning=on_warning,
    )


def add_cost(ledger: CostLedger, cost_usd: float) -> None:
    """Insere um registro com custo aproximado diretamente no banco (mock via ledger)."""
    # Usa modelo local (custo=0) e remenda o cálculo via patch
    usage = TokenUsage(
        prompt_tokens=0,
        completion_tokens=0,
        cached_tokens=0,
        total_tokens=0,
    )
    with patch.object(ledger._calculator, "compute", return_value=(cost_usd, cost_usd * 5.7)):
        ledger.record_turn_cost(
            provider=ProviderName.OPENROUTER,
            model="google/gemini-2.0-flash",
            usage=usage,
        )


# ---------------------------------------------------------------------------
# BudgetStatus — testes de cálculo
# ---------------------------------------------------------------------------


class TestBudgetStatus:
    def test_zero_spent(self) -> None:
        """0% usado quando sem gastos."""
        bs = BudgetStatus(daily_budget_usd=2.0, spent_today_usd=0.0)
        assert bs.percentage_used == 0.0
        assert not bs.limit_reached
        assert not bs.warning_triggered
        assert bs.remaining_usd == 2.0

    def test_half_budget_used(self) -> None:
        """50% usado — sem alerta e sem bloqueio."""
        bs = BudgetStatus(daily_budget_usd=2.0, spent_today_usd=1.0)
        assert abs(bs.percentage_used - 50.0) < 1e-6
        assert not bs.limit_reached
        assert not bs.warning_triggered
        assert abs(bs.remaining_usd - 1.0) < 1e-6

    def test_warning_threshold_reached(self) -> None:
        """85% deve disparar warning_triggered."""
        bs = BudgetStatus(daily_budget_usd=2.0, spent_today_usd=1.7)
        assert bs.warning_triggered
        assert not bs.limit_reached

    def test_exactly_100_percent(self) -> None:
        """100% exato deve disparar limit_reached."""
        bs = BudgetStatus(daily_budget_usd=2.0, spent_today_usd=2.0)
        assert bs.limit_reached
        assert abs(bs.remaining_usd) < 1e-6

    def test_over_100_percent(self) -> None:
        """Mais de 100% gasto — limite ainda alcançado e remaining=0."""
        bs = BudgetStatus(daily_budget_usd=2.0, spent_today_usd=3.0)
        assert bs.limit_reached
        assert bs.percentage_used > 100.0
        assert bs.remaining_usd == 0.0

    def test_zero_budget_no_division(self) -> None:
        """daily_budget_usd=0 não deve levantar ZeroDivisionError."""
        bs = BudgetStatus(daily_budget_usd=0.0, spent_today_usd=0.0)
        assert bs.percentage_used == 0.0

    def test_custom_warning_threshold(self) -> None:
        """Limiar customizado de warning é respeitado."""
        bs = BudgetStatus(
            daily_budget_usd=10.0,
            spent_today_usd=7.0,
            warning_threshold_pct=70.0,
        )
        assert bs.warning_triggered  # 70% >= 70%

    def test_repr(self) -> None:
        """repr deve incluir informações relevantes."""
        bs = BudgetStatus(daily_budget_usd=2.0, spent_today_usd=1.0)
        r = repr(bs)
        assert "spent" in r
        assert "budget" in r


# ---------------------------------------------------------------------------
# BudgetWarningEvent
# ---------------------------------------------------------------------------


class TestBudgetWarningEvent:
    def test_str_contains_percentage(self) -> None:
        """String deve incluir percentual usado."""
        event = BudgetWarningEvent(
            daily_budget_usd=2.0,
            spent_today_usd=1.7,
            percentage_used=85.0,
            threshold_pct=85.0,
        )
        msg = str(event)
        assert "85.0%" in msg or "85%" in msg

    def test_str_contains_amounts(self) -> None:
        """String deve incluir valores em USD."""
        event = BudgetWarningEvent(
            daily_budget_usd=2.0,
            spent_today_usd=1.7,
            percentage_used=85.0,
            threshold_pct=85.0,
        )
        msg = str(event)
        assert "$1.7" in msg or "1.7000" in msg

    def test_repr(self) -> None:
        """repr deve ser informativo."""
        event = BudgetWarningEvent(
            daily_budget_usd=2.0,
            spent_today_usd=1.7,
            percentage_used=85.0,
            threshold_pct=85.0,
        )
        r = repr(event)
        assert "BudgetWarningEvent" in r


# ---------------------------------------------------------------------------
# BudgetExceededError
# ---------------------------------------------------------------------------


class TestBudgetExceededError:
    def test_attributes(self) -> None:
        """Erro deve expor atributos diretamente acessíveis."""
        err = BudgetExceededError(
            daily_budget_usd=2.0,
            spent_today_usd=2.01,
            percentage_used=100.5,
        )
        assert err.daily_budget_usd == 2.0
        assert err.spent_today_usd == 2.01
        assert err.percentage_used == 100.5

    def test_message_informative(self) -> None:
        """Mensagem de erro deve mencionar valores relevantes."""
        err = BudgetExceededError(
            daily_budget_usd=5.0,
            spent_today_usd=5.01,
            percentage_used=100.2,
        )
        msg = str(err)
        assert "budget" in msg.lower() or "exceeded" in msg.lower()

    def test_is_exception(self) -> None:
        """Deve ser uma exceção."""
        err = BudgetExceededError(2.0, 2.5, 125.0)
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# BudgetGuard — inicialização e validação
# ---------------------------------------------------------------------------


class TestBudgetGuardInit:
    def test_default_values(self, tmp_ledger: CostLedger) -> None:
        """Valores padrão razoáveis."""
        guard = BudgetGuard(ledger=tmp_ledger)
        assert guard.daily_budget_usd == 2.0
        assert guard.warning_threshold_pct == 85.0

    def test_negative_budget_raises(self, tmp_ledger: CostLedger) -> None:
        """Orçamento negativo deve levantar ValueError."""
        with pytest.raises(ValueError):
            BudgetGuard(ledger=tmp_ledger, daily_budget_usd=-1.0)

    def test_invalid_threshold_raises(self, tmp_ledger: CostLedger) -> None:
        """Limiar fora de (0, 100) deve levantar ValueError."""
        with pytest.raises(ValueError):
            BudgetGuard(ledger=tmp_ledger, warning_threshold_pct=0.0)
        with pytest.raises(ValueError):
            BudgetGuard(ledger=tmp_ledger, warning_threshold_pct=100.0)
        with pytest.raises(ValueError):
            BudgetGuard(ledger=tmp_ledger, warning_threshold_pct=110.0)

    def test_zero_budget_no_error(self, tmp_ledger: CostLedger) -> None:
        """daily_budget_usd=0.0 deve ser aceito (sem limite)."""
        guard = BudgetGuard(ledger=tmp_ledger, daily_budget_usd=0.0)
        assert guard.daily_budget_usd == 0.0


# ---------------------------------------------------------------------------
# BudgetGuard.status()
# ---------------------------------------------------------------------------


class TestBudgetGuardStatus:
    def test_status_empty_ledger(self, tmp_ledger: CostLedger) -> None:
        """Status com ledger vazio."""
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        bs = guard.status()
        assert bs.spent_today_usd == 0.0
        assert bs.percentage_used == 0.0
        assert not bs.limit_reached

    def test_status_after_spending(self, tmp_ledger: CostLedger) -> None:
        """Status reflete gastos do ledger."""
        add_cost(tmp_ledger, 1.0)
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        bs = guard.status()
        assert abs(bs.spent_today_usd - 1.0) < 1e-6
        assert abs(bs.percentage_used - 50.0) < 1e-4

    def test_status_zero_budget(self, tmp_ledger: CostLedger) -> None:
        """Com budget=0, status.limit_reached é False (sem limite)."""
        guard = make_guard(tmp_ledger, daily_budget_usd=0.0)
        bs = guard.status()
        assert not bs.limit_reached


# ---------------------------------------------------------------------------
# BudgetGuard.check() — caminho normal
# ---------------------------------------------------------------------------


class TestBudgetGuardCheckNormal:
    def test_check_passes_under_budget(self, tmp_ledger: CostLedger) -> None:
        """check() retorna BudgetStatus sem exceção quando abaixo do teto."""
        add_cost(tmp_ledger, 0.5)
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        bs = guard.check()
        assert isinstance(bs, BudgetStatus)
        assert not bs.limit_reached

    def test_check_local_model_always_passes(self, tmp_ledger: CostLedger) -> None:
        """is_local_model=True nunca levanta BudgetExceededError."""
        add_cost(tmp_ledger, 999.0)  # orçamento estourado
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        # Não deve lançar exceção para modelo local
        bs = guard.check(is_local_model=True)
        assert isinstance(bs, BudgetStatus)

    def test_check_no_limit_with_zero_budget(self, tmp_ledger: CostLedger) -> None:
        """Com budget=0.0, qualquer gasto deve passar."""
        add_cost(tmp_ledger, 100.0)
        guard = make_guard(tmp_ledger, daily_budget_usd=0.0)
        bs = guard.check()
        assert isinstance(bs, BudgetStatus)


# ---------------------------------------------------------------------------
# BudgetGuard.check() — alerta de 85%
# ---------------------------------------------------------------------------


class TestBudgetGuardWarning:
    def test_warning_callback_called_at_85_pct(self, tmp_ledger: CostLedger) -> None:
        """Callback on_warning deve ser chamado ao atingir 85%."""
        callback = MagicMock()
        add_cost(tmp_ledger, 1.71)  # > 85% de $2.00
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0, on_warning=callback)
        guard.check()
        callback.assert_called_once()

    def test_warning_callback_receives_event(self, tmp_ledger: CostLedger) -> None:
        """Callback recebe um BudgetWarningEvent."""
        events = []
        add_cost(tmp_ledger, 1.8)  # 90% de $2.00
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0, on_warning=events.append)
        guard.check()
        assert len(events) == 1
        assert isinstance(events[0], BudgetWarningEvent)

    def test_warning_callback_not_called_below_threshold(
        self, tmp_ledger: CostLedger
    ) -> None:
        """Callback NÃO deve ser chamado abaixo do limiar."""
        callback = MagicMock()
        add_cost(tmp_ledger, 1.0)  # 50% de $2.00
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0, on_warning=callback)
        guard.check()
        callback.assert_not_called()

    def test_warning_callback_called_only_once_per_day(
        self, tmp_ledger: CostLedger
    ) -> None:
        """Callback deve ser chamado no máximo uma vez por dia."""
        callback = MagicMock()
        add_cost(tmp_ledger, 1.8)  # > 85% de $2.00
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0, on_warning=callback)
        guard.check()
        guard.check()
        guard.check()
        # Deve ter sido chamado apenas uma vez
        assert callback.call_count == 1

    def test_warning_no_callback_no_error(self, tmp_ledger: CostLedger) -> None:
        """Sem callback, atingir 85% não deve levantar erro."""
        add_cost(tmp_ledger, 1.8)
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0, on_warning=None)
        bs = guard.check()  # Não deve levantar
        assert bs.warning_triggered

    def test_reset_warning_state(self, tmp_ledger: CostLedger) -> None:
        """reset_warning_state() permite novo disparo do callback."""
        callback = MagicMock()
        add_cost(tmp_ledger, 1.8)
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0, on_warning=callback)
        guard.check()
        guard.reset_warning_state()
        guard.check()
        # Deve ter sido chamado duas vezes após reset
        assert callback.call_count == 2


# ---------------------------------------------------------------------------
# BudgetGuard.check() — bloqueio a 100%
# ---------------------------------------------------------------------------


class TestBudgetGuardBlocked:
    def test_check_raises_at_100_pct(self, tmp_ledger: CostLedger) -> None:
        """Deve lançar BudgetExceededError ao atingir 100%."""
        add_cost(tmp_ledger, 2.01)  # > $2.00
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        with pytest.raises(BudgetExceededError) as exc_info:
            guard.check()
        err = exc_info.value
        assert err.daily_budget_usd == 2.0
        assert err.spent_today_usd >= 2.0
        assert err.percentage_used >= 100.0

    def test_check_raises_exactly_at_budget(self, tmp_ledger: CostLedger) -> None:
        """Deve lançar BudgetExceededError quando gasto == teto exato."""
        add_cost(tmp_ledger, 2.0)
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        with pytest.raises(BudgetExceededError):
            guard.check()

    def test_check_local_model_bypasses_block(self, tmp_ledger: CostLedger) -> None:
        """is_local_model=True deve bypasses o bloqueio mesmo a 100%."""
        add_cost(tmp_ledger, 10.0)  # orçamento destruído
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        bs = guard.check(is_local_model=True)  # Não deve lançar
        assert isinstance(bs, BudgetStatus)


# ---------------------------------------------------------------------------
# BudgetGuard.update_budget()
# ---------------------------------------------------------------------------


class TestBudgetGuardUpdateBudget:
    def test_update_budget_valid(self, tmp_ledger: CostLedger) -> None:
        """Atualização de orçamento em tempo de execução."""
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        guard.update_budget(5.0)
        assert guard.daily_budget_usd == 5.0

    def test_update_budget_to_zero(self, tmp_ledger: CostLedger) -> None:
        """Atualizar para 0.0 desativa o limite."""
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        guard.update_budget(0.0)
        assert guard.daily_budget_usd == 0.0

    def test_update_budget_negative_raises(self, tmp_ledger: CostLedger) -> None:
        """Orçamento negativo deve levantar ValueError."""
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        with pytest.raises(ValueError):
            guard.update_budget(-1.0)

    def test_check_unblocked_after_budget_increase(
        self, tmp_ledger: CostLedger
    ) -> None:
        """Aumentar orçamento deve desbloquear chamadas bloqueadas."""
        add_cost(tmp_ledger, 2.01)
        guard = make_guard(tmp_ledger, daily_budget_usd=2.0)
        with pytest.raises(BudgetExceededError):
            guard.check()
        guard.update_budget(10.0)
        bs = guard.check()  # Não deve lançar
        assert not bs.limit_reached
