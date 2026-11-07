"""
O.R.I.O.N — Tool: glob
Busca arquivos por padrão (``**/*.py``), ordenados por modificação (mais recentes primeiro).

ActionLevel: LEVEL_1 (leitura passiva)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.runtime.tools.search_files import _is_ignored

DEFAULT_LIMIT = 250


class GlobTool(BaseTool):
    name = "glob"
    description = (
        "Find files by glob pattern (e.g. '**/*.py', 'src/**/test_*.py'). Results are sorted by "
        "modification time, newest first. Noise folders (.git, node_modules, .venv...) are skipped."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob pattern."},
            "path": {"type": "string", "description": "Directory to search (default: current)."},
            "limit": {"type": "integer", "minimum": 1, "description": f"Max results (default {DEFAULT_LIMIT})."},
        },
        "required": ["pattern"],
    }
    read_only = True

    async def run(
        self, pattern: str, path: str = ".", limit: int = DEFAULT_LIMIT, **_: Any
    ) -> RuntimeResult:
        if not pattern.strip():
            return RuntimeResult.fail("glob: 'pattern' must be non-empty.")
        root = Path(path).expanduser()
        if not root.is_dir():
            return RuntimeResult.fail(f"glob: not a directory: '{path}'")
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            return RuntimeResult.fail("glob: pattern must be relative and stay inside the search path.")

        found: list[tuple[float, Path]] = []
        try:
            for match in root.glob(pattern):
                rel = match.relative_to(root)
                if any(_is_ignored(part) for part in rel.parts) or not match.is_file():
                    continue
                try:
                    found.append((match.stat().st_mtime, rel))
                except OSError:
                    continue
        except (ValueError, NotImplementedError) as exc:
            return RuntimeResult.fail(f"glob: invalid pattern '{pattern}': {exc}")

        found.sort(key=lambda item: (-item[0], str(item[1])))
        shown = found[:limit]
        if not shown:
            return RuntimeResult.ok("(no matches)", count=0, truncated=False)
        text = "\n".join(str(rel) for _, rel in shown)
        truncated = len(found) > limit
        if truncated:
            text += f"\n[{len(found) - limit} more results omitted; narrow the pattern]"
        return RuntimeResult.ok(text, count=len(found), truncated=truncated)
