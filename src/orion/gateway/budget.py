"""
O.R.I.O.N — Budget Guard (v0.3.0 Sprint 3)

Módulo de controle orçamentário diário para o Model Gateway.

Verifica o consumo antes de cada despacho de inferência, emitindo
alertas proativos ao atingir 85% do teto e bloqueando chamadas
pagas ao atingir 100%.

Referência de design: ADR-009 (Ledger de Custos no CLI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from orion.gateway.ledger import CostLedger


# ---------------------------------------------------------------------------
# Exceções Tipadas
# ---------------------------------------------------------------------------


class BudgetExceededError(Exception):
    """Levantada quando o teto diário de gastos foi atingido.

    Ao capturar esta exceção, o chamador deve redirecionar para um
    modelo local (Ollama) ou informar o usuário e interromper a tarefa.

    Attributes:
        daily_budget_usd: Limite configurado em USD.
        spent_today_usd: Total gasto até o momento.
        percentage_used: Percentual do orçamento consumido.
    """

    def __init__(
        self,
        daily_budget_usd: float,
        spent_today_usd: float,
        percentage_used: float,
    ) -> None:
        self.daily_budget_usd = daily_budget_usd
        self.spent_today_usd = spent_today_usd
        self.percentage_used = percentage_used
        super().__init__(
            f"Daily budget exceeded: ${spent_today_usd:.4f} / ${daily_budget_usd:.4f} "
            f"({percentage_used:.1f}% used). "
            "Paid API calls are blocked. Switch to a local model or increase your budget."
        )


class BudgetWarningEvent:
    """Evento emitido quando o gasto atinge o limiar de alerta (padrão 85%).

    Não interrompe o fluxo — apenas notifica para exibição ao usuário.

    Attributes:
        daily_budget_usd: Limite configurado.
        spent_today_usd: Total gasto até agora.
        percentage_used: Percentual do orçamento consumido.
        threshold_pct: Limiar que disparou o aviso (ex: 85.0).
    """

    def __init__(
        self,
        daily_budget_usd: float,
        spent_today_usd: float,
        percentage_used: float,
        threshold_pct: float,
    ) -> None:
        self.daily_budget_usd = daily_budget_usd
        self.spent_today_usd = spent_today_usd
        self.percentage_used = percentage_used
        self.threshold_pct = threshold_pct

    def __str__(self) -> str:
        return (
            f"⚠️  ORION Budget Warning: {self.percentage_used:.1f}% do orçamento diário usado "
            f"(${self.spent_today_usd:.4f} / ${self.daily_budget_usd:.4f}). "
            f"Limiar de alerta: {self.threshold_pct:.0f}%."
        )

    def __repr__(self) -> str:
        return (
            f"BudgetWarningEvent(spent={self.spent_today_usd:.4f}, "
            f"budget={self.daily_budget_usd:.4f}, pct={self.percentage_used:.1f}%)"
        )


# ---------------------------------------------------------------------------
# Budget Status
# ---------------------------------------------------------------------------


class BudgetStatus:
    """Snapshot do estado orçamentário atual.

    Attributes:
        daily_budget_usd: Limite configurado em USD.
        spent_today_usd: Total gasto hoje em USD.
        percentage_used: Percentual do orçamento consumido (0.0–100.0+).
        limit_reached: True se o limite foi atingido (>= 100%).
        warning_triggered: True se o alerta de 85% foi disparado.
        remaining_usd: Saldo restante (pode ser negativo se ultrapassado).
    """

    def __init__(
        self,
        daily_budget_usd: float,
        spent_today_usd: float,
        warning_threshold_pct: float = 85.0,
    ) -> None:
        self.daily_budget_usd = daily_budget_usd
        self.spent_today_usd = spent_today_usd
        self.percentage_used = (
            (spent_today_usd / daily_budget_usd * 100.0) if daily_budget_usd > 0 else 0.0
        )
        self.limit_reached = self.percentage_used >= 100.0
        self.warning_triggered = self.percentage_used >= warning_threshold_pct
        self.remaining_usd = max(0.0, daily_budget_usd - spent_today_usd)

    def __repr__(self) -> str:
        return (
            f"BudgetStatus(spent={self.spent_today_usd:.4f}, "
            f"budget={self.daily_budget_usd:.4f}, "
            f"pct={self.percentage_used:.1f}%, "
            f"limit_reached={self.limit_reached})"
        )


# ---------------------------------------------------------------------------
# Budget Guard
# ---------------------------------------------------------------------------


@dataclass
class BudgetGuard:
    """Controlador orçamentário diário para o Model Gateway.

    Deve ser consultado antes de cada despacho de inferência pago.
    Emite avisos via callback ao atingir o limiar e lança
    ``BudgetExceededError`` ao atingir 100% do teto.

    Exemplo de uso:
        guard = BudgetGuard(ledger=ledger, daily_budget_usd=2.0)
        try:
            guard.check()           # lança se limite atingido
        except BudgetExceededError as e:
            # redirecionar para modelo local ou abortar
            ...

    Attributes:
        ledger: CostLedger para consultar o gasto de hoje.
        daily_budget_usd: Teto diário de gastos em USD. 0.0 = sem limite.
        warning_threshold_pct: Percentual para emitir aviso (padrão 85.0).
        on_warning: Callback opcional chamado ao emitir aviso de orçamento.
    """

    ledger: CostLedger
    daily_budget_usd: float = 2.0
    warning_threshold_pct: float = 85.0
    on_warning: Optional[object] = field(default=None, repr=False)

    # Estado interno — não fazer parte do hash/eq do dataclass
    _last_warning_date: Optional[str] = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.daily_budget_usd < 0:
            raise ValueError(
                f"daily_budget_usd deve ser >= 0. Recebido: {self.daily_budget_usd}"
            )
        if not (0.0 < self.warning_threshold_pct < 100.0):
            raise ValueError(
                f"warning_threshold_pct deve estar entre 0 e 100 exclusivo. "
                f"Recebido: {self.warning_threshold_pct}"
            )

    # ── Consulta ─────────────────────────────────────────────────────────────

    def status(self) -> BudgetStatus:
        """Retorna um snapshot do estado orçamentário atual (sem efeitos colaterais)."""
        if self.daily_budget_usd == 0.0:
            # Sem limite configurado — retorna estado "livre"
            return BudgetStatus(
                daily_budget_usd=0.0,
                spent_today_usd=self.ledger.spent_today_usd(),
                warning_threshold_pct=self.warning_threshold_pct,
            )
        spent = self.ledger.spent_today_usd()
        return BudgetStatus(
            daily_budget_usd=self.daily_budget_usd,
            spent_today_usd=spent,
            warning_threshold_pct=self.warning_threshold_pct,
        )

    # ── Verificação (com efeitos colaterais) ─────────────────────────────────

    def check(self, *, is_local_model: bool = False) -> BudgetStatus:
        """Verifica o estado do orçamento antes de um despacho de inferência.

        Modelos locais (Ollama) nunca são bloqueados — têm custo zero.

        Args:
            is_local_model: Se True, pula verificação de limite (custo zero).

        Returns:
            BudgetStatus com o estado atual.

        Raises:
            BudgetExceededError: Se o teto de 100% foi atingido e o modelo
                                  não é local.
        """
        bs = self.status()

        # Modelos locais não consomem orçamento
        if is_local_model:
            return bs

        # Sem limite configurado
        if self.daily_budget_usd == 0.0:
            return bs

        # Verificar se limite foi atingido
        if bs.limit_reached:
            raise BudgetExceededError(
                daily_budget_usd=self.daily_budget_usd,
                spent_today_usd=bs.spent_today_usd,
                percentage_used=bs.percentage_used,
            )

        # Emitir aviso se limiar atingido (uma vez por dia)
        if bs.warning_triggered:
            today = datetime.now(timezone.utc).date().isoformat()
            if self._last_warning_date != today:
                self._last_warning_date = today
                event = BudgetWarningEvent(
                    daily_budget_usd=self.daily_budget_usd,
                    spent_today_usd=bs.spent_today_usd,
                    percentage_used=bs.percentage_used,
                    threshold_pct=self.warning_threshold_pct,
                )
                if self.on_warning and callable(self.on_warning):
                    self.on_warning(event)  # type: ignore[operator]

        return bs

    def reset_warning_state(self) -> None:
        """Reseta o estado de aviso (útil para testes e virada de dia)."""
        self._last_warning_date = None

    def update_budget(self, new_daily_budget_usd: float) -> None:
        """Atualiza o teto diário de gastos em tempo de execução.

        Args:
            new_daily_budget_usd: Novo teto em USD (>= 0). 0.0 = sem limite.

        Raises:
            ValueError: Se o valor for negativo.
        """
        if new_daily_budget_usd < 0:
            raise ValueError(
                f"daily_budget_usd deve ser >= 0. Recebido: {new_daily_budget_usd}"
            )
        self.daily_budget_usd = new_daily_budget_usd
