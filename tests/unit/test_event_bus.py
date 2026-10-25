"""
Unit tests for src/orion/core/event_bus.py
"""

from __future__ import annotations

import asyncio

import pytest

from orion.core.event_bus import EventBus
from orion.core.events import Action, FinalAnswer, Observation, RiskLevel, TurnStarted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_action(tool: str = "read_file", turn: int = 0) -> Action:
    return Action(tool=tool, params={"path": "/tmp/test"}, turn_index=turn)


def make_observation(action_id: str, success: bool = True) -> Observation:
    return Observation(action_id=action_id, success=success, output="ok")


# ---------------------------------------------------------------------------
# Basic pub/sub
# ---------------------------------------------------------------------------


class TestEventBusPubSub:
    async def test_handler_called_on_publish(self) -> None:
        bus = EventBus()
        received: list[Action] = []

        @bus.subscribe(Action)
        async def handler(event: Action) -> None:
            received.append(event)

        action = make_action()
        await bus.publish(action)
        assert len(received) == 1
        assert received[0] is action

    async def test_multiple_handlers_same_type(self) -> None:
        bus = EventBus()
        log: list[str] = []

        @bus.subscribe(Action)
        async def h1(e: Action) -> None:
            log.append("h1")

        @bus.subscribe(Action)
        async def h2(e: Action) -> None:
            log.append("h2")

        await bus.publish(make_action())
        assert log == ["h1", "h2"]

    async def test_handler_not_called_for_wrong_type(self) -> None:
        bus = EventBus()
        called = False

        @bus.subscribe(Observation)
        async def handler(e: Observation) -> None:
            nonlocal called
            called = True

        await bus.publish(make_action())  # Action, not Observation
        assert not called

    async def test_subscribe_handler_imperative(self) -> None:
        bus = EventBus()
        received: list[Action] = []

        async def my_handler(e: Action) -> None:
            received.append(e)

        bus.subscribe_handler(Action, my_handler)
        await bus.publish(make_action())
        assert len(received) == 1

    async def test_no_handlers_publish_is_noop(self) -> None:
        bus = EventBus()
        # Should not raise
        await bus.publish(make_action())


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------


class TestEventBusUnsubscribe:
    async def test_unsubscribe_stops_delivery(self) -> None:
        bus = EventBus()
        received: list[Action] = []

        async def handler(e: Action) -> None:
            received.append(e)

        bus.subscribe_handler(Action, handler)
        await bus.publish(make_action())
        assert len(received) == 1

        bus.unsubscribe(Action, handler)
        await bus.publish(make_action())
        assert len(received) == 1  # still 1

    async def test_unsubscribe_nonexistent_is_idempotent(self) -> None:
        bus = EventBus()

        async def handler(e: Action) -> None:
            pass

        bus.unsubscribe(Action, handler)  # Should not raise


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class TestEventBusHistory:
    async def test_history_records_events(self) -> None:
        bus = EventBus()
        a1 = make_action("read_file")
        a2 = make_action("write_file", turn=1)
        await bus.publish(a1)
        await bus.publish(a2)
        hist = bus.history()
        assert len(hist) == 2
        assert hist[0] is a1
        assert hist[1] is a2

    async def test_history_of_filters_by_type(self) -> None:
        bus = EventBus()
        action = make_action()
        obs = make_observation(action.event_id)
        await bus.publish(action)
        await bus.publish(obs)

        assert bus.history_of(Action) == [action]
        assert bus.history_of(Observation) == [obs]

    async def test_history_respects_maxsize(self) -> None:
        bus = EventBus(history_size=3)
        for i in range(5):
            await bus.publish(make_action(turn=i))
        assert len(bus.history()) == 3

    async def test_clear_history(self) -> None:
        bus = EventBus()
        await bus.publish(make_action())
        bus.clear_history()
        assert bus.history() == []

    async def test_history_is_snapshot(self) -> None:
        """history() returns a copy — mutations don't affect internal state."""
        bus = EventBus()
        await bus.publish(make_action())
        snap = bus.history()
        snap.clear()
        assert len(bus.history()) == 1


# ---------------------------------------------------------------------------
# Error isolation
# ---------------------------------------------------------------------------


class TestEventBusErrorIsolation:
    async def test_failing_handler_does_not_crash_bus(self) -> None:
        bus = EventBus()
        called_second = False

        @bus.subscribe(Action)
        async def bad_handler(e: Action) -> None:
            raise RuntimeError("handler exploded")

        @bus.subscribe(Action)
        async def good_handler(e: Action) -> None:
            nonlocal called_second
            called_second = True

        await bus.publish(make_action())
        assert called_second  # second handler still ran


# ---------------------------------------------------------------------------
# Repr
# ---------------------------------------------------------------------------


class TestEventBusRepr:
    def test_repr(self) -> None:
        bus = EventBus()
        r = repr(bus)
        assert "EventBus" in r
