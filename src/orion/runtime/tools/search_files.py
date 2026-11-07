"""
O.R.I.O.N — Primitive Tool: search_files
Fast glob + regex grep with automatic noise-folder exclusion.

ActionLevel: LEVEL_1 (Passive read)

Parameters:
    path        (str)       : Root directory to search. Default: "." (cwd).
    pattern     (str)       : Glob pattern for file matching (e.g. "*.py").
                              OR a regex pattern when mode="grep".
    mode        (str)       : "glob" (default) or "grep".
    regex       (str|None)  : Regex to search inside matched files (for grep mode,
                              this is the primary pattern and *pattern* is the file glob).
    case_sensitive (bool)   : Whether regex is case-sensitive. Default: True.
    max_results (int)       : Maximum results to return. Default: 200.
    include_hidden (bool)   : Include hidden files/dirs. Default: False.

Output (glob mode):
    Newline-separated list of matching file paths.

Output (grep mode):
    Newline-separated list of "<file>:<line_no>:<line_content>" matches.

Excluded directories (always):
    .git, __pycache__, node_modules, .venv, venv, .tox, dist, build,
    .mypy_cache, .ruff_cache, .pytest_cache, .eggs, *.egg-info
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

_IGNORED_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        "dist",
        "build",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".eggs",
    }
)


def _is_ignored(part: str) -> bool:
    return part in _IGNORED_DIRS or part.endswith(".egg-info")


class SearchFilesTool(BaseTool):
    """Glob files and grep content with automatic noise exclusion."""

    name = "search_files"
    description = (
        "Find files by glob pattern (mode=glob) or search file contents with a regex (mode=grep)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Root directory (default: current)."},
            "pattern": {"type": "string", "description": "Glob for file names, e.g. '*.py'."},
            "mode": {"type": "string", "enum": ["glob", "grep"]},
            "regex": {"type": "string", "description": "Regex searched inside files (grep mode)."},
            "case_sensitive": {"type": "boolean"},
            "max_results": {"type": "integer", "minimum": 1},
            "include_hidden": {"type": "boolean"},
        },
    }
    read_only = True

    async def run(
        self,
        path: str = ".",
        pattern: str = "*",
        mode: str = "glob",
        regex: str | None = None,
        case_sensitive: bool = True,
        max_results: int = 200,
        include_hidden: bool = False,
        **_: Any,
    ) -> RuntimeResult:
        root = Path(path).resolve()

        if not root.exists():
            return RuntimeResult.fail(f"search_files: path not found: '{path}'")

        if mode == "glob":
            return self._glob(root, pattern, max_results, include_hidden)

        if mode in ("grep", "content"):  # "content" is the name the agent prompt uses
            file_pattern = pattern
            if not regex:
                # Only a text was given: search it as a regex inside every file,
                # instead of also (wrongly) using it as the file glob.
                regex, file_pattern = pattern, "*"
            return self._grep(root, file_pattern, regex, case_sensitive, max_results, include_hidden)

        return RuntimeResult.fail(
            f"search_files: unknown mode '{mode}'. Choose 'glob' or 'grep'."
        )

    # ------------------------------------------------------------------
    # Glob mode
    # ------------------------------------------------------------------

    def _glob(
        self,
        root: Path,
        pattern: str,
        max_results: int,
        include_hidden: bool,
    ) -> RuntimeResult:
        matches: list[str] = []
        for file_path in root.rglob(pattern):
            if len(matches) >= max_results:
                break
            if _should_skip(file_path, include_hidden):
                continue
            matches.append(str(file_path))

        if not matches:
            return RuntimeResult.ok(
                f"search_files (glob): no files matching '{pattern}' under '{root}'.",
                match_count=0,
                truncated=False,
            )

        truncated = len(matches) >= max_results
        output = "\n".join(matches)
        return RuntimeResult.ok(
            output,
            match_count=len(matches),
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # Grep mode
    # ------------------------------------------------------------------

    def _grep(
        self,
        root: Path,
        file_pattern: str,
        regex: str,
        case_sensitive: bool,
        max_results: int,
        include_hidden: bool,
    ) -> RuntimeResult:
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled = re.compile(regex, flags)
        except re.error as exc:
            return RuntimeResult.fail(f"search_files (grep): invalid regex '{regex}': {exc}")

        lines: list[str] = []
        truncated = False

        # An explicit file path is searched directly (rglob inside a file finds nothing).
        explicit_file = root.is_file()
        candidates = [root] if explicit_file else root.rglob(file_pattern)
        for file_path in candidates:
            if not explicit_file and _should_skip(file_path, include_hidden):
                continue
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for lineno, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    lines.append(f"{file_path}:{lineno}:{line}")
                    if len(lines) >= max_results:
                        truncated = True
                        break
            if truncated:
                break

        if not lines:
            return RuntimeResult.ok(
                f"search_files (grep): no matches for '{regex}' in files matching '{file_pattern}' under '{root}'.",
                match_count=0,
                truncated=False,
            )

        return RuntimeResult.ok(
            "\n".join(lines),
            match_count=len(lines),
            truncated=truncated,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _should_skip(path: Path, include_hidden: bool) -> bool:
    """Return True if *path* should be excluded from results."""
    for part in path.parts:
        if _is_ignored(part):
            return True
        if not include_hidden and part.startswith(".") and part not in (".", ".."):
            return True
    return False
