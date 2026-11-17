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


@pytest.fixture(autouse=True)
def _never_open_real_os_auth(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> None:
    """Nenhum teste pode abrir a autenticação real do SO (polkit, PAM, popup de senha).

    Testes que exercitam o gate fazem ``patch.object`` na instância, que tem
    precedência sobre este patch de classe.
    """
    from orion.tui import modal

    async def _no_popup(title: str, detail: str) -> None:
        return None

    monkeypatch.setattr(modal, "_graphical_secret", _no_popup)
    if request.module.__name__.endswith(("test_nuclear", "test_nuclear_auth")):
        return  # exercita as primitivas com subprocess/PAM simulados
    from orion.governance.nuclear import NuclearSafetyGate

    async def _blocked(self: object, _arg: str) -> tuple[str, bool]:
        return ("blocked_in_tests", False)

    monkeypatch.setattr(NuclearSafetyGate, "_try_polkit", _blocked)
    monkeypatch.setattr(NuclearSafetyGate, "_try_pam", _blocked)


@pytest.fixture(autouse=True)
def _no_real_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """A biblioteca ddgs faria rede de verdade: em teste, só com ``factory`` injetada."""
    from orion.runtime.search import SearchUnavailable
    from orion.runtime.search.providers import DdgsSearch

    original = DdgsSearch._make

    def guarded(self: DdgsSearch) -> object:
        if self._factory is None:
            raise SearchUnavailable("ddgs desligado nos testes")
        return original(self)

    monkeypatch.setattr(DdgsSearch, "_make", guarded)


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


@pytest.fixture(autouse=True)
def _no_live_recall(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recall por turno baixaria o modelo de embeddings; os testes o ligam explicitamente."""
    monkeypatch.setenv("ORION_RECALL", "0")
    # Estágio 2 do classificador (ADR-046) desligado: não consome o provider roteirizado.
    monkeypatch.setenv("ORION_CLASSIFIER_MODEL", "0")
