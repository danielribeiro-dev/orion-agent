"""Tipos compartilhados do núcleo de agentes (Sprint 6, ADR-028 a 031).

Tudo aqui é serializável em JSON: o mesmo envelope servirá de payload ao IPC do daemon
(Sprint 7), ao desktop (v0.7.0) e à voz (v0.6.0). Nenhum campo é específico de provedor.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Origin = Literal["user", "subagent", "loop", "cron", "daemon"]
AgentStatus = Literal[
    "ok",
    "partial_budget",
    "partial_turns",
    "partial_timeout",
    "cancelled",
    "error",
    "schema_invalid",
]
#: Estados em que o filho parou no meio do trabalho e pode ser retomado.
RESUMABLE_STATUSES: frozenset[str] = frozenset(
    {"partial_budget", "partial_turns", "partial_timeout"}
)


class UsageTotals(BaseModel):
    """Uso acumulado (tokens, cache e custo) de um agente."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0

    def add(
        self,
        *,
        prompt: int = 0,
        completion: int = 0,
        cached: int = 0,
        cache_write: int = 0,
        cost_usd: float = 0.0,
    ) -> None:
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached
        self.cache_write_tokens += cache_write
        self.cost_usd = round(self.cost_usd + cost_usd, 8)
        self.calls += 1

    def merge(self, other: UsageTotals) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cached_tokens += other.cached_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.cost_usd = round(self.cost_usd + other.cost_usd, 8)
        self.calls += other.calls


class ResolvedModel(BaseModel):
    """Modelo efetivo de um agente, já resolvido a partir de tier/perfil (ADR-031)."""

    model_config = ConfigDict(frozen=True)

    model_id: str
    tier: Literal["fast", "balanced", "heavy"]
    is_local: bool = False
    cost_input_m: float = 0.0
    cost_output_m: float = 0.0
    context_window: int = 100_000
    supports_prompt_cache: bool = False
    supports_tool_use: bool = True


class AgentResult(BaseModel):
    """Resultado de um subagent: resumo curto + referência ao completo em disco."""

    agent_id: str
    status: AgentStatus
    summary: str
    ref: str
    model_used: str = ""
    usage: UsageTotals = Field(default_factory=UsageTotals)
    resumable: bool = False
    agent: str = ""
    turns: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class AgentEventEnvelope(BaseModel):
    """Envelope JSON estável de eventos de agente (ADR-029)."""

    agent_id: str
    parent_id: str | None = None
    session_id: str
    origin: Origin = "subagent"
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TaskStatus(StrEnum):
    """Ciclo de vida de uma task (6B)."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"  # a sessão terminou com a task em andamento

    @property
    def terminal(self) -> bool:
        return self not in (TaskStatus.PENDING, TaskStatus.RUNNING)


class TaskRecord(BaseModel):
    """Linha persistida de uma task em segundo plano (``~/.orion/tasks.db``)."""

    task_id: str
    owner: str  # session_id dono
    agent: str
    goal: str
    status: TaskStatus = TaskStatus.PENDING
    origin: Origin = "subagent"
    model_tier: str = ""
    model_used: str = ""
    ref: str = ""
    summary: str = ""
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None
    resumable: bool = False


class WorkspaceOutcome(BaseModel):
    """O que sobrou de um workspace isolado ao liberá-lo."""

    kept: bool = False
    path: str = ""
    branch: str = ""
    changed_files: list[str] = Field(default_factory=list)


class TriageContext(BaseModel):
    """Contexto entregue ao gancho de triagem do ``/loop`` (6B)."""

    loop_id: str
    goal: str
    fired: int
    last_summary: str = ""
    last_status: str = ""


class TriageDecision(BaseModel):
    """Resposta da triagem: acordar o modelo ou não, e por quê."""

    wake: bool
    reason: str = ""
    conclusive: bool = True  # False = inconclusivo; o chamador pode escalar para tier fast
