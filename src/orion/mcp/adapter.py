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


LIST_RESOURCES_TOOL = "list_mcp_resources"
READ_RESOURCE_TOOL = "read_mcp_resource"


class ListMCPResourcesTool(BaseTool):
    """Lists the resources exposed by connected MCP servers (read-only)."""

    name = LIST_RESOURCES_TOOL
    description = (
        "List resources exposed by connected MCP servers (documents, files, records). "
        "Read one with read_mcp_resource."
    )
    input_schema = {
        "type": "object",
        "properties": {"server": {"type": "string", "description": "Only this server (optional)."}},
        "additionalProperties": False,
    }
    read_only = True

    def __init__(self, client: MCPClient) -> None:
        self._client = client

    async def run(self, **params: Any) -> RuntimeResult:
        server = params.get("server")
        rows = [
            f"{r.server_name}:{r.uri}" + (f"  {r.name}" if r.name else "")
            for r in self._client.all_resources()
            if server in (None, r.server_name)
        ]
        return RuntimeResult.ok("\n".join(rows) if rows else "No MCP resources available.")


class ReadMCPResourceTool(BaseTool):
    """Reads one MCP resource; content is untrusted data, never instructions."""

    name = READ_RESOURCE_TOOL
    description = "Read a resource from a connected MCP server by server name and URI."
    input_schema = {
        "type": "object",
        "properties": {
            "server": {"type": "string"},
            "uri": {"type": "string"},
        },
        "required": ["server", "uri"],
        "additionalProperties": False,
    }
    read_only = True

    def __init__(self, client: MCPClient) -> None:
        self._client = client

    async def run(self, **params: Any) -> RuntimeResult:
        ok, text = await self._client.read_resource(str(params["server"]), str(params["uri"]))
        return RuntimeResult.ok(text) if ok else RuntimeResult.fail(text)


def build_resource_tools(client: MCPClient) -> dict[str, BaseTool]:
    """Synthetic LEVEL_1 tools for resources; empty when no server exposes any."""
    if not client.all_resources():
        unregister_tool_levels(LIST_RESOURCES_TOOL)
        unregister_tool_levels(READ_RESOURCE_TOOL)
        return {}
    register_tool_level(LIST_RESOURCES_TOOL, ActionLevel.LEVEL_1)
    register_tool_level(READ_RESOURCE_TOOL, ActionLevel.LEVEL_1)
    return {
        LIST_RESOURCES_TOOL: ListMCPResourcesTool(client),
        READ_RESOURCE_TOOL: ReadMCPResourceTool(client),
    }
