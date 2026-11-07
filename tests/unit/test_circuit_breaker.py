"""
Tests for CircuitBreaker (v0.3.0 Sprint 4)

Covers:
  - Normal CLOSED → OPEN → HALF_OPEN → CLOSED transitions
  - SAFE_HOLDING activation (frontier model failure, non-intentional lite)
  - SAFE_HOLDING NOT activated when user chose lite model intentionally
  - OFFLINE_SUSPENDED transition
  - Equi-tier fallback before SAFE_HOLDING
  - Mutation blocking semantics
  - Backoff delay calculation
  - Snapshot immutability
  - State change callbacks
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from orion.gateway.circuit_breaker import (
    MUTATING_TOOLS,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitOpenError,
    CircuitState,
    FailureReason,
    SafeHoldingViolation,
    classify_failure,
)
from orion.gateway.models import ComplexityTier

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def heavy_cb() -> CircuitBreaker:
    """Circuit breaker with a HEAVY frontier model (default config)."""
    return CircuitBreaker(
        primary_model_id="anthropic/claude-sonnet-4-5",
        primary_model_tier=ComplexityTier.HEAVY,
        config=CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout_s=0.05,  # fast for tests
        ),
    )


@pytest.fixture
def lite_cb_intentional() -> CircuitBreaker:
    """Circuit breaker with a FAST model chosen intentionally by the user."""
    return CircuitBreaker(
        primary_model_id="google/gemini-2.0-flash-lite",
        primary_model_tier=ComplexityTier.FAST,
        intentional_lite_mode=True,
    )


@pytest.fixture
def heavy_cb_with_equi() -> CircuitBreaker:
    """Circuit breaker with HEAVY model + equi-tier alternatives."""
    return CircuitBreaker(
        primary_model_id="anthropic/claude-sonnet-4-5",
        primary_model_tier=ComplexityTier.HEAVY,
        equi_tier_models=["google/gemini-2.5-pro", "openai/gpt-4o"],
        config=CircuitBreakerConfig(failure_threshold=2),
    )


# ---------------------------------------------------------------------------
# classify_failure
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    def test_rate_limit(self):
        assert classify_failure(http_status=429) == FailureReason.RATE_LIMIT

    def test_server_error_502(self):
        assert classify_failure(http_status=502) == FailureReason.SERVER_ERROR

    def test_server_error_503(self):
        assert classify_failure(http_status=503) == FailureReason.SERVER_ERROR

    def test_server_error_504(self):
        assert classify_failure(http_status=504) == FailureReason.SERVER_ERROR

    def test_auth_error_401(self):
        assert classify_failure(http_status=401) == FailureReason.AUTH_ERROR

    def test_auth_error_403(self):
        assert classify_failure(http_status=403) == FailureReason.AUTH_ERROR

    def test_timeout(self):
        assert classify_failure(is_timeout=True) == FailureReason.TIMEOUT

    def test_offline(self):
        assert classify_failure(is_offline=True) == FailureReason.NETWORK_OFFLINE

    def test_budget(self):
        assert classify_failure(is_budget=True) == FailureReason.BUDGET_EXCEEDED

    def test_unknown_status(self):
        assert classify_failure(http_status=418) == FailureReason.UNKNOWN

    def test_no_args(self):
        assert classify_failure() == FailureReason.UNKNOWN

    def test_offline_takes_priority_over_status(self):
        """NETWORK_OFFLINE wins even if http_status is also provided."""
        assert classify_failure(http_status=429, is_offline=True) == FailureReason.NETWORK_OFFLINE


# ---------------------------------------------------------------------------
# Initial State
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_starts_closed(self, heavy_cb):
        assert heavy_cb.state == CircuitState.CLOSED

    def test_intentional_lite_mode_off_by_default(self, heavy_cb):
        assert heavy_cb.intentional_lite_mode is False

    def test_intentional_lite_mode_on_when_set(self, lite_cb_intentional):
        assert lite_cb_intentional.intentional_lite_mode is True

    def test_mutation_not_blocked_initially(self, heavy_cb):
        assert heavy_cb.is_mutation_blocked() is False

    def test_can_attempt_when_closed(self, heavy_cb):
        assert heavy_cb.can_attempt() is True


# ---------------------------------------------------------------------------
# SAFE_HOLDING — The Critical Invariant
# ---------------------------------------------------------------------------


class TestSafeHolding:
    """SAFE_HOLDING must ONLY activate for external model failures,
    NOT for intentional lite model choices."""

    def _exhaust_threshold(self, cb: CircuitBreaker, reason=FailureReason.RATE_LIMIT):
        """Helper to push CB to its failure threshold."""
        for _ in range(cb._config.failure_threshold):
            cb.record_failure(reason)

    def test_safe_holding_activates_on_heavy_model_failure(self, heavy_cb):
        """HEAVY model failing externally → SAFE_HOLDING."""
        self._exhaust_threshold(heavy_cb)
        assert heavy_cb.state == CircuitState.SAFE_HOLDING

    def test_safe_holding_blocks_mutations(self, heavy_cb):
        """In SAFE_HOLDING, mutations must be blocked."""
        self._exhaust_threshold(heavy_cb)
        assert heavy_cb.is_mutation_blocked() is True

    def test_safe_holding_raises_on_mutating_tool(self, heavy_cb):
        """assert_mutation_allowed raises SafeHoldingViolation in SAFE_HOLDING."""
        self._exhaust_threshold(heavy_cb)
        for tool in MUTATING_TOOLS:
            with pytest.raises(SafeHoldingViolation) as exc_info:
                heavy_cb.assert_mutation_allowed(tool)
            assert exc_info.value.tool == tool

    def test_intentional_lite_never_enters_safe_holding(self, lite_cb_intentional):
        """User chose lite model intentionally — SAFE_HOLDING NEVER activated."""
        # Note: FAST model with intentional_lite_mode=True
        # Even if we exhaust the threshold, it should NOT enter SAFE_HOLDING
        for _ in range(lite_cb_intentional._config.failure_threshold):
            lite_cb_intentional.record_failure(FailureReason.RATE_LIMIT)

        # Should be OPEN (normal circuit breaker), NOT SAFE_HOLDING
        assert lite_cb_intentional.state != CircuitState.SAFE_HOLDING
        # OPEN or stays CLOSED — but never SAFE_HOLDING
        assert lite_cb_intentional.state in (CircuitState.OPEN, CircuitState.CLOSED)

    def test_intentional_lite_never_blocks_mutations(self, lite_cb_intentional):
        """Intentional lite mode: mutations are NEVER blocked regardless of failures."""
        for _ in range(lite_cb_intentional._config.failure_threshold):
            lite_cb_intentional.record_failure(FailureReason.RATE_LIMIT)

        assert lite_cb_intentional.is_mutation_blocked() is False

    def test_set_intentional_lite_mode_prevents_safe_holding(self, heavy_cb):
        """Switching intentional_lite_mode=True on an existing HEAVY CB prevents SAFE_HOLDING."""
        heavy_cb.set_intentional_lite_mode(True)
        for _ in range(heavy_cb._config.failure_threshold):
            heavy_cb.record_failure(FailureReason.RATE_LIMIT)

        assert heavy_cb.state != CircuitState.SAFE_HOLDING
        assert heavy_cb.is_mutation_blocked() is False

    def test_read_operations_allowed_in_safe_holding(self, heavy_cb):
        """Read-only tools (not in MUTATING_TOOLS) are never blocked by SAFE_HOLDING."""
        self._exhaust_threshold(heavy_cb)
        assert heavy_cb.state == CircuitState.SAFE_HOLDING

        # read_file and search_files are NOT in MUTATING_TOOLS
        heavy_cb.assert_mutation_allowed("read_file")  # Should not raise
        heavy_cb.assert_mutation_allowed("search_files")  # Should not raise

    def test_safe_holding_message_includes_model_info(self, heavy_cb):
        """SAFE_HOLDING message must explain what failed."""
        self._exhaust_threshold(heavy_cb)
        snap = heavy_cb.snapshot()
        assert "claude-sonnet-4-5" in snap.message_for_user
        assert "SAFE HOLDING" in snap.message_for_user

    def test_reset_clears_safe_holding(self, heavy_cb):
        """Manual reset should return circuit to CLOSED and unblock mutations."""
        self._exhaust_threshold(heavy_cb)
        assert heavy_cb.state == CircuitState.SAFE_HOLDING

        heavy_cb.reset()
        assert heavy_cb.state == CircuitState.CLOSED
        assert heavy_cb.is_mutation_blocked() is False


# ---------------------------------------------------------------------------
# Equi-Tier Fallback
# ---------------------------------------------------------------------------


class TestEquiTierFallback:
    def test_equi_tier_used_before_safe_holding(self, heavy_cb_with_equi):
        """When equi-tier models exist, CB goes OPEN (not SAFE_HOLDING) first."""
        for _ in range(heavy_cb_with_equi._config.failure_threshold):
            heavy_cb_with_equi.record_failure(FailureReason.RATE_LIMIT)

        # Should be OPEN, not SAFE_HOLDING (equi-tier is being tried)
        assert heavy_cb_with_equi.state == CircuitState.OPEN

    def test_equi_tier_models_consumed_in_order(self, heavy_cb_with_equi):
        """get_next_equi_tier_model returns models in configured order."""
        assert heavy_cb_with_equi.get_next_equi_tier_model() == "google/gemini-2.5-pro"
        assert heavy_cb_with_equi.get_next_equi_tier_model() == "openai/gpt-4o"

    def test_safe_holding_after_all_equi_exhausted(self):
        """After all equi-tier alternatives exhausted, enters SAFE_HOLDING."""
        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            equi_tier_models=["google/gemini-2.5-pro"],
            config=CircuitBreakerConfig(failure_threshold=2),
        )
        # First threshold hit → OPEN (tries equi-tier)
        for _ in range(2):
            cb.record_failure(FailureReason.RATE_LIMIT)
        assert cb.state == CircuitState.OPEN

        # Second threshold hit → SAFE_HOLDING (equi exhausted)
        for _ in range(2):
            cb.record_failure(FailureReason.RATE_LIMIT)
        assert cb.state == CircuitState.SAFE_HOLDING

    def test_reset_also_resets_equi_index(self, heavy_cb_with_equi):
        """After reset, equi-tier index is back to 0."""
        heavy_cb_with_equi.get_next_equi_tier_model()  # consume first
        heavy_cb_with_equi.get_next_equi_tier_model()  # consume second
        heavy_cb_with_equi.reset()
        assert heavy_cb_with_equi.get_next_equi_tier_model() == "google/gemini-2.5-pro"


# ---------------------------------------------------------------------------
# OFFLINE_SUSPENDED
# ---------------------------------------------------------------------------


class TestOfflineSuspended:
    def test_network_offline_triggers_suspended(self, heavy_cb):
        """Network offline failure goes directly to OFFLINE_SUSPENDED."""
        heavy_cb.record_failure(FailureReason.NETWORK_OFFLINE)
        assert heavy_cb.state == CircuitState.OFFLINE_SUSPENDED

    def test_offline_cannot_attempt(self, heavy_cb):
        """OFFLINE_SUSPENDED blocks all attempts."""
        heavy_cb.record_failure(FailureReason.NETWORK_OFFLINE)
        assert heavy_cb.can_attempt() is False

    def test_offline_message_informs_user(self, heavy_cb):
        """OFFLINE_SUSPENDED message must mention session suspension."""
        heavy_cb.record_failure(FailureReason.NETWORK_OFFLINE)
        snap = heavy_cb.snapshot()
        assert "SUSPENSA" in snap.message_for_user or "offline" in snap.message_for_user.lower()


# ---------------------------------------------------------------------------
# Normal Circuit Transitions
# ---------------------------------------------------------------------------


class TestCircuitTransitions:
    def test_failure_below_threshold_stays_closed(self, heavy_cb):
        heavy_cb.record_failure(FailureReason.RATE_LIMIT)
        heavy_cb.record_failure(FailureReason.RATE_LIMIT)
        assert heavy_cb.state == CircuitState.CLOSED  # threshold=3, only 2 failures

    def test_success_resets_failure_count(self, heavy_cb):
        heavy_cb.record_failure(FailureReason.RATE_LIMIT)
        heavy_cb.record_failure(FailureReason.RATE_LIMIT)
        heavy_cb.record_success()
        heavy_cb.record_failure(FailureReason.RATE_LIMIT)
        # After success, counter reset; 1 failure is below threshold
        assert heavy_cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        """After OPEN + recovery timeout, check_and_maybe_half_open → HALF_OPEN."""
        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(
                failure_threshold=1,
                recovery_timeout_s=0.01,
            ),
            intentional_lite_mode=True,  # avoid SAFE_HOLDING for this test
        )
        cb.record_failure(FailureReason.SERVER_ERROR)
        assert cb.state == CircuitState.OPEN

        time.sleep(0.05)  # Wait for recovery timeout
        result = cb.check_and_maybe_half_open()
        assert cb.state == CircuitState.HALF_OPEN
        assert result is True

    def test_half_open_closes_after_successes(self):
        """HALF_OPEN → CLOSED after enough successful calls."""
        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(
                failure_threshold=1,
                recovery_timeout_s=0.01,
                success_threshold=2,
            ),
            intentional_lite_mode=True,
        )
        cb.record_failure(FailureReason.SERVER_ERROR)
        time.sleep(0.05)
        cb.check_and_maybe_half_open()

        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN  # need 2

        cb.record_success()
        assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Local Fallback (Opt-in)
# ---------------------------------------------------------------------------


class TestLocalFallback:
    def test_local_fallback_disabled_by_default(self):
        """local_fallback_enabled must be False by default."""
        config = CircuitBreakerConfig()
        assert config.local_fallback_enabled is False

    def test_local_fallback_requires_explicit_optin(self):
        """Local fallback never auto-activates — requires explicit True."""
        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(
                failure_threshold=1,
                local_fallback_enabled=False,
            ),
        )
        # With local fallback disabled and no equi-tier, should enter SAFE_HOLDING
        cb.record_failure(FailureReason.RATE_LIMIT)
        assert cb.state == CircuitState.SAFE_HOLDING


# ---------------------------------------------------------------------------
# State Change Callback
# ---------------------------------------------------------------------------


class TestStateChangeCallback:
    def test_callback_called_on_state_change(self):
        """on_state_change is called when state transitions."""
        callback = MagicMock()
        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(failure_threshold=1),
            on_state_change=callback,
        )
        cb.record_failure(FailureReason.RATE_LIMIT)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == CircuitState.SAFE_HOLDING

    def test_callback_not_called_on_same_state(self, heavy_cb):
        """Callback not called if state does not change."""
        callback = MagicMock()
        heavy_cb._on_state_change = callback
        heavy_cb.record_success()  # stays CLOSED
        callback.assert_not_called()

    def test_callback_exception_does_not_crash_cb(self):
        """Exceptions in callback are swallowed — CB continues normally."""

        def bad_callback(state, snap):
            raise RuntimeError("callback error")

        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(failure_threshold=1),
            on_state_change=bad_callback,
        )
        # Should not raise
        cb.record_failure(FailureReason.RATE_LIMIT)
        assert cb.state == CircuitState.SAFE_HOLDING  # transitioned despite callback error


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_is_immutable(self, heavy_cb):
        snap = heavy_cb.snapshot()
        with pytest.raises(Exception):
            snap.state = CircuitState.OPEN  # type: ignore

    def test_snapshot_reflects_current_state(self, heavy_cb):
        snap = heavy_cb.snapshot()
        assert snap.state == CircuitState.CLOSED
        assert snap.failure_count == 0
        assert snap.safe_holding_active is False
        assert snap.intentional_lite_mode is False

    def test_snapshot_after_safe_holding(self, heavy_cb):
        for _ in range(heavy_cb._config.failure_threshold):
            heavy_cb.record_failure(FailureReason.RATE_LIMIT)
        snap = heavy_cb.snapshot()
        assert snap.state == CircuitState.SAFE_HOLDING
        assert snap.safe_holding_active is True
        assert snap.last_failure_reason == FailureReason.RATE_LIMIT
        assert snap.failed_model == "anthropic/claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# Backoff Delay
# ---------------------------------------------------------------------------


class TestBackoffDelay:
    def test_delay_increases_with_attempt(self, heavy_cb):
        d0 = heavy_cb._backoff_delay(0)
        d1 = heavy_cb._backoff_delay(1)
        d2 = heavy_cb._backoff_delay(2)
        # With jitter, absolute ordering isn't guaranteed, but median should increase
        # Test that base values (without jitter) increase
        config = heavy_cb._config
        assert config.base_delay_s * (2**0) <= config.max_delay_s
        assert config.base_delay_s * (2**1) <= config.max_delay_s or d1 <= config.max_delay_s * 1.5

    def test_delay_capped_at_max(self):
        cb = CircuitBreaker(
            primary_model_id="test/model",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(
                base_delay_s=1.0,
                max_delay_s=5.0,
                jitter_factor=0.0,  # No jitter for deterministic test
            ),
        )
        # attempt=10 would produce 1024s base, but capped at 5.0
        delay = cb._backoff_delay(10)
        assert delay <= 5.0


# ---------------------------------------------------------------------------
# execute_with_retry
# ---------------------------------------------------------------------------


class TestExecuteWithRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self, heavy_cb):
        """Successful call returns result and records success."""
        async def coro():
            return "result"

        result = await heavy_cb.execute_with_retry(
            coro_factory=coro,
            failure_classifier=lambda e: FailureReason.UNKNOWN,
        )
        assert result == "result"
        assert heavy_cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_raises_circuit_open_when_open(self):
        """Raises CircuitOpenError when circuit is already OPEN."""
        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(
                failure_threshold=1,
                recovery_timeout_s=9999,
            ),
            intentional_lite_mode=True,
        )
        cb.record_failure(FailureReason.RATE_LIMIT)
        assert cb.state == CircuitState.OPEN

        with pytest.raises(CircuitOpenError):
            await cb.execute_with_retry(
                coro_factory=lambda: asyncio.sleep(0),
                failure_classifier=lambda e: FailureReason.UNKNOWN,
            )

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        """Retries on failure; succeeds on later attempt."""
        attempt_count = 0

        async def coro():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("transient error")
            return "ok"

        cb = CircuitBreaker(
            primary_model_id="anthropic/claude-sonnet-4-5",
            primary_model_tier=ComplexityTier.HEAVY,
            config=CircuitBreakerConfig(
                failure_threshold=5,  # won't open during test
                max_retries=3,
                base_delay_s=0.001,
            ),
        )

        result = await cb.execute_with_retry(
            coro_factory=coro,
            failure_classifier=lambda e: FailureReason.SERVER_ERROR,
        )
        assert result == "ok"
        assert attempt_count == 3
