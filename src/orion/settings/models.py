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
    "SubagentStart",
    "SubagentStop",
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


class AgentsSettings(BaseModel):
    """Tetos dos subagents (Sprint 6). ``None`` = não definido na camada; ver ``resolved()``."""

    model_config = ConfigDict(extra="ignore")

    max_concurrent: int | None = Field(default=None, ge=1, le=16)
    max_depth: int | None = Field(default=None, ge=1, le=3)
    default_max_turns: int | None = Field(default=None, ge=1, le=100)
    result_max_tokens: int | None = Field(default=None, ge=200, le=8000)
    default_budget_usd: float | None = Field(default=None, gt=0)
    aggregate_budget_usd: float | None = Field(default=None, gt=0)
    default_timeout_s: int | None = Field(default=None, ge=10, le=7200)
    allow_pinned_model: bool | None = None

    def is_set(self) -> bool:
        return any(v is not None for v in self.model_dump().values())

    def resolved(self) -> ResolvedAgents:
        """Valores efetivos, com os padrões seguros. Nunca há "sem limite"."""
        return ResolvedAgents(
            max_concurrent=self.max_concurrent or 4,
            max_depth=self.max_depth or 1,
            default_max_turns=self.default_max_turns or 20,
            result_max_tokens=self.result_max_tokens or 1500,
            default_budget_usd=self.default_budget_usd or 0.50,
            aggregate_budget_usd=self.aggregate_budget_usd or 1.00,
            default_timeout_s=self.default_timeout_s or 900,
            allow_pinned_model=bool(self.allow_pinned_model),
        )


class ResolvedAgents(BaseModel):
    """``AgentsSettings`` com todos os campos preenchidos."""

    max_concurrent: int
    max_depth: int
    default_max_turns: int
    result_max_tokens: int
    default_budget_usd: float
    aggregate_budget_usd: float
    default_timeout_s: int
    allow_pinned_model: bool


class ModelProfile(BaseModel):
    """Perfil de modelo nomeado: agentes referenciam o nome, nunca um ID concreto."""

    model_config = ConfigDict(extra="ignore")

    tier: str = "balanced"


class ModelsSettings(BaseModel):
    """``tiers``: lista ordenada de candidatos por tier (``fast|balanced|heavy``)."""

    model_config = ConfigDict(extra="ignore")

    tiers: dict[str, list[str]] = Field(default_factory=dict)
    profiles: dict[str, ModelProfile] = Field(default_factory=dict)

    def is_set(self) -> bool:
        return bool(self.tiers or self.profiles)


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
    agents: AgentsSettings = Field(default_factory=AgentsSettings)
    models: ModelsSettings = Field(default_factory=ModelsSettings)

    def has_risky_content(self) -> bool:
        """Verdadeiro se a camada traz algo que executa código ou afrouxa o PEP."""
        return bool(
            self.hooks
            or self.permissions.allow
            or self.mode
            or self.mcp
            or self.env
            or self.daily_budget_usd is not None
            or self.agents.is_set()
            or self.models.is_set()
        )

    def restricted(self) -> Settings:
        """Versão segura de uma camada não confiável: só restringe.

        Mantém ``deny``/``ask``, ``model`` e ``effort``. Descarta ``allow``,
        hooks, ``mode``, ``mcp``, ``env``, orçamento, ``agents`` e ``models``.
        """
        return Settings(
            model=self.model,
            effort=self.effort,
            permissions=Permissions(deny=list(self.permissions.deny), ask=list(self.permissions.ask)),
        )
