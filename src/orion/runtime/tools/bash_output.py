"""
O.R.I.O.N — Tool: bash_output
Lê a saída NOVA de um shell em background (cada chamada devolve só o que ainda não foi visto).

ActionLevel: LEVEL_1 (leitura passiva)
"""

from __future__ import annotations

import re
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.runtime.tools.shells import ShellManager


class BashOutputTool(BaseTool):
    name = "bash_output"
    description = (
        "Read new output from a background shell started with run_command(run_in_background=true). "
        "Returns only output not yet seen, plus the status (running or exit code). "
        "Optional 'filter' keeps only lines matching a regex."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "shell_id": {"type": "string", "description": "Id returned by run_command (e.g. shell_1)."},
            "filter": {"type": "string", "description": "Regex; only matching lines are returned."},
        },
        "required": ["shell_id"],
    }
    read_only = True

    def __init__(self, shells: ShellManager) -> None:
        self._shells = shells

    async def run(self, shell_id: str, filter: str | None = None, **_: Any) -> RuntimeResult:
        shell = self._shells.get(shell_id)
        if shell is None:
            known = ", ".join(s.shell_id for s in self._shells.list()) or "none"
            return RuntimeResult.fail(f"bash_output: unknown shell '{shell_id}'. Known: {known}.")
        if filter:
            try:
                re.compile(filter)
            except re.error as exc:
                return RuntimeResult.fail(f"bash_output: invalid filter regex: {exc}")
        text, truncated = self._shells.read_new(shell_id, filter)
        status = "running" if shell.running else f"exited ({shell.exit_code})"
        header = f"[{shell_id}: {status}]"
        if truncated:
            header += " [output truncated; call again for the rest]"
        return RuntimeResult.ok(
            f"{header}\n{text}" if text else f"{header}\n(no new output)",
            running=shell.running,
            exit_code=shell.exit_code,
            truncated=truncated,
        )
