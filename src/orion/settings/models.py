"""Modelos de settings (camadas user, projeto e local)."""

from __future__ import annotations

from typing import Any, Literal

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
    # Daemon (v0.5.0 Sprint 7)
    "DaemonStart",
    "DaemonStop",
    "ScheduleFire",
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
    """``tiers``: lista ordenada de candidatos por tier (``fast|balanced|heavy``).

    ``prefer_free``: modelos ``:free`` do catálogo passam à frente dos pagos em cada tier
    (roteamento automático e subagents). Tools mutantes continuam exigindo tier >= balanced.
    """

    model_config = ConfigDict(extra="ignore")

    tiers: dict[str, list[str]] = Field(default_factory=dict)
    prefer_free: bool = False
    profiles: dict[str, ModelProfile] = Field(default_factory=dict)

    def is_set(self) -> bool:
        return bool(self.tiers or self.profiles or self.prefer_free)


class NotifySettings(BaseModel):
    """Canais de notificação do daemon (ADR-032). O token do Telegram nunca fica aqui."""

    model_config = ConfigDict(extra="ignore")

    desktop: bool = True
    telegram: bool = False
    telegram_chat_id: int | None = None
    #: Validade de uma aprovação remota; expirada vale como negada.
    approval_ttl_s: int = Field(default=600, ge=30, le=86_400)


class PressureSettings(BaseModel):
    """Limiares do ``PressureMonitor`` (ADR-035). Entrada > saída: histerese."""

    model_config = ConfigDict(extra="ignore")

    sample_s: float = Field(default=10.0, ge=1.0, le=600.0)
    enter_cpu: float = Field(default=0.85, gt=0.0, le=1.0)
    exit_cpu: float = Field(default=0.60, gt=0.0, le=1.0)
    enter_mem: float = Field(default=0.90, gt=0.0, le=1.0)
    exit_mem: float = Field(default=0.75, gt=0.0, le=1.0)
    #: PSI ``some avg10`` de memória/CPU (percentual), quando o kernel expõe.
    enter_psi: float = Field(default=20.0, ge=0.0, le=100.0)
    exit_psi: float = Field(default=5.0, ge=0.0, le=100.0)
    min_dwell_s: float = Field(default=60.0, ge=0.0, le=3600.0)


class DaemonSettings(BaseModel):
    """Daemon opt-in (ADR-032). Só vale da camada do usuário: projeto nunca liga daemon."""

    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    autostart: Literal["off", "login", "boot"] = "off"
    boot_profile: Literal["auto", "minimal", "full"] = "auto"
    notifications: NotifySettings = Field(default_factory=NotifySettings)
    pressure: PressureSettings = Field(default_factory=PressureSettings)
    #: Teto de espera pela estabilização da máquina antes de subir componentes.
    stabilize_max_wait_s: float = Field(default=300.0, ge=0.0, le=3600.0)
    #: Teto diário em USD por origem (``cron``, ``daemon``, ``loop``). Nunca "sem limite".
    origin_budget_usd: dict[str, float] = Field(
        default_factory=lambda: {"cron": 0.50, "daemon": 0.25, "loop": 1.00}
    )
    max_concurrent_jobs: int = Field(default=2, ge=1, le=8)


class UiSettings(BaseModel):
    """Superfícies opcionais (ADR-034): pensamentos no stream e aba flutuante (v0.7.0)."""

    model_config = ConfigDict(extra="ignore")

    show_thinking: bool = False
    panel: bool = False


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
    daemon: DaemonSettings = Field(default_factory=DaemonSettings)
    ui: UiSettings = Field(default_factory=UiSettings)

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
