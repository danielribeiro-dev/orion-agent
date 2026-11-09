"""``/loop`` — verificações recorrentes em processo, com triagem antes de acordar o modelo.

Cada disparo é um subagent de orçamento limitado (origem ``loop`` no ledger). O que evita gasto
inútil é a **triagem**, que roda ANTES do modelo (:class:`TriagePort`):

1. determinística e grátis: a impressão digital do repositório (``HEAD`` + ``status`` + ``diff``)
   não mudou desde o último disparo => o modelo nem é acordado;
2. só se for inconclusiva (sem git, por exemplo) pergunta a um modelo do tier ``fast`` com
   ``max_tokens`` mínimo; sem modelo disponível, acorda (o teto de disparos continua valendo).

Tetos no código: expiração (7 dias por padrão), máximo de disparos, orçamento e turnos por
disparo, no máximo ``MAX_LOOPS`` ativos. Sem LLM em espera: o intervalo é um ``sleep``. Os loops
vivem na thread de fundo da sessão e morrem com ela; persistência durável e cron real são da
Sprint 7.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import subprocess
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from orion.agents.loop_thread import ThreadExecutor
from orion.agents.models import (
    AgentEventEnvelope,
    TriageContext,
    TriageDecision,
)
from orion.agents.ports import ModelGatewayPort, NoSuitableModel, NotifierPort, TriagePort
from orion.agents.runner import ParentHandle, TaskRequest
from orion.agents.tasks import TaskManager
from orion.gateway.models import LLMMessage, MessageRole

logger = logging.getLogger(__name__)

DEFAULT_TTL_S = 7 * 24 * 3600
DEFAULT_MAX_FIRES = 50
DEFAULT_BUDGET_USD = 0.05
DEFAULT_MAX_TURNS = 8
MIN_INTERVAL_S = 30.0
DYNAMIC_START_S = 60.0
DYNAMIC_MAX_S = 1800.0
MAX_LOOPS = 5
_MAX_DIFF_BYTES = 5_000_000
_INTERVAL = re.compile(r"^(\d+)\s*([smhd])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_interval(text: str) -> float | None:
    """``30s``, ``5m``, ``2h``, ``1d`` -> segundos; ``None`` se o texto não é um intervalo."""
    found = _INTERVAL.match(text.strip().lower())
    return float(int(found.group(1)) * _UNITS[found.group(2)]) if found else None


# ---------------------------------------------------------------------------
# Triagem
# ---------------------------------------------------------------------------


class DeterministicTriage:
    """Acorda o modelo só se o repositório mudou desde o último disparo (custo zero)."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace
        self._last: dict[str, str] = {}

    def fingerprint(self) -> str | None:
        """Hash do estado do repositório; ``None`` fora de um repositório git."""
        def run(*args: str) -> bytes | None:
            try:
                done = subprocess.run(  # noqa: S603 - argumentos fixos
                    ["git", *args], cwd=self._workspace, capture_output=True, check=False, timeout=20
                )
            except (OSError, subprocess.SubprocessError):
                return None
            return done.stdout if done.returncode == 0 else None

        head = run("rev-parse", "HEAD")
        status = run("status", "--porcelain", "--untracked-files=all")
        if head is None or status is None:
            return None
        diff = run("diff", "HEAD") or b""
        digest = hashlib.sha256()
        for chunk in (head, status, diff[:_MAX_DIFF_BYTES]):
            digest.update(chunk + b"\0")
        return digest.hexdigest()

    async def should_wake(self, ctx: TriageContext) -> TriageDecision:
        current = await asyncio.to_thread(self.fingerprint)
        if current is None:
            return TriageDecision(wake=True, reason="não há como medir mudanças aqui", conclusive=False)
        previous = self._last.get(ctx.loop_id)
        if previous == current:
            return TriageDecision(wake=False, reason="nada mudou desde o último disparo")
        self._last[ctx.loop_id] = current
        return TriageDecision(wake=True, reason="primeiro disparo" if previous is None else "o repositório mudou")


class ModelTriage:
    """Segundo estágio, só para o inconclusivo: uma chamada ``fast`` de ``max_tokens`` mínimo."""

    def __init__(self, gateway: ModelGatewayPort, max_tokens: int = 8) -> None:
        self._gateway = gateway
        self._max_tokens = max_tokens

    async def should_wake(self, ctx: TriageContext) -> TriageDecision:
        try:
            model = self._gateway.resolve(tier="fast", mutating=False)
        except NoSuitableModel:
            return TriageDecision(wake=True, reason="sem modelo para triagem", conclusive=False)
        llm = self._gateway.make_llm(
            model,
            agent_id=f"triage_{ctx.loop_id}",
            origin="loop",
            max_tokens=self._max_tokens,
            on_usage=lambda *_: None,
        )
        question = (
            f"Loop goal: {ctx.goal}\nLast result ({ctx.last_status or 'none'}): "
            f"{ctx.last_summary[:600] or '(none)'}\nShould the goal be checked again now? "
            "Answer exactly WAKE or SKIP."
        )
        try:
            turn = await llm(
                system="You triage recurring checks. Answer with one word.",
                messages=[LLMMessage(role=MessageRole.USER, content=question)],
                tools=[],
            )
        except Exception as exc:  # triagem nunca derruba o loop
            logger.info("ModelTriage falhou (%s); acordando por segurança", exc)
            return TriageDecision(wake=True, reason="triagem indisponível", conclusive=False)
        answer = turn.text.strip().upper()
        if answer.startswith("SKIP"):
            return TriageDecision(wake=False, reason="o modelo de triagem disse SKIP")
        return TriageDecision(wake=True, reason="o modelo de triagem disse WAKE")


class ChainedTriage:
    """Determinística primeiro; o modelo barato só quando ela é inconclusiva."""

    def __init__(self, first: TriagePort, second: TriagePort | None = None) -> None:
        self._first = first
        self._second = second

    async def should_wake(self, ctx: TriageContext) -> TriageDecision:
        decision = await self._first.should_wake(ctx)
        if decision.conclusive or self._second is None:
            return decision
        return await self._second.should_wake(ctx)


# ---------------------------------------------------------------------------
# Estado e agendador
# ---------------------------------------------------------------------------


@dataclass
class LoopState:
    """Um loop ativo ou encerrado (em memória, vive com a sessão)."""

    loop_id: str
    goal: str
    agent: str
    interval_s: float | None  # None = dinâmico
    expires_at: float
    max_fires: int
    budget_usd: float
    max_turns: int
    created_at: float
    status: str = "active"  # active | expired | stopped | done
    checks: int = 0
    fires: int = 0
    skipped: int = 0
    cost_usd: float = 0.0
    last_summary: str = ""
    last_status: str = ""
    last_reason: str = ""
    next_in_s: float = 0.0
    last_task_id: str = ""
    #: o ``concurrent.futures.Future`` do agendador (para cancelar)
    future: object = field(default=None, repr=False)

    @property
    def active(self) -> bool:
        return self.status == "active"


class LoopScheduler:
    """Dispara subagents recorrentes na thread de fundo, com tetos e triagem."""

    def __init__(
        self,
        *,
        executor: ThreadExecutor,
        manager: TaskManager,
        parent: Callable[[], ParentHandle],
        triage: TriagePort,
        notifier: NotifierPort,
        owner: str,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        min_interval_s: float = MIN_INTERVAL_S,
        dynamic_start_s: float = DYNAMIC_START_S,
    ) -> None:
        self._executor = executor
        self._manager = manager
        self._parent = parent
        self._triage = triage
        self._notifier = notifier
        self._owner = owner
        self._clock = clock
        self._sleep = sleep
        self._min_interval = min_interval_s
        self._dynamic_start = dynamic_start_s
        self._loops: dict[str, LoopState] = {}

    # ------------------------------------------------------------------

    def start(
        self,
        goal: str,
        *,
        interval_s: float | None = None,
        agent: str = "explore",
        ttl_s: float = DEFAULT_TTL_S,
        max_fires: int = DEFAULT_MAX_FIRES,
        budget_usd: float = DEFAULT_BUDGET_USD,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> LoopState:
        """Cria o loop. Levanta ``ValueError`` se violar os tetos (nunca há "sem limite")."""
        if not goal.strip():
            raise ValueError("informe o que verificar")
        if interval_s is not None and interval_s < self._min_interval:
            raise ValueError(f"intervalo mínimo: {self._min_interval:g}s")
        if ttl_s <= 0 or max_fires < 1 or budget_usd <= 0 or max_turns < 1:
            raise ValueError("expiração, disparos, orçamento e turnos precisam ser positivos")
        if sum(1 for s in self._loops.values() if s.active) >= MAX_LOOPS:
            raise ValueError(f"no máximo {MAX_LOOPS} loops ativos")
        now = self._clock()
        state = LoopState(
            loop_id=f"loop_{uuid.uuid4().hex[:6]}",
            goal=goal.strip(),
            agent=agent,
            interval_s=interval_s,
            expires_at=now + ttl_s,
            max_fires=max_fires,
            budget_usd=budget_usd,
            max_turns=max_turns,
            created_at=now,
        )
        self._loops[state.loop_id] = state
        state.future = self._executor.run_coroutine(self._run(state))
        return state

    def list(self) -> list[LoopState]:
        return sorted(self._loops.values(), key=lambda s: s.created_at)

    def get(self, loop_id: str) -> LoopState | None:
        return self._loops.get(loop_id)

    def active_count(self) -> int:
        return sum(1 for s in self._loops.values() if s.active)

    def stop(self, loop_id: str) -> bool:
        state = self._loops.get(loop_id)
        if state is None or not state.active:
            return False
        state.status = "stopped"
        future = state.future
        if future is not None and hasattr(future, "cancel"):
            future.cancel()
        return True

    def stop_all(self) -> int:
        return sum(1 for loop_id in list(self._loops) if self.stop(loop_id))

    # ------------------------------------------------------------------

    def _interval(self, state: LoopState, current: float) -> float:
        return state.interval_s if state.interval_s is not None else current

    async def _run(self, state: LoopState) -> None:
        current = self._dynamic_start
        try:
            while state.active:
                wait = min(self._interval(state, current), max(state.expires_at - self._clock(), 0.0))
                state.next_in_s = wait
                await self._sleep(wait)
                if self._clock() >= state.expires_at:
                    self._end(state, "expired", "loop.expired", "expirou")
                    return
                state.checks += 1
                decision = await self._triage.should_wake(
                    TriageContext(
                        loop_id=state.loop_id,
                        goal=state.goal,
                        fired=state.fires,
                        last_summary=state.last_summary,
                        last_status=state.last_status,
                    )
                )
                state.last_reason = decision.reason
                if not decision.wake:
                    state.skipped += 1
                    current = min(current * 2, DYNAMIC_MAX_S)  # dinâmico: sem novidade, espaça
                    continue
                if state.fires >= state.max_fires:
                    self._end(state, "done", "loop.done", f"atingiu {state.max_fires} disparos")
                    return
                state.fires += 1
                current = self._dynamic_start
                await self._fire(state)
        except asyncio.CancelledError:
            if state.status == "active":
                state.status = "stopped"
            raise

    async def _fire(self, state: LoopState) -> None:
        context = f"Previous check result:\n{state.last_summary[:1500]}" if state.last_summary else ""
        request = TaskRequest(
            agent=state.agent,
            goal=state.goal,
            context=context,
            origin="loop",
            budget_usd=state.budget_usd,
            max_turns=state.max_turns,
        )
        rec = self._manager.start(request, self._parent())
        state.last_task_id = rec.task_id
        result = await self._manager.wait(rec.task_id)
        if result is not None:
            state.last_summary = result.summary
            state.last_status = result.status
            state.cost_usd += result.usage.cost_usd

    def _end(self, state: LoopState, status: str, kind: str, why: str) -> None:
        state.status = status
        self._notifier.notify(
            AgentEventEnvelope(
                agent_id=state.loop_id,
                session_id=self._owner,
                origin="loop",
                kind=kind,
                payload={
                    "loop_id": state.loop_id,
                    "goal": state.goal[:200],
                    "why": why,
                    "fires": state.fires,
                    "cost_usd": state.cost_usd,
                },
            )
        )


def describe(state: LoopState) -> str:
    """Linha de status para ``/loop list``."""
    every = "dinâmico" if state.interval_s is None else f"{state.interval_s:g}s"
    return (
        f"{state.loop_id} · {state.status} · a cada {every} · disparos {state.fires}/{state.max_fires} · "
        f"pulados {state.skipped} · ${state.cost_usd:.4f} · {state.goal[:60]}"
    )

