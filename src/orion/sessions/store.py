"""
O.R.I.O.N — Store de sessões em JSONL (v0.5.0 Sprint 3, CA-04)

Layout (somente em ``~/.orion/``, permissões 0700/0600):

    sessions/<workspace-slug>/<session_id>.jsonl      log append-only
    sessions/<workspace-slug>/<session_id>.blobs/<sha256>   conteúdo dos arquivos (rewind)

Escrita imediata por mensagem (um crash perde no máximo a linha em curso); a leitura
ignora uma última linha truncada. ``rewind`` trunca o log de forma atômica.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from orion.sessions.transcript import (
    SessionMeta,
    TranscriptEntry,
    user_turns,
    workspace_slug,
)

logger = logging.getLogger(__name__)

_List = builtins.list  # ``list`` é sombreado pelo método ``SessionStore.list``


class SessionStore(Protocol):
    """Contrato de persistência de sessões."""

    def append(self, session_id: str, entry: TranscriptEntry) -> None: ...
    def load(self, session_id: str) -> _List[TranscriptEntry]: ...
    def list(self, workspace: Path) -> _List[SessionMeta]: ...
    def rewind(self, session_id: str, to_entry: int) -> None: ...


class SessionNotFoundError(LookupError):
    """Nenhuma sessão com o identificador (ou prefixo) informado."""


class JsonlSessionStore:
    """Implementação em arquivos JSONL por workspace."""

    def __init__(self, root: Path, workspace: Path) -> None:
        self._root = root
        self._workspace = workspace.resolve()
        self._counts: dict[str, int] = {}
        self._paths: dict[str, Path] = {}

    # ── Caminhos ──

    def _dir(self, workspace: Path | None = None) -> Path:
        return self._root / workspace_slug(workspace or self._workspace)

    def _path(self, session_id: str) -> Path:
        cached = self._paths.get(session_id)
        if cached is not None:
            return cached
        existing = self._find(session_id)
        path = existing if existing is not None else self._dir() / f"{session_id}.jsonl"
        self._paths[session_id] = path
        return path

    def _find(self, session_id: str) -> Path | None:
        if not self._root.is_dir():
            return None
        for candidate in self._root.glob(f"*/{session_id}.jsonl"):
            return candidate
        return None

    def resolve_id(self, prefix: str) -> str:
        """Id completo a partir de um prefixo único (``/resume ab12``)."""
        matches = sorted({p.stem for p in self._root.glob("*/*.jsonl") if p.stem.startswith(prefix)})
        if not matches:
            raise SessionNotFoundError(f"Nenhuma sessão começa com '{prefix}'.")
        if len(matches) > 1:
            raise SessionNotFoundError(f"Prefixo '{prefix}' é ambíguo ({len(matches)} sessões).")
        return matches[0]

    # ── Leitura / escrita ──

    def exists(self, session_id: str) -> bool:
        return self._find(session_id) is not None

    def append(self, session_id: str, entry: TranscriptEntry) -> None:
        path = self._path(session_id)
        first = not path.exists()
        if first:
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._counts[session_id] = 0
            self._write(path, self._meta_entry(session_id, 0))
            self._counts[session_id] = 1
        index = self._counts.get(session_id)
        if index is None:
            index = len(self.load(session_id))
        entry = entry.model_copy(update={"index": index})
        self._write(path, entry)
        self._counts[session_id] = index + 1

    def _meta_entry(self, session_id: str, index: int) -> TranscriptEntry:
        return TranscriptEntry.of_meta(
            session_id=session_id, workspace=str(self._workspace)
        ).model_copy(update={"index": index})

    @staticmethod
    def _write(path: Path, entry: TranscriptEntry) -> None:
        line = entry.model_dump_json(exclude_none=True) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(line)

    def load(self, session_id: str) -> _List[TranscriptEntry]:
        path = self._find(session_id)
        if path is None:
            raise SessionNotFoundError(f"Sessão '{session_id}' não encontrada.")
        entries: _List[TranscriptEntry] = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                entries.append(TranscriptEntry.model_validate_json(line))
            except (ValidationError, ValueError):
                logger.warning("Sessão %s: linha %d inválida ignorada.", session_id, number + 1)
        self._counts[session_id] = len(entries)
        return entries

    def list(self, workspace: Path) -> _List[SessionMeta]:
        """Sessões do workspace, da mais recente para a mais antiga."""
        directory = self._dir(workspace)
        if not directory.is_dir():
            return []
        metas: _List[SessionMeta] = []
        for path in directory.glob("*.jsonl"):
            try:
                entries = self.load(path.stem)
            except SessionNotFoundError:  # pragma: no cover - corrida com remoção
                continue
            turns = user_turns(entries)
            if not turns:
                continue
            metas.append(
                SessionMeta(
                    session_id=path.stem,
                    workspace=str(workspace.resolve()),
                    created_at=entries[0].ts if entries else "",
                    updated_at=entries[-1].ts if entries else "",
                    turns=len(turns),
                    preview=turns[0].preview,
                )
            )
        return sorted(metas, key=lambda m: m.updated_at, reverse=True)

    def rewind(self, session_id: str, to_entry: int) -> None:
        """Trunca o log mantendo as entradas com ``index < to_entry`` (atômico)."""
        entries = self.load(session_id)
        kept = [e for e in entries if e.index < to_entry]
        path = self._path(session_id)
        temp = path.with_suffix(".jsonl.tmp")
        body = "".join(e.model_dump_json(exclude_none=True) + "\n" for e in kept)
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(temp, path)
        self._counts[session_id] = len(kept)

    # ── Blobs (conteúdo de arquivos para o /rewind) ──

    def _blobs(self, session_id: str) -> Path:
        return self._path(session_id).with_suffix(".blobs")

    def put_blob(self, session_id: str, text: str) -> str:
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        directory = self._blobs(session_id)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = directory / sha
        if not target.exists():
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
        return sha

    def get_blob(self, session_id: str, sha: str) -> str:
        return (self._blobs(session_id) / sha).read_text(encoding="utf-8")

    def dump(self, session_id: str) -> str:  # pragma: no cover - depuração
        return json.dumps([e.model_dump(mode="json") for e in self.load(session_id)], indent=1)
