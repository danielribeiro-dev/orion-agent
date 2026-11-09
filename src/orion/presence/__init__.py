"""Política de presença do ORION (ADR-036): mecanismos determinísticos, regras vindas da memória."""

from orion.presence.activity import ActivityLog
from orion.presence.policy import PresencePolicy
from orion.presence.rules import (
    InvalidWindow,
    PresenceRule,
    PresenceRuleStore,
    Window,
    parse_window,
)

__all__ = [
    "ActivityLog",
    "InvalidWindow",
    "PresencePolicy",
    "PresenceRule",
    "PresenceRuleStore",
    "Window",
    "parse_window",
]
