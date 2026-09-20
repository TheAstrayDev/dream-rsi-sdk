"""Event system for Dream-RSI.

Provides typed event emission and callback support.  Callback errors
are logged but never crash the main campaign.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from dreamrsi.models.events import Event, EventType

logger = logging.getLogger("dreamrsi.events")


# Callback type: sync or async callable accepting an Event
EventCallback = Callable[[Event], Any] | Callable[[Event], Awaitable[Any]]


class Callback:
    """Base class for Dream-RSI lifecycle callbacks.

    Override any method you care about.  Exceptions in callbacks
    are caught and logged, never propagated to the main loop.
    """

    async def on_run_start(self, event: Event) -> None:
        pass

    async def on_run_complete(self, event: Event) -> None:
        pass

    async def on_node_created(self, event: Event) -> None:
        pass

    async def on_evaluation(self, event: Event) -> None:
        pass

    async def on_round_end(self, event: Event) -> None:
        pass

    async def on_dream_start(self, event: Event) -> None:
        pass

    async def on_dream_complete(self, event: Event) -> None:
        pass

    async def on_policy_generated(self, event: Event) -> None:
        pass

    async def on_policy_promoted(self, event: Event) -> None:
        pass

    async def on_error(self, event: Event) -> None:
        pass


_CALLBACK_MAP: dict[EventType, str] = {
    EventType.RUN_STARTED: "on_run_start",
    EventType.RUN_COMPLETED: "on_run_complete",
    EventType.NODE_CREATED: "on_node_created",
    EventType.NODE_EVALUATED: "on_evaluation",
    EventType.ROUND_COMPLETED: "on_round_end",
    EventType.DREAM_STARTED: "on_dream_start",
    EventType.DREAM_COMPLETED: "on_dream_complete",
    EventType.POLICY_CREATED: "on_policy_generated",
    EventType.POLICY_PROMOTED: "on_policy_promoted",
    EventType.ERROR: "on_error",
}


class EventEmitter:
    """Central event hub for the Dream-RSI runtime."""

    def __init__(self) -> None:
        self._listeners: list[EventCallback] = []
        self._callbacks: list[Callback] = []

    def on(self, callback: EventCallback) -> None:
        """Register a general event listener."""
        self._listeners.append(callback)

    def add_callback(self, cb: Callback) -> None:
        """Register a structured callback object."""
        self._callbacks.append(cb)

    async def emit(self, event: Event) -> None:
        """Emit an event to all listeners and callbacks.

        Errors in listeners/callbacks are logged but never propagated.
        """
        # General listeners
        for listener in self._listeners:
            try:
                result = listener(event)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Error in event listener for %s", event.type.value)

        # Structured callbacks
        method_name = _CALLBACK_MAP.get(event.type)
        if method_name:
            for cb in self._callbacks:
                handler = getattr(cb, method_name, None)
                if handler is not None:
                    try:
                        result = handler(event)
                        if inspect.isawaitable(result):
                            await result
                    except Exception:
                        logger.exception(
                            "Error in callback %s.%s",
                            type(cb).__name__,
                            method_name,
                        )


__all__ = ["Event", "EventType", "Callback", "EventEmitter"]
