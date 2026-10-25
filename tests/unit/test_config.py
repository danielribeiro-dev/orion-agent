"""
Unit tests for src/orion/config.py
Covers: enums, ProviderConfig, PathsConfig, OrionConfig validation and defaults.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from orion.config import (
    AutonomyLevel,
    OrionConfig,
    PathsConfig,
    ProviderConfig,
    ProviderName,
    RoutingMode,
)


# ---------------------------------------------------------------------------
# RoutingMode
# ---------------------------------------------------------------------------


class TestRoutingMode:
    def test_values(self) -> None:
        assert RoutingMode.AUTO.value == "auto"
        assert RoutingMode.FIXED.value == "fixed"

    def test_from_string(self) -> None:
        assert RoutingMode("auto") is RoutingMode.AUTO
        assert RoutingMode("fixed") is RoutingMode.FIXED

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            RoutingMode("invalid")


# ---------------------------------------------------------------------------
# AutonomyLevel
# ---------------------------------------------------------------------------


class TestAutonomyLevel:
    def test_values(self) -> None:
        assert AutonomyLevel.SUPERVISED.value == "supervised"
        assert AutonomyLevel.SEMI_AUTO.value == "semi_auto"
        assert AutonomyLevel.AUTONOMOUS.value == "autonomous"

    def test_from_string(self) -> None:
        assert AutonomyLevel("supervised") is AutonomyLevel.SUPERVISED


# ---------------------------------------------------------------------------
# ProviderConfig
# ---------------------------------------------------------------------------


class TestProviderConfig:
    def test_minimal_valid(self, anthropic_provider: ProviderConfig) -> None:
        assert anthropic_provider.name == ProviderName.ANTHROPIC
        assert anthropic_provider.default_model == "claude-sonnet-4-5"

    def test_timeout_bounds(self) -> None:
        # Below minimum
        with pytest.raises(ValidationError):
            ProviderConfig(
                name=ProviderName.OPENAI,
                default_model="gpt-4o",
                timeout_seconds=4,
            )
        # Above maximum
        with pytest.raises(ValidationError):
            ProviderConfig(
                name=ProviderName.OPENAI,
                default_model="gpt-4o",
                timeout_seconds=301,
            )

    def test_max_retries_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ProviderConfig(
                name=ProviderName.OPENAI,
                default_model="gpt-4o",
                max_retries=-1,
            )
        with pytest.raises(ValidationError):
            ProviderConfig(
                name=ProviderName.OPENAI,
                default_model="gpt-4o",
                max_retries=11,
            )

    def test_defaults(self) -> None:
        p = ProviderConfig(name=ProviderName.OLLAMA, default_model="llama3")
        assert p.timeout_seconds == 60
        assert p.max_retries == 3
        assert p.api_key is None
        assert p.base_url is None

    def test_ollama_base_url(self, ollama_provider: ProviderConfig) -> None:
        assert ollama_provider.base_url == "http://localhost:11434"

    def test_frozen(self, anthropic_provider: ProviderConfig) -> None:
        """ProviderConfig must be immutable (frozen Pydantic model)."""
        with pytest.raises(Exception):
            anthropic_provider.api_key = "new-key"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PathsConfig
# ---------------------------------------------------------------------------


class TestPathsConfig:
    def test_default_global_home(self) -> None:
        paths = PathsConfig()
        assert paths.global_home == Path.home() / ".orion"

    def test_default_local_home(self) -> None:
        paths = PathsConfig()
        assert paths.local_home == Path(".orion")

    def test_derived_properties(self, tmp_paths: PathsConfig) -> None:
        assert tmp_paths.global_artifacts_dir == tmp_paths.global_home / "brain"
        assert tmp_paths.global_audit_log == tmp_paths.global_home / "audit.log"
        assert tmp_paths.local_artifacts_dir == tmp_paths.local_home / "artifacts"

    def test_tilde_expansion(self) -> None:
        paths = PathsConfig(global_home="~/.orion_test")
        assert not str(paths.global_home).startswith("~")

    def test_frozen(self) -> None:
        paths = PathsConfig()
        with pytest.raises(Exception):
            paths.global_home = Path("/other")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# OrionConfig
# ---------------------------------------------------------------------------


class TestOrionConfig:
    def test_default_factory(self, default_config: OrionConfig) -> None:
        assert default_config.routing_mode == RoutingMode.AUTO
        assert default_config.autonomy_level == AutonomyLevel.SUPERVISED
        assert default_config.max_turns == 20
        assert default_config.fixed_provider is None
        assert default_config.providers == []

    def test_fixed_mode_requires_provider(self) -> None:
        with pytest.raises(ValidationError, match="fixed_provider must be set"):
            OrionConfig(routing_mode=RoutingMode.FIXED)

    def test_fixed_mode_with_provider(self, fixed_config: OrionConfig) -> None:
        assert fixed_config.routing_mode == RoutingMode.FIXED
        assert fixed_config.fixed_provider == ProviderName.OLLAMA

    def test_max_turns_bounds(self) -> None:
        with pytest.raises(ValidationError):
            OrionConfig(max_turns=0)
        with pytest.raises(ValidationError):
            OrionConfig(max_turns=101)

    def test_valid_max_turns_boundary(self) -> None:
        low = OrionConfig(max_turns=1)
        assert low.max_turns == 1
        high = OrionConfig(max_turns=100)
        assert high.max_turns == 100

    def test_frozen(self, default_config: OrionConfig) -> None:
        with pytest.raises(Exception):
            default_config.max_turns = 5  # type: ignore[misc]

    def test_with_providers(
        self,
        anthropic_provider: ProviderConfig,
        ollama_provider: ProviderConfig,
    ) -> None:
        config = OrionConfig(providers=[anthropic_provider, ollama_provider])
        assert len(config.providers) == 2
        assert config.providers[0].name == ProviderName.ANTHROPIC
        assert config.providers[1].name == ProviderName.OLLAMA

    def test_paths_are_pathsconfig_instance(self, default_config: OrionConfig) -> None:
        assert isinstance(default_config.paths, PathsConfig)

    def test_custom_paths(self, tmp_paths: PathsConfig) -> None:
        config = OrionConfig(paths=tmp_paths)
        assert config.paths is tmp_paths
