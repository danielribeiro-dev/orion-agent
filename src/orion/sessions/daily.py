"""
O.R.I.O.N — Daily (v0.5.3 Sprint 3, ADR-051)

Uma daily por data local (``daily-YYYY-MM-DD``), estável entre recargas: é a sessão padrão do
daemon, da voz sem TUI e da TUI aberta em ``~`` (ou com ``--daily``). A virada acontece na
primeira atividade depois de ``memory.day_starts_at`` (nunca por relógio, ADR-022): fecha as
dailies anteriores ainda abertas com um cartão determinístico (contagens e títulos das threads;
o cartão por modelo chega na Sprint 5) e abre a nova com o resumo curto da anterior.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from orion.sessions.clock import daily_id_for, day_of_daily, local_day, local_now
from orion.sessions.index import SessionIndex, SessionRecord
from orion.sessions.store import JsonlSessionStore, SessionNotFoundError
from orion.sessions.transcript import user_turns

logger = logging.getLogger(__name__)

#: Teto do resumo de abertura (~300 tokens a 4 caracteres por token).
OPENING_MAX_CHARS = 1200
_WEEKDAYS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@dataclass
class DailyState:
    """Resultado de ``DailyBook.ensure``: a daily de hoje e o que a virada fechou."""

    today: SessionRecord
    created: bool = False
    closed: list[str] = field(default_factory=list)


def daily_title(daily_id: str) -> str:
    day = day_of_daily(daily_id)
    if day is None:
        return daily_id
    return f"Daily {day:%d/%m/%Y} ({_WEEKDAYS[day.weekday()]})"


class DailyBook:
    """Cuida da daily do dia: id, virada, cartão e resumo de abertura."""

    def __init__(self, index: SessionIndex, store: JsonlSessionStore) -> None:
        self.index = index
        self.store = store

    def today_id(self, now: datetime | None = None) -> str:
        moment = now or local_now(self.index.tz)
        return daily_id_for(local_day(moment, self.index.starts_at, self.index.tz))

    def ensure(self, now: datetime | None = None) -> DailyState:
        """Garante a daily de hoje; na virada fecha as anteriores e gera o resumo de abertura."""
        today_id = self.today_id(now)
        closed: list[str] = []
        for old in self.index.open_dailies_before(today_id):
            self.index.close_session(old.id, card=self.card(old))
            closed.append(old.id)
        existing = self.index.get(today_id)
        if existing is not None:
            return DailyState(today=existing, closed=closed)
        previous = self.index.latest_daily_before(today_id)
        opening = self.opening_for(previous) if previous is not None else ""
        record = self.index.register(
            today_id,
            "daily",
            title=daily_title(today_id),
            daily_id=today_id,
            opening=opening or None,
        )
        return DailyState(today=record, created=True, closed=closed)

    # ── Cartão e resumo (determinísticos nesta sprint) ──

    def card(self, daily: SessionRecord) -> dict[str, Any]:
        threads = [
            {"id": t.id, "title": t.display_title, "turns": t.turn_count, "workspace": t.workspace or ""}
            for t in self.index.children(daily.id)
            if t.turn_count > 0
        ]
        requests: list[str] = []
        try:
            requests = [t.preview for t in user_turns(self.store.load(daily.id))][:8]
        except SessionNotFoundError:
            pass
        except Exception:  # pragma: no cover - transcript ilegível não impede a virada
            logger.exception("DailyBook: transcript da daily %s ilegível", daily.id)
        card: dict[str, Any] = {
            "kind": "daily",
            "date": daily.local_date,
            "turns": daily.turn_count,
            "thread_count": len(threads),
            "threads": threads,
            "requests": requests,
        }
        card["summary"] = self._summary(daily.id, card)
        return card

    @staticmethod
    def _summary(daily_id: str, card: dict[str, Any]) -> str:
        day = day_of_daily(daily_id)
        label = f"{day:%d/%m/%Y}" if day else daily_id
        parts = [f"Daily de {label}: {card['turns']} pedido(s) na daily"]
        threads = card.get("threads") or []
        if threads:
            names = ", ".join(f"'{t['title']}' ({t['turns']})" for t in threads[:8])
            parts.append(f"{len(threads)} thread(s): {names}")
        requests = card.get("requests") or []
        if requests:
            parts.append("Pedidos: " + "; ".join(requests))
        return ". ".join(parts) + "."

    def opening_for(self, previous: SessionRecord) -> str:
        """Resumo curto (até ~300 tokens) da daily anterior para abrir a nova."""
        card = previous.card if previous.card else self.card(previous)
        summary = str(card.get("summary") or "")
        if not summary or (not card.get("turns") and not card.get("threads")):
            return ""
        if len(summary) > OPENING_MAX_CHARS:
            cut = summary[:OPENING_MAX_CHARS]
            summary = cut[: cut.rfind(" ")].rstrip(" ,;") + "."
        return summary
