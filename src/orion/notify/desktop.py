"""Notificação nativa do desktop via ``notify-send`` (ADR-032).

Canal garantido quando não há terminal nem áudio. Nunca usa shell: ``create_subprocess_exec``
através de um runner injetável (testes não tocam D-Bus).
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import shutil
from pathlib import Path
from typing import Protocol

from orion.notify.models import Delivery, OutgoingMessage

logger = logging.getLogger(__name__)

_APP_NAME = "ORION"
_MAX_TITLE = 100
_MAX_BODY = 500
_SHOW_TIMEOUT_S = 10.0


class CommandRunner(Protocol):
    """Executa um argv e devolve ``(código de saída, stdout)``."""

    async def run(self, argv: list[str], timeout_s: float | None) -> tuple[int, str]: ...


class SubprocessRunner:
    """Runner real: ``asyncio.create_subprocess_exec``, mata o processo no timeout."""

    async def run(self, argv: list[str], timeout_s: float | None) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except (TimeoutError, asyncio.CancelledError):
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        return (proc.returncode if proc.returncode is not None else -1), out.decode(
            "utf-8", "replace"
        )


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


_URGENCY = {"critical": "critical", "high": "normal", "normal": "normal", "low": "low"}


class DesktopNotifier:
    """Notificações nativas com botões de ação."""

    def __init__(
        self,
        runner: CommandRunner | None = None,
        *,
        app_name: str = _APP_NAME,
        available: bool | None = None,
    ) -> None:
        self._runner: CommandRunner = runner or SubprocessRunner()
        self._app_name = app_name
        self._forced_available = available

    def available(self) -> bool:
        """``notify-send`` instalado e barramento de sessão presente."""
        if self._forced_available is not None:
            return self._forced_available
        if shutil.which("notify-send") is None:
            return False
        if os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
            return True
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        if not runtime:
            return False
        return (Path(runtime) / "bus").exists()

    def build_argv(
        self, msg: OutgoingMessage, delivery: Delivery, *, wait: bool, expire_ms: int | None = None
    ) -> list[str]:
        argv = [
            "notify-send",
            f"--app-name={self._app_name}",
            f"--urgency={_URGENCY.get(msg.priority, 'normal')}",
        ]
        if expire_ms is not None:
            argv.append(f"--expire-time={expire_ms}")
        if delivery.silent:
            argv.append("--hint=boolean:suppress-sound:true")
        for action in msg.actions:
            argv.append(f"--action={action.id}={action.label}")
        if wait:
            argv.append("--wait")
        argv += [
            "--",
            _truncate(msg.title, _MAX_TITLE),
            html.escape(_truncate(msg.body, _MAX_BODY), quote=False),
        ]
        return argv

    async def show(self, msg: OutgoingMessage, delivery: Delivery) -> None:
        """Dispara e esquece (sem ``--wait``); erros são apenas registrados."""
        try:
            await self._runner.run(self.build_argv(msg, delivery, wait=False), _SHOW_TIMEOUT_S)
        except (OSError, TimeoutError) as exc:
            logger.warning("notify-send falhou: %s", type(exc).__name__)

    async def ask(self, msg: OutgoingMessage, delivery: Delivery, timeout_s: float) -> str | None:
        """Mostra com botões e espera a escolha; None se dispensada, expirada ou com erro."""
        argv = self.build_argv(msg, delivery, wait=True, expire_ms=int(timeout_s * 1000))
        try:
            code, out = await self._runner.run(argv, timeout_s)
        except (OSError, TimeoutError) as exc:
            logger.warning("notify-send --wait falhou: %s", type(exc).__name__)
            return None
        choice = out.strip()
        if code != 0 or not choice:
            return None
        valid = {a.id for a in msg.actions}
        return choice if choice in valid else None
