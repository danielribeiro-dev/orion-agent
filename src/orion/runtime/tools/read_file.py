"""
O.R.I.O.N — Primitive Tool: read_file
Leitura paginada de texto (com numeração), imagens e PDF.

ActionLevel: LEVEL_1 (leitura passiva)

Parâmetros:
    path        : caminho do arquivo.
    offset      : primeira linha (1-based). Alias legado: start_line.
    limit       : nº máximo de linhas. Alias legado: end_line (última linha, inclusive).
    numbered    : prefixa ``N→`` em cada linha (padrão True).
    pages       : intervalo de páginas de PDF, ex. "1-5".
    byte_offset / max_bytes : fatiamento e teto em bytes do texto devolvido.

Imagens (png/jpg/gif/webp) são devolvidas como bloco de imagem ao modelo
(``metadata["image"]``); PDFs são convertidos para texto com ``pdftotext``.
"""

from __future__ import annotations

import base64
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

_DEFAULT_MAX_BYTES = 45 * 1024 * 1024  # 45 MiB
DEFAULT_LINE_LIMIT = 2000
MAX_LINE_CHARS = 2000
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES_PER_CALL = 20
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_PAGES = re.compile(r"^(\d+)(?:-(\d+))?$")


def encode_image(path: Path) -> dict[str, str] | None:
    """Bloco ``source`` base64 de uma imagem suportada; None se não for imagem."""
    media_type = IMAGE_TYPES.get(path.suffix.lower())
    if media_type is None:
        return None
    return {
        "type": "base64",
        "media_type": media_type,
        "data": base64.standard_b64encode(path.read_bytes()).decode("ascii"),
    }


class ReadFileTool(BaseTool):
    """Lê arquivos de texto, imagens e PDFs."""

    name = "read_file"
    description = (
        "Read a file. Text is returned with line numbers (N→); use offset/limit for large files "
        f"(default {DEFAULT_LINE_LIMIT} lines). Images (png, jpg, gif, webp) are shown to you "
        "visually. PDFs are converted to text; use 'pages' (e.g. '1-5') for long ones. "
        "Always read a file before editing it."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path (absolute or relative to the workspace)."},
            "offset": {"type": "integer", "minimum": 1, "description": "First line to read (1-based)."},
            "limit": {"type": "integer", "minimum": 1, "description": "Number of lines to read."},
            "start_line": {"type": "integer", "minimum": 1, "description": "Alias of offset."},
            "end_line": {"type": "integer", "minimum": 1, "description": "Last line (inclusive)."},
            "numbered": {"type": "boolean", "description": "Prefix lines with numbers (default true)."},
            "pages": {"type": "string", "description": "PDF page range, e.g. '1-5' or '3'."},
            "byte_offset": {"type": "integer", "minimum": 0},
            "max_bytes": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
    }
    read_only = True

    async def run(
        self,
        path: str,
        offset: int | None = None,
        limit: int | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        numbered: bool = True,
        pages: str | None = None,
        byte_offset: int = 0,
        max_bytes: int = _DEFAULT_MAX_BYTES,
        **_: Any,
    ) -> RuntimeResult:
        if not path:
            return RuntimeResult.fail("read_file: 'path' parameter is required.")

        file_path = Path(path).expanduser()
        if not file_path.exists():
            return RuntimeResult.fail(f"read_file: file not found: '{path}'")
        if not file_path.is_file():
            return RuntimeResult.fail(f"read_file: path is not a regular file: '{path}'")

        suffix = file_path.suffix.lower()
        if suffix in IMAGE_TYPES:
            return self._read_image(file_path, path)
        if suffix == ".pdf":
            return self._read_pdf(file_path, path, pages)

        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            return RuntimeResult.fail(f"read_file: cannot read '{path}': {exc}")
        if b"\x00" in raw[:8192]:
            return RuntimeResult.fail(f"read_file: '{path}' looks like a binary file.")

        lines = raw.decode("utf-8", errors="replace").splitlines(keepends=True)
        total = len(lines)

        first = (offset or start_line or 1) - 1
        if limit is not None:
            last = first + limit
        elif end_line is not None:
            last = end_line
        else:
            last = first + DEFAULT_LINE_LIMIT
        last = min(last, total)
        selected = lines[first:last]
        capped = limit is None and end_line is None and last < total

        if numbered:
            body = "".join(
                f"{first + i + 1:>6}→{_clip(line)}" for i, line in enumerate(selected)
            )
        else:
            body = "".join(selected)

        if byte_offset > 0:
            body = body[byte_offset:]
        truncated = len(body.encode("utf-8")) > max_bytes
        if truncated:
            body = body.encode("utf-8")[:max_bytes].decode("utf-8", errors="replace")
        if capped:
            body += (
                f"\n[showing lines {first + 1}-{last} of {total}; "
                f"use offset={last + 1} to continue]"
            )
        elif first >= total and total:
            body = f"[offset {first + 1} is beyond the end of the file ({total} lines)]"

        return RuntimeResult(
            success=True,
            output=body,
            error="",
            metadata={
                "total_lines": total,
                "returned_lines": len(selected),
                "truncated": truncated or capped,
            },
        )

    @staticmethod
    def _read_image(file_path: Path, shown: str) -> RuntimeResult:
        size = file_path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            return RuntimeResult.fail(
                f"read_file: image '{shown}' has {size} bytes; the limit is {MAX_IMAGE_BYTES}."
            )
        try:
            source = encode_image(file_path)
        except OSError as exc:
            return RuntimeResult.fail(f"read_file: cannot read '{shown}': {exc}")
        return RuntimeResult.ok(
            f"[image {file_path.name}, {size} bytes, attached for visual inspection]",
            image=source,
            is_image=True,
        )

    @staticmethod
    def _read_pdf(file_path: Path, shown: str, pages: str | None) -> RuntimeResult:
        binary = shutil.which("pdftotext")
        if binary is None:
            return RuntimeResult.fail("read_file: PDF support requires 'pdftotext' (poppler-utils).")
        cmd = [binary, "-layout"]
        if pages:
            match = _PAGES.match(pages.strip())
            if match is None:
                return RuntimeResult.fail(f"read_file: invalid 'pages' value '{pages}' (use '3' or '1-5').")
            first = int(match.group(1))
            last = int(match.group(2) or first)
            if last < first or last - first + 1 > MAX_PDF_PAGES_PER_CALL:
                return RuntimeResult.fail(
                    f"read_file: 'pages' must be a valid range of at most {MAX_PDF_PAGES_PER_CALL} pages."
                )
            cmd += ["-f", str(first), "-l", str(last)]
        try:
            proc = subprocess.run(  # noqa: S603
                [*cmd, str(file_path), "-"], capture_output=True, timeout=60, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return RuntimeResult.fail(f"read_file: cannot convert '{shown}': {exc}")
        if proc.returncode != 0:
            return RuntimeResult.fail(
                f"read_file: pdftotext failed: {proc.stderr.decode('utf-8', 'replace').strip()}"
            )
        text = proc.stdout.decode("utf-8", errors="replace")
        if not pages and text.count("\f") > MAX_PDF_PAGES_PER_CALL:
            return RuntimeResult.fail(
                f"read_file: '{shown}' has {text.count(chr(12))} pages; pass 'pages' "
                f"(at most {MAX_PDF_PAGES_PER_CALL} per call)."
            )
        return RuntimeResult.ok(text.replace("\f", "\n[page break]\n"), is_pdf=True)


def _clip(line: str) -> str:
    if len(line) <= MAX_LINE_CHARS:
        return line
    return line[:MAX_LINE_CHARS] + "[... line truncated]\n"
