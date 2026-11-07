"""
Tests — TelegramHITLConnector (Sprint 3, v0.2.0)

Validates (using MockTelegramHITLConnector — no real network calls):
  - TEST 5 (spec): Inactivity simulation dispatches payload with approved/rejected callback
  - Auto-approval and auto-rejection flows
  - Timeout simulation
  - Unauthorized chat_id is rejected
  - HITLRequest and HITLDecision data contracts

The real TelegramHITLConnector is tested for import-error behaviour when
python-telegram-bot is absent.
"""

from __future__ import annotations

import asyncio

import pytest

from orion.memory.hitl_telegram import (
    HITLDecision,
    HITLRequest,
    HITLTimeoutError,
    MockTelegramHITLConnector,
    TelegramHITLConnector,
)

# ---------------------------------------------------------------------------
# HITLRequest & HITLDecision contracts
# ---------------------------------------------------------------------------


class TestHITLRequestModel:
    def test_request_has_request_id(self):
        req = HITLRequest(
            action_description="rm -rf /tmp/old",
            risk_level="LEVEL_3",
            chat_id=99999,
        )
        assert req.request_id is not None
        assert len(req.request_id) > 0

    def test_request_default_ttl(self):
        req = HITLRequest(
            action_description="chmod 777 /etc/passwd",
            risk_level="LEVEL_2",
            chat_id=12345,
        )
        assert req.ttl_seconds == 600

    def test_custom_ttl(self):
        req = HITLRequest(
            action_description="deploy to prod",
            risk_level="LEVEL_3",
            chat_id=12345,
            ttl_seconds=120,
        )
        assert req.ttl_seconds == 120


class TestHITLDecisionModel:
    def test_decision_approved(self):
        d = HITLDecision(request_id="req-1", approved=True, responder_chat_id=99)
        assert d.approved is True
        assert d.timed_out is False

    def test_decision_rejected(self):
        d = HITLDecision(request_id="req-2", approved=False)
        assert d.approved is False


# ---------------------------------------------------------------------------
# MockTelegramHITLConnector
# ---------------------------------------------------------------------------


class TestMockConnectorApproval:
    """TEST 5 (spec): Inactivity sim → approval dispatched & received."""

    @pytest.mark.asyncio
    async def test_auto_approve(self):
        mock = MockTelegramHITLConnector(auto_approve=True, authorized_chat_id=12345)
        req = HITLRequest(
            action_description="kubectl delete pod cache-0",
            risk_level="LEVEL_3",
            chat_id=12345,
        )
        decision = await mock.request_approval(req)

        assert decision.approved is True
        assert decision.request_id == req.request_id
        assert decision.responder_chat_id == 12345

    @pytest.mark.asyncio
    async def test_auto_reject(self):
        mock = MockTelegramHITLConnector(auto_approve=False, authorized_chat_id=12345)
        req = HITLRequest(
            action_description="DROP TABLE users;",
            risk_level="LEVEL_3",
            chat_id=12345,
        )
        decision = await mock.request_approval(req)

        assert decision.approved is False

    @pytest.mark.asyncio
    async def test_request_is_recorded(self):
        mock = MockTelegramHITLConnector(auto_approve=True)
        req = HITLRequest(
            action_description="reboot server",
            risk_level="LEVEL_2",
            chat_id=99,
        )
        await mock.request_approval(req)

        assert len(mock.dispatched_requests) == 1
        assert mock.dispatched_requests[0].action_description == "reboot server"

    @pytest.mark.asyncio
    async def test_multiple_requests_recorded(self):
        mock = MockTelegramHITLConnector(auto_approve=True)
        for i in range(3):
            req = HITLRequest(
                action_description=f"action_{i}",
                risk_level="LEVEL_2",
                chat_id=99,
            )
            await mock.request_approval(req)

        assert len(mock.dispatched_requests) == 3


class TestMockConnectorTimeout:
    @pytest.mark.asyncio
    async def test_simulate_timeout_raises(self):
        mock = MockTelegramHITLConnector(simulate_timeout=True)
        req = HITLRequest(
            action_description="long operation",
            risk_level="LEVEL_3",
            chat_id=12345,
            ttl_seconds=10,
        )
        with pytest.raises(HITLTimeoutError) as exc_info:
            await mock.request_approval(req)

        assert exc_info.value.request_id == req.request_id
        assert exc_info.value.ttl == 10

    @pytest.mark.asyncio
    async def test_timeout_error_message(self):
        mock = MockTelegramHITLConnector(simulate_timeout=True)
        req = HITLRequest(
            action_description="any",
            risk_level="LEVEL_2",
            chat_id=99,
        )
        with pytest.raises(HITLTimeoutError) as exc_info:
            await mock.request_approval(req)

        error_msg = str(exc_info.value)
        assert "timed out" in error_msg.lower()


# ---------------------------------------------------------------------------
# TelegramHITLConnector — handle_callback security
# ---------------------------------------------------------------------------


class TestCallbackSecurity:
    """Unauthorized chat_ids must be silently rejected."""

    @pytest.mark.asyncio
    async def test_unauthorized_chat_id_ignored(self):
        connector = TelegramHITLConnector(
            bot_token="fake-token",
            authorized_chat_id=12345,
        )
        # Inject a fake pending event
        fake_event = asyncio.Event()
        connector._pending["req-xyz"] = fake_event
        connector._decisions["req-xyz"] = False  # not set yet

        # Callback from unauthorized chat_id 99999
        await connector.handle_callback("req-xyz", chat_id=99999, approved=True)

        # Event must NOT be set (unauthorized callback was dropped)
        assert not fake_event.is_set()
        # Decision must not be recorded as approved
        assert connector._decisions.get("req-xyz") is False

    @pytest.mark.asyncio
    async def test_authorized_chat_id_accepted(self):
        connector = TelegramHITLConnector(
            bot_token="fake-token",
            authorized_chat_id=12345,
        )
        fake_event = asyncio.Event()
        connector._pending["req-abc"] = fake_event

        await connector.handle_callback("req-abc", chat_id=12345, approved=True)

        assert fake_event.is_set()
        assert connector._decisions.get("req-abc") is True

    @pytest.mark.asyncio
    async def test_unknown_request_id_ignored(self):
        connector = TelegramHITLConnector(
            bot_token="fake-token",
            authorized_chat_id=12345,
        )
        # No pending request with this ID
        await connector.handle_callback("nonexistent-id", chat_id=12345, approved=True)
        # No error raised — silently ignored


# ---------------------------------------------------------------------------
# TelegramHITLConnector — import error when library absent
# ---------------------------------------------------------------------------


class TestImportGuard:
    @pytest.mark.asyncio
    async def test_raises_import_error_without_telegram(self, monkeypatch):
        """If python-telegram-bot is absent, request_approval raises ImportError."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "telegram":
                raise ImportError("No module named 'telegram'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        connector = TelegramHITLConnector(
            bot_token="fake",
            authorized_chat_id=12345,
        )
        req = HITLRequest(
            action_description="test action",
            risk_level="LEVEL_2",
            chat_id=12345,
        )
        with pytest.raises(ImportError, match="orion-agent\\[telegram\\]"):
            await connector.request_approval(req)
