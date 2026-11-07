"""Sessões persistentes: transcript JSONL, resume e rewind (v0.5.0 Sprint 3)."""

from orion.sessions.rewind import RestoreReport, restore_files
from orion.sessions.store import JsonlSessionStore, SessionNotFoundError, SessionStore
from orion.sessions.transcript import (
    FileSnapshot,
    SessionMeta,
    TranscriptEntry,
    TurnRef,
    file_changes_from,
    replay,
    user_turns,
)

__all__ = [
    "FileSnapshot",
    "JsonlSessionStore",
    "RestoreReport",
    "SessionMeta",
    "SessionNotFoundError",
    "SessionStore",
    "TranscriptEntry",
    "TurnRef",
    "file_changes_from",
    "replay",
    "restore_files",
    "user_turns",
]
