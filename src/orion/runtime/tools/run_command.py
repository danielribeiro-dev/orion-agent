"""
O.R.I.O.N — Primitive Tool: run_command
Async shell execution via asyncio.subprocess with timeout and child-kill.

ActionLevel: LEVEL_3 (Critical)

Parameters:
    command      (str)           : Shell command string to execute.
    timeout      (float)         : Max seconds before SIGKILL. Default: 30.
    cwd          (str | None)    : Working directory. Default: None (inherit).
    env          (dict | None)   : Extra environment variables to merge.

Output:
    Combined stdout + stderr from the process.
    Metadata: exit_code (int), timed_out (bool).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import os
from typing import Any

from orion.governance.askpass import AskpassBroker, AskpassReport, rewrite_sudo, uses_sudo
from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.runtime.tools.shells import ShellManager

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MiB cap per stream


class RunCommandTool(BaseTool):
    """Execute an arbitrary shell command asynchronously."""

    name = "run_command"
    description = (
        "Run a shell command and return stdout/stderr and the exit code. "
        "Requires user approval. Prefer dedicated tools for reading and editing files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute."},
            "timeout": {"type": "number", "exclusiveMinimum": 0, "description": "Seconds before the process is killed."},
            "cwd": {"type": "string", "description": "Working directory."},
            "env": {"type": "object", "additionalProperties": {"type": "string"}},
            "run_in_background": {
                "type": "boolean",
                "description": "Start and return a shell_id immediately; read it with bash_output.",
            },
        },
        "required": ["command"],
    }

    def __init__(self, shells: ShellManager | None = None, askpass: AskpassBroker | None = None) -> None:
        self._shells = shells
        self._askpass = askpass

    def set_askpass(self, broker: AskpassBroker | None) -> None:
        """Liga o askpass do ORION (ADR-048): ``sudo`` vira ``sudo -A`` e pede a senha à sessão."""
        self._askpass = broker

    async def run(
        self,
        command: str,
        timeout: float = _DEFAULT_TIMEOUT,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        run_in_background: bool = False,
        **_: Any,
    ) -> RuntimeResult:
        """Run *command* in a subprocess with a hard timeout.

        On timeout, the process *and all its children* are killed via SIGKILL
        before raising the result so no zombie processes linger.
        """
        if not command or not command.strip():
            return RuntimeResult.fail("run_command: 'command' parameter is required and must be non-empty.")

        if run_in_background:
            if self._shells is None:
                return RuntimeResult.fail("run_command: background shells are not available.")
            try:
                shell = self._shells.start(command, cwd=cwd, env=env)
            except OSError as exc:
                return RuntimeResult.fail(f"run_command: failed to start background shell: {exc}")
            return RuntimeResult.ok(
                f"Started in background as '{shell.shell_id}'. "
                "Use bash_output to read its output and kill_shell to stop it.",
                shell_id=shell.shell_id,
                background=True,
            )

        if self._askpass is not None and uses_sudo(command):
            async with self._askpass.session(command) as (askpass_env, report):
                result = await self._run_foreground(
                    rewrite_sudo(command), timeout, cwd, {**(env or {}), **askpass_env}
                )
            return _with_askpass_report(result, report)
        return await self._run_foreground(command, timeout, cwd, env)

    async def _run_foreground(
        self, command: str, timeout: float, cwd: str | None, env: dict[str, str] | None
    ) -> RuntimeResult:
        merged_env: dict[str, str] | None = None
        if env:
            merged_env = {**os.environ, **env}

        timed_out = False
        proc: asyncio.subprocess.Process | None = None

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd,
                env=merged_env,
                # Create a new process group so we can SIGKILL all children
                start_new_session=True,
            )

            try:
                raw, _stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                timed_out = True
                _kill_process_group(proc)
                await proc.wait()
                raw = b""

        except Exception as exc:
            return RuntimeResult.fail(
                f"run_command: failed to start subprocess: {exc}",
                exit_code=-1,
                timed_out=False,
            )

        output_str = _decode_output(raw[:_MAX_OUTPUT_BYTES])
        exit_code = proc.returncode if proc else -1

        if timed_out:
            return RuntimeResult.fail(
                f"run_command: command timed out after {timeout}s.\n{output_str}",
                exit_code=exit_code,
                timed_out=True,
            )

        if exit_code != 0:
            return RuntimeResult(
                success=False,
                output=output_str,
                error=f"run_command: process exited with code {exit_code}.",
                metadata={"exit_code": exit_code, "timed_out": False},
            )

        return RuntimeResult.ok(output_str, exit_code=exit_code, timed_out=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with_askpass_report(result: RuntimeResult, report: AskpassReport) -> RuntimeResult:
    """Anexa o que o askpass fez (sem segredo) e explica falhas típicas ao modelo."""
    metadata = {**result.metadata, "askpass": report.summary()}
    notes: list[str] = []
    if "cancelled" in report.sources:
        notes.append("o Senhor cancelou o pedido de senha do sudo")
    if report.keyring_rejected:
        notes.append(
            "a senha guardada no chaveiro não confere mais; o Senhor pode atualizá-la com "
            "`orion setup sudo`"
        )
    error = result.error
    if notes and not result.success:
        error = f"{error or 'run_command failed.'} ({'; '.join(notes)})"
    return dataclasses.replace(result, metadata=metadata, error=error)


def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    """Send SIGKILL to the process group of *proc*."""
    import signal

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        # Process may have already exited
        with contextlib.suppress(Exception):
            proc.kill()


def _decode_output(raw: bytes) -> str:
    """Decode subprocess output bytes to str, replacing undecodable bytes."""
    return raw.decode("utf-8", errors="replace")
