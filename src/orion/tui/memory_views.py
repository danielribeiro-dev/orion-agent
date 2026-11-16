"""Listas legíveis da memória: ``/timeline`` e ``/recall`` (v0.5.2 Sprint 4, N-18 a N-21).

Uma linha por evento, ``hh:mm  papel  resumo…``, agrupada por dia (``hoje``, ``ontem``,
``dd/mm``). O resumo é o markdown convertido em texto plano: sem cercas de código, pipes de tabela,
``#``, ênfase e crases. As linhas são cortadas com reticências na largura atual (reflow na tela
cheia).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text

ROLE_LABELS = {
    "user": "Senhor",
    "assistant": "ORION",
    "agent": "ORION",
    "tool": "ferramenta",
    "observation": "ferramenta",
    "action": "ferramenta",
    "checkpoint": "sistema",
    "system": "sistema",
}
STATUS_LABELS = {"CONFIRMED": "confirmado", "INFERRED": "inferido", "DEPRECATED": "obsoleto"}
_ROLE_WIDTH = 11

_FENCE = re.compile(r"```[^\n]*\n(.*?)(```|$)", re.S)
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", re.M)
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_LIST = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.M)
_QUOTE = re.compile(r"^\s*>\s?", re.M)
_EMPHASIS = re.compile(r"(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1")


def markdown_to_plain(text: str) -> str:
    """Markdown → uma linha de texto corrido, sem marcação."""
    text = _FENCE.sub(lambda m: " " + " ".join(m.group(1).split()) + " ", text)
    text = _TABLE_RULE.sub(" ", text)
    text = _LINK.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _LIST.sub("", text)
    text = _QUOTE.sub("", text)
    text = _EMPHASIS.sub(r"\2", text)
    text = text.replace("`", "").replace("|", " ")
    return " ".join(text.split())


def role_label(event_type: str) -> str:
    return ROLE_LABELS.get(event_type, event_type or "evento")


def day_label(day: date, today: date) -> str:
    if day == today:
        return "hoje"
    if day == today - timedelta(days=1):
        return "ontem"
    return day.strftime("%d/%m") if day.year == today.year else day.strftime("%d/%m/%Y")


@dataclass(frozen=True)
class Entry:
    when: datetime
    role: str
    text: str


def entries_from_records(records: Iterable[Any]) -> list[Entry]:
    """Converte registros da timeline (``timestamp``, ``event_type``, ``content``)."""
    out = []
    for record in records:
        when = getattr(record, "timestamp", None)
        if not isinstance(when, datetime):
            continue
        out.append(
            Entry(when, role_label(str(getattr(record, "event_type", ""))), str(getattr(record, "content", "")))
        )
    return out


class TimelineView:
    """Lista agrupada por dia, uma linha por evento, que se ajusta à largura."""

    def __init__(
        self,
        entries: Sequence[Entry],
        title: str,
        *,
        highlight: str = "",
        today: date | None = None,
        footer: str = "",
    ) -> None:
        self.entries = sorted(entries, key=lambda e: e.when)
        self.title = title
        self.highlight = highlight
        self.today = today or date.today()
        self.footer = footer

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        head = Text(no_wrap=True, overflow="ellipsis")
        head.append(self.title, style="accent_cyan")
        count = len(self.entries)
        head.append(f" · {count} {'evento' if count == 1 else 'eventos'}", style="text_dim")
        yield head
        current: date | None = None
        for entry in self.entries:
            day = entry.when.date()
            if day != current:
                current = day
                yield Text(day_label(day, self.today), style="faint")
            line = Text(no_wrap=True, overflow="ellipsis")
            line.append(f"  {entry.when:%H:%M}  ", style="text_dim")
            role_style = "accent_cyan" if entry.role == "Senhor" else "text_dim"
            line.append(f"{entry.role:<{_ROLE_WIDTH}}", style=role_style)
            line.append(markdown_to_plain(entry.text), style="text_primary")
            if self.highlight:
                line.highlight_words([self.highlight], style="bold accent_blue", case_sensitive=False)
            line.truncate(width, overflow="ellipsis")
            yield line
        if self.footer:
            yield Text(self.footer, style="faint", no_wrap=True, overflow="ellipsis")


@dataclass(frozen=True)
class FactRow:
    key: str
    value: str
    status: str


class FactsView:
    """Fatos da memória com selo de status (``confirmado``, ``inferido``, ``obsoleto``)."""

    def __init__(self, facts: Sequence[FactRow], highlight: str = "") -> None:
        self.facts = facts
        self.highlight = highlight

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        width = options.max_width
        head = Text(no_wrap=True)
        head.append("Fatos", style="accent_cyan")
        head.append(f" · {len(self.facts)}", style="text_dim")
        yield head
        for fact in self.facts:
            label = STATUS_LABELS.get(fact.status.upper(), fact.status.lower())
            line = Text(no_wrap=True, overflow="ellipsis")
            line.append("  ● ", style="status_ok" if label == "confirmado" else "pep_warn")
            line.append(f"{label:<11}", style="text_dim")
            line.append(f"{fact.key}: ", style="text_dim")
            line.append(markdown_to_plain(fact.value), style="text_primary")
            if self.highlight:
                line.highlight_words([self.highlight], style="bold accent_blue", case_sensitive=False)
            line.truncate(width, overflow="ellipsis")
            yield line
