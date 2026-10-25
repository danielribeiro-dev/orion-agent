"""
O.R.I.O.N — Audit Logger
Append-only structured audit trail for all actions validated by the PEP.

File: ~/.orion/audit.log
Format: one JSON object per line (JSON-Lines).

Each entry contains:
  - timestamp     : ISO-8601 UTC
  - action_id     : UUID of the Action event
  - tool          : tool name
  - params        : tool parameters (sanitised)
  - level         : ActionLevel integer
  - user_authorized : True = human confirmed | False = auto-approved by policy
  - result_status : "pending" | "success" | "denied" | "error"
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LOG_PATH = Path.home() / ".orion" / "audit.log"


class AuditLogger:
    """Append-only audit logger for governance events.

    Writes one JSON-Lines record per action to *log_path*.
    The file is opened in append mode on every write to survive process
    restarts and avoid file-descriptor leaks in daemon mode.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        self._path: Path = log_path or _DEFAULT_LOG_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def log_path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log(
        self,
        *,
        action_id: str,
        tool: str,
        params: dict[str, Any],
        level: int,
        user_authorized: bool,
        result_status: str,
    ) -> None:
        """Write a single audit record.

        Args:
            action_id       : UUID of the Action event.
            tool            : Name of the tool being audited.
            params          : Parameters passed to the tool (will be
                              serialised; non-serialisable values are
                              replaced with their string representation).
            level           : ActionLevel integer value.
            user_authorized : Whether a human explicitly approved this action.
            result_status   : One of "pending", "success", "denied", "error".
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_id": action_id,
            "tool": tool,
            "params": _safe_json(params),
            "level": level,
            "user_authorized": user_authorized,
            "result_status": result_status,
        }
        self._append(record)

    def log_denied(
        self,
        *,
        action_id: str,
        tool: str,
        params: dict[str, Any],
        level: int,
        reason: str,
    ) -> None:
        """Convenience helper for recording a PEP denial."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action_id": action_id,
            "tool": tool,
            "params": _safe_json(params),
            "level": level,
            "user_authorized": False,
            "result_status": "denied",
            "denial_reason": reason,
        }
        self._append(record)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append(self, record: dict[str, Any]) -> None:
        """Write *record* as a single JSON-Lines entry."""
        line = json.dumps(record, ensure_ascii=False)
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            # Never crash the agent because of a logging failure
            logger.error("AuditLogger: failed to write to %s: %s", self._path, exc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_json(params: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe copy of *params*, converting non-serialisable values."""
    safe: dict[str, Any] = {}
    for k, v in params.items():
        try:
            json.dumps(v)
            safe[k] = v
        except (TypeError, ValueError):
            safe[k] = repr(v)
    return safe
