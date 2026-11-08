"""Escrita e leitura privadas de JSON (arquivo 0600, diretório 0700, atômica)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def write_private_json(path: Path, data: Any) -> None:
    """Grava ``data`` em ``path`` de forma atômica com permissão 0600.

    Cria o diretório pai com 0700 quando ele ainda não existe.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temp, path)
    os.chmod(path, 0o600)


def read_json_object(path: Path) -> dict[str, Any] | None:
    """Lê um objeto JSON; devolve ``None`` se ausente, ilegível ou não for objeto."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
