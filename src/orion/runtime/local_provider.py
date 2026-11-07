"""
O.R.I.O.N — Local Runtime Provider
Orchestrates the 5 native primitive tools and cognitive memory tools,
integrating with the PEP.

Dispatch flow:
  LocalRuntimeProvider.execute(tool, params)
      └─► PEP.evaluate(action)            ← governance gate
              ├── approved → tool execution → RuntimeResult
              └── denied  → RuntimeResult.fail("ActionDenied")
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

from orion.core.events import Action, RiskLevel
from orion.gateway.models import ToolSpec
from orion.governance.pep import ActionDenied, PolicyEnforcementPoint
from orion.governance.permissions import (
    WorkspaceScope,
    is_read_only_tool,
    register_tool_level,
    risk_to_action_level,
    tool_risk_level,
)
from orion.runtime.provider import BaseRuntimeProvider, RuntimeResult
from orion.runtime.tools.bash_output import BashOutputTool
from orion.runtime.tools.edit_file import EditFileTool
from orion.runtime.tools.glob import GlobTool
from orion.runtime.tools.grep import GrepTool
from orion.runtime.tools.kill_shell import KillShellTool
from orion.runtime.tools.notebook_edit import NotebookEditTool
from orion.runtime.tools.read_file import ReadFileTool
from orion.runtime.tools.run_command import RunCommandTool
from orion.runtime.tools.search_files import SearchFilesTool
from orion.runtime.tools.shells import ShellManager
from orion.runtime.tools.web_fetch import WebFetchTool
from orion.runtime.tools.web_search import WebSearchTool
from orion.runtime.tools.write_file import WriteFileTool

if TYPE_CHECKING:
    from orion.memory.facts_store import FactsStore
    from orion.memory.hybrid_retriever import HybridRetriever
    from orion.runtime.environment import EnvironmentMonitor
    from orion.skills.engine import SkillsEngine

logger = logging.getLogger(__name__)

class LocalRuntimeProvider(BaseRuntimeProvider):
    """Concrete runtime that executes native primitive and cognitive tools on the host.

    Args:
        pep                 : PolicyEnforcementPoint instance.
        scope               : WorkspaceScope for path validation.
        facts_store         : Optional FactsStore to enable memory tools (memorize, recall, deprecate_fact).
        retriever           : Optional HybridRetriever for deep recall.
        environment_monitor : Optional EnvironmentMonitor for inspect_environment.
        skills_engine       : Optional SkillsEngine to enable use_skill.
        extra_tools         : Optional sequence of custom tool instances.
        shells              : ShellManager for background shells (a private one is created if omitted).
    """

    def __init__(
        self,
        pep: PolicyEnforcementPoint | None = None,
        scope: WorkspaceScope | None = None,
        facts_store: FactsStore | None = None,
        retriever: HybridRetriever | None = None,
        environment_monitor: EnvironmentMonitor | None = None,
        skills_engine: SkillsEngine | None = None,
        extra_tools: Sequence[Any] | None = None,
        shells: ShellManager | None = None,
    ) -> None:
        self._scope = scope or WorkspaceScope.default()
        self._pep = pep or PolicyEnforcementPoint(scope=self._scope)

        self.shells = shells or ShellManager()

        # Primitive + parity tools (interactive ones — todo/ask_user/plan mode — come via extra_tools)
        self._tools: dict[str, Any] = {
            t.name: t
            for t in [
                RunCommandTool(self.shells),
                ReadFileTool(),
                WriteFileTool(),
                EditFileTool(),
                SearchFilesTool(),
                GlobTool(),
                GrepTool(),
                NotebookEditTool(),
                WebFetchTool(),
                WebSearchTool(),
                BashOutputTool(self.shells),
                KillShellTool(self.shells),
            ]
        }

        # Cognitive tools integration
        if facts_store is not None:
            from orion.memory.tools import DeprecateFactTool, MemorizeTool, RecallTool

            self._tools["memorize"] = MemorizeTool(facts_store=facts_store)
            self._tools["recall"] = RecallTool(facts_store=facts_store, retriever=retriever)
            self._tools["deprecate_fact"] = DeprecateFactTool(facts_store=facts_store)

        if environment_monitor is not None:
            from orion.memory.tools import InspectEnvironmentTool

            self._tools["inspect_environment"] = InspectEnvironmentTool(monitor=environment_monitor)

        if skills_engine is not None:
            self._tools["use_skill"] = skills_engine.tool

        if extra_tools:
            for tool_inst in extra_tools:
                self.register_tool(tool_inst)

    # ------------------------------------------------------------------
    # Tool registration API
    # ------------------------------------------------------------------

    def register_tool(
        self,
        tool_inst: Any,
        name: str | None = None,
        risk: RiskLevel | None = None,
    ) -> None:
        """Register an arbitrary tool instance conforming to the contract."""
        tool_name = name or getattr(tool_inst, "name", getattr(tool_inst, "TOOL_NAME", None))
        if not tool_name:
            raise ValueError(f"Could not determine name for tool instance {tool_inst!r}")

        self._tools[tool_name] = tool_inst
        if risk is not None:
            register_tool_level(tool_name, risk_to_action_level(risk))

    # ------------------------------------------------------------------
    # BaseRuntimeProvider contract
    # ------------------------------------------------------------------

    def supports(self, tool: str) -> bool:
        return tool in self._tools

    def is_read_only(self, tool: str) -> bool:
        return self.supports(tool) and is_read_only_tool(tool)

    def tool_specs(self) -> list[ToolSpec]:
        """Tool definitions exposed to the model, in a stable order (cache-friendly)."""
        specs: list[ToolSpec] = []
        for name in sorted(self._tools):
            impl = self._tools[name]
            schema = getattr(impl, "input_schema", None)
            description = getattr(impl, "description", "")
            if not isinstance(schema, dict) or not description:
                continue  # sem contrato de schema: não é exposta ao modelo
            specs.append(ToolSpec(name=name, description=description, input_schema=schema))
        return specs

    def validate_params(self, tool: str, params: dict[str, Any]) -> str | None:
        """Validate *params* against the tool's JSON schema; None when valid."""
        schema = getattr(self._tools.get(tool), "input_schema", None)
        if not isinstance(schema, dict):
            return None
        error = best_match(Draft202012Validator(schema).iter_errors(params))
        if error is None:
            return None
        where = ".".join(str(p) for p in error.absolute_path)
        return f"Invalid parameters for '{tool}'" + (f" at '{where}'" if where else "") + f": {error.message}"

    async def execute(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
        """PEP-gate then dispatch *tool* with *params*.

        The PEP always runs first. If an action is denied (user says no or
        policy blocks it), a failed RuntimeResult is returned immediately
        without touching the OS.
        """
        if not self.supports(tool):
            return RuntimeResult.fail(
                f"LocalRuntimeProvider: unknown tool '{tool}'. "
                f"Available: {sorted(self._tools)}"
            )

        invalid = self.validate_params(tool, params)
        if invalid is not None:
            return RuntimeResult.fail(invalid, invalid_params=True)

        action = Action(tool=tool, params=params, risk_level=tool_risk_level(tool))

        # ── Governance gate ──────────────────────────────────────────────
        try:
            approved = await self._pep.evaluate(action)
        except ActionDenied as exc:
            return RuntimeResult.fail(
                f"PEP denied '{tool}': {exc.reason}",
                action_id=exc.action_id,
                denied=True,
            )

        if not approved:
            reason = self._pep.take_rejection_reason(action.event_id)
            return RuntimeResult.fail(
                f"PEP: '{tool}' not executed: {reason}"
                if reason
                else f"PEP: user rejected execution of '{tool}'.",
                denied=True,
            )

        # ── Execute ──────────────────────────────────────────────────────
        params = self._pep.take_edited_params(action.event_id) or params
        impl = self._tools[tool]
        try:
            return await self._dispatch_impl(impl, params)
        except Exception as exc:
            logger.exception("LocalRuntimeProvider: unhandled error in tool '%s'", tool)
            return RuntimeResult.fail(f"'{tool}' raised an unexpected error: {exc}")

    # ------------------------------------------------------------------
    # Direct tool access (bypasses PEP — use only in tests / trusted paths)
    # ------------------------------------------------------------------

    async def execute_direct(self, tool: str, params: dict[str, Any]) -> RuntimeResult:
        """Execute *tool* WITHOUT going through the PEP.

        WARNING: This method bypasses all governance checks.
        It is intended exclusively for unit tests and trusted internal calls.
        """
        if not self.supports(tool):
            return RuntimeResult.fail(f"LocalRuntimeProvider: unknown tool '{tool}'.")
        impl = self._tools[tool]
        return await self._dispatch_impl(impl, params)

    async def _dispatch_impl(self, impl: Any, params: dict[str, Any]) -> RuntimeResult:
        """Dispatch parameters to tool implementation supporting either run or execute."""
        if hasattr(impl, "run"):
            res = impl.run(**params)
            return await res if asyncio.iscoroutine(res) else res
        if hasattr(impl, "execute"):
            res = impl.execute(params)
            return await res if asyncio.iscoroutine(res) else res
        res = impl(**params)
        return await res if asyncio.iscoroutine(res) else res

    @property
    def pep(self) -> PolicyEnforcementPoint:
        return self._pep

    @property
    def scope(self) -> WorkspaceScope:
        return self._scope

    @property
    def available_tools(self) -> list[str]:
        return sorted(list(self._tools.keys()))
