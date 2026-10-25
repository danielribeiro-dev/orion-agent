"""
O.R.I.O.N — Primitive Tool: edit_file
Surgical exact-block replacement (target → replacement).

ActionLevel: LEVEL_2 (Project mutation)

Inspired by the Claude Code / Antigravity edit_file design principle:
  "Exact string target replacement — never full rewrites."

Parameters:
    path        (str) : Target file path.
    target      (str) : Exact string that must appear UNIQUELY in the file.
    replacement (str) : String to substitute in place of *target*.
                        Pass "" to delete *target*.

Safety rules:
  - The operation is rejected if *target* does not appear in the file.
  - The operation is rejected if *target* appears MORE THAN ONCE (ambiguous).
  - The write is atomic (tempfile + os.replace).

Output:
    Confirmation message.
    Metadata: occurrences_found (int), bytes_before (int), bytes_after (int).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool


class EditFileTool(BaseTool):
    """Surgical exact-block replacement in a file."""

    name = "edit_file"

    async def run(
        self,
        path: str,
        target: str,
        replacement: str = "",
        **_: Any,
    ) -> RuntimeResult:
        """Replace the unique occurrence of *target* with *replacement* in *path*.

        Args:
            path        : Path to the file to edit.
            target      : Exact substring to locate (must be unique).
            replacement : String to put in place of *target*.
        """
        if not path:
            return RuntimeResult.fail("edit_file: 'path' parameter is required.")
        if not target:
            return RuntimeResult.fail("edit_file: 'target' parameter is required and must be non-empty.")

        file_path = Path(path)

        if not file_path.exists():
            return RuntimeResult.fail(f"edit_file: file not found: '{path}'")
        if not file_path.is_file():
            return RuntimeResult.fail(f"edit_file: path is not a regular file: '{path}'")

        try:
            original = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return RuntimeResult.fail(f"edit_file: cannot read '{path}': {exc}")

        occurrences = original.count(target)

        if occurrences == 0:
            return RuntimeResult.fail(
                f"edit_file: target string not found in '{path}'. "
                "The file was not modified.",
                occurrences_found=0,
            )

        if occurrences > 1:
            return RuntimeResult.fail(
                f"edit_file: target string appears {occurrences} times in '{path}'. "
                "The target must be unique to ensure a safe surgical edit. "
                "The file was not modified.",
                occurrences_found=occurrences,
            )

        # Exactly one occurrence — safe to replace
        new_content = original.replace(target, replacement, 1)
        encoded = new_content.encode("utf-8")
        bytes_before = len(original.encode("utf-8"))
        bytes_after = len(encoded)

        try:
            dir_path = file_path.parent
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".orion_edit_")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(encoded)
                os.replace(tmp_path, file_path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as exc:
            return RuntimeResult.fail(f"edit_file: cannot write to '{path}': {exc}")

        action = "deleted" if replacement == "" else "replaced"
        return RuntimeResult.ok(
            f"edit_file: {action} target in '{path}' ({bytes_before} → {bytes_after} bytes).",
            occurrences_found=1,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
        )
