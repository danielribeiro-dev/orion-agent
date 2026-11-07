"""
O.R.I.O.N TUI — Agent Session.

Liga o Stream CLI ao núcleo: Model Gateway em streaming, ReAct Engine, PEP e
ferramentas. Mantém o estado que sobrevive entre turnos (conversa, modo, custos,
mudanças de arquivo e ramificações de contexto).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from rich.console import Console, RenderableType

from orion.core.engine import ModelTurn, ReActEngine, compose_system
from orion.core.errors import PromptInjectionSuspected, TurnBudgetExceeded
from orion.core.event_bus import EventBus
from orion.core.events import Action, ActionEmitted, Observation
from orion.gateway.budget import BudgetExceededError, BudgetGuard
from orion.gateway.circuit_breaker import CircuitBreaker
from orion.gateway.credentials import load_anthropic_key
from orion.gateway.failover import FailoverEvent, FailoverProvider, build_candidates
from orion.gateway.ledger import CostLedger
from orion.gateway.models import (
    CacheControl,
    ComplexityTier,
    ContentBlock,
    LLMMessage,
    LLMRequest,
    MessageRole,
    ModelSpec,
    ProviderName,
    ThinkingConfig,
    TokenUsage,
    ToolSpec,
)
from orion.gateway.providers.base import BaseLLMProvider
from orion.gateway.registry import ModelRegistry
from orion.gateway.router import (
    ANTHROPIC_TIER_MODELS,
    ModelRouter,
    RoutingMode,
)
from orion.governance.audit import AuditLogger
from orion.governance.pep import AutonomyMode, PolicyEnforcementPoint
from orion.governance.permissions import ActionLevel, WorkspaceScope
from orion.memory.timeline import TimelineManager
from orion.runtime.local_provider import LocalRuntimeProvider
from orion.timeline.branch_manager import BranchManager
from orion.timeline.compactor import ContextCompactor, TurnData, estimate_tokens
from orion.tui.completer import resolve_mentions
from orion.tui.diff_viewer import FileDiff, diff_texts
from orion.tui.status_bar import ReasoningEffort, SessionStatusBar
from orion.tui.stream_renderer import StreamRenderer

logger = logging.getLogger(__name__)

_MAX_MENTION_CHARS = 20_000
_MUTATING_TOOLS = {"write_file", "edit_file"}
PLAN_MODE_NOTE = "\nPlan mode is active: read only. Every mutation is denied. Finish with a plan for approval."


class AgentMode(StrEnum):
    """Modos operacionais de CLI_DESIGN_SYSTEM §5.1."""

    PLAN = "plan"
    ACCEPT_EDITS = "accept-edits"
    AUTO = "auto"
    MANUAL = "manual"


MODE_CYCLE = [AgentMode.PLAN, AgentMode.ACCEPT_EDITS, AgentMode.AUTO, AgentMode.MANUAL]
_MODE_RULES: dict[AgentMode, tuple[AutonomyMode, int]] = {
    AgentMode.PLAN: (AutonomyMode.SUPERVISED, 1),
    AgentMode.ACCEPT_EDITS: (AutonomyMode.WORKSPACE_AUTO, 2),
    AgentMode.AUTO: (AutonomyMode.FULLY_AUTO, 2),
    AgentMode.MANUAL: (AutonomyMode.SUPERVISED, 3),
}
EFFORT_CYCLE = [
    ReasoningEffort.HIGH,
    ReasoningEffort.MEDIUM,
    ReasoningEffort.LOW,
    ReasoningEffort.OFF,
]

PepAsker = Callable[[Action, ActionLevel], Awaitable[Any]]
ProviderFactory = Callable[[ModelSpec], BaseLLMProvider]


@dataclass(frozen=True)
class FileChange:
    """Uma mutação aplicada; before None significa arquivo criado."""

    path: Path
    before: str | None
    after: str


class ChangeTracker:
    """Fotografa arquivos antes das ferramentas para /diff, /undo e os painéis de diff."""

    def __init__(self) -> None:
        self.changes: list[FileChange] = []
        self._pending: dict[str, tuple[Path, str | None]] = {}

    @staticmethod
    def _read(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def begin(self, action_id: str, path: Path) -> None:
        """Guarda o conteúdo anterior do arquivo."""
        self._pending[action_id] = (path, self._read(path))

    def finish(self, action_id: str) -> FileChange | None:
        """Compara com o disco e registra a mudança, se houver."""
        entry = self._pending.pop(action_id, None)
        if entry is None:
            return None
        path, before = entry
        after = self._read(path)
        if after is None or after == before:
            return None
        change = FileChange(path, before, after)
        self.changes.append(change)
        return change

    def undo(self) -> FileChange | None:
        """Desfaz atomicamente a última mutação registrada."""
        if not self.changes:
            return None
        change = self.changes.pop()
        if change.before is None:
            change.path.unlink(missing_ok=True)
        else:
            temp = change.path.with_name(f".{change.path.name}.orion-undo")
            temp.write_text(change.before, encoding="utf-8")
            os.replace(temp, change.path)
        return change

    def session_diffs(self) -> list[FileDiff]:
        """Diff acumulado da sessão por arquivo."""
        first: dict[Path, FileChange] = {}
        for change in self.changes:
            first.setdefault(change.path, change)
        return [
            diff_texts(change.before or "", self._read(path) or "", str(path))
            for path, change in first.items()
        ]


class AgentSession:
    """Sessão interativa do orion-agent."""

    def __init__(
        self,
        status_bar: SessionStatusBar,
        console: Console,
        workspace: Path | None = None,
        home: Path | None = None,
        provider_factory: ProviderFactory | None = None,
        ask_pep: PepAsker | None = None,
        max_turns: int = 20,
    ) -> None:
        self.status_bar = status_bar
        self.console = console
        self.workspace = (workspace or Path.cwd()).resolve()
        self.home = home or Path.home() / ".orion"
        self.session_id = str(uuid.uuid4())
        self.config_path = self.home / "config.json"
        self.max_turns = max_turns
        self._provider_factory = provider_factory or self._default_provider
        self._ask_pep = ask_pep

        self.registry = ModelRegistry()
        self.anthropic_key = load_anthropic_key(self.home)
        self.router = ModelRouter(
            registry=self.registry,
            tier_models=ANTHROPIC_TIER_MODELS if self.anthropic_key else None,
        )
        self.allow_downgrade = os.environ.get("ORION_ALLOW_DOWNGRADE") == "1"
        self.breaker = CircuitBreaker(
            primary_model_id=self.router.tier_model(ComplexityTier.HEAVY),
            primary_model_tier=ComplexityTier.HEAVY,
        )
        self.ledger = CostLedger(db_path=self.home / "metrics.db", registry=self.registry)
        self.budget = BudgetGuard(ledger=self.ledger)
        self.compactor = ContextCompactor()
        self.branches = BranchManager()
        self.tracker = ChangeTracker()
        self.renderer = StreamRenderer(
            console,
            effort=lambda: self.status_bar.reasoning_effort.value.lower(),
            status_line=self.status_bar.render_bottom_bar,
        )

        self.history: list[LLMMessage] = []
        self.mention_tokens = 0
        self.tokens_in = self.tokens_out = self.tokens_cached = 0
        self.cost_in = self.cost_out = self.cost_total = 0.0
        self.mode = AgentMode.ACCEPT_EDITS
        self.always_allowed: set[tuple[str, str]] = set()
        self._branch_snapshots: dict[str, list[LLMMessage]] = {}
        self._active_user_text = ""
        self._running: dict[str, str] = {}

        self.bus = EventBus()
        self.bus.subscribe(ActionEmitted)(self._on_action)
        self.bus.subscribe(Observation)(self._on_observation)

        scope = WorkspaceScope([self.workspace])
        self.pep = PolicyEnforcementPoint(
            scope=scope,
            action_confirm=self._confirm,
            audit_logger=AuditLogger(self.home / "audit.log"),
        )
        self.facts = self._open_facts()
        self.runtime = LocalRuntimeProvider(pep=self.pep, scope=scope, facts_store=self.facts)
        self.identity = self._open_identity()
        self.mcp: Any = None
        self._mcp_adapters: dict[str, Any] = {}

        status_bar.session_tokens_in = status_bar.session_tokens_out = 0
        status_bar.session_cost_usd = 0.0
        self.pep.attach_circuit_breaker(self.breaker)
        self.online = bool(os.environ.get("OPENROUTER_API_KEY") or self.anthropic_key)
        status_bar.is_online = self.online
        self.selected_model: str | None = None
        self._load_settings()
        self.set_mode(self.mode)
        if self.selected_model is None and not self.online:
            self.set_model(self._local_default())
        self.status_bar.model_name = self.selected_model or self.router.tier_model(ComplexityTier.HEAVY)

    # ── Inicialização tolerante a falhas ────────────────────────────

    def _open_facts(self) -> Any:
        try:
            from orion.memory.facts_store import FactsStore

            store = FactsStore(self.home / "facts.db")
            store.initialize()
            return store
        except Exception as exc:
            logger.warning("AgentSession: FactsStore indisponível: %s", exc)
            return None

    @staticmethod
    def _open_identity() -> Any:
        try:
            from orion.core.identity import IdentityManager

            return IdentityManager()
        except Exception as exc:
            logger.warning("AgentSession: identidade indisponível: %s", exc)
            return None

    def _local_default(self) -> str:
        return self.registry.local_models()[0].id

    # ── Preferências persistidas ────────────────────────────────────

    def _load_settings(self) -> None:
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(data.get("model"), str) and data["model"] in self.registry:
            self.set_model(data["model"])
        with contextlib.suppress(ValueError, KeyError):
            self.status_bar.reasoning_effort = ReasoningEffort(data["effort"])
        with contextlib.suppress(ValueError, KeyError):
            self.mode = AgentMode(data["mode"])
        with contextlib.suppress(ValueError, KeyError, TypeError):
            self.budget.update_budget(float(data["daily_budget_usd"]))

    def save_settings(self) -> None:
        """Grava as preferências em ~/.orion/config.json."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "model": self.selected_model,
            "effort": self.status_bar.reasoning_effort.value,
            "mode": self.mode.value,
            "daily_budget_usd": self.budget.daily_budget_usd,
        }
        self.config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # ── Controles da sessão ─────────────────────────────────────────

    def set_mode(self, mode: AgentMode) -> None:
        """Aplica um modo operacional ao PEP e à linha de status."""
        self.mode = mode
        autonomy, level = _MODE_RULES[mode]
        self.pep.set_mode(autonomy)
        self.status_bar.agent_mode = mode.value
        self.status_bar.pep_level = level

    def cycle_mode(self) -> None:
        """Shift+Tab: plan → accept-edits → auto → manual."""
        self.set_mode(MODE_CYCLE[(MODE_CYCLE.index(self.mode) + 1) % len(MODE_CYCLE)])

    def cycle_effort(self) -> None:
        """Alt+T: HIGH → MEDIUM → LOW → OFF."""
        current = EFFORT_CYCLE.index(self.status_bar.reasoning_effort)
        self.status_bar.reasoning_effort = EFFORT_CYCLE[(current + 1) % len(EFFORT_CYCLE)]

    def toggle_fast(self) -> None:
        """Alt+O: força o tier FAST."""
        self.status_bar.fast_mode = not self.status_bar.fast_mode

    def set_model(self, model_id: str | None) -> None:
        """Fixa um modelo; None devolve o roteamento automático."""
        self.selected_model = model_id
        if model_id is None:
            self.router.set_mode(RoutingMode.AUTO)
        else:
            self.router.set_mode(RoutingMode.FIXED, model_id)
            self.status_bar.model_name = model_id

    def available_models(self) -> list[ModelSpec]:
        """Modelos selecionáveis: sem chave de nuvem, só os locais."""
        return self.registry.all_models() if self.online else self.registry.local_models()

    # ── Provedores ──────────────────────────────────────────────────

    def _default_provider(self, spec: ModelSpec) -> BaseLLMProvider:
        if spec.provider == ProviderName.OLLAMA:
            from orion.gateway.providers.local_ollama import LocalOllamaProvider

            return LocalOllamaProvider(model_id=spec.id)
        openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
        if spec.provider == ProviderName.ANTHROPIC:
            if not self.anthropic_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY ausente: defina a variável ou grave a chave em "
                    "~/.orion/anthropic_api_key (chmod 600)."
                )
            from orion.gateway.providers.anthropic import AnthropicProvider
            from orion.gateway.providers.local_ollama import LocalOllamaProvider
            from orion.gateway.providers.openrouter import OpenRouterProvider

            chain = build_candidates(
                spec,
                self.registry,
                AnthropicProvider(api_key=self.anthropic_key),
                openrouter=(lambda: OpenRouterProvider(api_key=openrouter_key))
                if openrouter_key
                else None,
                local=lambda local_spec: LocalOllamaProvider(model_id=local_spec.id),
            )
            return FailoverProvider(
                chain,
                breaker=self.breaker,
                allow_downgrade=self.allow_downgrade,
                on_event=self._on_failover,
            )
        from orion.gateway.providers.openrouter import OpenRouterProvider

        return OpenRouterProvider(api_key=openrouter_key)

    def _on_failover(self, event: FailoverEvent) -> None:
        kind = "DOWNGRADE" if event.downgrade else "failover"
        suffix = " (mutações bloqueadas pelo PEP)" if self.breaker.is_mutation_blocked() else ""
        self.renderer.warn(
            f"{kind}: {event.from_model} -> {event.to_model} via "
            f"{event.to_provider.value} [{event.reason.value}]{suffix}"
        )

    def _resolve_model(self) -> tuple[ModelSpec, ComplexityTier, str]:
        decision = self.router.route(self._active_user_text)
        model_id = decision.selected_model
        if self.status_bar.fast_mode and self.online:
            model_id = self.router.tier_model(ComplexityTier.FAST)
        return self.registry.require(model_id), decision.complexity, decision.mode.value

    def _extra_params(self, spec: ModelSpec) -> dict[str, Any]:
        if spec.provider in (ProviderName.OLLAMA, ProviderName.ANTHROPIC):
            return {}
        extra: dict[str, Any] = {"usage": {"include": True}}
        effort = self.status_bar.reasoning_effort
        if spec.supports_thinking and effort != ReasoningEffort.OFF:
            extra["reasoning"] = {"effort": effort.value.lower()}
        return extra

    def _thinking(self, spec: ModelSpec) -> ThinkingConfig | None:
        """Esforço -> thinking adaptativo (Claude 5 não aceita budget_tokens nem desligar)."""
        if spec.provider != ProviderName.ANTHROPIC:
            return None
        effort = self.status_bar.reasoning_effort
        if not spec.supports_thinking or effort == ReasoningEffort.OFF:
            return ThinkingConfig(type="adaptive", effort="low") if spec.supports_thinking else None
        return ThinkingConfig(type="adaptive", display="summarized", effort=effort.value.lower())  # type: ignore[arg-type]

    # ── Ponte LLM ───────────────────────────────────────────────────

    def system_extra(self) -> str:
        """Avisos de sessão anexados ao system prompt (modo plano)."""
        return PLAN_MODE_NOTE.strip() if self.mode == AgentMode.PLAN else ""

    def system_prompt(self) -> str:
        """System prompt completo da sessão (identidade, regras e avisos)."""
        return compose_system(self.identity, extra=self.system_extra())

    # ── MCP (Sprint 5) ──────────────────────────────────────────────

    def start_mcp(self, client: Any = None) -> None:
        """Inicia o cliente MCP em background (não bloqueia o boot do CLI)."""
        try:
            if client is None:
                from orion.mcp.client import load_server_configs
                from orion.mcp.runner import BackgroundMCPClient

                configs = load_server_configs(self.home, self.workspace)
                client = BackgroundMCPClient(configs)
            self.mcp = client
            if hasattr(client, "start_in_background"):
                client.start_in_background()
        except Exception:
            logger.exception("AgentSession: falha ao iniciar o cliente MCP")
            self.mcp = None

    def refresh_mcp(self) -> None:
        """Registra no runtime as tools MCP já conectadas (barato; roda a cada turno)."""
        if self.mcp is None:
            return
        try:
            from orion.mcp.adapter import MCPSchemaTool, build_adapters

            connected = sum(1 for s in self.mcp.servers.values() if s.status == "connected")
            if connected == getattr(self, "_mcp_connected", -1):
                return
            self._mcp_connected = connected
            for name in self._mcp_adapters:
                self.runtime._tools.pop(name, None)
            self._mcp_adapters = build_adapters(self.mcp)
            for name, adapter in self._mcp_adapters.items():
                self.runtime.register_tool(adapter, name=name)
            if self._mcp_adapters:
                self.runtime.register_tool(MCPSchemaTool(self._mcp_adapters), name="mcp_schema")
        except Exception:
            logger.exception("AgentSession: falha ao registrar tools MCP")

    async def _llm(
        self, *, system: str, messages: list[LLMMessage], tools: list[ToolSpec]
    ) -> ModelTurn:
        """Uma volta com o modelo: stream ao vivo no renderer e blocos tipados de volta ao engine."""
        spec, tier, routing = self._resolve_model()
        self.status_bar.model_name = spec.id
        self.budget.check(is_local_model=spec.provider == ProviderName.OLLAMA)
        # Modelo leve só é "intencional" se o tier resolvido não é HEAVY; senão uma falha
        # externa do modelo de topo ativa SAFE_HOLDING (mutações bloqueadas).
        self.breaker.set_intentional_lite_mode(tier != ComplexityTier.HEAVY)

        anthropic = spec.provider == ProviderName.ANTHROPIC
        wire = [LLMMessage(role=MessageRole.SYSTEM, content=system), *messages]
        request = LLMRequest(
            model=spec.id,
            messages=wire,
            tools=tools,
            max_tokens=16_000 if anthropic else 4096,
            complexity_tier=tier,
            extra_params=self._extra_params(spec),
            thinking=self._thinking(spec),
            cache_control=CacheControl() if anthropic else None,
        )

        started = time.monotonic()
        self.renderer.begin_thinking()
        usage: TokenUsage | None = None
        stop_reason: str | None = None
        blocks: list[ContentBlock] = []
        text = ""
        reasoning_chars = 0
        provider = self._provider_factory(spec)
        async for chunk in provider.stream(request):
            if chunk.reasoning_delta:
                reasoning_chars += len(chunk.reasoning_delta)
                self.renderer.add_reasoning(chunk.reasoning_delta)
            if chunk.delta:
                text += chunk.delta
                self.renderer.add_text(chunk.delta)
            if chunk.block is not None:
                blocks.append(chunk.block)
            if chunk.stop_reason:
                stop_reason = chunk.stop_reason
            if chunk.usage is not None:
                usage = chunk.usage
        self.renderer.end_message()

        served = getattr(provider, "served", None)
        if served is not None:
            # Failover: custo na tarifa do destino que de fato respondeu.
            spec = self.registry.require(served.pricing_model)
            provider_name = served.provider
        else:
            provider_name = spec.provider
        self._record_cost(
            spec,
            usage or self._estimate_usage(wire, text, reasoning_chars),
            tier,
            routing,
            (time.monotonic() - started) * 1000,
            provider_name,
        )

        if not any(b.type == "text" for b in blocks) and text.strip():
            # Providers legados só emitem deltas: monta o bloco de texto a partir deles.
            blocks.insert(0, ContentBlock.of_text(text))
        return ModelTurn(blocks=blocks, stop_reason=stop_reason or "end_turn")

    @staticmethod
    def _estimate_usage(messages: list[LLMMessage], text: str, reasoning_chars: int) -> TokenUsage:
        prompt_tokens = sum(estimate_tokens(m.text) for m in messages)
        completion = estimate_tokens(text) + reasoning_chars // 4
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion,
            total_tokens=prompt_tokens + completion,
        )

    def _record_cost(
        self,
        spec: ModelSpec,
        usage: TokenUsage,
        tier: ComplexityTier,
        routing: str,
        latency_ms: float,
        provider_name: ProviderName | None = None,
    ) -> None:
        record = self.ledger.record_turn_cost(
            provider=provider_name or spec.provider,
            model=spec.id,
            usage=usage,
            routing_mode=routing,
            complexity=tier,
            task_id=self.session_id,
            latency_ms=latency_ms,
        )
        self.tokens_in += usage.prompt_tokens
        self.tokens_out += usage.completion_tokens
        self.tokens_cached += usage.cached_tokens
        self.cost_in += usage.prompt_tokens * spec.cost_input_m / 1_000_000
        self.cost_out += usage.completion_tokens * spec.cost_output_m / 1_000_000
        self.cost_total += record.cost_usd
        self.status_bar.session_tokens_in = self.tokens_in
        self.status_bar.session_tokens_out = self.tokens_out
        self.status_bar.session_cost_usd = self.cost_total

    # ── Eventos do engine → interface ───────────────────────────────

    def _target_path(self, params: dict[str, Any]) -> Path:
        return (self.workspace / str(params.get("path", ""))).resolve()

    async def _on_action(self, event: ActionEmitted) -> None:
        self._running[event.action_id] = event.tool
        if event.tool in _MUTATING_TOOLS:
            self.tracker.begin(event.action_id, self._target_path(event.params))
        self.renderer.tool_started(event.tool, event.params, key=event.action_id)
        self.branches.record_event(f"{event.tool}: {event.params}"[:200])

    async def _on_observation(self, event: Observation) -> None:
        tool = self._running.pop(event.action_id, "")
        change = self.tracker.finish(event.action_id)
        diff = None
        if change is not None:
            diff = diff_texts(change.before or "", change.after, str(change.path))
        self.renderer.tool_finished(
            tool,
            event.success,
            event.output or event.error or "",
            event.metadata,
            diff,
            key=event.action_id,
        )

    # ── Governança ──────────────────────────────────────────────────

    async def _confirm(self, action: Action, level: ActionLevel) -> Any:
        if self.mode == AgentMode.PLAN:
            return False
        key = (action.tool, str(action.params.get("command", action.params.get("path", ""))))
        if key in self.always_allowed:
            return True
        asker = self._ask_pep
        if asker is None:
            from orion.tui.modal import ask_pep_decision

            async def asker(act: Action, lvl: ActionLevel) -> Any:
                return await ask_pep_decision(self.console, act, lvl)

        self.renderer.pause()
        try:
            decision = await asker(action, level)
        finally:
            self.renderer.resume()
        if decision == "a":
            self.always_allowed.add(key)
            return True
        if isinstance(decision, dict):
            return decision
        return decision == "y"

    # ── Turnos ──────────────────────────────────────────────────────

    def _with_mentions(self, text: str) -> str:
        blocks: list[str] = []
        for mention, path in resolve_mentions(text, workspace_root=self.workspace).items():
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")[:_MAX_MENTION_CHARS]
            except OSError:
                continue
            blocks.append(f'<file path="{mention}">\n{content}\n</file>')
        if not blocks:
            return text
        self.mention_tokens += estimate_tokens("".join(blocks))
        return text + "\n\n" + "\n".join(blocks)

    async def run_turn(self, text: str) -> str | None:
        """Executa um turno completo; erros operacionais viram mensagem, nunca traceback."""
        self._active_user_text = text
        self.refresh_mcp()
        content = self._with_mentions(text)
        engine = ReActEngine(
            event_bus=self.bus,
            llm=self._llm,
            max_turns=self.max_turns,
            session_id=self.session_id,
            runtime=self.runtime,
            identity_manager=self.identity,
            system_extra=self.system_extra,
        )
        self.status_bar.is_busy = True
        await self._log_timeline("user", "user", text)
        try:
            answer = await engine.run(content, history=self.history)
        except asyncio.CancelledError:
            # A conversa permanece válida (tool_use pendentes foram fechados): preserva o contexto.
            self.history = engine.messages
            raise
        except PromptInjectionSuspected:
            self.renderer.error("Entrada bloqueada: padrão de injeção de prompt detectado.")
            return None
        except TurnBudgetExceeded:
            self.renderer.error(f"Limite de {self.max_turns} passos atingido sem resposta final.")
            return None
        except BudgetExceededError as exc:
            self.renderer.error(f"Orçamento diário atingido: {exc}")
            return None
        except Exception as exc:
            logger.exception("AgentSession: falha no turno")
            self.renderer.error(f"Falha no turno: {exc}")
            return None
        finally:
            self.renderer.close()
            self.status_bar.is_busy = False

        self.history = engine.messages
        self.branches.record_event(answer[:200], event_type="observation")
        await self._log_timeline("assistant", "agent", answer)
        return answer

    async def run_tool(self, tool: str, params: dict[str, Any]) -> bool:
        """Executa uma ferramenta direta (/run) pelo PEP, com o mesmo card de um turno."""
        self.renderer.tool_started(tool, params)
        try:
            result = await self.runtime.execute(tool, params)
            self.renderer.tool_finished(
                tool, result.success, result.output or result.error or "", result.metadata
            )
            return result.success
        finally:
            self.renderer.close()

    async def _log_timeline(self, event_type: str, source: str, content: str) -> None:
        with contextlib.suppress(Exception):
            timeline = await self.open_timeline()
            try:
                await timeline.append_event(
                    session_id=self.session_id,
                    event_type=event_type,
                    source=source,
                    content=content,
                )
            finally:
                await timeline.close()

    async def open_timeline(self) -> TimelineManager:
        """Abre a Main Timeline; quem chama fecha."""
        timeline = TimelineManager(self.home / "timeline.db")
        await timeline.initialize()
        return timeline

    # ── Contexto e branches ─────────────────────────────────────────

    def context_breakdown(self) -> dict[str, int]:
        """Composição estimada da janela de contexto ativa."""
        conversation = sum(estimate_tokens(m.text) for m in self.history)
        return {
            "sistema": estimate_tokens(self.identity.render_system_preamble()) if self.identity else 0,
            "ferramentas": estimate_tokens(self.system_prompt()),
            "memória": 0,
            "arquivos": min(self.mention_tokens, conversation),
            "conversa": max(conversation - self.mention_tokens, 0),
        }

    def context_window(self) -> int:
        """Janela do modelo ativo."""
        spec = self.registry.get(self.status_bar.model_name)
        return spec.context_window if spec else 200_000

    def _turn_starts(self) -> list[int]:
        """Índices das mensagens que abrem um turno (usuário com texto, não tool_result)."""
        starts: list[int] = []
        for i, message in enumerate(self.history):
            if message.role != MessageRole.USER:
                continue
            if isinstance(message.content, str) or any(b.type != "tool_result" for b in message.blocks):
                starts.append(i)
        return starts

    def compact(self, focus: str | None = None) -> str:
        """Substitui a conversa antiga por um resumo, preservando a cauda vital."""
        starts = self._turn_starts()
        bounds = [*starts, len(self.history)]
        pairs = [
            TurnData(
                turn_index=n,
                user_input=self.history[bounds[n]].text,
                tool_output=self._answer_text(self.history[bounds[n] + 1 : bounds[n + 1]]),
            )
            for n in range(len(starts))
        ]
        result = self.compactor.compact(pairs, focus=focus)
        keep = result.preserved_tail_turns
        tail = self.history[starts[-keep] :] if keep and starts else []
        if result.original_turns > keep:
            summary = LLMMessage(
                role=MessageRole.USER,
                content=f"Resumo da conversa anterior:\n{result.compacted_summary}",
            )
            ack = LLMMessage(role=MessageRole.ASSISTANT, content="Entendido.")
            self.history = [summary, ack, *tail]
        return self.compactor.format_notification(result)

    @staticmethod
    def _answer_text(messages: list[LLMMessage]) -> str:
        """Texto final do assistente num turno (ignora tool_use/tool_result intermediários)."""
        for message in reversed(messages):
            if message.role == MessageRole.ASSISTANT:
                return "".join(b.text or "" for b in message.blocks if b.type == "text")
        return ""

    def create_branch(self, name: str) -> None:
        """Abre uma ramificação de contexto isolada."""
        self.branches.create_branch(name)
        self._branch_snapshots.setdefault(name, list(self.history))

    async def merge_branch(self, outcome: str) -> str:
        """Sintetiza a branch ativa e volta à conversa principal só com o checkpoint."""
        name = self.branches.active_branch
        checkpoint = await self.branches.merge_branch(outcome=outcome)
        base = self._branch_snapshots.pop(name, self.history)
        self.history = [
            *base,
            LLMMessage(role=MessageRole.USER, content=f"Checkpoint da branch {name}:\n{checkpoint}"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Entendido."),
        ]
        await self._log_timeline("checkpoint", "system", checkpoint)
        return checkpoint

    def status_line(self, width: int) -> RenderableType:
        """Atalho para a linha de status atual."""
        return self.status_bar.render_bottom_bar(width)
