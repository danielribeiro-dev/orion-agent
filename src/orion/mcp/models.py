"""
O.R.I.O.N — MCP contracts
Pydantic models for MCP server configuration and discovered tools.

Reference: docs/planning/versions/v0.4.0/sprints/sprint-5.md
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration of a single MCP server (stdio subprocess or remote SSE)."""

    name: str
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    transport: Literal["stdio", "sse"] = "stdio"

    #: Disabled servers are never spawned/connected.
    enabled: bool = True
    #: Tool names known to be read-only (PEP LEVEL_1). Anything else is LEVEL_2.
    read_only_tools: list[str] = Field(default_factory=list)
    #: Tools never exposed to the model (editing / redundant with ORION memory).
    hidden_tools: list[str] = Field(default_factory=list)
    #: Estimated tool-definition overhead (tokens) if fully loaded; shown in /mcp.
    est_tokens: int = 0
    #: Short human description (catalog / /mcp).
    description: str = ""
    #: True when the entry comes from the bundled starter pack.
    bundled: bool = False


class MCPToolDefinition(BaseModel):
    """A tool discovered on an MCP server."""

    server_name: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    #: MCP annotation ``readOnlyHint`` when the server provides it.
    read_only_hint: bool | None = None

    @property
    def qualified_name(self) -> str:
        """Unique name exposed to the ReAct engine: ``mcp__<server>__<tool>``."""
        return f"mcp__{self.server_name}__{self.name}"
