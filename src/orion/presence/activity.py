"""Registro de atividade do Senhor (ADR-036).

Guarda apenas o primeiro e o último sinal de atividade por dia local, num JSON pequeno em
``~/.orion/`` (o caminho vem de quem instancia). Alimenta janelas relativas como
"até a primeira atividade do dia".
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_DAYS = 30


def _aware_now() -> datetime:
    return datetime.now(UTC).astimezone()


class ActivityLog:
    """Implementa ``ActivityPort`` com persistência atômica (modo 0600)."""

    def __init__(
        self,
        path: Path,
        *,
        clock: Callable[[], datetime] = _aware_now,
    ) -> None:
        self._path = path
        self._clock = clock
        # dia (ISO) -> [primeiro, último] em ISO 8601 com offset
        self._days: dict[str, list[str]] = {}
        self._load()

    # ------------------------------------------------------------------
    # ActivityPort
    # ------------------------------------------------------------------

    def first_activity_on(self, day: date) -> datetime | None:
        entry = self._days.get(day.isoformat())
        return datetime.fromisoformat(entry[0]) if entry else None

    def last_activity(self) -> datetime | None:
        if not self._days:
            return None
        entry = self._days[max(self._days)]
        return datetime.fromisoformat(entry[1])

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def record(self, at: datetime | None = None) -> None:
        """Registra uma atividade em ``at`` (padrão: agora)."""
        moment = at if at is not None else self._clock()
        if moment.tzinfo is None:
            moment = moment.astimezone()
        key = moment.date().isoformat()
        entry = self._days.get(key)
        if entry is None:
            self._days[key] = [moment.isoformat(), moment.isoformat()]
        else:
            first = datetime.fromisoformat(entry[0])
            last = datetime.fromisoformat(entry[1])
            if moment < first:
                entry[0] = moment.isoformat()
            if moment > last:
                entry[1] = moment.isoformat()
        self._prune()
        self._save()

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _prune(self) -> None:
        for old in sorted(self._days)[:-MAX_DAYS]:
            del self._days[old]

    def _load(self) -> None:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            days = raw["days"]
            self._days = {
                str(k): [str(v[0]), str(v[1])] for k, v in days.items()
            }
        except FileNotFoundError:
            self._days = {}
        except (ValueError, KeyError, TypeError, IndexError, OSError):
            logger.warning("Registro de atividade ilegível em %s; recomeçando.", self._path)
            self._days = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, prefix=".activity-")
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"days": self._days}, fh)
            os.replace(tmp, self._path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
