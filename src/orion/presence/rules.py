"""Regras de presença (ADR-036): modelo, gramática de janelas e armazenamento em fatos.

O código só oferece mecanismos. As preferências do Senhor vivem em ``facts.db`` como fatos
``presence.<kind>.<slug>``: o modelo as interpreta uma vez na conversa, o Senhor confirma, e a
avaliação posterior é determinística (``policy.py``). Proposta (INFERRED) nunca é aplicada.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, ValidationError

from orion.memory.facts_store import FactsStore
from orion.memory.models import FactCategory, FactEntry, FactStatus
from orion.notify.models import ActivityPort, Channel

logger = logging.getLogger(__name__)

RuleKind = Literal["quiet_window", "digest", "channel_cap", "briefing"]

KEY_PREFIX = "presence."

_HHMM = r"(?P<{n}>[01]\d|2[0-3]):(?P<{m}>[0-5]\d)"
_DELTA = r"(?P<num>\d{1,4})(?P<unit>[mh])"
_RANGE_RE = re.compile(_HHMM.format(n="h1", m="m1") + "-" + _HHMM.format(n="h2", m="m2") + "$")
_DAILY_RE = re.compile("daily@" + _HHMM.format(n="h1", m="m1") + "$")
_REL_RE = re.compile(r"first_activity\+" + _DELTA + "$")
_START_REL_RE = re.compile(_HHMM.format(n="h1", m="m1") + r"-first_activity\+" + _DELTA + "$")


class InvalidWindow(ValueError):
    """Janela fora da gramática aceita."""


@dataclass(frozen=True)
class Window:
    """Janela de tempo já interpretada."""

    mode: Literal["range", "until_first", "after_first", "start_until_first", "point"]
    start: time | None = None
    end: time | None = None
    delta: timedelta | None = None

    def point(self) -> time | None:
        return self.start if self.mode == "point" else None

    def contains(self, now_local: datetime, activity: ActivityPort) -> bool:
        """Diz se ``now_local`` está dentro da janela. Janelas ``daily@`` nunca "contêm"."""
        if self.mode == "point":
            return False
        t = now_local.time().replace(tzinfo=None)
        if self.mode == "range":
            assert self.start is not None and self.end is not None
            if self.start < self.end:
                return self.start <= t < self.end
            return t >= self.start or t < self.end

        first = activity.first_activity_on(now_local.date())
        if first is not None and now_local.tzinfo is not None:
            first = first.astimezone(now_local.tzinfo)
        if self.mode == "until_first":
            return first is None or now_local < first
        assert self.delta is not None
        limit = None if first is None else first + self.delta
        if self.mode == "after_first":
            return limit is None or now_local < limit
        # start_until_first
        assert self.start is not None
        return t >= self.start and (limit is None or now_local < limit)


def _delta(m: re.Match[str]) -> timedelta:
    n = int(m["num"])
    if n <= 0:
        raise InvalidWindow("O deslocamento da janela precisa ser maior que zero.")
    return timedelta(minutes=n) if m["unit"] == "m" else timedelta(hours=n)


def parse_window(text: str) -> Window:
    """Interpreta o texto da janela; levanta :class:`InvalidWindow` se inválido."""
    s = text.strip().lower()
    if s == "until_first_activity":
        return Window("until_first")
    if m := _RANGE_RE.match(s):
        start = time(int(m["h1"]), int(m["m1"]))
        end = time(int(m["h2"]), int(m["m2"]))
        if start == end:
            raise InvalidWindow(f"Janela vazia: início e fim iguais em '{text}'.")
        return Window("range", start=start, end=end)
    if m := _DAILY_RE.match(s):
        return Window("point", start=time(int(m["h1"]), int(m["m1"])))
    if m := _REL_RE.match(s):
        return Window("after_first", delta=_delta(m))
    if m := _START_REL_RE.match(s):
        return Window(
            "start_until_first", start=time(int(m["h1"]), int(m["m1"])), delta=_delta(m)
        )
    raise InvalidWindow(
        f"Janela inválida: '{text}'. Use HH:MM-HH:MM, until_first_activity, "
        "first_activity+90m, HH:MM-first_activity+30m ou daily@HH:MM."
    )


class PresenceRule(BaseModel):
    """Uma regra de presença confirmada (ou proposta) pelo Senhor."""

    key: str = ""
    kind: RuleKind
    window: str
    channel_cap: Channel = "inbox"
    allow_critical: bool = True
    days: list[int] | None = None
    description: str = ""

    def parsed_window(self) -> Window:
        return parse_window(self.window)

    def applies_on(self, weekday: int) -> bool:
        return self.days is None or weekday in self.days


def _slug(rule: PresenceRule) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", rule.window.strip().lower()).strip("-")
    return f"{KEY_PREFIX}{rule.kind}.{base}"


class PresenceRuleStore:
    """Lê e grava regras de presença como fatos USER_PREFERENCE em ``facts.db``."""

    def __init__(self, facts: FactsStore) -> None:
        self._facts = facts

    def _validated(self, rule: PresenceRule) -> PresenceRule:
        rule.parsed_window()  # levanta InvalidWindow
        if rule.days is not None and any(d < 0 or d > 6 for d in rule.days):
            raise ValueError("Dias da semana devem estar entre 0 (segunda) e 6 (domingo).")
        key = rule.key or _slug(rule)
        if not key.startswith(KEY_PREFIX):
            raise ValueError(f"Chave de regra deve começar com '{KEY_PREFIX}'.")
        return rule.model_copy(update={"key": key})

    def _write(self, rule: PresenceRule, status: FactStatus) -> PresenceRule:
        ready = self._validated(rule)
        confirmed = status == FactStatus.CONFIRMED
        self._facts.upsert(
            FactEntry(
                key=ready.key,
                value=ready.model_dump_json(),
                category=FactCategory.USER_PREFERENCE,
                status=status,
                confidence=1.0 if confirmed else 0.5,
                source="user" if confirmed else "agent",
            )
        )
        return ready

    def propose(self, rule: PresenceRule) -> PresenceRule:
        """Grava como INFERRED: proposta que ainda não vale (anti-poisoning preservado)."""
        return self._write(rule, FactStatus.INFERRED)

    def confirm(self, rule: PresenceRule) -> PresenceRule:
        """Grava como CONFIRMED (o Senhor aprovou); passa a valer."""
        return self._write(rule, FactStatus.CONFIRMED)

    def remove(self, key: str) -> bool:
        if not key.startswith(KEY_PREFIX):
            return False
        return self._facts.deprecate(key)

    def list_active(self) -> list[PresenceRule]:
        return self._load(FactStatus.CONFIRMED)

    def proposals(self) -> list[PresenceRule]:
        return self._load(FactStatus.INFERRED)

    def _load(self, status: FactStatus) -> list[PresenceRule]:
        entries = self._facts.search(
            category=FactCategory.USER_PREFERENCE, status=status, limit=1000
        )
        rules: list[PresenceRule] = []
        for entry in entries:
            if not entry.key.startswith(KEY_PREFIX):
                continue
            try:
                rule = PresenceRule.model_validate_json(entry.value)
                rule.parsed_window()
            except (ValidationError, InvalidWindow, ValueError):
                logger.warning("Regra de presença ilegível ignorada: %s", entry.key)
                continue
            rules.append(rule.model_copy(update={"key": entry.key}))
        return rules
