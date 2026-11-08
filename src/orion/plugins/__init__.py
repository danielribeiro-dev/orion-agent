"""Plugin mínimo do ORION (comandos, skills, hooks e MCP empacotados)."""

from orion.plugins.loader import Plugin, discover_plugins

__all__ = ["Plugin", "discover_plugins"]
