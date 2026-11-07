"""
O.R.I.O.N — Tool: kill_shell
Encerra um shell em background iniciado pelo próprio ORION (nunca processos arbitrários).

ActionLevel: LEVEL_2 (afeta processos da sessão)
"""

from __future__ import annotations

from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.runtime.tools.shells import ShellManager


class KillShellTool(BaseTool):
    name = "kill_shell"
    description = "Terminate a background shell started with run_command(run_in_background=true)."
    input_schema = {
        "type": "object",
        "properties": {"shell_id": {"type": "string", "description": "Id returned by run_command."}},
        "required": ["shell_id"],
    }

    def __init__(self, shells: ShellManager) -> None:
        self._shells = shells

    async def run(self, shell_id: str, **_: Any) -> RuntimeResult:
        if self._shells.get(shell_id) is None:
            return RuntimeResult.fail(f"kill_shell: unknown shell '{shell_id}'.")
        killed = self._shells.kill(shell_id)
        if not killed:
            return RuntimeResult.ok(f"kill_shell: '{shell_id}' had already exited.", killed=False)
        return RuntimeResult.ok(f"kill_shell: '{shell_id}' terminated.", killed=True)
