"""
O.R.I.O.N — Background shells
Processos de longa duração (servidores, watchers, suítes lentas) disparados por
``run_command(run_in_background=true)`` e monitorados por ``bash_output``/``kill_shell``.

O CLI roda cada turno em um ``asyncio.run`` próprio, então o processo é um
``subprocess.Popen`` comum e a saída vai para um arquivo: nada depende de um loop vivo.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

MAX_READ_BYTES = 64 * 1024


@dataclass
class BackgroundShell:
    shell_id: str
    command: str
    proc: subprocess.Popen[bytes]
    log_path: Path
    started_at: float = field(default_factory=time.time)
    read_offset: int = 0

    @property
    def running(self) -> bool:
        return self.proc.poll() is None

    @property
    def exit_code(self) -> int | None:
        return self.proc.poll()


class ShellManager:
    """Registro dos shells em background da sessão; mata tudo ao sair."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir or Path(tempfile.gettempdir()) / "orion-shells"
        self._shells: dict[str, BackgroundShell] = {}
        self._counter = 0
        atexit.register(self.kill_all)

    def start(self, command: str, cwd: str | None = None, env: dict[str, str] | None = None) -> BackgroundShell:
        self._base.mkdir(parents=True, exist_ok=True)
        self._counter += 1
        shell_id = f"shell_{self._counter}"
        log_path = self._base / f"{os.getpid()}-{shell_id}.log"
        with open(log_path, "wb") as log:
            proc = subprocess.Popen(  # noqa: S602 - comando já passou pelo PEP
                command,
                shell=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=cwd,
                env={**os.environ, **env} if env else None,
                start_new_session=True,
            )
        shell = BackgroundShell(shell_id, command, proc, log_path)
        self._shells[shell_id] = shell
        return shell

    def get(self, shell_id: str) -> BackgroundShell | None:
        return self._shells.get(shell_id)

    def list(self) -> list[BackgroundShell]:
        return list(self._shells.values())

    def read_new(self, shell_id: str, pattern: str | None = None) -> tuple[str, bool]:
        """Saída ainda não lida e se foi truncada; ``pattern`` filtra linhas por regex."""
        shell = self._shells[shell_id]
        with open(shell.log_path, "rb") as fh:
            fh.seek(shell.read_offset)
            chunk = fh.read(MAX_READ_BYTES + 1)
        truncated = len(chunk) > MAX_READ_BYTES
        chunk = chunk[:MAX_READ_BYTES]
        shell.read_offset += len(chunk)
        text = chunk.decode("utf-8", errors="replace")
        if pattern:
            rx = re.compile(pattern)
            text = "\n".join(line for line in text.splitlines() if rx.search(line))
        return text, truncated

    def kill(self, shell_id: str) -> bool:
        """Encerra o grupo de processos (SIGTERM, depois SIGKILL); False se já havia terminado."""
        shell = self._shells[shell_id]
        if not shell.running:
            return False
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
                os.killpg(os.getpgid(shell.proc.pid), sig)
            try:
                shell.proc.wait(timeout=2)
                break
            except subprocess.TimeoutExpired:
                continue
        return True

    def kill_all(self) -> None:
        for shell_id in list(self._shells):
            with contextlib.suppress(Exception):
                self.kill(shell_id)
