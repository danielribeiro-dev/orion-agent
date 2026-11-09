"""Infra de teste dos subagents: gateway falso (custo zero real), pai real e runner montado."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.agents.budget import DailyBudget
from orion.agents.definitions import AgentCatalog, load_agents
from orion.agents.loop_thread import NotificationQueue, ThreadExecutor
from orion.agents.models import AgentResult, ResolvedModel, TaskRecord
from orion.agents.ports import LLMPort, NoSuitableModel
from orion.agents.refs import resolve_ref
from orion.agents.runner import AgentRunner, ParentHandle, RunnerDeps
from orion.agents.tasks import SqliteTaskStore, TaskManager
from orion.core.engine import ModelTurn
from orion.core.event_bus import EventBus
from orion.gateway.models import LLMMessage, TokenUsage, ToolSpec
from orion.governance.audit import AuditLogger
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import WorkspaceScope
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.runtime.tools.task import TaskTool
from orion.runtime.tools.tasks import (
    SendMessageTool,
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskStopTool,
)
from orion.settings.models import AgentsSettings, HookSpec, ResolvedAgents
from tests.llm_script import ScriptedLLM, say

DEFAULT_MODEL = ResolvedModel(
    model_id="fake-balanced",
    tier="balanced",
    cost_input_m=1.0,
    cost_output_m=5.0,
    context_window=200_000,
)


@dataclass
class FakeGateway:
    """Gateway sem rede: cada ``make_llm`` consome o próximo roteiro de ``scripts``."""

    scripts: list[ScriptedLLM] = field(default_factory=list)
    cost_per_call: float = 0.001
    model: ResolvedModel = DEFAULT_MODEL
    fail_resolve: str | None = None
    resolved: list[dict[str, Any]] = field(default_factory=list)
    made: list[dict[str, Any]] = field(default_factory=list)
    on_call: Callable[[], Any] | None = None

    def resolve(
        self,
        *,
        tier: str,
        mutating: bool,
        profile: str | None = None,
        pinned: str | None = None,
        reuse: str | None = None,
    ) -> ResolvedModel:
        self.resolved.append(
            {"tier": tier, "mutating": mutating, "profile": profile, "pinned": pinned, "reuse": reuse}
        )
        if self.fail_resolve:
            raise NoSuitableModel(self.fail_resolve)
        if reuse:
            return self.model.model_copy(update={"model_id": reuse})
        return self.model

    def make_llm(
        self,
        model: ResolvedModel,
        *,
        agent_id: str,
        origin: str,
        max_tokens: int,
        on_usage: Callable[[ResolvedModel, TokenUsage, float], None],
    ) -> LLMPort:
        script = self.scripts[len(self.made)] if len(self.made) < len(self.scripts) else ScriptedLLM(say("ok"), repeat=True)
        self.made.append({"agent_id": agent_id, "origin": origin, "max_tokens": max_tokens, "script": script})

        async def llm(*, system: str, messages: list[LLMMessage], tools: list[ToolSpec]) -> ModelTurn:
            if self.on_call is not None:
                result = self.on_call()
                if hasattr(result, "__await__"):
                    await result
            turn = await script(system=system, messages=messages, tools=tools)
            on_usage(model, TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120), self.cost_per_call)
            return turn

        return llm


@dataclass
class Rig:
    """Pai real (PEP + runtime), catálogo e runner prontos para teste."""

    home: Path
    workspace: Path
    pep: PolicyEnforcementPoint
    runtime: LocalRuntimeProvider
    gateway: FakeGateway
    runner: AgentRunner
    parent: ParentHandle
    audit: AuditLogger
    catalog: AgentCatalog
    child_buses: list[str] = field(default_factory=list)


def make_rig(
    tmp_path: Path,
    scripts: list[ScriptedLLM] | None = None,
    *,
    mode: AutonomyMode = AutonomyMode.WORKSPACE_AUTO,
    limits: AgentsSettings | None = None,
    daily_headroom: Callable[[], float | None] = lambda: None,
    gateway: FakeGateway | None = None,
    extra_agents: dict[str, str] | None = None,
    parent_confirm: bool = True,
    hook_specs: dict[str, list[HookSpec]] | None = None,
    bus: EventBus | None = None,
    workspace_port: Any = None,
) -> Rig:
    home = tmp_path / "home"
    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    home.mkdir(parents=True, exist_ok=True)
    for name, text in (extra_agents or {}).items():
        agents_dir = home / "agents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / f"{name}.md").write_text(text, encoding="utf-8")
    scope = WorkspaceScope([workspace])
    audit = AuditLogger(home / "audit.log")
    pep = PolicyEnforcementPoint(
        scope=scope, mode=mode, audit_logger=audit, confirm=lambda _p: parent_confirm
    )
    runtime = LocalRuntimeProvider(pep=pep, scope=scope)
    runtime.set_ref_resolver(lambda ref: resolve_ref(ref, home))
    resolved: ResolvedAgents = (limits or AgentsSettings()).resolved()
    catalog = load_agents(home, workspace, limits=resolved)
    gw = gateway or FakeGateway(scripts=scripts or [])
    deps = RunnerDeps(
        home=home,
        workspace=workspace,
        session_id="sess-test",
        gateway=gw,  # type: ignore[arg-type]
        catalog=lambda: catalog,
        limits=lambda: resolved,
        hook_specs=lambda: hook_specs or {},
        audit=audit,
        daily=DailyBudget(daily_headroom),
        bus=bus,
        workspace_port=workspace_port,
    )
    runner = AgentRunner(deps)
    parent = ParentHandle(pep=pep, runtime=runtime)
    runtime.register_tool(TaskTool(runner.bind(parent)))
    return Rig(home, workspace, pep, runtime, gw, runner, parent, audit, catalog)


# ── Segundo plano (Sprint 6B) ───────────────────────────────────────────────


@dataclass
class TaskRig:
    """Rig + executor em thread, store SQLite, fila de notificações e TaskManager."""

    rig: Rig
    manager: TaskManager
    queue: NotificationQueue
    executor: ThreadExecutor
    store: SqliteTaskStore
    results: list[tuple[AgentResult, TaskRecord]] = field(default_factory=list)

    def close(self) -> None:
        self.executor.shutdown(timeout=3)


def make_task_rig(tmp_path: Path, scripts: list[ScriptedLLM] | None = None, **kwargs: Any) -> TaskRig:
    rig = make_rig(tmp_path, scripts, **kwargs)
    queue = NotificationQueue()
    executor = ThreadExecutor()
    store = SqliteTaskStore(rig.home / "tasks.db")
    results: list[tuple[AgentResult, TaskRecord]] = []
    manager = TaskManager(
        store=store,
        executor=executor,
        runner=rig.runner,
        notifier=queue,
        owner="sess-test",
        on_result=lambda result, rec: results.append((result, rec)),
    )
    for tool in (
        TaskCreateTool(manager, rig.parent),
        TaskListTool(manager),
        TaskGetTool(manager),
        TaskStopTool(manager),
        SendMessageTool(manager),
    ):
        rig.runtime.register_tool(tool)
    return TaskRig(rig, manager, queue, executor, store, results)


async def wait_until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Espera ativa (assíncrona) por uma condição produzida por outra thread."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condição não ocorreu a tempo")
        await asyncio.sleep(0.01)
