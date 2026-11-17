"""
O.R.I.O.N — Filtros do ``/resume`` e do ``session_switch`` (v0.5.3 Sprint 3, ADR-051)

Texto livre vira um ``SessionQuery``: datas (``hoje``, ``ontem``, ``semana``,
``semana passada``, ``mês``, ``nov``/``novembro``, ``2026-11``, ``2026``, ``16/11``,
``16/11/2026``), tipo (``daily``/``thread``) e workspace (``@.`` = o atual, ``@nome``).
O que sobra é busca FTS no título e no cartão. Datas são datas de daily (já deslocadas pela
hora da virada) e o intervalo é fechado nas duas pontas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

_MONTHS: dict[str, int] = {}
for _number, _names in enumerate(
    (
        ("jan", "janeiro"),
        ("fev", "fevereiro"),
        ("mar", "marco"),
        ("abr", "abril"),
        ("mai", "maio"),
        ("jun", "junho"),
        ("jul", "julho"),
        ("ago", "agosto"),
        ("set", "setembro"),
        ("out", "outubro"),
        ("nov", "novembro"),
        ("dez", "dezembro"),
    ),
    start=1,
):
    for _name in _names:
        _MONTHS[_name] = _number

_YEAR = re.compile(r"^(19|20)\d\d$")
_YEAR_MONTH = re.compile(r"^((?:19|20)\d\d)-(0[1-9]|1[0-2])$")
_DAY_MONTH = re.compile(r"^(\d{1,2})/(\d{1,2})(?:/((?:19|20)\d\d))?$")
_ISO_DAY = re.compile(r"^((?:19|20)\d\d)-(\d\d)-(\d\d)$")


def fold(text: str) -> str:
    """Minúsculas sem acento (``Março`` -> ``marco``)."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass
class SessionQuery:
    """Filtro de sessões; campos None não restringem."""

    date_from: date | None = None
    date_to: date | None = None
    kind: str | None = None
    workspace: str | None = None  # caminho exato (``@.``)
    workspace_name: str | None = None  # trecho do nome da pasta (``@orion``)
    terms: list[str] = field(default_factory=list)

    @property
    def has_dates(self) -> bool:
        return self.date_from is not None or self.date_to is not None

    def narrow(self, start: date, end: date) -> None:
        """Interseção com ``[start, end]``."""
        self.date_from = start if self.date_from is None else max(self.date_from, start)
        self.date_to = end if self.date_to is None else min(self.date_to, end)

    def describe(self) -> str:
        parts: list[str] = []
        if self.date_from and self.date_to:
            if self.date_from == self.date_to:
                parts.append(self.date_from.strftime("%d/%m/%Y"))
            else:
                parts.append(f"{self.date_from:%d/%m/%Y} a {self.date_to:%d/%m/%Y}")
        if self.kind:
            parts.append(self.kind)
        if self.workspace or self.workspace_name:
            parts.append("@" + (self.workspace_name or Path(self.workspace or "").name))
        if self.terms:
            parts.append(" ".join(self.terms))
        return " · ".join(parts)


def _month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return start, end - timedelta(days=1)


def parse_query(text: str, today: date, workspace: Path | None = None) -> SessionQuery:
    """Interpreta o texto do seletor relativo a ``today`` (data da daily atual)."""
    query = SessionQuery()
    tokens = text.split()
    year: int | None = None
    month: int | None = None
    index = 0
    while index < len(tokens):
        raw = tokens[index]
        token = fold(raw)
        nxt = fold(tokens[index + 1]) if index + 1 < len(tokens) else ""
        index += 1
        if token == "semana" and nxt == "passada":
            index += 1
            monday = today - timedelta(days=today.weekday())
            query.narrow(monday - timedelta(days=7), monday - timedelta(days=1))
        elif token == "hoje":
            query.narrow(today, today)
        elif token == "ontem":
            yesterday = today - timedelta(days=1)
            query.narrow(yesterday, yesterday)
        elif token == "semana":
            query.narrow(today - timedelta(days=today.weekday()), today)
        elif token in ("mes", "mês"):
            query.narrow(*_month_range(today.year, today.month))
        elif token in _MONTHS:
            month = _MONTHS[token]
        elif _YEAR.match(token):
            year = int(token)
        elif match := _YEAR_MONTH.match(token):
            query.narrow(*_month_range(int(match.group(1)), int(match.group(2))))
        elif match := _ISO_DAY.match(token):
            try:
                day = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                query.terms.append(raw)
                continue
            query.narrow(day, day)
        elif match := _DAY_MONTH.match(token):
            explicit = match.group(3)
            try:
                day = date(int(explicit) if explicit else today.year, int(match.group(2)), int(match.group(1)))
            except ValueError:
                query.terms.append(raw)
                continue
            if not explicit and day > today:
                day = day.replace(year=day.year - 1)
            query.narrow(day, day)
        elif token in ("daily", "dailies"):
            query.kind = "daily"
        elif token in ("thread", "threads"):
            query.kind = "thread"
        elif raw.startswith("@") and len(raw) > 1:
            if raw == "@." and workspace is not None:
                query.workspace = str(workspace.resolve())
            else:
                query.workspace_name = raw[1:]
        else:
            query.terms.append(raw)
    if month is not None:
        chosen = year if year is not None else today.year
        if year is None and month > today.month:
            chosen -= 1
        query.narrow(*_month_range(chosen, month))
    elif year is not None:
        query.narrow(date(year, 1, 1), date(year, 12, 31))
    return query


def fts_expression(terms: list[str]) -> str:
    """Termos -> expressão FTS5 segura (prefixo em cada termo, todos obrigatórios)."""
    words: list[str] = []
    for term in terms:
        for word in re.findall(r"\w+", term, flags=re.UNICODE):
            words.append(f'"{word}"*')
    return " ".join(words)
