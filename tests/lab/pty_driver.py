"""Terminal de laboratório: ORION num pty, emulado pelo pyte, com amostragem da tela.

Responde ao pedido de posição do cursor (CPR, ``ESC[6n``) como um terminal real, salvo quando
``cpr=False`` simula um emulador sem suporte (achados V-05/V-06).
"""

from __future__ import annotations

import codecs
import contextlib
import fcntl
import hashlib
import os
import pty
import re
import select
import signal
import struct
import sys
import termios
import time
from dataclasses import dataclass, field
from pathlib import Path

import pyte

LAUNCHER = Path(__file__).with_name("launcher.py")
KEYS = {
    "enter": "\r", "esc": "\x1b", "up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C",
    "left": "\x1b[D", "tab": "\t", "shift-tab": "\x1b[Z", "ctrl-c": "\x03", "ctrl-d": "\x04",
    "backspace": "\x7f", "alt-e": "\x1be", "alt-E": "\x1bE", "alt-r": "\x1br",
}
_CPR_REQUEST = "\x1b[6n"


@dataclass
class Sample:
    t: float
    digest: str


@dataclass
class LabTerminal:
    """Um ORION vivo num pty. Use como context manager."""

    workspace: Path
    home: Path
    scripts: Path
    cols: int = 110
    rows: int = 36
    cpr: bool = True
    env: dict[str, str] = field(default_factory=dict)
    pid: int = 0
    fd: int = -1
    samples: list[Sample] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.screen = pyte.HistoryScreen(self.cols, self.rows, history=5000)
        self.stream = pyte.Stream(self.screen)
        self.t0 = time.monotonic()
        self._tail = ""
        self.raw = bytearray()
        # Incremental: um caractere de 3 bytes (bordas ╭─╮) pode chegar partido entre leituras.
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    # ── Ciclo ──
    def start(self) -> LabTerminal:
        env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_RUNTIME_DIR": str(self.home / "run"),
            "COLORTERM": "truecolor",
            "TERM": "xterm-256color",
            **self.env,
        }
        (self.home / "run").mkdir(parents=True, exist_ok=True)
        argv = [
            sys.executable, str(LAUNCHER), "--workspace", str(self.workspace),
            "--home", str(self.home / ".orion"), "--scripts", str(self.scripts),
        ]
        self.pid, self.fd = pty.fork()
        if self.pid == 0:  # filho
            os.chdir(self.workspace)
            os.execve(sys.executable, argv, env)
        self._set_size(self.cols, self.rows)
        return self

    def close(self) -> None:
        if self.pid:
            with contextlib.suppress(ProcessLookupError):
                os.kill(self.pid, signal.SIGKILL)
            with contextlib.suppress(ChildProcessError):
                os.waitpid(self.pid, 0)
            self.pid = 0
        if self.fd >= 0:
            with contextlib.suppress(OSError):
                os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> LabTerminal:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def alive(self) -> bool:
        if not self.pid:
            return False
        done, _ = os.waitpid(self.pid, os.WNOHANG)
        return done == 0

    # ── Entrada e saída ──
    def _set_size(self, cols: int, rows: int) -> None:
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def pump(self, seconds: float) -> None:
        """Lê o pty por *seconds*, alimentando o emulador e respondendo CPR."""
        end = time.monotonic() + seconds
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            ready, _, _ = select.select([self.fd], [], [], min(remaining, 0.02))
            if not ready:
                continue
            try:
                data = os.read(self.fd, 65536)
            except OSError:
                return
            if not data:
                return
            self.raw += data
            text = self._decoder.decode(data)
            self.stream.feed(text)
            window = self._tail + text
            if self.cpr and _CPR_REQUEST in window:
                y, x = self.screen.cursor.y + 1, self.screen.cursor.x + 1
                os.write(self.fd, f"\x1b[{y};{x}R".encode())
            self._tail = window[-4:]
            self.samples.append(Sample(self.now(), self._digest()))

    def now(self) -> float:
        return time.monotonic() - self.t0

    def _digest(self) -> str:
        return hashlib.md5(self.screen_text().encode()).hexdigest()[:10]

    def send(self, text: str) -> None:
        os.write(self.fd, text.encode())

    def key(self, name: str) -> None:
        self.send(KEYS[name])

    def submit(self, text: str) -> None:
        self.send(text + "\r")

    def resize(self, cols: int, rows: int) -> None:
        self.cols, self.rows = cols, rows
        self.screen.resize(rows, cols)
        self._set_size(cols, rows)
        os.kill(self.pid, signal.SIGWINCH)

    # ── Leitura ──
    def screen_text(self) -> str:
        return "\n".join(line.rstrip() for line in self.screen.display)

    def history_text(self) -> str:
        """Scrollback inteiro + tela visível (o que o Senhor veria rolando para cima)."""
        rows = [
            "".join(line[x].data for x in range(self.screen.columns)).rstrip()
            for line in self.screen.history.top
        ]
        return "\n".join([*rows, self.screen_text()])

    def wait_for(self, pattern: str, timeout: float = 30.0, *, history: bool = False) -> bool:
        """Espera *pattern* (regex) aparecer na tela ou no histórico."""
        regex = re.compile(pattern)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.pump(0.05)
            if regex.search(self.history_text() if history else self.screen_text()):
                return True
        return False

    def wait_ready(self, timeout: float = 60.0) -> bool:
        """Turno concluído: estado Ready na linha de status e prompt vazio."""
        return self.wait_for(r"Ready ●", timeout)

    def boot(self, timeout: float = 90.0) -> None:
        if not self.wait_for("❯", timeout):
            raise AssertionError("ORION não subiu no pty:\n" + self.screen_text())
        self.pump(0.8)

    def cpu_seconds(self) -> float:
        """CPU (usuário + sistema) do processo do ORION, via /proc."""
        stat = Path(f"/proc/{self.pid}/stat").read_text().rsplit(")", 1)[1].split()
        return (int(stat[11]) + int(stat[12])) / os.sysconf("SC_CLK_TCK")
