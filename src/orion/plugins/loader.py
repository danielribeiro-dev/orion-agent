"""Plugin mínimo: uma pasta em ``~/.orion/plugins/<nome>/`` que empacota extensões.

Estrutura (tudo opcional exceto ``plugin.json``)::

    plugin.json        {"name": "...", "version": "..."}
    commands/*.md      comandos custom, expostos como ``/<plugin>:<comando>``
    agents/*.md        subagents (mesmo formato de ``~/.orion/agents``)
    skills/            skills (mesmo formato de ``~/.orion/skills``)
    hooks.json         {"PreToolUse": [{"command": "...", "matcher": "..."}]}
    mcp.json           {"servers": {...}}  (consumido pelo cliente MCP)

Plugins são instalados pelo próprio Senhor em ``~/.orion/plugins`` (camada
user, confiável). Não há marketplace nem instalação remota nesta versão.
Nada aqui concede privilégio: comandos viram prompts, hooks só bloqueiam e
tools continuam passando pelo PEP.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from orion.settings.io import read_json_object
from orion.settings.models import HookSpec, Settings

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MANIFEST = "plugin.json"


@dataclass(frozen=True)
class Plugin:
    """Um plugin descoberto."""

    name: str
    version: str
    root: Path

    @property
    def commands_dir(self) -> Path:
        return self.root / "commands"

    @property
    def skills_dir(self) -> Path:
        return self.root / "skills"

    @property
    def agents_dir(self) -> Path:
        return self.root / "agents"

    def settings_layer(self) -> Settings:
        """Hooks e servidores MCP do plugin, como camada de settings."""
        hooks: dict[str, list[HookSpec]] = {}
        raw_hooks = read_json_object(self.root / "hooks.json") or {}
        for event, specs in raw_hooks.items():
            if not isinstance(specs, list):
                continue
            for spec in specs:
                try:
                    hooks.setdefault(event, []).append(HookSpec.model_validate(spec))
                except ValidationError:
                    logger.warning("plugin %s: hook inválido em %s ignorado", self.name, event)
        mcp_raw = read_json_object(self.root / "mcp.json") or {}
        servers = mcp_raw.get("servers") or mcp_raw.get("mcpServers") or {}
        mcp: dict[str, dict[str, Any]] = {
            f"{self.name}-{name}": cfg for name, cfg in servers.items() if isinstance(cfg, dict)
        }
        return Settings(hooks=hooks, mcp=mcp)


def discover_plugins(home: Path) -> list[Plugin]:
    """Lê ``<home>/plugins/*/plugin.json``; manifestos inválidos são ignorados."""
    base = home / "plugins"
    if not base.is_dir():
        return []
    found: list[Plugin] = []
    for entry in sorted(base.iterdir()):
        manifest = read_json_object(entry / MANIFEST) if entry.is_dir() else None
        if manifest is None:
            continue
        name = str(manifest.get("name", ""))
        if not _NAME_RE.match(name):
            logger.warning("plugin em %s ignorado: nome inválido '%s'", entry, name)
            continue
        found.append(Plugin(name=name, version=str(manifest.get("version", "0")), root=entry))
    return found
