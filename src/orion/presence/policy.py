"""Política de presença determinística (ADR-036).

Sem LLM, sem provedor e sem preferências embutidas: sem regras ativas devolve
``DEFAULT_DELIVERY``. Só as regras confirmadas pelo Senhor (lidas de ``facts.db``) restringem.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, tzinfo

from orion.notify.models import (
    DEFAULT_DELIVERY,
    ActivityPort,
    Channel,
    Delivery,
    OutgoingMessage,
    channel_rank,
    min_channel,
)
from orion.presence.rules import PresenceRule


class PresencePolicy:
    """Implementa ``PresenceGate``."""

    def __init__(
        self,
        rules: Callable[[], list[PresenceRule]],
        activity: ActivityPort,
        *,
        tz: tzinfo | None = None,
    ) -> None:
        self._rules = rules
        self._activity = activity
        self._tz = tz

    def _local(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            return now.replace(tzinfo=self._tz) if self._tz else now
        return now.astimezone(self._tz)

    def _matches(self, rule: PresenceRule, local: datetime) -> bool:
        if not rule.applies_on(local.weekday()):
            return False
        window = rule.parsed_window()
        if window.point() is not None:
            # Resumo diário com horário fixo segura mensagens leves o tempo todo.
            return rule.kind == "digest"
        return window.contains(local, self._activity)

    def _active(self, now: datetime) -> list[PresenceRule]:
        local = self._local(now)
        return [r for r in self._rules() if self._matches(r, local)]

    def quiet_now(self, now: datetime) -> bool:
        return any(r.kind == "quiet_window" for r in self._active(now))

    def decide(self, message: OutgoingMessage, now: datetime) -> Delivery:
        active = self._active(now)
        if not active:
            return DEFAULT_DELIVERY

        cap: Channel = DEFAULT_DELIVERY.channel_cap
        silent = False
        digest = False
        decisive: PresenceRule | None = None
        decisive_rank = channel_rank(cap) + 1
        reasons: list[str] = []
        # Mensagens que já são resumo não voltam para o resumo.
        holdable = message.kind not in ("digest", "briefing")

        for rule in active:
            r_cap: Channel = DEFAULT_DELIVERY.channel_cap
            r_silent = False
            r_digest = False
            if rule.kind == "quiet_window":
                breaks = message.is_approval or message.priority == "critical"
                if breaks and rule.allow_critical:
                    r_cap = "notify"
                    r_silent = message.is_approval
                    reasons.append("janela de silêncio: exceção crítica")
                else:
                    r_cap = rule.channel_cap
                    r_silent = True
                    r_digest = holdable
                    reasons.append("janela de silêncio")
            elif rule.kind == "channel_cap":
                r_cap = rule.channel_cap
                reasons.append("teto de canal")
            elif rule.kind == "digest":
                if message.priority in ("low", "normal") and not message.is_approval and holdable:
                    r_digest = True
                    reasons.append("resumo agrupado")
            has_effect = r_silent or r_digest or r_cap != DEFAULT_DELIVERY.channel_cap
            if has_effect and (
                decisive is None
                or channel_rank(r_cap) < decisive_rank
            ):
                decisive = rule
                decisive_rank = channel_rank(r_cap)
            cap = min_channel(cap, r_cap)
            silent = silent or r_silent
            digest = digest or r_digest

        if decisive is None:
            # Regras ativas sem efeito sobre esta mensagem.
            return DEFAULT_DELIVERY.model_copy(
                update={"reason": "regras de presença sem efeito nesta mensagem"}
            )
        if digest:
            cap = min_channel(cap, "inbox")
        return Delivery(
            channel_cap=cap,
            silent=silent,
            digest=digest,
            reason="Presença: " + "; ".join(dict.fromkeys(reasons)),
            rule_key=decisive.key or None,
        )

    def due_briefings(
        self, now: datetime, last_sent: dict[str, date]
    ) -> list[PresenceRule]:
        local = self._local(now)
        today = local.date()
        due: list[PresenceRule] = []
        for rule in self._rules():
            if rule.kind not in ("briefing", "digest"):
                continue
            point = rule.parsed_window().point()
            if point is None or not rule.applies_on(local.weekday()):
                continue
            if local.time().replace(tzinfo=None) >= point and last_sent.get(rule.key) != today:
                due.append(rule)
        return due


__all__ = ["PresencePolicy", "channel_rank"]
