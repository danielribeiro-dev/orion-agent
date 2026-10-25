"""
Shared pytest fixtures for ORION test suite.
Provides async utilities, config mocks and CLI test runner.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from orion.cli import app
from orion.config import (
    AutonomyLevel,
    OrionConfig,
    PathsConfig,
    ProviderConfig,
    ProviderName,
    RoutingMode,
)


# ---------------------------------------------------------------------------
# CLI Runner
# ---------------------------------------------------------------------------


@pytest.fixture()
def cli_runner() -> CliRunner:
    """Typer CLI test runner (isolated, no sys.exit)."""
    return CliRunner()


@pytest.fixture()
def invoke(cli_runner: CliRunner):  # type: ignore[no-untyped-def]
    """Helper that invokes the ORION CLI and returns the Result."""

    def _invoke(*args: str):  # type: ignore[no-untyped-def]
        return cli_runner.invoke(app, list(args))

    return _invoke


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def default_config() -> OrionConfig:
    """Minimal safe default config."""
    return OrionConfig.default()


@pytest.fixture()
def fixed_config() -> OrionConfig:
    """Config with FIXED routing mode pointing to Ollama."""
    return OrionConfig(
        routing_mode=RoutingMode.FIXED,
        fixed_provider=ProviderName.OLLAMA,
        autonomy_level=AutonomyLevel.SUPERVISED,
        max_turns=10,
    )


@pytest.fixture()
def anthropic_provider() -> ProviderConfig:
    """Sample Anthropic provider config."""
    return ProviderConfig(
        name=ProviderName.ANTHROPIC,
        default_model="claude-sonnet-4-5",
        api_key="test-key-anthropic",
    )


@pytest.fixture()
def ollama_provider() -> ProviderConfig:
    """Sample Ollama (local) provider config."""
    return ProviderConfig(
        name=ProviderName.OLLAMA,
        default_model="qwen2.5-coder:7b",
        base_url="http://localhost:11434",
    )


@pytest.fixture()
def tmp_paths(tmp_path: pytest.TempPathFactory) -> PathsConfig:
    """PathsConfig pointing to pytest's tmp_path for isolation."""
    return PathsConfig(
        global_home=tmp_path / ".orion_global",
        local_home=tmp_path / ".orion_local",
    )
