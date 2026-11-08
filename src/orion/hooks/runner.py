"""Hooks: scripts do Senhor executados em pontos fixos do ciclo do agente.

Regras (ADR-024):

* Exit code **2** bloqueia; o stderr volta ao modelo como motivo.
* Qualquer outro código (inclusive falha ou timeout) **não bloqueia**: segue
  para o PEP, que continua sendo quem decide. Um hook nunca aprova uma ação
  nem altera seus parâmetros.
* Cada execução é auditada (comando, evento, código de saída, duração).
* A saída de um hook é dado não confiável: delimitadores forjados são
  neutralizados e o texto é truncado antes de chegar ao modelo.
"""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import json
import logging
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orion.governance.audit import AuditLogger
from orion.settings.models import HOOK_EVENTS, HookSpec

logger = logging.getLogger(__name__)

BLOCK_EXIT_CODE = 2
MAX_MESSAGE_CHARS = 2_000
_FORGED = "<<<ORION_"


@dataclass(frozen=True)
class HookOutcome:
    """Resultado agregado das execuções de um evento."""

    blocked: bool = False
    message: str | None = None
    ran: int = 0
    warnings: list[str] = field(default_factory=list)


def sanitize_hook_text(text: str) -> str:
    """Trata a saída de um hook como dado não confiável."""
    cleaned = text.strip().replace(_FORGED, "<<_ORION_")
    if len(cleaned) > MAX_MESSAGE_CHARS:
        cleaned = cleaned[:MAX_MESSAGE_CHARS] + " […]"
    return cleaned


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        proc.kill()


class HookRunner:
    """Executa os hooks configurados para um evento."""

    def __init__(
        self,
        specs: Callable[[], dict[str, list[HookSpec]]],
        *,
        cwd: Path,
        audit: AuditLogger | None = None,
        session_id: Callable[[], str] | None = None,
    ) -> None:
        self._specs = specs
        self._cwd = cwd
        self._audit = audit
        self._session_id = session_id

    def has_hooks(self, event: str) -> bool:
        return bool(self._specs().get(event))

    async def run(
        self, event: str, payload: dict[str, Any] | None = None, *, tool: str | None = None
    ) -> HookOutcome:
        """Roda, em ordem, os hooks de *event*. O primeiro que bloqueia encerra a cadeia."""
        if event not in HOOK_EVENTS:
            raise ValueError(f"evento de hook desconhecido: {event}")
        ran = 0
        warnings: list[str] = []
        for spec in self._specs().get(event, []):
            if not self._matches(spec, tool):
                continue
            ran += 1
            code, stderr, note = await self._execute(event, spec, payload or {}, tool)
            if note:
                warnings.append(note)
            if code == BLOCK_EXIT_CODE:
                message = sanitize_hook_text(stderr) or f"blocked by {event} hook"
                return HookOutcome(blocked=True, message=message, ran=ran, warnings=warnings)
        return HookOutcome(ran=ran, warnings=warnings)

    @staticmethod
    def _matches(spec: HookSpec, tool: str | None) -> bool:
        if not spec.matcher or spec.matcher == "*" or tool is None:
            return True
        return any(fnmatch.fnmatchcase(tool, part) for part in spec.matcher.split("|"))

    async def _execute(
        self, event: str, spec: HookSpec, payload: dict[str, Any], tool: str | None
    ) -> tuple[int | None, str, str]:
        body = json.dumps(
            {"event": event, "tool": tool, "session_id": self._sid(), **payload},
            ensure_ascii=False,
            default=str,
        )
        env = {
            **os.environ,
            "ORION_HOOK_EVENT": event,
            "ORION_PROJECT_DIR": str(self._cwd),
            "ORION_SESSION_ID": self._sid(),
        }
        started = time.monotonic()
        code: int | None = None
        stderr = ""
        note = ""
        try:
            proc = await asyncio.create_subprocess_exec(
                "/bin/sh",
                "-c",
                spec.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            note = f"hook {event} não iniciou: {exc}"
            self._record(event, spec, None, started, note)
            return None, "", note
        try:
            _, err = await asyncio.wait_for(
                proc.communicate(body.encode("utf-8")), timeout=spec.timeout
            )
            code = proc.returncode
            stderr = err.decode("utf-8", errors="replace")
            if code not in (0, BLOCK_EXIT_CODE):
                note = f"hook {event} saiu com código {code}"
        except TimeoutError:
            _kill_group(proc)
            with contextlib.suppress(Exception):
                await proc.wait()
            note = f"hook {event} excedeu {spec.timeout:g}s e foi encerrado"
        except asyncio.CancelledError:
            _kill_group(proc)
            raise
        self._record(event, spec, code, started, note)
        return code, stderr, note

    def _sid(self) -> str:
        return self._session_id() if self._session_id else ""

    def _record(
        self, event: str, spec: HookSpec, code: int | None, started: float, note: str
    ) -> None:
        if self._audit is None:
            return
        self._audit.log_event(
            kind="hook",
            detail={
                "hook_event": event,
                "command": spec.command,
                "exit_code": code,
                "duration_s": round(time.monotonic() - started, 3),
                "note": note,
            },
        )
