"""Jobs supervisionados do daemon (Sprint 7B).

Um job é um comando de shell que um agendamento dispara. Ele SÓ chega aqui depois de aprovado
pelo PEP da sessão de disparo (não interativa, autonomia limitada pela do agendamento); este
módulo é o corpo que executa com limites:

* **Headroom Guard:** recusa iniciar sob pressão do sistema ou sem memória livre suficiente;
* teto de concorrência, tempo máximo, ``nice`` e teto de bytes de saída;
* log em ``~/.orion/jobs/<id>.log`` (0600); cada linha de stdout vira evento ``job.output``
  (com teto de eventos por job para não inundar os clientes).

Nenhum modelo é chamado aqui (ADR-022).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

JobStatus = Literal["ok", "failed", "timeout", "refused"]
MAX_OUTPUT_BYTES = 1_000_000
MAX_LINE_EVENTS = 200
_TAIL_CHARS = 2000


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    exit_code: int | None = None
    log_path: str = ""
    tail: str = ""
    reason: str = ""
    duration_s: float = 0.0


def _lower_priority() -> None:  # pragma: no cover - roda no processo filho
    with contextlib.suppress(OSError):
        os.nice(10)


class JobSupervisor:
    """Executa comandos aprovados com limites, logs e eventos."""

    def __init__(
        self,
        home: Path,
        *,
        publish: Callable[[dict[str, Any]], None] | None = None,
        headroom: Callable[[], str | None] | None = None,
        max_concurrent: int = 2,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.log_dir = home / "jobs"
        self._publish = publish or (lambda _e: None)
        self._headroom = headroom or (lambda: None)
        self._slots = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        self._running: dict[str, asyncio.subprocess.Process] = {}
        self._clock = clock

    @property
    def running(self) -> list[str]:
        return sorted(self._running)

    async def run(
        self,
        job_id: str,
        command: str,
        *,
        cwd: Path,
        timeout_s: float = 900.0,
        max_output_bytes: int = MAX_OUTPUT_BYTES,
    ) -> JobResult:
        refusal = self._headroom()
        if refusal:
            return JobResult(job_id=job_id, status="refused", reason=refusal)
        if len(self._running) >= self._max_concurrent:
            return JobResult(job_id=job_id, status="refused", reason="teto de jobs simultâneos atingido")
        async with self._slots:
            return await self._run(job_id, command, cwd, timeout_s, max_output_bytes)

    async def _run(
        self, job_id: str, command: str, cwd: Path, timeout_s: float, max_output_bytes: int
    ) -> JobResult:
        self.log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        log_path = self.log_dir / f"{job_id}.log"
        fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        started = self._clock()
        tail = ""
        self._emit(job_id, "job.started", {"command": command[:200]})
        with os.fdopen(fd, "wb") as log:
            proc = await asyncio.create_subprocess_exec(
                "/bin/sh",
                "-c",
                command,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                stdin=asyncio.subprocess.DEVNULL,
                preexec_fn=_lower_priority,
                start_new_session=True,
            )
            self._running[job_id] = proc
            written = 0
            events = 0
            truncated = False

            async def pump() -> None:
                nonlocal written, events, truncated, tail
                assert proc.stdout is not None
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        return
                    if written < max_output_bytes:
                        chunk = line[: max_output_bytes - written]
                        log.write(chunk)
                        written += len(chunk)
                    else:
                        truncated = True
                    text = line.decode(errors="replace").rstrip("\n")
                    tail = (tail + text + "\n")[-_TAIL_CHARS:]
                    if events < MAX_LINE_EVENTS:
                        events += 1
                        self._emit(job_id, "job.output", {"line": text[:500]})

            try:
                await asyncio.wait_for(pump(), timeout_s)
                code = await proc.wait()
            except TimeoutError:
                self._kill(proc)
                await proc.wait()
                return self._finish(job_id, "timeout", None, log_path, tail, started, f"passou de {timeout_s:g}s")
            except asyncio.CancelledError:
                self._kill(proc)
                raise
            finally:
                self._running.pop(job_id, None)
            if truncated:
                log.write(b"\n[saida truncada]\n")
        status: JobStatus = "ok" if code == 0 else "failed"
        return self._finish(job_id, status, code, log_path, tail, started, "" if code == 0 else f"saiu com {code}")

    def _finish(
        self,
        job_id: str,
        status: JobStatus,
        code: int | None,
        log_path: Path,
        tail: str,
        started: float,
        reason: str,
    ) -> JobResult:
        result = JobResult(
            job_id=job_id,
            status=status,
            exit_code=code,
            log_path=str(log_path),
            tail=tail,
            reason=reason,
            duration_s=self._clock() - started,
        )
        self._emit(job_id, "job.finished", {"status": status, "exit_code": code, "reason": reason})
        return result

    @staticmethod
    def _kill(proc: asyncio.subprocess.Process) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, 9)

    def _emit(self, job_id: str, kind: str, payload: dict[str, Any]) -> None:
        self._publish({"kind": kind, "job_id": job_id, **payload})
