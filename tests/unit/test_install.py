"""Instalação fora da venv, atualização e reversão (ADR-044, v0.5.2 Sprint 1). Sem rede: a origem
é um repositório git local com tags."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from orion import install
from orion.governance.nuclear import BlastRadiusClassifier
from orion.install import InstallError, Layout


def _fake_builder(target: Path, source: Path, editable: bool) -> None:
    """Simula a venv: grava os executáveis que os atalhos chamam."""
    bin_dir = target / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    for name in install.SHIM_NAMES:
        exe = bin_dir / name
        exe.write_text(f"#!/bin/sh\necho {name} {source.name} {'dev' if editable else 'fixo'}\n")
        exe.chmod(0o755)


def _checkout(path: Path, version: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text(f'[project]\nname = "orion-agent"\nversion = "{version}"\n')
    return path


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def layout(tmp_path: Path) -> Layout:
    return Layout(tmp_path / "share" / "orion", tmp_path / "bin")


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """Repositório de origem com as tags v0.5.1 e v0.5.2."""
    repo = _checkout(tmp_path / "origin", "0.5.1")
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "add", ".", cwd=repo)
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "a", cwd=repo)
    _git("tag", "v0.5.1", cwd=repo)
    (repo / "pyproject.toml").write_text('[project]\nname = "orion-agent"\nversion = "0.5.2"\n')
    _git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qam", "b", cwd=repo)
    _git("tag", "v0.5.2", cwd=repo)
    return repo


def test_version_order_handles_prereleases() -> None:
    ordered = sorted(["0.5.2-alpha", "0.5.2", "v0.5.10", "0.5.2-rc1", "0.4.0"], key=install.version_key)
    assert ordered == ["0.4.0", "0.5.2-alpha", "0.5.2-rc1", "0.5.2", "v0.5.10"]
    with pytest.raises(ValueError):
        install.version_key("latest")


def test_install_creates_version_current_and_shims(tmp_path: Path, layout: Layout) -> None:
    source = _checkout(tmp_path / "repo", "0.5.2")
    version = install.install(source, layout=layout, builder=_fake_builder, origin="")
    assert version == "0.5.2"
    assert layout.current.is_symlink()
    assert layout.current.resolve() == layout.version_dir("0.5.2").resolve()
    shim = layout.bin_dir / "orion"
    body = shim.read_text()
    assert str(layout.current / "venv" / "bin" / "orion") in body
    assert shim.stat().st_mode & 0o111
    out = subprocess.run([str(shim)], capture_output=True, text=True, check=True).stdout
    assert out.strip() == "orion repo fixo"
    meta = json.loads((layout.version_dir("0.5.2") / "meta.json").read_text())
    assert meta["version"] == "0.5.2" and meta["editable"] == "0"


def test_dev_install_is_named_dev_and_refuses_update(tmp_path: Path, layout: Layout) -> None:
    source = _checkout(tmp_path / "repo", "0.5.2")
    assert install.install(source, layout=layout, editable=True, builder=_fake_builder, origin="x") == "dev"
    with pytest.raises(InstallError, match="git pull"):
        install.check_update(layout)


def test_failed_build_leaves_current_untouched(tmp_path: Path, layout: Layout) -> None:
    install.install(_checkout(tmp_path / "a", "0.5.1"), layout=layout, builder=_fake_builder, origin="")

    def broken(target: Path, source: Path, editable: bool) -> None:
        raise InstallError("pip falhou")

    with pytest.raises(InstallError):
        install.install(_checkout(tmp_path / "b", "0.5.2"), layout=layout, builder=broken, origin="")
    assert install.read_state(layout)["current"] == "0.5.1"
    assert not layout.version_dir("0.5.2").exists()


def test_update_rollback_and_prune(origin: Path, tmp_path: Path, layout: Layout) -> None:
    install.install(_checkout(tmp_path / "old", "0.5.0"), layout=layout, builder=_fake_builder, origin=str(origin))
    install.install(_checkout(tmp_path / "mid", "0.5.1"), layout=layout, builder=_fake_builder, origin=str(origin))

    plan = install.check_update(layout)
    assert plan.current == "0.5.1" and plan.latest == "v0.5.2" and plan.available
    assert install.apply_update(plan, layout, builder=_fake_builder) == "0.5.2"
    state = install.read_state(layout)
    assert state == {"current": "0.5.2", "previous": "0.5.1"}
    assert install.installed_versions(layout) == ["0.5.2", "0.5.1"]  # 0.5.0 podada
    assert not (layout.root / "checkouts" / "0.5.2").exists()

    assert install.rollback(layout) == "0.5.1"
    assert layout.current.resolve() == layout.version_dir("0.5.1").resolve()
    assert install.check_update(layout).available


def test_up_to_date_and_bad_origin(origin: Path, tmp_path: Path, layout: Layout) -> None:
    install.install(_checkout(tmp_path / "x", "0.5.2"), layout=layout, builder=_fake_builder, origin=str(origin))
    assert not install.check_update(layout).available
    with pytest.raises(InstallError, match="nenhuma versão nova"):
        install.apply_update(install.check_update(layout), layout, builder=_fake_builder)
    with pytest.raises(InstallError, match="não consegui listar"):
        install.remote_versions(str(tmp_path / "nao-existe"))


def test_check_update_without_install(layout: Layout) -> None:
    with pytest.raises(InstallError, match="install.sh"):
        install.check_update(layout)
    with pytest.raises(InstallError, match="anterior"):
        install.rollback(layout)


def test_diagnose_reports_missing_shim_path_and_duplicate(tmp_path: Path, layout: Layout) -> None:
    rows = dict((name, (ok, detail)) for name, ok, detail in install.diagnose(layout, path_env="/usr/bin"))
    assert rows["Atalho"][0] is False and "install.sh" in rows["Atalho"][1]

    install.install(_checkout(tmp_path / "r", "0.5.2"), layout=layout, builder=_fake_builder, origin="")
    rows = dict((n, (ok, d)) for n, ok, d in install.diagnose(layout, path_env="/usr/bin"))
    assert rows["Atalho"][0] is False and "PATH" in rows["Atalho"][1]

    rows = dict(
        (n, (ok, d))
        for n, ok, d in install.diagnose(layout, path_env=str(layout.bin_dir), executable="/repo/.venv/bin/python")
    )
    assert rows["Atalho"][0] is True
    assert "há também a instalada" in rows["Instalação"][1]


def test_main_installs_from_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path))
    source = _checkout(tmp_path / "repo", "0.5.2")
    monkeypatch.setattr(install, "install", _wrap_install(install.install))
    assert install.main(["--source", str(source)]) == 0
    assert "instalado" in capsys.readouterr().out
    assert (tmp_path / ".local" / "bin" / "orion").is_file()
    assert install.main(["--source", str(tmp_path / "vazio")]) == 1


def _wrap_install(real):  # type: ignore[no-untyped-def]
    def wrapper(source, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["builder"] = _fake_builder
        kwargs.setdefault("origin", "")
        return real(source, **kwargs)

    return wrapper


def test_agent_self_update_is_nuclear() -> None:
    assert BlastRadiusClassifier.is_nuclear("orion update --yes")
    assert BlastRadiusClassifier.is_nuclear("orion-agent update")
    assert BlastRadiusClassifier.is_nuclear("python3 -m orion.install --dev")
    assert not BlastRadiusClassifier.is_nuclear("orion --version")


def test_update_command_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    from orion import cli

    monkeypatch.setattr(install, "rollback", lambda: "0.5.1")
    assert cli.run_update(rollback=True) == 0

    plan = install.UpdatePlan(current="0.5.1", latest="v0.5.2", origin="o")
    monkeypatch.setattr(install, "check_update", lambda: plan)
    assert cli.run_update(check=True) == 0
    applied: list[str] = []
    monkeypatch.setattr(install, "apply_update", lambda p: applied.append(p.latest) or "0.5.2")
    assert cli.run_update(yes=True) == 0 and applied == ["v0.5.2"]
    # sem TTY e sem --yes: recusa
    monkeypatch.setattr(type(cli.console), "is_terminal", property(lambda self: False))
    assert cli.run_update() == 2

    monkeypatch.setattr(install, "check_update", lambda: install.UpdatePlan("0.5.2", "v0.5.2", "o"))
    assert cli.run_update() == 0

    def fail() -> install.UpdatePlan:
        raise InstallError("x")

    monkeypatch.setattr(install, "check_update", fail)
    assert cli.run_update() == 1
