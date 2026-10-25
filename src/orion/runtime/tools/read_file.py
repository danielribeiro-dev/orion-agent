"""
O.R.I.O.N — Primitive Tool: read_file
Paginated file reading with line-range and byte-offset support.

ActionLevel: LEVEL_1 (Passive read)

Parameters:
    path         (str)      : Absolute or relative path to the file.
    start_line   (int|None) : First line to read (1-based, inclusive). Default: 1.
    end_line     (int|None) : Last line to read (inclusive). Default: end of file.
    byte_offset  (int)      : Byte offset into the line range. Default: 0.
    max_bytes    (int)      : Maximum bytes to return. Default: 47185920 (45 MiB).

Output:
    File content as a UTF-8 string (with replacement for undecodable bytes).
    Metadata: total_lines (int), returned_lines (int), truncated (bool).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

_DEFAULT_MAX_BYTES = 45 * 1024 * 1024  # 45 MiB


class ReadFileTool(BaseTool):
    """Read a file with optional line-range pagination and byte limits."""

    name = "read_file"

    async def run(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        byte_offset: int = 0,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        **_: Any,
    ) -> RuntimeResult:
        """Return the contents of *path*, optionally sliced by line range.

        Args:
            path        : Path to the file (required).
            start_line  : First line to include (1-based). None means line 1.
            end_line    : Last line to include (1-based, inclusive). None means EOF.
            byte_offset : Skip this many bytes from the start of the slice.
            max_bytes   : Hard cap on returned bytes.
        """
        if not path:
            return RuntimeResult.fail("read_file: 'path' parameter is required.")

        file_path = Path(path)

        if not file_path.exists():
            return RuntimeResult.fail(f"read_file: file not found: '{path}'")

        if not file_path.is_file():
            return RuntimeResult.fail(f"read_file: path is not a regular file: '{path}'")

        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            return RuntimeResult.fail(f"read_file: cannot read '{path}': {exc}")

        text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        total_lines = len(lines)

        # Normalise line indices (convert to 0-based)
        sl = max(0, (start_line - 1) if start_line is not None else 0)
        el = (end_line if end_line is not None else total_lines)
        el = min(el, total_lines)

        selected = lines[sl:el]
        content = "".join(selected)

        # Apply byte offset
        if byte_offset > 0:
            content = content[byte_offset:]

        # Apply byte cap
        truncated = len(content.encode("utf-8")) > max_bytes
        if truncated:
            content = content.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")

        return RuntimeResult(
            success=True,
            output=content,
            error="",
            metadata={
                "total_lines": total_lines,
                "returned_lines": len(selected),
                "truncated": truncated,
            },
        )
