"""
O.R.I.O.N — Remote HITL Connector via Telegram Bot (Sprint 3, v0.2.0)

Out-of-Band Escalation for PEP Level 2/3 approvals when the developer is
away from the terminal (inactivity > 180s).

Flow:
  1. Agent detects PEP LEVEL_2/LEVEL_3 action with no local terminal input
     for ``inactivity_timeout_seconds`` (default: 180).
  2. TelegramHITLConnector dispatches an approval request to the developer's
     Telegram chat via Bot API.
  3. Developer taps [Aprovar] or [Rejeitar] on mobile.
  4. Connector polls for the callback (with TTL of 10 minutes) and returns
     HITLDecision(approved=True/False).

Security:
  - Strict ``chat_id`` verification: callbacks from unknown chats are ignored.
  - TTL enforcement: callbacks arriving after 10 minutes are treated as REJECTED.
  - Bot token is read from the environment variable ORION_TELEGRAM_BOT_TOKEN.

Optional dependency:
  This module requires ``python-telegram-bot>=21.0`` (optional group).
  If the library is not installed, TelegramHITLConnector raises ImportError
  with a helpful installation message.

ADR-016: Remote HITL via Telegram
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 600       # 10 minutes
_POLL_INTERVAL_SECONDS = 2.0     # Check for callback every 2 seconds
_ENV_BOT_TOKEN = "ORION_TELEGRAM_BOT_TOKEN"


@dataclass
class HITLRequest:
    """Describes a PEP action requiring out-of-band human approval."""

    action_description: str
    risk_level: str           # "LEVEL_2" | "LEVEL_3"
    chat_id: int
    ttl_seconds: int = _DEFAULT_TTL_SECONDS
    # Internal state
    request_id: str = field(default_factory=lambda: str(int(time.time())))
    dispatched_at: float = field(default_factory=time.monotonic)


@dataclass
class HITLDecision:
    """Outcome of a remote HITL approval request."""

    request_id: str
    approved: bool
    responded_at: float = field(default_factory=time.monotonic)
    timed_out: bool = False
    responder_chat_id: int | None = None


class HITLTimeoutError(Exception):
    """Raised when no decision is received within the TTL window."""

    def __init__(self, request_id: str, ttl: int) -> None:
        super().__init__(
            f"HITL request '{request_id}' timed out after {ttl}s with no response."
        )
        self.request_id = request_id
        self.ttl = ttl


class TelegramHITLConnector:
    """
    Out-of-Band PEP approval connector via Telegram Bot.

    Requires the ``telegram`` optional dependency:
        pip install "orion-agent[telegram]"

    Usage::

        connector = TelegramHITLConnector(bot_token="...", authorized_chat_id=123456)
        decision = await connector.request_approval(
            HITLRequest(
                action_description="rm -rf /var/log/old_data",
                risk_level="LEVEL_3",
                chat_id=123456,
            )
        )
        if decision.approved:
            # proceed
        else:
            # abort

    For unit testing without Telegram connectivity, use MockTelegramHITLConnector.
    """

    def __init__(
        self,
        *,
        bot_token: str | None = None,
        authorized_chat_id: int,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._bot_token = bot_token or os.environ.get(_ENV_BOT_TOKEN, "")
        self._authorized_chat_id = authorized_chat_id
        self._ttl_seconds = ttl_seconds
        self._pending: dict[str, asyncio.Event] = {}
        self._decisions: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def request_approval(self, request: HITLRequest) -> HITLDecision:
        """
        Dispatch an approval request to the developer's Telegram chat.

        Sends a message with [Aprovar] / [Rejeitar] inline keyboard buttons
        and polls for the callback within the TTL window.

        Args:
            request: HITLRequest describing the action needing approval.

        Returns:
            HITLDecision with approved=True/False.

        Raises:
            HITLTimeoutError: If no response arrives within TTL.
            ImportError: If python-telegram-bot is not installed.
        """
        self._require_telegram()

        if not self._bot_token:
            raise ValueError(
                f"Telegram bot token not set. "
                f"Set the environment variable {_ENV_BOT_TOKEN} or pass bot_token=."
            )

        event = asyncio.Event()
        self._pending[request.request_id] = event

        try:
            await self._send_approval_message(request)
            decision_approved = await self._await_callback(request, event)
            return HITLDecision(
                request_id=request.request_id,
                approved=decision_approved,
                responder_chat_id=self._authorized_chat_id,
            )
        finally:
            self._pending.pop(request.request_id, None)
            self._decisions.pop(request.request_id, None)

    async def handle_callback(self, request_id: str, chat_id: int, approved: bool) -> None:
        """
        Receive and record a callback from the Telegram webhook/polling loop.

        Security: callbacks from unauthorized chat_ids are silently dropped.

        Args:
            request_id: Matches HITLRequest.request_id.
            chat_id:    The Telegram chat_id of the responder.
            approved:   True if [Aprovar] was tapped, False for [Rejeitar].
        """
        if chat_id != self._authorized_chat_id:
            logger.warning(
                "HITL callback from unauthorized chat_id %d ignored "
                "(expected %d).",
                chat_id,
                self._authorized_chat_id,
            )
            return

        if request_id not in self._pending:
            logger.warning("HITL callback for unknown request_id '%s' ignored.", request_id)
            return

        self._decisions[request_id] = approved
        self._pending[request_id].set()
        logger.info(
            "HITL callback received: request_id='%s' approved=%s chat_id=%d",
            request_id,
            approved,
            chat_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send_approval_message(self, request: HITLRequest) -> None:
        """Send the approval request message with inline keyboard."""
        from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

        bot = Bot(token=self._bot_token)
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✔ Aprovar",
                    callback_data=f"hitl:approve:{request.request_id}",
                ),
                InlineKeyboardButton(
                    "✖ Rejeitar",
                    callback_data=f"hitl:reject:{request.request_id}",
                ),
            ]
        ])
        text = (
            f"! *O.R.I.O.N — Aprovação PEP {request.risk_level} Necessária*\n\n"
            f"Ação: `{request.action_description}`\n\n"
            f"ID: `{request.request_id}`\n"
            f"TTL: {request.ttl_seconds // 60} minutos"
        )
        await bot.send_message(
            chat_id=request.chat_id,
            text=text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        logger.info(
            "HITL approval request dispatched to chat_id=%d (request_id='%s').",
            request.chat_id,
            request.request_id,
        )

    async def _await_callback(self, request: HITLRequest, event: asyncio.Event) -> bool:
        """
        Wait for the approval event, respecting TTL.

        Returns:
            True if approved, False if rejected.

        Raises:
            HITLTimeoutError: If TTL expires without a decision.
        """
        ttl = self._ttl_seconds
        try:
            await asyncio.wait_for(event.wait(), timeout=float(ttl))
        except TimeoutError:
            raise HITLTimeoutError(request.request_id, ttl)

        return self._decisions.get(request.request_id, False)

    @staticmethod
    def _require_telegram() -> None:
        """Raise ImportError with helpful message if python-telegram-bot is absent."""
        try:
            import telegram  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The Telegram HITL connector requires python-telegram-bot>=21.0.\n"
                "Install it with: pip install 'orion-agent[telegram]'"
            ) from exc


# ---------------------------------------------------------------------------
# Test-friendly mock — no real network calls
# ---------------------------------------------------------------------------


class MockTelegramHITLConnector:
    """
    In-memory mock for TelegramHITLConnector, suitable for unit testing.

    Simulates approval or rejection without real network calls.

    Usage::

        mock = MockTelegramHITLConnector(auto_approve=True)
        decision = await mock.request_approval(request)
        assert decision.approved is True
    """

    def __init__(
        self,
        *,
        auto_approve: bool = True,
        auto_delay_seconds: float = 0.0,
        authorized_chat_id: int = 12345,
        simulate_timeout: bool = False,
    ) -> None:
        self.auto_approve = auto_approve
        self.auto_delay_seconds = auto_delay_seconds
        self.authorized_chat_id = authorized_chat_id
        self.simulate_timeout = simulate_timeout
        self.dispatched_requests: list[HITLRequest] = []

    async def request_approval(self, request: HITLRequest) -> HITLDecision:
        """Simulate an approval/rejection without network I/O."""
        self.dispatched_requests.append(request)

        if self.simulate_timeout:
            raise HITLTimeoutError(request.request_id, request.ttl_seconds)

        if self.auto_delay_seconds > 0:
            await asyncio.sleep(self.auto_delay_seconds)

        return HITLDecision(
            request_id=request.request_id,
            approved=self.auto_approve,
            responder_chat_id=self.authorized_chat_id,
        )
