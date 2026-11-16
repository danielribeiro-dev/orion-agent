"""Instalação fora da venv, atualização e reversão (ADR-044).

Layout (código; os dados do Senhor ficam só em ``~/.orion``)::

    ~/.local/share/orion/
        versions/<versão>/venv/      venv própria de cada versão
        versions/<versão>/src/       checkout da tag (atualizações)
        versions/<versão>/meta.json  origem, versão, modo editável
        current -> versions/<versão> symlink trocado de forma atômica
        state.json                   versão atual e anterior (rollback)
    ~/.local/bin/orion, orion-agent  atalhos que executam current/venv/bin/orion

Este módulo só usa a biblioteca padrão: ``scripts/install.sh`` o executa com o ``python3`` do
sistema antes de existir qualquer venv. Rede só por comando explícito (``git ls-remote``/``clone``).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

SHIM_NAMES = ("orion", "orion-agent")
KEEP_VERSIONS = 2
_TAG = re.compile(r"refs/tags/(v?\d+\.\d+\.\d+(?:[-.]?(?:a|alpha|b|beta|rc)\.?\d*)?)$")

Runner = Callable[..., subprocess.CompletedProcess[str]]
Builder = Callable[[Path, Path, bool], None]
"""Cria a venv em ``target/venv`` e instala o pacote de ``source`` (editável ou não)."""


class InstallError(RuntimeError):
    """Falha de instalação com mensagem pronta para o Senhor."""


@dataclass(frozen=True)
class Layout:
    root: Path
    bin_dir: Path

    @classmethod
    def default(cls) -> Layout:
        data = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return cls(Path(data) / "orion", Path.home() / ".local" / "bin")

    @property
    def versions(self) -> Path:
        return self.root / "versions"

    @property
    def current(self) -> Path:
        return self.root / "current"

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    def version_dir(self, version: str) -> Path:
        return self.versions / version


# ── Versões ─────────────────────────────────────────────────────────────

_PRE_ORDER = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}


def version_key(version: str) -> tuple[int, int, int, int, int]:
    """Ordena ``0.5.2`` > ``0.5.2-rc1`` > ``0.5.2-alpha``; aceita prefixo ``v``."""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:[-.]?(a|alpha|b|beta|rc)\.?(\d*))?", version.strip())
    if match is None:
        raise ValueError(f"versão inválida: {version}")
    major, minor, patch, pre, num = match.groups()
    if pre is None:
        return int(major), int(minor), int(patch), 9, 0
    return int(major), int(minor), int(patch), _PRE_ORDER[pre], int(num or 0)


def remote_versions(origin: str, runner: Runner = subprocess.run) -> list[str]:
    """Tags ``vX.Y.Z`` do repositório de origem, da mais nova para a mais antiga."""
    proc = runner(
        ["git", "ls-remote", "--tags", origin],
        capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode != 0:
        raise InstallError(f"não consegui listar as versões de {origin}: {proc.stderr.strip()[:200]}")
    tags = set()
    for line in proc.stdout.splitlines():
        match = _TAG.search(line.split("\t")[-1].removesuffix("^{}"))
        if match:
            tags.add(match.group(1))
    return sorted(tags, key=version_key, reverse=True)


# ── Estado ──────────────────────────────────────────────────────────────


def read_state(layout: Layout) -> dict[str, str]:
    try:
        data = json.loads(layout.state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(v) for k, v in data.items() if isinstance(v, str)}


def _write_state(layout: Layout, state: dict[str, str]) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    tmp = layout.state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, layout.state_file)


def read_meta(path: Path) -> dict[str, str]:
    try:
        data = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: str(v) for k, v in data.items()}


def installed_versions(layout: Layout) -> list[str]:
    if not layout.versions.is_dir():
        return []
    return sorted((p.name for p in layout.versions.iterdir() if p.is_dir()), key=_safe_key, reverse=True)


def _safe_key(version: str) -> tuple[int, int, int, int, int]:
    try:
        return version_key(version)
    except ValueError:
        return (-1, 0, 0, 0, 0)


# ── Peças da instalação ─────────────────────────────────────────────────


def switch_current(layout: Layout, version: str) -> None:
    """Aponta ``current`` para a versão de forma atômica (link temporário + ``os.replace``)."""
    target = layout.version_dir(version)
    if not target.is_dir():
        raise InstallError(f"versão {version} não está instalada")
    tmp = layout.root / ".current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(target, target_is_directory=True)
    os.replace(tmp, layout.current)
    state = read_state(layout)
    if state.get("current") and state["current"] != version:
        state["previous"] = state["current"]
    state["current"] = version
    _write_state(layout, state)


def write_shims(layout: Layout) -> list[Path]:
    """Atalhos em ``~/.local/bin`` que executam a versão atual, sem precisar ativar venv."""
    layout.bin_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in SHIM_NAMES:
        shim = layout.bin_dir / name
        target = layout.current / "venv" / "bin" / name
        body = (
            "#!/bin/sh\n"
            "# Atalho do O.R.I.O.N (ADR-044): executa a versão em ~/.local/share/orion/current\n"
            "unset PYTHONHOME PYTHONPATH\n"
            f'exec "{target}" "$@"\n'
        )
        if shim.is_symlink():
            shim.unlink()
        shim.write_text(body, encoding="utf-8")
        shim.chmod(0o755)
        written.append(shim)
    return written


def prune(layout: Layout) -> list[str]:
    """Remove versões antigas: ficam só a atual e a anterior (``KEEP_VERSIONS``)."""
    state = read_state(layout)
    protected = {state.get("current", ""), state.get("previous", "")} - {""}
    removed = []
    for version in installed_versions(layout):
        if version not in protected:
            shutil.rmtree(layout.version_dir(version), ignore_errors=True)
            removed.append(version)
    return removed


def default_builder(target: Path, source: Path, editable: bool) -> None:
    """Cria ``target/venv`` e instala o ORION de ``source`` (usa ``uv`` quando disponível)."""
    venv = target / "venv"
    spec = ["-e", str(source)] if editable else [str(source)]
    uv = shutil.which("uv")
    if uv:
        _run([uv, "venv", "--quiet", "--python", sys.executable, str(venv)])
        _run([uv, "pip", "install", "--quiet", "--python", str(venv / "bin" / "python"), *spec])
        return
    _run([sys.executable, "-m", "venv", str(venv)])
    _run([str(venv / "bin" / "python"), "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    _run([str(venv / "bin" / "python"), "-m", "pip", "install", "--quiet", *spec])


def _run(cmd: Sequence[str]) -> None:
    proc = subprocess.run(list(cmd), capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise InstallError(f"falhou: {' '.join(cmd[:3])}…\n{proc.stderr.strip()[-800:]}")


def source_version(source: Path) -> str:
    """Versão declarada no ``pyproject.toml`` do checkout."""
    import tomllib

    with (source / "pyproject.toml").open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def git_origin(source: Path, runner: Runner = subprocess.run) -> str:
    proc = runner(
        ["git", "-C", str(source), "remote", "get-url", "origin"],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def install(
    source: Path,
    *,
    layout: Layout | None = None,
    editable: bool = False,
    version: str | None = None,
    origin: str | None = None,
    builder: Builder = default_builder,
) -> str:
    """Instala o checkout *source* como uma versão e a torna a atual. Devolve a versão."""
    layout = layout or Layout.default()
    source = source.resolve()
    if not (source / "pyproject.toml").is_file():
        raise InstallError(f"{source} não é um checkout do ORION (sem pyproject.toml)")
    name = "dev" if editable else (version or source_version(source))
    target = layout.version_dir(name)
    # A venv grava caminhos absolutos nos scripts: constrói no lugar final. Reinstalar a mesma
    # versão guarda a anterior ao lado e a restaura se a construção falhar.
    backup = layout.versions / f".{name}.old"
    shutil.rmtree(backup, ignore_errors=True)
    layout.versions.mkdir(parents=True, exist_ok=True)
    if target.exists():
        os.replace(target, backup)
    target.mkdir()
    try:
        builder(target, source, editable)
        meta = {
            "version": source_version(source),
            "editable": "1" if editable else "0",
            "source": str(source),
            "origin": origin if origin is not None else git_origin(source),
        }
        (target / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        if backup.exists():
            os.replace(backup, target)
        raise
    shutil.rmtree(backup, ignore_errors=True)
    switch_current(layout, name)
    write_shims(layout)
    prune(layout)
    return name


@dataclass
class UpdatePlan:
    current: str
    latest: str | None
    origin: str

    @property
    def available(self) -> bool:
        return self.latest is not None and _safe_key(self.latest) > _safe_key(self.current)


def check_update(layout: Layout | None = None, runner: Runner = subprocess.run) -> UpdatePlan:
    layout = layout or Layout.default()
    state = read_state(layout)
    current = state.get("current", "")
    if not current:
        raise InstallError("o ORION não está instalado em ~/.local/share/orion (rode scripts/install.sh)")
    meta = read_meta(layout.version_dir(current))
    if meta.get("editable") == "1":
        raise InstallError("instalação de desenvolvimento (editável): atualize com git pull no repositório")
    origin = meta.get("origin", "")
    if not origin:
        raise InstallError("origem desconhecida: reinstale com scripts/install.sh a partir de um clone git")
    tags = remote_versions(origin, runner)
    installed_version = meta.get("version", current)
    return UpdatePlan(current=installed_version, latest=tags[0] if tags else None, origin=origin)


def apply_update(
    plan: UpdatePlan,
    layout: Layout | None = None,
    runner: Runner = subprocess.run,
    builder: Builder = default_builder,
) -> str:
    """Clona a tag mais nova ao lado, instala e troca o ``current``."""
    layout = layout or Layout.default()
    if not plan.available or plan.latest is None:
        raise InstallError("nenhuma versão nova")
    name = plan.latest.removeprefix("v")
    checkout = layout.root / "checkouts" / name
    shutil.rmtree(checkout, ignore_errors=True)
    checkout.parent.mkdir(parents=True, exist_ok=True)
    proc = runner(
        ["git", "clone", "--quiet", "--depth", "1", "--branch", plan.latest, plan.origin, str(checkout)],
        capture_output=True, text=True, timeout=600, check=False,
    )
    if proc.returncode != 0:
        raise InstallError(f"falha ao baixar {plan.latest}: {proc.stderr.strip()[:300]}")
    try:
        return install(checkout, layout=layout, version=name, origin=plan.origin, builder=builder)
    finally:
        shutil.rmtree(checkout, ignore_errors=True)


def rollback(layout: Layout | None = None) -> str:
    layout = layout or Layout.default()
    state = read_state(layout)
    previous = state.get("previous", "")
    if not previous or not layout.version_dir(previous).is_dir():
        raise InstallError("não há versão anterior para voltar")
    switch_current(layout, previous)
    return previous


# ── Diagnóstico (/doctor) ───────────────────────────────────────────────


def diagnose(
    layout: Layout | None = None,
    path_env: str | None = None,
    executable: str | None = None,
) -> list[tuple[str, bool, str]]:
    """Linhas do ``/doctor``: atalho no PATH e instalação duplicada."""
    layout = layout or Layout.default()
    path_dirs = [Path(p) for p in (path_env if path_env is not None else os.environ.get("PATH", "")).split(os.pathsep) if p]
    shim = layout.bin_dir / "orion"
    state = read_state(layout)
    running = Path(executable or sys.executable).resolve()
    in_venv_repo = layout.root.resolve() not in running.parents
    rows: list[tuple[str, bool, str]] = []
    if not shim.is_file():
        rows.append(("Atalho", False, "ausente: rode scripts/install.sh para usar `orion` sem venv"))
    elif layout.bin_dir not in path_dirs:
        rows.append(("Atalho", False, f"{layout.bin_dir} fora do PATH (adicione ao ~/.profile)"))
    else:
        rows.append(("Atalho", True, f"{shim} → versão {state.get('current', '?')}"))
    if shim.is_file() and in_venv_repo:
        rows.append(("Instalação", True, f"rodando de {running.parent.parent} (há também a instalada)"))
    elif state.get("current"):
        rows.append(("Instalação", True, f"versão {state['current']} · anterior {state.get('previous', '-')}"))
    return rows


# ── CLI (``python -m orion.install``) ───────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orion-install", description="Instala o O.R.I.O.N fora da venv")
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--dev", action="store_true", help="instalação editável apontando para o checkout")
    args = parser.parse_args(argv)
    try:
        layout = Layout.default()
        version = install(Path(args.source), layout=layout, editable=args.dev)
    except InstallError as exc:
        print(f"✖ {exc}", file=sys.stderr)
        return 1
    print(f"✔ O.R.I.O.N {version} instalado em {layout.current}")
    if str(layout.bin_dir) not in os.environ.get("PATH", "").split(os.pathsep):
        print(f'! adicione ao PATH: export PATH="{layout.bin_dir}:$PATH"')
    else:
        print("● pronto: rode `orion` em qualquer terminal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
