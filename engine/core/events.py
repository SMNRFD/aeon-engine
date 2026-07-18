"""Event bus — the central nervous system of the engine.

Features
--------
* Priority-ordered, cancellable, propagation-stopping handlers.
* Type-safe handler registration by event class.
* Sync and async dispatch (async via `dispatch_async`).
* Per-event-class statistics for profiling.
* Plugin event scoping (events can be marked `@plugin_event`).
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Awaitable, Callable, Optional, Type, TypeVar, Union

from engine.core.logging import get_logger


log = get_logger("events")


class Priority(IntEnum):
    """Handler execution priority. Lower runs first."""

    LOWEST = 100
    LOW = 75
    NORMAL = 50
    HIGH = 25
    HIGHEST = 10
    MONITOR = 0  # observers — always last, cannot cancel


E = TypeVar("E", bound="Event")
HandlerFn = Callable[["Event"], Optional[Union[bool, Awaitable[Optional[bool]]]]]


@dataclass
class Event:
    """Base class for all events.

    Set `cancelled = True` to stop further non-MONITOR handlers from running.
    Set `propagation_stopped = True` to halt dispatch entirely.
    """

    cancelled: bool = False
    propagation_stopped: bool = False
    timestamp: float = field(default_factory=time.time)
    source: Optional[str] = None

    def cancel(self) -> None:
        self.cancelled = True

    def stop_propagation(self) -> None:
        self.propagation_stopped = True


@dataclass
class _Handler:
    fn: HandlerFn
    priority: Priority
    plugin: Optional[str] = None

    def __lt__(self, other: "_Handler") -> bool:
        return (self.priority, id(self)) < (other.priority, id(other))


class EventBus:
    """A thread-safe, priority-ordered event dispatcher."""

    def __init__(self) -> None:
        self._handlers: dict[Type[Event], list[_Handler]] = {}
        self._lock = threading.RLock()
        self._stats: dict[Type[Event], int] = {}
        self._timings: dict[Type[Event], float] = {}

    def subscribe(
        self,
        event_type: Type[E],
        handler: HandlerFn,
        priority: Priority = Priority.NORMAL,
        plugin: Optional[str] = None,
    ) -> None:
        """Register a handler for `event_type`."""
        with self._lock:
            self._handlers.setdefault(event_type, []).append(
                _Handler(fn=handler, priority=priority, plugin=plugin)
            )
            self._handlers[event_type].sort()
        log.debug(
            "Subscribed %s to %s at priority %s",
            getattr(handler, "__name__", handler),
            event_type.__name__,
            priority.name,
        )

    def unsubscribe(self, event_type: Type[E], handler: HandlerFn) -> None:
        with self._lock:
            handlers = self._handlers.get(event_type, [])
            self._handlers[event_type] = [h for h in handlers if h.fn is not handler]

    def unsubscribe_plugin(self, plugin_name: str) -> int:
        """Remove all handlers registered by a given plugin."""
        count = 0
        with self._lock:
            for event_type, handlers in list(self._handlers.items()):
                kept = [h for h in handlers if h.plugin != plugin_name]
                count += len(handlers) - len(kept)
                self._handlers[event_type] = kept
        if count:
            log.info("Unsubscribed %d handlers from plugin %s", count, plugin_name)
        return count

    def dispatch(self, event: Event) -> bool:
        """Synchronously dispatch an event. Returns True if it was *not* cancelled."""
        event_type = type(event)
        with self._lock:
            handlers = list(self._handlers.get(event_type, ()))
        self._stats[event_type] = self._stats.get(event_type, 0) + 1
        start = time.perf_counter()
        try:
            for handler in handlers:
                if event.propagation_stopped:
                    break
                if event.cancelled and handler.priority != Priority.MONITOR:
                    continue
                try:
                    result = handler.fn(event)
                except Exception:  # noqa: BLE001
                    log.exception(
                        "Handler %s raised on %s",
                        getattr(handler.fn, "__name__", handler.fn),
                        event_type.__name__,
                    )
                    continue
                if inspect.isawaitable(result):
                    log.warning(
                        "Async handler %s registered for sync dispatch on %s — awaiting in loop",
                        getattr(handler.fn, "__name__", handler.fn),
                        event_type.__name__,
                    )
                    try:
                        asyncio.get_event_loop().run_until_complete(result)  # type: ignore[arg-type]
                    except RuntimeError:
                        asyncio.run(result)  # type: ignore[arg-type]
                elif result is True:
                    # Returning True explicitly stops propagation.
                    event.stop_propagation()
        finally:
            elapsed = time.perf_counter() - start
            self._timings[event_type] = self._timings.get(event_type, 0.0) + elapsed
        return not event.cancelled

    async def dispatch_async(self, event: Event) -> bool:
        """Asynchronously dispatch an event, awaiting coroutine handlers."""
        event_type = type(event)
        with self._lock:
            handlers = list(self._handlers.get(event_type, ()))
        self._stats[event_type] = self._stats.get(event_type, 0) + 1
        for handler in handlers:
            if event.propagation_stopped:
                break
            if event.cancelled and handler.priority != Priority.MONITOR:
                continue
            try:
                result = handler.fn(event)
                if inspect.isawaitable(result):
                    result = await result
            except Exception:  # noqa: BLE001
                log.exception("Async handler raised on %s", event_type.__name__)
                continue
            if result is True:
                event.stop_propagation()
        return not event.cancelled

    def stats(self) -> dict[str, dict[str, Any]]:
        """Return per-event-type dispatch statistics."""
        out: dict[str, dict[str, Any]] = {}
        with self._lock:
            for event_type, count in self._stats.items():
                out[event_type.__name__] = {
                    "count": count,
                    "total_time": self._timings.get(event_type, 0.0),
                    "handlers": len(self._handlers.get(event_type, [])),
                }
        return out

    def clear(self) -> None:
        with self._lock:
            self._handlers.clear()
            self._stats.clear()
            self._timings.clear()


# Global event bus for convenience. Subsystems should generally accept their own
# bus via dependency injection; this singleton is for legacy/single-context code.
_global_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _global_bus
    if _global_bus is None:
        _global_bus = EventBus()
    return _global_bus


__all__ = [
    "Event",
    "EventBus",
    "Priority",
    "HandlerFn",
    "EventHandler",
    "get_event_bus",
]


# Re-export for typing convenience.
EventHandler = HandlerFn
