"""
O.R.I.O.N — Tool: notebook_edit
Edita células de um Jupyter Notebook (.ipynb): replace, insert ou delete.

ActionLevel: LEVEL_2 (mutação de projeto)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

_MODES = ("replace", "insert", "delete")
_TYPES = ("code", "markdown")


class NotebookEditTool(BaseTool):
    name = "notebook_edit"
    description = (
        "Edit a Jupyter notebook cell. edit_mode: 'replace' (default), 'insert' (new cell AFTER "
        "cell_index, or at the start when cell_index is omitted) or 'delete'. Indexes are 0-based."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the .ipynb file."},
            "cell_index": {"type": "integer", "minimum": 0},
            "new_source": {"type": "string", "description": "New cell content (not needed for delete)."},
            "cell_type": {"type": "string", "enum": list(_TYPES)},
            "edit_mode": {"type": "string", "enum": list(_MODES)},
        },
        "required": ["path"],
    }

    async def run(
        self,
        path: str,
        cell_index: int | None = None,
        new_source: str | None = None,
        cell_type: str | None = None,
        edit_mode: str = "replace",
        **_: Any,
    ) -> RuntimeResult:
        file = Path(path).expanduser()
        if file.suffix != ".ipynb":
            return RuntimeResult.fail("notebook_edit: only .ipynb files are supported.")
        if not file.is_file():
            return RuntimeResult.fail(f"notebook_edit: file not found: '{path}'")
        try:
            nb = json.loads(file.read_text(encoding="utf-8"))
            cells: list[dict[str, Any]] = nb["cells"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return RuntimeResult.fail(f"notebook_edit: '{path}' is not a valid notebook: {exc}")

        if edit_mode != "insert" and cell_index is None:
            return RuntimeResult.fail(f"notebook_edit: 'cell_index' is required for {edit_mode}.")
        if edit_mode != "delete" and new_source is None:
            return RuntimeResult.fail(f"notebook_edit: 'new_source' is required for {edit_mode}.")
        if edit_mode != "insert" and cell_index is not None and cell_index >= len(cells):
            return RuntimeResult.fail(
                f"notebook_edit: cell_index {cell_index} out of range (notebook has {len(cells)} cells)."
            )
        if edit_mode == "insert" and cell_index is not None and cell_index >= len(cells):
            return RuntimeResult.fail(
                f"notebook_edit: cell_index {cell_index} out of range (notebook has {len(cells)} cells)."
            )

        source_lines = (new_source or "").splitlines(keepends=True)
        if edit_mode == "delete":
            assert cell_index is not None
            del cells[cell_index]
            done = f"deleted cell {cell_index}"
        elif edit_mode == "insert":
            kind = cell_type or "code"
            cell: dict[str, Any] = {"cell_type": kind, "metadata": {}, "source": source_lines}
            if kind == "code":
                cell.update(execution_count=None, outputs=[])
            at = 0 if cell_index is None else cell_index + 1
            cells.insert(at, cell)
            done = f"inserted {kind} cell at {at}"
        else:
            assert cell_index is not None
            target = cells[cell_index]
            target["source"] = source_lines
            if cell_type and cell_type != target.get("cell_type"):
                target["cell_type"] = cell_type
                if cell_type == "code":
                    target.update(execution_count=None, outputs=[])
                else:
                    target.pop("outputs", None)
                    target.pop("execution_count", None)
            elif target.get("cell_type") == "code":
                target["outputs"], target["execution_count"] = [], None
            done = f"replaced cell {cell_index}"

        payload = (json.dumps(nb, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            fd, tmp = tempfile.mkstemp(dir=file.parent, prefix=".orion_nb_")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(payload)
                os.replace(tmp, file)
            except Exception:
                os.unlink(tmp)
                raise
        except OSError as exc:
            return RuntimeResult.fail(f"notebook_edit: cannot write '{path}': {exc}")
        return RuntimeResult.ok(f"notebook_edit: {done} in '{path}' ({len(cells)} cells).", cells=len(cells))
