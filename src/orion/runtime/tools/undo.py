"""
O.R.I.O.N — Tool: undo_last (v0.5.3 Sprint 2, ADR-047)
Restaura o snapshot mais recente do lixo do ORION (deleções e sobrescritas feitas pelo agente).

Faixa: Livre (desfazer só devolve arquivos; a versão atual de um caminho ocupado é preservada
como ``.orion-undo-<id>``). ActionLevel: LEVEL_2 (muda arquivos: negada no modo plano).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

#: ``async (snapshot_id | None) -> resumo | None`` (None = nada para desfazer).
Undoer = Callable[[str | None], Awaitable[str | None]]


class UndoLastTool(BaseTool):
    name = "undo_last"
    description = (
        "Restore files that an earlier command of this session deleted or overwrote (rm, mv/cp "
        "over a file, > redirection, sed -i, git reset --hard, git checkout -- ., git clean). "
        "Without snapshot_id restores the most recent snapshot. Current versions of occupied "
        "paths are kept aside as <name>.orion-undo-<id>."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "snapshot_id": {"type": "string", "description": "Snapshot id (from the turn line or /undo list)."}
        },
    }

    def __init__(self, undo: Undoer | None = None) -> None:
        self._undo = undo

    async def run(self, snapshot_id: str | None = None, **_: Any) -> RuntimeResult:
        if self._undo is None:
            return RuntimeResult.fail("undo_last: not available in this session.")
        summary = await self._undo(snapshot_id or None)
        if summary is None:
            return RuntimeResult.fail("undo_last: nothing to undo (no snapshot found).")
        return RuntimeResult.ok(summary)
