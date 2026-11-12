"""Fixtures do laboratório: HOME temporário, workspace de exemplo, sem rede e sem custo."""

from __future__ import annotations

import contextlib
import socket
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("pyte")

from tests.lab.pty_driver import LabTerminal  # noqa: E402
from tests.lab.scripted_provider import ScriptBook  # noqa: E402

SAMPLE = '''import sys


def greet(name):
    print("ola", name)


def main():
    greet(sys.argv[1] if len(sys.argv) > 1 else "mundo")


if __name__ == "__main__":
    main()
'''

class NetworkTrap:
    """Proxy local que só conta conexões e as fecha: rede nunca sai da máquina.

    Todo cliente HTTP que respeita ``HTTP(S)_PROXY`` (huggingface_hub, requests, httpx) cai aqui;
    ``connections > 0`` prova uma tentativa de rede.
    """

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.connections = 0
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.sock.getsockname()[1]}"

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.connections += 1
            conn.close()

    def env(self) -> dict[str, str]:
        url = self.url
        return {"HTTP_PROXY": url, "HTTPS_PROXY": url, "http_proxy": url, "https_proxy": url,
                "NO_PROXY": "", "no_proxy": ""}

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self.sock.close()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/lab/" in str(item.fspath):
            item.add_marker(pytest.mark.lab)
            # O filho do pty.fork só faz chdir + execve: o aviso de fork com threads não se aplica.
            item.add_marker(pytest.mark.filterwarnings("ignore:This process.*forkpty"))


@pytest.fixture()
def network_trap() -> Iterator[NetworkTrap]:
    trap = NetworkTrap()
    yield trap
    trap.close()


@pytest.fixture()
def open_lab(tmp_path: Path, network_trap: NetworkTrap) -> Iterator[Callable[..., LabTerminal]]:
    """Fábrica: ``open_lab({"palavra": [passos]}, cols=110, rows=36, cpr=True)`` já com boot."""
    opened: list[LabTerminal] = []

    def factory(
        scripts: dict[str, list[dict[str, Any]]] | None = None,
        *,
        cols: int = 110,
        rows: int = 36,
        cpr: bool = True,
        env: dict[str, str] | None = None,
        chunk: int = 6,
        delay: float = 0.03,
    ) -> LabTerminal:
        home = tmp_path / "home"
        workspace = tmp_path / "ws"
        (home / ".orion").mkdir(parents=True, exist_ok=True)
        workspace.mkdir(exist_ok=True)
        (workspace / "sample.py").write_text(SAMPLE, encoding="utf-8")
        book = tmp_path / "scripts.json"
        ScriptBook.dump(book, scripts or {}, chunk=chunk, delay=delay)
        terminal = LabTerminal(
            workspace=workspace,
            home=home,
            scripts=book,
            cols=cols,
            rows=rows,
            cpr=cpr,
            env={
                **network_trap.env(),
                "FASTEMBED_CACHE_PATH": str(tmp_path / "fastembed"),
                "ORION_RECALL": "1",  # como em produção (o conftest raiz desliga o recall)
                **(env or {}),
            },
        )
        opened.append(terminal)
        terminal.start()
        terminal.boot()
        return terminal

    yield factory
    for terminal in opened:
        terminal.close()
