"""
O.R.I.O.N — Primitive Tool: write_file
Atomic file creation / overwrite via tempfile + os.replace.

ActionLevel: LEVEL_2 (Project mutation)

Parameters:
    path      (str)  : Target file path (will be created if absent).
    content   (str)  : Full UTF-8 content to write.
    overwrite (bool) : If False and file exists, the write is rejected. Default: False.
    append    (bool) : Append to file instead of replacing. Mutually exclusive
                       with overwrite=True. Default: False.

Output:
    Confirmation message with byte count.
    Metadata: bytes_written (int), created (bool).
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool


class WriteFileTool(BaseTool):
    """Write content to a file atomically (tempfile + os.replace)."""

    name = "write_file"
    description = (
        "Create a file, or replace/append to it, with the given UTF-8 content. "
        "Existing files require overwrite=true. Prefer edit_file for small changes."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target file path."},
            "content": {"type": "string", "description": "Full content to write."},
            "overwrite": {"type": "boolean", "description": "Allow replacing an existing file."},
            "append": {"type": "boolean", "description": "Append instead of replacing."},
        },
        "required": ["path", "content"],
    }

    async def run(
        self,
        path: str,
        content: str,
        overwrite: bool = False,
        append: bool = False,
        **_: Any,
    ) -> RuntimeResult:
        """Write *content* to *path*.

        Atomic write strategy:
        1. Write content to a sibling temp file in the same directory.
        2. ``os.replace`` moves it atomically to *path*.

        This guarantees the file is never left in a partially-written state.

        Args:
            path      : Destination file path.
            content   : UTF-8 string content to write.
            overwrite : Allow replacing an existing file.
            append    : Append to the existing file (creates if absent).
        """
        if not path:
            return RuntimeResult.fail("write_file: 'path' parameter is required.")

        if overwrite and append:
            return RuntimeResult.fail(
                "write_file: 'overwrite' and 'append' are mutually exclusive."
            )

        file_path = Path(path).expanduser()
        already_exists = file_path.exists()

        if already_exists and not overwrite and not append:
            return RuntimeResult.fail(
                f"write_file: file already exists: '{path}'. "
                "Pass overwrite=True to replace it."
            )

        # Ensure parent directory exists
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return RuntimeResult.fail(
                f"write_file: cannot create parent directory for '{path}': {exc}"
            )

        encoded = content.encode("utf-8")
        bytes_written = len(encoded)

        try:
            if append:
                with file_path.open("ab") as fh:
                    fh.write(encoded)
            else:
                # Atomic write
                dir_path = file_path.parent
                fd, tmp_path = tempfile.mkstemp(dir=dir_path, prefix=".orion_write_")
                try:
                    with os.fdopen(fd, "wb") as fh:
                        fh.write(encoded)
                    os.replace(tmp_path, file_path)
                except Exception:
                    # Clean up the temp file on failure
                    with contextlib.suppress(OSError):
                        os.unlink(tmp_path)
                    raise
        except OSError as exc:
            return RuntimeResult.fail(f"write_file: cannot write to '{path}': {exc}")

        action = "appended to" if append else ("overwrote" if already_exists else "created")
        return RuntimeResult.ok(
            f"write_file: {action} '{path}' ({bytes_written} bytes).",
            bytes_written=bytes_written,
            created=not already_exists,
        )
