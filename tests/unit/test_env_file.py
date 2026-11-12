"""~/.orion/.env: leitura, precedência, criação 0600 e proteção do PEP (v0.5.1)."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from orion.gateway.credentials import (
    ENV_FILE_NAME,
    ensure_env_file,
    inspect_anthropic_key,
    load_anthropic_key,
    load_openrouter_key,
    openrouter_key_status,
    read_env_file,
)
from orion.governance.pep import is_protected_state_path, is_secret_path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_ensure_creates_template_with_0600(tmp_path: Path) -> None:
    path = ensure_env_file(tmp_path)
    assert path == tmp_path / ENV_FILE_NAME
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "OPENROUTER_API_KEY=" in path.read_text()
    assert read_env_file(tmp_path) == {"OPENROUTER_API_KEY": ""}


def test_ensure_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / ENV_FILE_NAME).write_text("OPENROUTER_API_KEY=sk-or-mine\n")
    ensure_env_file(tmp_path)
    assert read_env_file(tmp_path)["OPENROUTER_API_KEY"] == "sk-or-mine"


def test_parsing_comments_quotes_and_export(tmp_path: Path) -> None:
    (tmp_path / ENV_FILE_NAME).write_text(
        '# comentário\n\nexport OPENROUTER_API_KEY="sk-or-abc"\nOUTRA = \'x y\'\nlinha sem igual\n'
    )
    assert read_env_file(tmp_path) == {"OPENROUTER_API_KEY": "sk-or-abc", "OUTRA": "x y"}


def test_precedence_env_then_dotenv_then_legacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "openrouter_api_key").write_text("sk-or-legacy")
    assert load_openrouter_key(tmp_path) == "sk-or-legacy"
    (tmp_path / ENV_FILE_NAME).write_text("OPENROUTER_API_KEY=sk-or-dotenv\n")
    assert load_openrouter_key(tmp_path) == "sk-or-dotenv"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-shell")
    assert load_openrouter_key(tmp_path) == "sk-or-shell"


def test_empty_template_counts_as_absent(tmp_path: Path) -> None:
    ensure_env_file(tmp_path)
    assert load_openrouter_key(tmp_path) is None
    ok, detail = openrouter_key_status(tmp_path)
    assert not ok and "~/.orion/.env" in detail


def test_status_flags_open_permissions_without_leaking(tmp_path: Path) -> None:
    env = tmp_path / ENV_FILE_NAME
    env.write_text("OPENROUTER_API_KEY=sk-or-secret\n")
    env.chmod(0o644)
    ok, detail = openrouter_key_status(tmp_path)
    assert not ok and "chmod 600" in detail and "sk-or-secret" not in detail
    env.chmod(0o600)
    assert openrouter_key_status(tmp_path) == (True, "configurada via .env")


def test_anthropic_key_from_dotenv(tmp_path: Path) -> None:
    env = tmp_path / ENV_FILE_NAME
    env.write_text("ANTHROPIC_API_KEY=sk-ant-x\n")
    env.chmod(0o600)
    assert load_anthropic_key(tmp_path) == "sk-ant-x"
    status = inspect_anthropic_key(tmp_path)
    assert status.ok and status.source == ".env"


def test_secret_paths(tmp_path: Path) -> None:
    home = tmp_path / ".orion"
    assert is_secret_path(str(home / ".env"), home)
    assert is_secret_path(str(home / "openrouter_api_key"), home)
    assert is_secret_path(str(home / "secrets" / "telegram_token"), home)
    assert is_secret_path(str(home), home)  # busca recursiva a partir da raiz
    assert not is_secret_path(str(home / "timeline.db"), home)
    assert not is_secret_path(str(tmp_path / ".env"), home)  # .env de projeto não é do ORION
    assert is_protected_state_path(str(home / ".env"), home)


async def test_pep_denies_reading_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orion.core.events import Action, RiskLevel
    from orion.governance.pep import ActionDenied
    from tests.unit.test_core_fixes_v050 import _pep

    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".orion").mkdir()
    pep = _pep(tmp_path)
    for tool, params in (
        ("read_file", {"path": "~/.orion/.env"}),
        ("grep", {"pattern": "KEY", "path": "~/.orion"}),
        ("write_file", {"path": "~/.orion/.env", "content": "x"}),
    ):
        action = Action(tool=tool, params=params, risk_level=RiskLevel.SAFE)
        with pytest.raises(ActionDenied):
            await pep.evaluate(action)
