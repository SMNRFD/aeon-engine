"""Tests for the event bus."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.core.events import Event, EventBus, Priority


class TickEvent(Event):
    def __init__(self, n: int = 0):
        super().__init__()
        self.n = n


class DeathEvent(Event):
    def __init__(self, entity_id: int):
        super().__init__()
        self.entity_id = entity_id


def test_subscribe_and_dispatch():
    bus = EventBus()
    received = []
    bus.subscribe(TickEvent, lambda e: received.append(e.n))
    bus.dispatch(TickEvent(n=42))
    assert received == [42]


def test_priority_order():
    bus = EventBus()
    order = []
    bus.subscribe(TickEvent, lambda e: order.append("low"), priority=Priority.LOW)
    bus.subscribe(TickEvent, lambda e: order.append("normal"), priority=Priority.NORMAL)
    bus.subscribe(TickEvent, lambda e: order.append("high"), priority=Priority.HIGH)
    bus.dispatch(TickEvent())
    assert order == ["high", "normal", "low"]


def test_cancellation():
    bus = EventBus()
    received = []
    def cancel_handler(e):
        e.cancel()
    bus.subscribe(TickEvent, cancel_handler, priority=Priority.HIGH)
    bus.subscribe(TickEvent, lambda e: received.append("after"), priority=Priority.NORMAL)
    bus.dispatch(TickEvent())
    assert received == []


def test_monitor_runs_after_cancel():
    bus = EventBus()
    monitor_ran = []
    bus.subscribe(TickEvent, lambda e: e.cancel(), priority=Priority.HIGH)
    bus.subscribe(TickEvent, lambda e: monitor_ran.append(True), priority=Priority.MONITOR)
    bus.dispatch(TickEvent())
    assert monitor_ran == [True]


def test_unsubscribe_plugin():
    bus = EventBus()
    received = []
    bus.subscribe(TickEvent, lambda e: received.append(1), plugin="p1")
    bus.subscribe(TickEvent, lambda e: received.append(2), plugin="p2")
    bus.unsubscribe_plugin("p1")
    bus.dispatch(TickEvent())
    assert received == [2]


def test_stats():
    bus = EventBus()
    bus.subscribe(TickEvent, lambda e: None)
    bus.dispatch(TickEvent())
    bus.dispatch(TickEvent())
    stats = bus.stats()
    assert "TickEvent" in stats
    assert stats["TickEvent"]["count"] == 2
