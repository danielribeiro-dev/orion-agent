"""Gestão da unit systemd de usuário do daemon (ADR-032).

Níveis: ``install`` (grava a unit), ``enable`` (inicia no login), ``enable --boot`` (exige
``loginctl enable-linger`` explícito). ``disable`` reverte tudo e preserva ``~/.orion/``.
Sem shell: comandos via ``create_subprocess_exec``.
"""

from __future__ import annotations

import asyncio
import getpass
import shlex
import sys
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

UNIT_NAME = "orion-daemon.service"
DOCS_URL = "https://github.com/danielribeiro-dev/orion-agent"


class ServiceError(RuntimeError):
    """Falha ao executar systemctl/loginctl."""


def render_unit(
    exec_start: list[str],
    *,
    environment: dict[str, str] | None = None,
    memory_high: str = "512M",
) -> str:
    """Gera o texto da unit com prioridade baixa de CPU/IO e teto suave de memória."""
    lines = [
        "[Unit]",
        "Description=O.R.I.O.N daemon",
        f"Documentation={DOCS_URL}",
        "",
        "[Service]",
        "Type=simple",
        f"ExecStart={shlex.join(exec_start)}",
        "Restart=on-failure",
        "RestartSec=5",
        "Nice=10",
        "CPUWeight=20",
        "IOWeight=20",
        f"MemoryHigh={memory_high}",
    ]
    for key, value in (environment or {}).items():
        lines.append(f"Environment={shlex.quote(f'{key}={value}')}")
    lines += ["NoNewPrivileges=yes", "", "[Install]", "WantedBy=default.target", ""]
    return "\n".join(lines)


class CommandResult(BaseModel):
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    async def run(self, argv: list[str]) -> CommandResult: ...


class SubprocessRunner:
    """Executa argv sem shell."""

    async def run(self, argv: list[str]) -> CommandResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
        except FileNotFoundError as exc:
            return CommandResult(returncode=127, stderr=str(exc))
        out, err = await proc.communicate()
        return CommandResult(
            returncode=proc.returncode or 0,
            stdout=out.decode(errors="replace"),
            stderr=err.decode(errors="replace"),
        )


class ServiceManager:
    """Instala, habilita e remove a unit de usuário do daemon."""

    def __init__(
        self,
        *,
        home: Path,
        unit_dir: Path | None = None,
        runner: CommandRunner | None = None,
        exec_start: list[str] | None = None,
        user: str | None = None,
    ) -> None:
        self._home = home
        self._unit_dir = unit_dir or Path.home() / ".config" / "systemd" / "user"
        self._runner: CommandRunner = runner or SubprocessRunner()
        self._exec = exec_start or [sys.executable, "-m", "orion.cli", "daemon", "run"]
        self._user = user or getpass.getuser()

    @property
    def unit_path(self) -> Path:
        return self._unit_dir / UNIT_NAME

    @property
    def _marker(self) -> Path:
        return self._home / "daemon" / "linger_by_orion"

    async def _run(self, argv: list[str], *, check: bool = True) -> CommandResult:
        result = await self._runner.run(argv)
        if check and result.returncode != 0:
            raise ServiceError(result.stderr.strip() or f"{argv[0]} falhou ({result.returncode})")
        return result

    async def _systemctl(self, *args: str, check: bool = True) -> CommandResult:
        return await self._run(["systemctl", "--user", *args], check=check)

    async def install(self) -> Path:
        self._unit_dir.mkdir(parents=True, exist_ok=True)
        self.unit_path.write_text(render_unit(self._exec))
        self.unit_path.chmod(0o644)
        await self._systemctl("daemon-reload")
        return self.unit_path

    async def enable(self, *, boot: bool = False) -> None:
        if not self.unit_path.exists():
            await self.install()
        await self._systemctl("enable", UNIT_NAME)
        if boot:
            await self._run(["loginctl", "enable-linger", self._user])
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._marker.write_text(self._user)

    async def disable(self) -> None:
        await self._systemctl("disable", "--now", UNIT_NAME, check=False)
        if self.unit_path.exists():
            self.unit_path.unlink()
        await self._systemctl("daemon-reload", check=False)
        if self._marker.exists():
            await self._run(["loginctl", "disable-linger", self._user])
            self._marker.unlink()

    async def start(self) -> None:
        await self._systemctl("start", UNIT_NAME)

    async def stop(self) -> None:
        await self._systemctl("stop", UNIT_NAME)

    async def is_active(self) -> bool:
        return (await self._systemctl("is-active", UNIT_NAME, check=False)).returncode == 0

    async def is_enabled(self) -> bool:
        return (await self._systemctl("is-enabled", UNIT_NAME, check=False)).returncode == 0

    async def status(self) -> dict[str, Any]:
        return {
            "installed": self.unit_path.exists(),
            "enabled": await self.is_enabled(),
            "active": await self.is_active(),
            "linger_by_orion": self._marker.exists(),
        }

    async def verify(self) -> tuple[bool, str]:
        result = await self._run(
            ["systemd-analyze", "--user", "verify", str(self.unit_path)], check=False
        )
        return result.returncode == 0, (result.stderr or result.stdout).strip()
