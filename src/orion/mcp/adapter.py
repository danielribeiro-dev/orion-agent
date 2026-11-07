"""
O.R.I.O.N — MCPToolAdapter
Exposes a remote MCP tool as a native ORION ``BaseTool`` and registers its
PEP ActionLevel (read-only ⇒ LEVEL_1, anything else ⇒ LEVEL_2).

Lazy loading: :func:`catalog_lines` yields one short line per tool (what the
model sees by default); the full JSON schema is only fetched through
:meth:`MCPToolAdapter.schema` when the tool is selected.
"""

from __future__ import annotations

from typing import Any

from orion.governance.permissions import (
    ActionLevel,
    register_tool_level,
    unregister_tool_levels,
)
from orion.mcp.client import MCPClient
from orion.mcp.models import MCPServerConfig, MCPToolDefinition
from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool


def classify(defn: MCPToolDefinition, cfg: MCPServerConfig) -> ActionLevel:
    """Read-only only if the user/catalog allowlist says so, or the server
    annotates ``readOnlyHint`` on a non-bundled-mutating tool. Default: mutating.
    """
    if defn.name in cfg.read_only_tools:
        return ActionLevel.LEVEL_1
    if defn.read_only_hint is True:
        return ActionLevel.LEVEL_1
    return ActionLevel.LEVEL_2


class MCPToolAdapter(BaseTool):
    def __init__(self, client: MCPClient, defn: MCPToolDefinition, level: ActionLevel) -> None:
        self._client = client
        self.definition = defn
        self.level = level
        self.name = defn.qualified_name  # type: ignore[misc]  # por-instância (schema vem do servidor MCP)
        self.description = defn.description or defn.name  # type: ignore[misc]  # por-instância (schema vem do servidor MCP)
        self.input_schema = defn.input_schema or {"type": "object", "properties": {}}  # type: ignore[misc]  # por-instância (schema vem do servidor MCP)
        self.read_only = level <= ActionLevel.LEVEL_1  # type: ignore[misc]  # por-instância (schema vem do servidor MCP)

    def summary(self, max_len: int = 80) -> str:
        desc = " ".join(self.definition.description.split())
        if len(desc) > max_len:
            desc = desc[: max_len - 1] + "…"
        return f"{self.name}: {desc}"

    def schema(self) -> dict[str, Any]:
        """Full JSON schema — only requested once the tool is selected."""
        return self.definition.input_schema

    async def run(self, **params: Any) -> RuntimeResult:
        ok, text = await self._client.call_tool(
            self.definition.server_name, self.definition.name, params
        )
        return RuntimeResult.ok(text) if ok else RuntimeResult.fail(text)


def build_adapters(client: MCPClient) -> dict[str, MCPToolAdapter]:
    """Create adapters for every connected tool and register PEP levels."""
    adapters: dict[str, MCPToolAdapter] = {}
    for state in client.servers.values():
        unregister_tool_levels(f"mcp__{state.config.name}__")
        if state.status != "connected":
            continue
        for defn in state.tools:
            if defn.name in state.config.hidden_tools:
                continue
            level = classify(defn, state.config)
            register_tool_level(defn.qualified_name, level)
            adapters[defn.qualified_name] = MCPToolAdapter(client, defn, level)
    return adapters


def catalog_lines(adapters: dict[str, MCPToolAdapter]) -> list[str]:
    """Compact tool listing for the prompt (no schemas)."""
    return [a.summary() for a in adapters.values()]
