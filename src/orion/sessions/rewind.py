"""
O.R.I.O.N — Rewind de arquivos (v0.5.0 Sprint 3, CA-04)

Desfaz, em ordem inversa, as mutações de arquivo registradas após um ponto da sessão.
Nunca sobrescreve trabalho externo: se o arquivo no disco difere do estado registrado
após a mutação, ele é preservado e reportado como conflito.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from orion.sessions.store import JsonlSessionStore
from orion.sessions.transcript import FileSnapshot


@dataclass
class RestoreReport:
    restored: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{len(self.restored)} arquivo(s) restaurado(s)"]
        if self.conflicts:
            parts.append(
                f"{len(self.conflicts)} preservado(s) por alteração externa: " + ", ".join(self.conflicts)
            )
        return "; ".join(parts)


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def restore_files(
    store: JsonlSessionStore, session_id: str, changes: list[FileSnapshot]
) -> RestoreReport:
    """Aplica ``changes`` (da mais recente para a mais antiga) revertendo cada arquivo."""
    report = RestoreReport()
    for change in changes:
        path = Path(change.path)
        after = store.get_blob(session_id, change.after_sha)
        current = _read(path)
        before = store.get_blob(session_id, change.before_sha) if change.before_sha else None
        if current == before:
            continue  # já no estado desejado (mutações sucessivas no mesmo arquivo)
        if current != after:
            report.conflicts.append(change.path)
            continue
        if before is None:
            path.unlink(missing_ok=True)
        else:
            temp = path.with_name(f".{path.name}.orion-rewind")
            temp.write_text(before, encoding="utf-8")
            os.replace(temp, path)
        report.restored.append(change.path)
    return report
