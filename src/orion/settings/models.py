"""Modelos de settings (camadas user, projeto e local)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

HOOK_EVENTS: tuple[str, ...] = (
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
    "SessionStart",
    "SessionEnd",
    "PreCompact",
    "Notification",
)


class Permissions(BaseModel):
    """Regras declarativas no formato ``Tool`` ou ``Tool(padrão)``."""

    model_config = ConfigDict(extra="ignore")

    allow: list[str] = Field(default_factory=list)
    deny: list[str] = Field(default_factory=list)
    ask: list[str] = Field(default_factory=list)


class HookSpec(BaseModel):
    """Um hook shell: ``matcher`` filtra pelo nome da tool (``*`` ou vazio = todas)."""

    model_config = ConfigDict(extra="ignore")

    command: str
    matcher: str | None = None
    timeout: float = Field(default=10.0, gt=0, le=300)


class Settings(BaseModel):
    """Settings efetivos ou de uma única camada. Chaves desconhecidas são ignoradas."""

    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    effort: str | None = None
    mode: str | None = None
    daily_budget_usd: float | None = None
    permissions: Permissions = Field(default_factory=Permissions)
    hooks: dict[str, list[HookSpec]] = Field(default_factory=dict)
    mcp: dict[str, dict[str, Any]] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)

    def has_risky_content(self) -> bool:
        """Verdadeiro se a camada traz algo que executa código ou afrouxa o PEP."""
        return bool(
            self.hooks
            or self.permissions.allow
            or self.mode
            or self.mcp
            or self.env
            or self.daily_budget_usd is not None
        )

    def restricted(self) -> Settings:
        """Versão segura de uma camada não confiável: só restringe.

        Mantém ``deny``/``ask``, ``model`` e ``effort``. Descarta ``allow``,
        hooks, ``mode``, ``mcp``, ``env`` e orçamento.
        """
        return Settings(
            model=self.model,
            effort=self.effort,
            permissions=Permissions(deny=list(self.permissions.deny), ask=list(self.permissions.ask)),
        )
