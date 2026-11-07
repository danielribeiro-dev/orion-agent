"""
O.R.I.O.N — Tool: grep
Busca de conteúdo por regex. Usa ``ripgrep`` quando instalado; senão, implementação Python.

ActionLevel: LEVEL_1 (leitura passiva)
"""

from __future__ import annotations

import asyncio
import fnmatch
import re
import shutil
from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool
from orion.runtime.tools.search_files import _is_ignored

DEFAULT_HEAD_LIMIT = 250
MAX_FILE_BYTES = 2 * 1024 * 1024
_MODES = ("content", "files_with_matches", "count")


class GrepTool(BaseTool):
    name = "grep"
    description = (
        "Search file contents with a regex (ripgrep syntax when available). output_mode: "
        "'files_with_matches' (default), 'content' (matching lines, with context via context/"
        "before/after) or 'count'. Filter files with 'glob' (e.g. '*.py'). Noise folders are skipped."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regular expression."},
            "path": {"type": "string", "description": "File or directory (default: current)."},
            "glob": {"type": "string", "description": "File name filter, e.g. '*.py'."},
            "output_mode": {"type": "string", "enum": list(_MODES)},
            "case_insensitive": {"type": "boolean"},
            "context": {"type": "integer", "minimum": 0, "maximum": 20},
            "before": {"type": "integer", "minimum": 0, "maximum": 20},
            "after": {"type": "integer", "minimum": 0, "maximum": 20},
            "head_limit": {"type": "integer", "minimum": 1, "description": "Max output lines."},
        },
        "required": ["pattern"],
    }
    read_only = True

    async def run(
        self,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        output_mode: str = "files_with_matches",
        case_insensitive: bool = False,
        context: int = 0,
        before: int = 0,
        after: int = 0,
        head_limit: int = DEFAULT_HEAD_LIMIT,
        **_: Any,
    ) -> RuntimeResult:
        if not pattern:
            return RuntimeResult.fail("grep: 'pattern' must be non-empty.")
        try:
            rx = re.compile(pattern, re.IGNORECASE if case_insensitive else 0)
        except re.error as exc:
            return RuntimeResult.fail(f"grep: invalid regex: {exc}")
        root = Path(path).expanduser()
        if not root.exists():
            return RuntimeResult.fail(f"grep: path not found: '{path}'")
        before, after = before or context, after or context

        lines: list[str] | None = None
        engine = "python"
        binary = shutil.which("rg")
        if binary:
            lines = await self._ripgrep(
                binary, pattern, root, glob, output_mode, case_insensitive, before, after
            )
            engine = "ripgrep"
        if lines is None:
            lines = self._python(rx, root, glob, output_mode, before, after)
            engine = "python"

        if not lines:
            return RuntimeResult.ok("(no matches)", count=0, engine=engine, truncated=False)
        truncated = len(lines) > head_limit
        text = "\n".join(lines[:head_limit])
        if truncated:
            text += f"\n[{len(lines) - head_limit} more lines omitted; narrow the pattern or path]"
        return RuntimeResult.ok(text, count=len(lines), engine=engine, truncated=truncated)

    # ── ripgrep ─────────────────────────────────────────────────────────
    @staticmethod
    async def _ripgrep(
        binary: str,
        pattern: str,
        root: Path,
        glob: str | None,
        mode: str,
        icase: bool,
        before: int,
        after: int,
    ) -> list[str] | None:
        cmd = [binary, "--no-heading", "--with-filename", "--color", "never", "--max-columns", "500"]
        cmd += {"files_with_matches": ["-l"], "count": ["-c"], "content": ["-n"]}[mode]
        if icase:
            cmd.append("-i")
        if mode == "content":
            if before:
                cmd += ["-B", str(before)]
            if after:
                cmd += ["-A", str(after)]
        if glob:
            cmd += ["--glob", glob]
        cmd += ["-e", pattern, "--", str(root)]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        except (OSError, TimeoutError):
            return None
        if proc.returncode not in (0, 1):  # 1 = sem matches; >1 = erro => cai para Python
            return None
        return out.decode("utf-8", errors="replace").splitlines()

    # ── fallback Python ─────────────────────────────────────────────────
    @staticmethod
    def _files(root: Path, glob: str | None) -> list[Path]:
        if root.is_file():
            return [root]
        found: list[Path] = []
        for candidate in sorted(root.rglob("*")):
            rel = candidate.relative_to(root)
            if any(_is_ignored(part) or part.startswith(".") for part in rel.parts[:-1]):
                continue
            if candidate.is_file() and (not glob or fnmatch.fnmatch(candidate.name, glob)):
                found.append(candidate)
        return found

    def _python(
        self, rx: re.Pattern[str], root: Path, glob: str | None, mode: str, before: int, after: int
    ) -> list[str]:
        out: list[str] = []
        for file in self._files(root, glob):
            try:
                if file.stat().st_size > MAX_FILE_BYTES:
                    continue
                raw = file.read_bytes()
            except OSError:
                continue
            if b"\x00" in raw[:4096]:
                continue
            text_lines = raw.decode("utf-8", errors="replace").splitlines()
            hits = [i for i, line in enumerate(text_lines) if rx.search(line)]
            if not hits:
                continue
            if mode == "files_with_matches":
                out.append(str(file))
            elif mode == "count":
                out.append(f"{file}:{len(hits)}")
            else:
                shown: set[int] = set()
                for i in hits:
                    shown.update(range(max(0, i - before), min(len(text_lines), i + after + 1)))
                for i in sorted(shown):
                    sep = ":" if i in hits else "-"
                    out.append(f"{file}{sep}{i + 1}{sep}{text_lines[i]}")
        return out
