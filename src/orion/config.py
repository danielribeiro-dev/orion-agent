"""
O.R.I.O.N — Configuration Models
Pydantic v2 typed configuration contracts for runtime, providers and paths.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RoutingMode(str, Enum):
    """Controls how the Model Gateway selects LLM providers per turn.

    AUTO  — Dynamic routing: ORION autonomously switches between heavy-reasoning
            models (Claude Sonnet/Opus) and fast-execution models (Gemini Flash /
            Qwen Coder) based on turn complexity score.
    FIXED — Always uses the single provider specified in `OrionConfig.fixed_provider`.
    """

    AUTO = "auto"
    FIXED = "fixed"


class AutonomyLevel(str, Enum):
    """Maps to PEP governance levels.

    SUPERVISED — Requires explicit [Y/n] confirmation for every mutating action.
    SEMI_AUTO  — Confirms only destructive (LEVEL_2+) actions.
    AUTONOMOUS — No confirmations; all PEP checks are logged but non-blocking.
                 USE WITH CAUTION — reserved for trusted, isolated environments.
    """

    SUPERVISED = "supervised"
    SEMI_AUTO = "semi_auto"
    AUTONOMOUS = "autonomous"


class ProviderName(str, Enum):
    """Supported LLM providers."""

    OPENROUTER = "openrouter"
    GEMINI = "gemini"
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ProviderConfig(BaseModel):
    """Configuration for a single LLM provider endpoint."""

    model_config = {"frozen": True}

    name: ProviderName
    api_key: str | None = Field(
        default=None,
        description="API key for authentication. If None, reads from environment variable.",
    )
    base_url: str | None = Field(
        default=None,
        description="Override the provider's default base URL (useful for proxies/Ollama).",
    )
    default_model: str = Field(
        description="Default model identifier to use for this provider.",
    )
    timeout_seconds: Annotated[int, Field(ge=5, le=300)] = Field(
        default=60,
        description="Request timeout in seconds.",
    )
    max_retries: Annotated[int, Field(ge=0, le=10)] = Field(
        default=3,
        description="Maximum number of retries on transient errors.",
    )


class PathsConfig(BaseModel):
    """Filesystem paths used by ORION for persistent data."""

    model_config = {"frozen": True}

    global_home: Path = Field(
        default_factory=lambda: Path.home() / ".orion",
        description="Global ORION home directory for persistent data across all projects.",
    )
    local_home: Path = Field(
        default_factory=lambda: Path(".orion"),
        description="Project-local ORION directory (relative to CWD).",
    )

    @property
    def global_artifacts_dir(self) -> Path:
        """Directory for global artifact storage."""
        return self.global_home / "brain"

    @property
    def global_audit_log(self) -> Path:
        """Append-only audit log path."""
        return self.global_home / "audit.log"

    @property
    def local_artifacts_dir(self) -> Path:
        """Directory for project-local artifact storage."""
        return self.local_home / "artifacts"

    @field_validator("global_home", "local_home", mode="before")
    @classmethod
    def expand_path(cls, v: object) -> Path:
        """Expand ~ and env vars in path strings."""
        if isinstance(v, str):
            return Path(v).expanduser()
        if isinstance(v, Path):
            return v.expanduser()
        return Path(str(v)).expanduser()  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------


class OrionConfig(BaseModel):
    """Root configuration for the ORION agent runtime."""

    model_config = {"frozen": True}

    # --- Routing & Intelligence ---
    routing_mode: RoutingMode = Field(
        default=RoutingMode.AUTO,
        description="Model Gateway routing strategy.",
    )
    fixed_provider: ProviderName | None = Field(
        default=None,
        description="Provider to use when routing_mode=FIXED. Required in FIXED mode.",
    )
    providers: list[ProviderConfig] = Field(
        default_factory=list,
        description="List of configured LLM providers.",
    )

    # --- Governance ---
    autonomy_level: AutonomyLevel = Field(
        default=AutonomyLevel.SUPERVISED,
        description="PEP autonomy level. Defaults to safest mode.",
    )

    # --- Turn Budgeting ---
    max_turns: Annotated[int, Field(ge=1, le=100)] = Field(
        default=20,
        description="Maximum reasoning turns before the engine halts and requests user input.",
    )

    # --- Paths ---
    paths: PathsConfig = Field(
        default_factory=PathsConfig,
        description="Filesystem path configuration.",
    )

    @model_validator(mode="after")
    def validate_fixed_mode(self) -> OrionConfig:
        """Ensure fixed_provider is set when routing_mode is FIXED."""
        if self.routing_mode == RoutingMode.FIXED and self.fixed_provider is None:
            raise ValueError(
                "fixed_provider must be set when routing_mode is RoutingMode.FIXED."
            )
        return self

    @classmethod
    def default(cls) -> OrionConfig:
        """Return a safe, minimal default config suitable for first-run."""
        return cls(
            routing_mode=RoutingMode.AUTO,
            autonomy_level=AutonomyLevel.SUPERVISED,
            max_turns=20,
        )
