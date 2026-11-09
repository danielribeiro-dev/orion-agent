"""Portas do núcleo de agentes (ADR-031).

``agents/`` só conhece estas interfaces. Nenhum campo de provedor (ex.: ``cache_control``)
atravessa a fronteira: quem fala com a Anthropic, o OpenRouter ou o Ollama é o adaptador
que implementa :class:`ModelGatewayPort`. Novos executores (daemon, processo, remoto),
armazenamentos e notificadores entram como adaptadores, sem reescrever o runner.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from orion.agents.models import (
    AgentEventEnvelope,
    AgentResult,
    ResolvedModel,
    TaskRecord,
    TaskStatus,
    TriageContext,
    TriageDecision,
    WorkspaceOutcome,
)

if TYPE_CHECKING:
    from orion.core.engine import ModelTurn
    from orion.gateway.models import LLMMessage, TokenUsage, ToolSpec
    from orion.governance.permissions import WorkspaceScope


class LLMPort(Protocol):
    """= a callable do engine: ``await llm(system=..., messages=..., tools=...) -> ModelTurn``."""

    async def __call__(
        self, *, system: str, messages: list[LLMMessage], tools: list[ToolSpec]
    ) -> ModelTurn: ...


class NoSuitableModel(Exception):
    """Nenhum candidato adequado para o tier pedido (sem downgrade silencioso, CA-11)."""


@runtime_checkable
class ModelGatewayPort(Protocol):
    """Resolve tiers em modelos e entrega chamadas isoladas da sessão (breaker, UI, contadores)."""

    def resolve(
        self,
        *,
        tier: str,
        mutating: bool,
        profile: str | None = None,
        pinned: str | None = None,
        reuse: str | None = None,
    ) -> ResolvedModel:
        """Modelo efetivo ou :class:`NoSuitableModel`. ``reuse`` fixa o modelo de uma retomada."""
        ...

    def make_llm(
        self,
        model: ResolvedModel,
        *,
        agent_id: str,
        origin: str,
        max_tokens: int,
        on_usage: Callable[[ResolvedModel, TokenUsage, float], None],
    ) -> LLMPort:
        """Callable de LLM do filho. Nunca toca breaker, renderer, status bar ou contadores do pai.

        ``on_usage(modelo_que_respondeu, uso, custo_usd)`` roda após cada chamada, já com o custo real.
        """
        ...


class TaskHandle(Protocol):
    """Alça de uma execução submetida a um :class:`ExecutorPort`."""

    agent_id: str

    def done(self) -> bool: ...

    async def wait(self) -> AgentResult: ...


class ExecutorPort(Protocol):
    """Onde um subagent roda: 6A no loop do turno; 6B em thread; Sprint 7 no daemon."""

    def submit(
        self, coro_factory: Callable[[], Awaitable[AgentResult]], *, agent_id: str
    ) -> TaskHandle: ...

    async def cancel(self, agent_id: str) -> None: ...


class TaskStorePort(Protocol):
    """Persistência de tasks (6B: SQLite; a Sprint 7 reaproveita o esquema)."""

    def upsert(self, rec: TaskRecord) -> None: ...

    def get(self, task_id: str) -> TaskRecord | None: ...

    def list(self, *, status: TaskStatus | None = None) -> list[TaskRecord]: ...


class NotifierPort(Protocol):
    """Entrega de eventos ao Senhor (6B: fila em processo; Sprint 7: notify-send/Telegram)."""

    def notify(self, event: AgentEventEnvelope) -> None: ...


class WorkspacePort(Protocol):
    """Onde o filho escreve: o workspace compartilhado, um worktree (6B) ou, no futuro, sandbox."""

    async def prepare(self, agent_id: str) -> WorkspaceScope: ...

    async def release(self, agent_id: str, *, keep_if_changed: bool) -> WorkspaceOutcome: ...


class TriagePort(Protocol):
    """Decide se um disparo de ``/loop`` precisa acordar o modelo (determinístico primeiro)."""

    async def should_wake(self, ctx: TriageContext) -> TriageDecision: ...
