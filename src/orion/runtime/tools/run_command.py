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
import logging
import os
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0
_MAX_OUTPUT_BYTES = 1024 * 1024  # 1 MiB cap per stream


class RunCommandTool(BaseTool):
    """Execute an arbitrary shell command asynchronously."""

    name = "run_command"

    async def run(
        self,
        command: str,
        timeout: float = _DEFAULT_TIMEOUT,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        **_: Any,
    ) -> RuntimeResult:
        """Run *command* in a subprocess with a hard timeout.

        On timeout, the process *and all its children* are killed via SIGKILL
        before raising the result so no zombie processes linger.
        """
        if not command or not command.strip():
            return RuntimeResult.fail("run_command: 'command' parameter is required and must be non-empty.")

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
                raw, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
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


def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    """Send SIGKILL to the process group of *proc*."""
    import signal

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        # Process may have already exited
        try:
            proc.kill()
        except Exception:
            pass


def _decode_output(raw: bytes) -> str:
    """Decode subprocess output bytes to str, replacing undecodable bytes."""
    return raw.decode("utf-8", errors="replace")
