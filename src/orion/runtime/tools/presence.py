"""
O.R.I.O.N — Tools de presença (v0.5.0 Sprint 7C, ADR-036)

O modelo interpreta UMA vez o pedido do Senhor ("de manhã, até eu começar a mexer, fique quieto")
e o converte numa regra estruturada; a confirmação do PEP (LEVEL_3) é a confirmação do Senhor, e
só então a regra vira fato CONFIRMED em ``facts.db``. Daí em diante a política é determinística.
``presence_rule_list`` é LEVEL_0. Nunca entregues a subagents.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from orion.presence.rules import InvalidWindow, PresenceRule, PresenceRuleStore
from orion.runtime.provider import RuntimeResult
from orion.runtime.tools.base import BaseTool

_WINDOW_HELP = (
    "window grammar: 'HH:MM-HH:MM' (may wrap midnight), 'until_first_activity', "
    "'first_activity+90m', 'HH:MM-first_activity+30m', or 'daily@HH:MM' (for briefing/digest)"
)


def _line(rule: PresenceRule) -> str:
    days = "" if rule.days is None else " dias " + ",".join(str(d) for d in rule.days)
    critical = "" if rule.allow_critical else " · crítico também silenciado"
    return f"{rule.key} · {rule.kind} · {rule.window} · teto {rule.channel_cap}{days}{critical} · {rule.description[:60]}"


class _PresenceTool(BaseTool):
    def __init__(self, facts: Callable[[], Any]) -> None:
        self._facts = facts

    def _store(self) -> PresenceRuleStore | None:
        facts = self._facts()
        return PresenceRuleStore(facts) if facts is not None else None


class PresenceRuleCreateTool(_PresenceTool):
    name = "presence_rule_create"
    description = (
        "Save a presence preference of the user (how and when ORION may reach them when no terminal "
        "is attached). kinds: quiet_window (silence; content goes to a digest; only approvals and "
        "critical alerts break through when allow_critical), channel_cap (max channel: none|inbox|"
        "notify|voice), digest (group low-priority items), briefing (deliver the digest at a time). "
        + _WINDOW_HELP
        + ". Put the user's own words in description. The user confirms before it is stored."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["quiet_window", "digest", "channel_cap", "briefing"]},
            "window": {"type": "string", "minLength": 1},
            "channel_cap": {"type": "string", "enum": ["none", "inbox", "notify", "voice"]},
            "allow_critical": {"type": "boolean"},
            "days": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 6}},
            "description": {"type": "string"},
        },
        "required": ["kind", "window", "description"],
    }

    async def run(self, **params: Any) -> RuntimeResult:
        store = self._store()
        if store is None:
            return RuntimeResult.fail("memory (facts.db) is unavailable")
        try:
            rule = PresenceRule(
                kind=params["kind"],
                window=str(params["window"]),
                channel_cap=params.get("channel_cap") or "inbox",
                allow_critical=bool(params.get("allow_critical", True)),
                days=params.get("days"),
                description=str(params.get("description") or ""),
            )
            saved = store.confirm(rule)
        except (InvalidWindow, ValueError) as exc:
            return RuntimeResult.fail(f"invalid rule: {exc}. {_WINDOW_HELP}")
        return RuntimeResult.ok(f"Presence rule saved: {_line(saved)}", key=saved.key)


class PresenceRuleListTool(_PresenceTool):
    name = "presence_rule_list"
    description = "List the user's confirmed presence rules (quiet windows, channel caps, digests, briefings)."
    input_schema = {"type": "object", "properties": {}}
    read_only = True

    async def run(self, **params: Any) -> RuntimeResult:
        store = self._store()
        if store is None:
            return RuntimeResult.fail("memory (facts.db) is unavailable")
        rules = store.list_active()
        if not rules:
            return RuntimeResult.ok("No presence rules: default behavior (no silence, all channels).")
        return RuntimeResult.ok("\n".join(_line(r) for r in rules), count=len(rules))


class PresenceRuleDeleteTool(_PresenceTool):
    name = "presence_rule_delete"
    description = "Remove a presence rule by key (see presence_rule_list)."
    input_schema = {
        "type": "object",
        "properties": {"key": {"type": "string", "minLength": 1}},
        "required": ["key"],
    }

    async def run(self, **params: Any) -> RuntimeResult:
        store = self._store()
        if store is None:
            return RuntimeResult.fail("memory (facts.db) is unavailable")
        key = str(params["key"])
        if not store.remove(key):
            return RuntimeResult.fail(f"no presence rule {key}")
        return RuntimeResult.ok(f"Presence rule {key} removed.")
