"""Especificações de agenda: cron de 5 campos, intervalos e disparo único (ISO 8601).

Tudo é puro e determinístico (sem relógio, sem I/O). O cron é avaliado na zona ``tz`` (padrão: a
zona local do sistema); o resultado de :func:`next_fire` é sempre UTC com fuso.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Literal

from orion.agents.loops import parse_interval

SpecKind = Literal["cron", "interval", "once"]

MIN_INTERVAL_S = 60.0
_SEARCH_YEARS = 5

_MACROS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
}
_MONTHS = {
    n: i + 1
    for i, n in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    )
}
_DOWS = {n: i for i, n in enumerate(["sun", "mon", "tue", "wed", "thu", "fri", "sat"])}
_EVERY = re.compile(r"^every\s+(.+)$")


class InvalidSpec(ValueError):
    """Especificação de agenda inválida (mensagem em PT-BR)."""


def _expand_macro(text: str) -> str:
    return _MACROS.get(text, text)


def _interval_seconds(text: str) -> float | None:
    body = text.strip().lower()
    found = _EVERY.match(body)
    if found:
        body = found.group(1).strip()
    return parse_interval(body)


def _parse_once(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text.strip())
    except ValueError:
        return None


def spec_kind(text: str) -> SpecKind:
    """Classifica a especificação: ``cron``, ``interval`` ou ``once``."""
    body = text.strip().lower()
    if body.startswith("@") or len(body.split()) == 5:
        return "cron"
    if _interval_seconds(body) is not None:
        return "interval"
    if _parse_once(text) is not None:
        return "once"
    raise InvalidSpec(f"Especificação não reconhecida: {text!r}")


def _parse_value(token: str, names: dict[str, int], lo: int, hi: int, label: str) -> int:
    if token in names:
        return names[token]
    if not token.isdigit():
        raise InvalidSpec(f"Valor inválido no campo {label}: {token!r}")
    value = int(token)
    if not lo <= value <= hi:
        raise InvalidSpec(f"Valor fora do intervalo no campo {label}: {value} (válido {lo}-{hi})")
    return value


def _parse_field(
    text: str, lo: int, hi: int, label: str, names: dict[str, int] | None = None
) -> set[int]:
    names = names or {}
    result: set[int] = set()
    for part in text.split(","):
        if not part:
            raise InvalidSpec(f"Lista vazia no campo {label}")
        base, _, step_text = part.partition("/")
        step = 1
        if "/" in part:
            if not step_text.isdigit() or int(step_text) < 1:
                raise InvalidSpec(f"Passo inválido no campo {label}: {part!r}")
            step = int(step_text)
        if base == "*":
            start, end = lo, hi
        elif "-" in base:
            a, _, b = base.partition("-")
            start = _parse_value(a, names, lo, hi, label)
            end = _parse_value(b, names, lo, hi, label)
            if start > end:
                raise InvalidSpec(f"Faixa invertida no campo {label}: {base!r}")
        else:
            start = _parse_value(base, names, lo, hi, label)
            end = hi if "/" in part else start
        result.update(range(start, end + 1, step))
    return result


class _Cron:
    """Campos de cron já expandidos."""

    def __init__(self, text: str) -> None:
        fields = _expand_macro(text.strip().lower()).split()
        if len(fields) != 5:
            raise InvalidSpec("Cron precisa de 5 campos: minuto hora dia-do-mês mês dia-da-semana")
        self.minutes = sorted(_parse_field(fields[0], 0, 59, "minuto"))
        self.hours = sorted(_parse_field(fields[1], 0, 23, "hora"))
        self.doms = _parse_field(fields[2], 1, 31, "dia-do-mês")
        self.months = _parse_field(fields[3], 1, 12, "mês", _MONTHS)
        self.dows = {d % 7 for d in _parse_field(fields[4], 0, 7, "dia-da-semana", _DOWS)}
        self.dom_star = fields[2].startswith("*")
        self.dow_star = fields[4].startswith("*")
        self.normalized = " ".join(fields)

    def day_matches(self, year: int, month: int, day: int) -> bool:
        if month not in self.months:
            return False
        dom_ok = day in self.doms
        dow_ok = (datetime(year, month, day).weekday() + 1) % 7 in self.dows
        if not self.dom_star and not self.dow_star:
            return dom_ok or dow_ok
        return dom_ok and dow_ok


def validate_spec(text: str) -> str:
    """Valida e devolve a especificação normalizada; levanta :class:`InvalidSpec`."""
    if not text or not text.strip():
        raise InvalidSpec("Especificação vazia")
    kind = spec_kind(text)
    if kind == "cron":
        raw = text.strip().lower()
        cron = _Cron(raw)
        return raw if raw in _MACROS else cron.normalized
    if kind == "interval":
        seconds = _interval_seconds(text)
        assert seconds is not None
        if seconds < MIN_INTERVAL_S:
            raise InvalidSpec("Intervalo mínimo é de 60 segundos (1m)")
        body = text.strip().lower()
        return body if body.startswith("every") else f"every {body}"
    return text.strip()


def _localize(naive: datetime, fold: int, tz: tzinfo | None) -> datetime | None:
    """Naive local -> UTC; ``None`` se o horário local não existe (salto de DST)."""
    local = naive.replace(fold=fold, tzinfo=tz) if tz else naive.replace(fold=fold)
    utc = local.astimezone(UTC)
    back = utc.astimezone(tz).replace(tzinfo=None) if tz else utc.astimezone().replace(tzinfo=None)
    return utc if back == naive else None


def _cron_next(cron: _Cron, after: datetime, tz: tzinfo | None) -> datetime | None:
    local_after = after.astimezone(tz) if tz else after.astimezone()
    day = local_after.date() - timedelta(days=1)
    last = local_after.date() + timedelta(days=366 * _SEARCH_YEARS)
    one = timedelta(days=1)
    while day < last:
        day += one
        if not cron.day_matches(day.year, day.month, day.day):
            continue
        best: datetime | None = None
        for hour in cron.hours:
            for minute in cron.minutes:
                naive = datetime(day.year, day.month, day.day, hour, minute)
                for fold in (0, 1):
                    cand = _localize(naive, fold, tz)
                    if cand is not None and cand > after and (best is None or cand < best):
                        best = cand
        if best is not None:
            return best
    return None


def next_fire(spec: str, after: datetime, *, tz: tzinfo | None = None) -> datetime | None:
    """Próximo disparo estritamente posterior a ``after`` (UTC), ou ``None`` se não houver."""
    if after.tzinfo is None:
        raise ValueError("`after` precisa ter fuso horário")
    kind = spec_kind(spec)
    if kind == "cron":
        return _cron_next(_Cron(spec), after, tz)
    if kind == "interval":
        seconds = _interval_seconds(spec)
        assert seconds is not None
        if seconds < MIN_INTERVAL_S:
            raise InvalidSpec("Intervalo mínimo é de 60 segundos (1m)")
        return after.astimezone(UTC) + timedelta(seconds=seconds)
    when = _parse_once(spec)
    assert when is not None
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz) if tz else when.astimezone()
    when = when.astimezone(UTC)
    return when if when > after else None


def describe(spec: str) -> str:
    """Descrição curta em PT-BR."""
    kind = spec_kind(spec)
    if kind == "cron":
        return f"cron `{_Cron(spec).normalized}`"
    if kind == "interval":
        seconds = _interval_seconds(spec) or 0
        if seconds % 86400 == 0:
            return f"a cada {int(seconds // 86400)} dia(s)"
        if seconds % 3600 == 0:
            return f"a cada {int(seconds // 3600)} hora(s)"
        return f"a cada {int(seconds // 60)} minuto(s)"
    return f"uma vez em {spec.strip()}"
