"""
O.R.I.O.N — Async In-Process EventBus
Pub/Sub broadcast with circular history buffer and typed handlers.

Design: Fully decoupled. Publishers call `publish()` without knowing who listens.
Subscribers register handlers per event type. History is maintained in a bounded
deque to allow post-hoc inspection without memory growth.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from orion.core.events import OrionEvent

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

T = TypeVar("T", bound=OrionEvent)
AsyncHandler = Callable[[Any], Coroutine[Any, Any, None]]

# ---------------------------------------------------------------------------
# EventBus
# ---------------------------------------------------------------------------

_DEFAULT_HISTORY_SIZE = 1_000


class EventBus:
    """Asynchronous in-process pub/sub event bus.

    Usage:
        bus = EventBus()

        @bus.subscribe(Action)
        async def on_action(event: Action) -> None:
            print(event.tool)

        await bus.publish(Action(tool="read_file", params={"path": "/tmp/x"}))
    """

    def __init__(self, history_size: int = _DEFAULT_HISTORY_SIZE) -> None:
        self._handlers: dict[type[OrionEvent], list[AsyncHandler]] = {}
        self._history: deque[OrionEvent] = deque(maxlen=history_size)
        self._history_size = history_size
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(
        self, event_type: type[T]
    ) -> Callable[[AsyncHandler], AsyncHandler]:
        """Decorator to register an async handler for an event type."""

        def decorator(handler: AsyncHandler) -> AsyncHandler:
            self._handlers.setdefault(event_type, []).append(handler)
            logger.debug(
                "EventBus: subscribed %s to %s",
                handler.__qualname__,
                event_type.__name__,
            )
            return handler

        return decorator

    def subscribe_handler(self, event_type: type[T], handler: AsyncHandler) -> None:
        """Imperatively register an async handler for an event type."""
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug(
            "EventBus: subscribed %s to %s",
            handler.__qualname__,
            event_type.__name__,
        )

    def unsubscribe(self, event_type: type[T], handler: AsyncHandler) -> None:
        """Remove a previously registered handler."""
        handlers = self._handlers.get(event_type, [])
        try:
            handlers.remove(handler)
        except ValueError:
            pass  # Idempotent: no error if handler not found

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: OrionEvent) -> None:
        """Broadcast *event* to all subscribers of its type.

        The event is appended to the history buffer first, then handlers
        are awaited sequentially (fan-out without parallelism to preserve
        ordering guarantees for the ReAct loop).
        """
        async with self._lock:
            self._history.append(event)

        event_type = type(event)
        handlers = self._handlers.get(event_type, [])

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "EventBus: unhandled exception in handler %s for event %s",
                    handler.__qualname__,
                    event_type.__name__,
                )

    # ------------------------------------------------------------------
    # History / Introspection
    # ------------------------------------------------------------------

    def history(self) -> list[OrionEvent]:
        """Return a snapshot of the full event history (oldest first)."""
        return list(self._history)

    def history_of(self, event_type: type[T]) -> list[T]:
        """Return only events of a specific type from history."""
        return [e for e in self._history if isinstance(e, event_type)]

    def clear_history(self) -> None:
        """Wipe the event history buffer."""
        self._history.clear()

    @property
    def history_size(self) -> int:
        return self._history_size

    def __repr__(self) -> str:
        return (
            f"EventBus(subscriptions={len(self._handlers)}, "
            f"history={len(self._history)}/{self._history_size})"
        )
