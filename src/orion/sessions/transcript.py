"""
O.R.I.O.N — Transcript de sessão (v0.5.0 Sprint 3, CA-04)

A sessão é um log JSONL append-only de ``TranscriptEntry``. O estado da conversa é
reconstruído por ``replay``: ``message`` acrescenta; ``compact`` SUBSTITUI a conversa por
um instantâneo (a auto-compactação); ``file_change`` não afeta a conversa — registra uma
mutação de arquivo (com ponteiros para blobs) para o ``/rewind`` desfazê-la.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from orion.gateway.models import LLMMessage
from orion.timeline.autocompact import is_turn_start

EntryKind = Literal["meta", "message", "compact", "file_change"]


def _now() -> str:
    return datetime.now(UTC).isoformat()


class FileSnapshot(BaseModel):
    """Uma mutação de arquivo; ``before_sha`` None = arquivo criado. Conteúdo vive em blobs."""

    path: str
    before_sha: str | None = None
    after_sha: str


class TranscriptEntry(BaseModel):
    """Linha do transcript. ``index`` é atribuído pelo store (posição no arquivo)."""

    index: int = -1
    ts: str = Field(default_factory=_now)
    kind: EntryKind
    message: LLMMessage | None = None
    messages: list[LLMMessage] | None = None
    file: FileSnapshot | None = None
    meta: dict[str, Any] | None = None

    @classmethod
    def of_message(cls, message: LLMMessage) -> TranscriptEntry:
        return cls(kind="message", message=message)

    @classmethod
    def of_compact(cls, messages: list[LLMMessage]) -> TranscriptEntry:
        return cls(kind="compact", messages=list(messages))

    @classmethod
    def of_file(cls, snapshot: FileSnapshot) -> TranscriptEntry:
        return cls(kind="file_change", file=snapshot)

    @classmethod
    def of_meta(cls, **meta: Any) -> TranscriptEntry:
        return cls(kind="meta", meta=meta)


class SessionMeta(BaseModel):
    """Resumo de uma sessão para listagem (``/resume``, ``--continue``)."""

    session_id: str
    workspace: str
    created_at: str
    updated_at: str
    turns: int
    preview: str = ""


class TurnRef(BaseModel):
    """Um turno do usuário endereçável pelo ``/rewind``."""

    number: int
    entry_index: int
    preview: str


def replay(entries: list[TranscriptEntry]) -> list[LLMMessage]:
    """Reconstrói a conversa a partir do log."""
    messages: list[LLMMessage] = []
    for entry in entries:
        if entry.kind == "message" and entry.message is not None:
            messages.append(entry.message)
        elif entry.kind == "compact" and entry.messages is not None:
            messages = list(entry.messages)
    return messages


def user_turns(entries: list[TranscriptEntry]) -> list[TurnRef]:
    """Pedidos do usuário (numerados a partir de 1) que podem servir de ponto de retorno."""
    turns: list[TurnRef] = []
    for entry in entries:
        message = entry.message
        if entry.kind == "message" and message is not None and is_turn_start(message):
            text = "".join(b.text or "" for b in message.blocks if b.type == "text")
            first = " ".join(text.split())[:80]
            turns.append(TurnRef(number=len(turns) + 1, entry_index=entry.index, preview=first))
    return turns


def file_changes_from(entries: list[TranscriptEntry], start_index: int) -> list[FileSnapshot]:
    """Mutações de arquivo registradas a partir de ``start_index``, da mais recente à mais antiga."""
    changes = [
        e.file for e in entries if e.kind == "file_change" and e.file is not None and e.index >= start_index
    ]
    return list(reversed(changes))


def workspace_slug(workspace: Path) -> str:
    """Nome de diretório estável e legível para um workspace."""
    import hashlib

    resolved = str(workspace.resolve())
    name = "".join(c if c.isalnum() else "-" for c in workspace.resolve().name) or "root"
    return f"{name}-{hashlib.sha256(resolved.encode()).hexdigest()[:10]}"
