"""Roteador de saída do daemon (ADR-032, ADR-036).

Ordem de prioridade: cliente anexado > notificação nativa > Telegram > voz (v0.6.0, não
implementada). O roteador apenas obedece a :class:`Delivery` devolvida pelo ``PresenceGate`` e
nunca fixa preferências. Aprovação NUCLEAR remota é proibida.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from orion.notify.desktop import DesktopNotifier
from orion.notify.inbox import Inbox
from orion.notify.models import (
    DEFAULT_DELIVERY,
    Channel,
    Delivery,
    FeedbackEvent,
    FeedbackSignal,
    OutgoingMessage,
    PresenceGate,
    channel_rank,
)
from orion.notify.telegram import TelegramNotifier

logger = logging.getLogger(__name__)

_NUCLEAR_REASON = "aprovação nuclear remota é proibida"


class AttachedClientPort(Protocol):
    """Clientes (TUI/desktop) anexados ao daemon."""

    def has_clients(self) -> bool: ...

    async def deliver(self, message: OutgoingMessage, delivery: Delivery) -> None: ...


class RouteResult(BaseModel):
    channels: list[str]
    held_for_digest: bool
    delivery: Delivery


class ApprovalResult(BaseModel):
    approved: bool
    action_id: str | None
    channel: str | None
    reason: str


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _feedback_channel(channel: str | None) -> Channel:
    return "notify" if channel in ("desktop", "telegram") else "inbox"


class OutputRouter:
    def __init__(
        self,
        *,
        inbox: Inbox,
        presence: PresenceGate | None = None,
        clients: AttachedClientPort | None = None,
        desktop: DesktopNotifier | None = None,
        telegram: TelegramNotifier | None = None,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._inbox = inbox
        self._presence = presence
        self._clients = clients
        self._desktop = desktop
        self._telegram = telegram
        self._clock = clock

    # ------------------------------------------------------------------ helpers

    def _decide(self, message: OutgoingMessage) -> Delivery:
        if self._presence is None:
            return DEFAULT_DELIVERY
        return self._presence.decide(message, self._clock())

    def _client_ready(self) -> bool:
        return self._clients is not None and self._clients.has_clients()

    def _desktop_ready(self) -> bool:
        return self._desktop is not None and self._desktop.available()

    def _feedback(
        self, message: OutgoingMessage, signal: FeedbackSignal, channel: str | None, d: Delivery
    ) -> None:
        self._inbox.record_feedback(
            FeedbackEvent(
                message_id=message.id,
                signal=signal,
                channel=_feedback_channel(channel),
                rule_key=d.rule_key,
                at=self._clock(),
            )
        )

    # --------------------------------------------------------------------- send

    async def send(self, message: OutgoingMessage) -> RouteResult:
        delivery = self._decide(message)
        is_digest = bool(message.payload.get("digest"))
        if delivery.digest and not is_digest and not message.is_approval:
            self._inbox.hold(message)
            return RouteResult(channels=[], held_for_digest=True, delivery=delivery)

        self._inbox.add(message)
        channels: list[str] = []
        cap = channel_rank(delivery.channel_cap)

        if cap >= channel_rank("inbox") and self._client_ready():
            assert self._clients is not None
            await self._clients.deliver(message, delivery)
            self._inbox.mark_read(message.id)
            channels.append("client")
            return RouteResult(channels=channels, held_for_digest=False, delivery=delivery)

        if cap >= channel_rank("notify"):
            desktop_ok = self._desktop_ready()
            if desktop_ok:
                assert self._desktop is not None
                await self._desktop.show(message, delivery)
                channels.append("desktop")
            wants_telegram = (
                not desktop_ok or message.priority in ("high", "critical") or message.is_approval
            )
            if (
                self._telegram is not None
                and wants_telegram
                and await self._telegram.send(message, delivery) is not None
            ):
                channels.append("telegram")
        return RouteResult(channels=channels, held_for_digest=False, delivery=delivery)

    # ----------------------------------------------------------------- approval

    async def request_approval(self, message: OutgoingMessage, *, ttl_s: int) -> ApprovalResult:
        message = message.model_copy(update={"kind": "approval", "ttl_s": ttl_s})
        delivery = self._decide(message)

        if message.payload.get("nuclear"):
            self._inbox.add(message, status="expired")
            self._feedback(message, "denied", None, delivery)
            return ApprovalResult(
                approved=False, action_id=None, channel=None, reason=_NUCLEAR_REASON
            )

        self._inbox.add(message)
        cap = channel_rank(delivery.channel_cap)
        tasks: dict[asyncio.Task[str | None], str] = {}

        if cap >= channel_rank("inbox") and self._client_ready():
            assert self._clients is not None
            await self._clients.deliver(message, delivery)
        if cap >= channel_rank("notify"):
            if self._desktop_ready():
                assert self._desktop is not None
                tasks[asyncio.ensure_future(self._desktop.ask(message, delivery, ttl_s))] = (
                    "desktop"
                )
            if self._telegram is not None:
                tasks[asyncio.ensure_future(self._telegram.ask(message, delivery, ttl_s))] = (
                    "telegram"
                )

        async def _inbox_wait() -> str | None:
            item = await self._inbox.wait_resolution(message.id, ttl_s)
            return item.resolution if item is not None and item.status == "resolved" else None

        tasks[asyncio.ensure_future(_inbox_wait())] = "inbox"

        action_id: str | None = None
        channel: str | None = None
        desktop_dismissed = False
        pending = set(tasks)
        loop = asyncio.get_running_loop()
        end = loop.time() + ttl_s
        try:
            while pending and action_id is None:
                remaining = end - loop.time()
                if remaining <= 0:
                    break
                done, pending = await asyncio.wait(
                    pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                )
                if not done:
                    break
                for task in done:
                    name = tasks[task]
                    try:
                        result = task.result()
                    except Exception as exc:  # canal nunca derruba a aprovação
                        logger.warning("canal %s falhou: %s", name, type(exc).__name__)
                        result = None
                    if result is None:
                        if name == "desktop":
                            desktop_dismissed = True
                    elif action_id is None:
                        action_id, channel = result, name
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        if channel == "inbox":
            won = self._inbox.get(message.id)
            channel = (won.resolved_by if won is not None else None) or "inbox"

        if action_id is None:
            self._inbox.expire(message.id)
            item = self._inbox.get(message.id)
            if item is not None and item.status == "resolved" and item.resolution:
                action_id, channel = item.resolution, item.resolved_by
        elif channel != "inbox" and not self._inbox.resolve(message.id, action_id, channel or ""):
            item = self._inbox.get(message.id)
            if item is not None and item.status == "resolved" and item.resolution:
                action_id, channel = item.resolution, item.resolved_by
            else:
                action_id, channel = None, None

        if action_id is None:
            signal: FeedbackSignal = "dismissed" if desktop_dismissed else "expired"
            self._feedback(message, signal, "desktop" if desktop_dismissed else None, delivery)
            return ApprovalResult(
                approved=False, action_id=None, channel=None, reason="TTL esgotado sem resposta"
            )

        approved = action_id == "approve"
        self._feedback(message, "approved" if approved else "denied", channel, delivery)
        return ApprovalResult(
            approved=approved,
            action_id=action_id,
            channel=channel,
            reason="aprovado" if approved else "negado",
        )

    # ------------------------------------------------------------------- digest

    async def flush_digest(self) -> RouteResult | None:
        held = self._inbox.take_held()
        if not held:
            return None
        bullets = "\n".join(f"- {m.title}" for m in held)
        digest = OutgoingMessage(
            kind="digest",
            title=f"Resumo: {len(held)} itens",
            body=bullets,
            payload={"digest": True},
        )
        return await self.send(digest)
