"""Orçamento de agentes com reserva antecipada (ADR-030).

Três níveis encadeados, todos verificados *antes* de cada chamada paga:

    AgentBudget (filho)  ->  AggregateBudget (uma chamada de ``task``)  ->  teto diário

Cada nível guarda o que já gastou e o que está reservado por chamadas em voo. Reservar
estima o pior caso da chamada (prompt + ``max_tokens`` de saída ao preço do modelo) e
falha se qualquer nível da cadeia não comporta: assim N filhos em paralelo não
ultrapassam o teto por checarem ao mesmo tempo (TOCTOU). Ao receber o uso real, a
reserva é convertida em gasto. Estouro nunca levanta no meio do trabalho do filho: o
runner devolve um resultado parcial marcado e retomável.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from orion.agents.models import ResolvedModel

#: Uma trava única: as cadeias de reserva são curtas e a contenção é desprezível.
_LOCK = threading.RLock()


class BudgetExhausted(Exception):
    """Algum nível da cadeia não comporta a chamada (ou turnos/tempo acabaram)."""

    def __init__(self, scope: str, detail: str) -> None:
        self.scope = scope  # "agent" | "aggregate" | "daily" | "turns" | "time"
        self.detail = detail
        super().__init__(f"{scope}: {detail}")


@dataclass
class Reservation:
    """Valor reservado em cada nível da cadeia até o uso real ser conhecido."""

    usd: float
    settled: bool = False


class BudgetNode:
    """Um nível de teto em USD. ``cap_usd=None`` não limita este nível (o pai ainda limita)."""

    scope = "agent"

    def __init__(
        self,
        cap_usd: float | None,
        *,
        parent: BudgetNode | None = None,
        headroom: Callable[[], float | None] | None = None,
    ) -> None:
        self.cap_usd = cap_usd
        self.parent = parent
        self._headroom = headroom
        self.spent = 0.0
        self.reserved = 0.0

    def available(self) -> float | None:
        """Quanto ainda cabe neste nível (``None`` = sem teto próprio)."""
        with _LOCK:
            room: list[float] = []
            if self.cap_usd is not None:
                room.append(self.cap_usd - self.spent - self.reserved)
            if self._headroom is not None:
                outside = self._headroom()
                if outside is not None:
                    room.append(outside - self.reserved)
            return min(room) if room else None

    def reserve(self, usd: float) -> Reservation:
        """Reserva *usd* em toda a cadeia (tudo ou nada)."""
        with _LOCK:
            node: BudgetNode | None = self
            while node is not None:
                left = node.available()
                if left is not None and usd > left + 1e-12:
                    raise BudgetExhausted(
                        node.scope,
                        f"preciso de até ${usd:.4f}, restam ${max(left, 0.0):.4f}",
                    )
                node = node.parent
            node = self
            while node is not None:
                node.reserved += usd
                node = node.parent
            return Reservation(usd)

    def settle(self, reservation: Reservation, actual_usd: float) -> None:
        """Troca a reserva pelo gasto real, em toda a cadeia (idempotente)."""
        with _LOCK:
            if reservation.settled:
                return
            reservation.settled = True
            node: BudgetNode | None = self
            while node is not None:
                node.reserved = max(0.0, node.reserved - reservation.usd)
                node.spent += actual_usd
                node = node.parent

    def release(self, reservation: Reservation) -> None:
        """Devolve uma reserva sem gasto (a chamada falhou antes de custar)."""
        self.settle(reservation, 0.0)


class AggregateBudget(BudgetNode):
    """Teto somado dos filhos de uma única chamada da tool ``task``."""

    scope = "aggregate"


class DailyBudget(BudgetNode):
    """Raiz da cadeia: o teto diário global, lido do ledger (só rastreia o reservado)."""

    scope = "daily"

    def __init__(self, headroom: Callable[[], float | None]) -> None:
        super().__init__(None, headroom=headroom)


class AgentBudget(BudgetNode):
    """Orçamento de um filho: USD, turnos de modelo e tempo de parede."""

    scope = "agent"

    def __init__(
        self,
        usd: float | None,
        *,
        max_turns: int,
        timeout_s: float | None = None,
        parent: BudgetNode | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(usd, parent=parent)
        self.max_turns = max_turns
        self.timeout_s = timeout_s
        self.turns = 0
        self._clock = clock
        self._started = clock()

    def start_clock(self) -> None:
        self._started = self._clock()

    def elapsed(self) -> float:
        return self._clock() - self._started

    def check_before_call(self) -> None:
        """Turnos e tempo são tetos duros: o filho para antes de nova chamada."""
        if self.turns >= self.max_turns:
            raise BudgetExhausted("turns", f"{self.max_turns} turnos de modelo usados")
        if self.timeout_s is not None and self.elapsed() >= self.timeout_s:
            raise BudgetExhausted("time", f"{self.timeout_s:g}s de tempo de parede esgotados")

    def reserve_call(self, estimate_usd: float) -> Reservation:
        """Confere turnos/tempo e reserva o pior caso da chamada na cadeia."""
        self.check_before_call()
        reservation = self.reserve(estimate_usd)
        self.turns += 1
        return reservation


def estimate_call_usd(model: ResolvedModel, prompt_tokens: int, max_output_tokens: int) -> float:
    """Pior caso de uma chamada: prompt inteiro a preço cheio + saída máxima (local = 0)."""
    if model.is_local:
        return 0.0
    return (
        prompt_tokens * model.cost_input_m / 1_000_000
        + max_output_tokens * model.cost_output_m / 1_000_000
    )
