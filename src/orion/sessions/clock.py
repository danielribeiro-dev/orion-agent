"""
O.R.I.O.N — Relógio das dailies (v0.5.3 Sprint 3, ADR-051)

A daily é identificada pela data local deslocada pela hora da virada
(``settings.memory.day_starts_at``, padrão 04:00): às 02:00 do dia 17 a daily ainda é a do
dia 16. Nada roda por relógio (ADR-022): a virada acontece na primeira atividade depois dela.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo

DAILY_PREFIX = "daily-"
DEFAULT_DAY_STARTS_AT = "04:00"


def parse_hhmm(value: str | None) -> time:
    """``"04:00"`` -> ``time(4, 0)``; valor inválido cai no padrão."""
    try:
        hours, minutes = (value or DEFAULT_DAY_STARTS_AT).split(":")
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        return time(4, 0)


def local_now(tz: tzinfo | None = None) -> datetime:
    """Agora com fuso (o local do sistema, se ``tz`` for None)."""
    return datetime.now(tz) if tz is not None else datetime.now().astimezone()


def to_local(moment: datetime, tz: tzinfo | None = None) -> datetime:
    """Converte para o fuso pedido (ou o local); instantes sem fuso são tratados como UTC."""
    if moment.tzinfo is None:
        from datetime import UTC

        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(tz) if tz is not None else moment.astimezone()


def local_day(moment: datetime, starts_at: time, tz: tzinfo | None = None) -> date:
    """Data da daily a que ``moment`` pertence."""
    local = to_local(moment, tz)
    if local.time() < starts_at:
        return local.date() - timedelta(days=1)
    return local.date()


def daily_id_for(day: date) -> str:
    return f"{DAILY_PREFIX}{day.isoformat()}"


def is_daily_id(session_id: str) -> bool:
    return session_id.startswith(DAILY_PREFIX)


def day_of_daily(session_id: str) -> date | None:
    """``daily-2026-11-16`` -> ``date(2026, 11, 16)``; None se não for uma daily."""
    if not is_daily_id(session_id):
        return None
    try:
        return date.fromisoformat(session_id[len(DAILY_PREFIX) :])
    except ValueError:
        return None


def parse_iso(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        from datetime import UTC

        moment = moment.replace(tzinfo=UTC)
    return moment
