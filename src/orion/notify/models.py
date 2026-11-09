"""Contratos de saída do daemon (ADR-032, ADR-034, ADR-036).

Tudo o que o ORION quer dizer ao Senhor sem terminal vira um :class:`OutgoingMessage`. Antes de
qualquer entrega, um :class:`PresenceGate` (a política de presença lida da memória) devolve uma
:class:`Delivery`: até que canal a mensagem pode subir, se toca som e se vai para o resumo
agrupado. O roteador (``notify/router.py``) respeita esse teto e segue a ordem de prioridade
cliente anexado > notificação nativa > Telegram > voz (v0.6.0).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

#: Teto de canal, em ordem crescente de intrusão. ``notify`` cobre desktop e Telegram.
Channel = Literal["none", "inbox", "notify", "voice"]
CHANNEL_ORDER: tuple[Channel, ...] = ("none", "inbox", "notify", "voice")

Priority = Literal["low", "normal", "high", "critical"]
MessageKind = Literal["message", "approval", "digest", "briefing", "alert", "job"]


def channel_rank(channel: Channel) -> int:
    return CHANNEL_ORDER.index(channel)


def min_channel(a: Channel, b: Channel) -> Channel:
    return a if channel_rank(a) <= channel_rank(b) else b


class NotifyAction(BaseModel):
    """Botão de uma notificação (``approve``, ``deny``, ``open``...)."""

    id: str
    label: str


class OutgoingMessage(BaseModel):
    """Uma saída do ORION para o Senhor, independente de canal."""

    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:10]}")
    kind: MessageKind = "message"
    title: str
    body: str = ""
    priority: Priority = "normal"
    actions: list[NotifyAction] = Field(default_factory=list)
    origin: str = "daemon"
    #: Validade de uma aprovação; expirada, vale como negada (nunca como aprovada).
    ttl_s: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_approval(self) -> bool:
        return self.kind == "approval"


class Delivery(BaseModel):
    """Decisão da política de presença para uma mensagem."""

    channel_cap: Channel = "voice"
    #: Sem som (notificação silenciosa / urgência baixa).
    silent: bool = False
    #: Segura a mensagem e a entrega agrupada no próximo resumo.
    digest: bool = False
    reason: str = "sem regra de presença"
    #: Regra que decidiu (chave do fato na memória), para auditoria e feedback.
    rule_key: str | None = None


DEFAULT_DELIVERY = Delivery()


class PresenceGate(Protocol):
    """Política de presença determinística (implementada em ``presence/policy.py``)."""

    def decide(self, message: OutgoingMessage, now: datetime) -> Delivery: ...


class ActivityPort(Protocol):
    """Sinais de atividade do Senhor (prompt, attach, clique numa notificação)."""

    def first_activity_on(self, day: date) -> datetime | None: ...

    def last_activity(self) -> datetime | None: ...


FeedbackSignal = Literal["approved", "denied", "dismissed", "ignored", "expired", "opened"]


class FeedbackEvent(BaseModel):
    """Sinal de feedback sobre uma entrega, guardado para a memória viva (ADR-027)."""

    message_id: str
    signal: FeedbackSignal
    channel: Channel
    rule_key: str | None = None
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
