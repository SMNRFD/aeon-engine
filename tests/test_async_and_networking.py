"""Tests for async NPC simulation and plugin networking hooks."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.core.ecs import World, Entity
from engine.entities.factory import EntityFactory
from engine.utils.rng import RNG
from engine.npc.async_simulator import AsyncNPCSimulator
from engine.plugins.networking_hooks import PluginNetworkingHooks
from engine.network import NetworkMessage, MessageType


def test_async_npc_simulator_basic():
    """Test basic async NPC simulation."""
    world = World()
    factory = EntityFactory(world, RNG(42))
    sim = AsyncNPCSimulator(num_workers=2, batch_size=10)
    # Register some NPCs
    for _ in range(20):
        npc = factory.create_npc("Test")
        sim.register_npc(npc.id)
    sim.start()
    try:
        processed_count = [0]
        def process_fn(entity: Entity, dt: float) -> None:
            processed_count[0] += 1
        count = sim.tick(world, 0.1, process_fn)
        assert count == 20
        assert processed_count[0] == 20
    finally:
        sim.stop()


def test_async_npc_simulator_stats():
    """Test that stats are tracked correctly."""
    world = World()
    factory = EntityFactory(world, RNG(42))
    sim = AsyncNPCSimulator(num_workers=2, batch_size=5)
    for _ in range(10):
        npc = factory.create_npc("Test")
        sim.register_npc(npc.id)
    sim.start()
    try:
        sim.tick(world, 0.1, lambda e, dt: None)
        stats = sim.stats()
        assert stats["total_processed"] == 10
        assert stats["num_workers"] == 2
    finally:
        sim.stop()


def test_async_npc_simulator_unregister():
    """Test unregistering NPCs."""
    world = World()
    factory = EntityFactory(world, RNG(42))
    sim = AsyncNPCSimulator(num_workers=1, batch_size=10)
    npc = factory.create_npc("Test")
    sim.register_npc(npc.id)
    assert len(sim._batches) > 0
    sim.unregister_npc(npc.id)
    # NPC should no longer be in any batch
    for batch in sim._batches.values():
        assert npc.id not in batch.entity_ids


# ---------- Plugin Networking Hooks ----------

def test_plugin_networking_hooks_incoming():
    """Test incoming message hooks."""
    hooks = PluginNetworkingHooks()
    received = []
    def hook(msg: NetworkMessage) -> NetworkMessage:
        received.append(msg)
        return msg
    hooks.register_incoming("test_plugin", MessageType.PLAYER_ACTION, hook)
    msg = NetworkMessage(type=MessageType.PLAYER_ACTION, payload={"action": "move"})
    result = hooks.process_incoming(msg)
    assert result is not None
    assert len(received) == 1


def test_plugin_networking_hooks_block():
    """Test that a hook can block a message."""
    hooks = PluginNetworkingHooks()
    def blocking_hook(msg: NetworkMessage):
        return None  # block
    hooks.register_incoming("blocker", MessageType.CHAT, blocking_hook)
    msg = NetworkMessage(type=MessageType.CHAT, payload={"text": "hello"})
    result = hooks.process_incoming(msg)
    assert result is None  # blocked


def test_plugin_networking_hooks_modify():
    """Test that a hook can modify a message."""
    hooks = PluginNetworkingHooks()
    def modify_hook(msg: NetworkMessage) -> NetworkMessage:
        msg.payload["modified"] = True
        return msg
    hooks.register_incoming("modifier", MessageType.PLAYER_ACTION, modify_hook)
    msg = NetworkMessage(type=MessageType.PLAYER_ACTION, payload={"action": "move"})
    result = hooks.process_incoming(msg)
    assert result is not None
    assert result.payload.get("modified") is True


def test_plugin_networking_hooks_unregister():
    """Test unregistering all hooks from a plugin."""
    hooks = PluginNetworkingHooks()
    hooks.register_incoming("plugin_a", MessageType.CHAT, lambda m: m)
    hooks.register_incoming("plugin_a", MessageType.PLAYER_ACTION, lambda m: m)
    hooks.register_incoming("plugin_b", MessageType.CHAT, lambda m: m)
    count = hooks.unregister_plugin("plugin_a")
    assert count == 2
    stats = hooks.stats()
    assert stats["incoming_hooks"] == 1  # only plugin_b remains


def test_plugin_networking_hooks_outgoing():
    """Test outgoing message hooks."""
    hooks = PluginNetworkingHooks()
    received = []
    def hook(msg: NetworkMessage):
        received.append(msg)
        return msg
    hooks.register_outgoing("test_plugin", MessageType.WORLD_SNAPSHOT, hook)
    msg = NetworkMessage(type=MessageType.WORLD_SNAPSHOT, payload={"tick": 1})
    result = hooks.process_outgoing(msg)
    assert result is not None
    assert len(received) == 1


def test_plugin_networking_hooks_priority():
    """Test that hooks are called in priority order."""
    hooks = PluginNetworkingHooks()
    order = []
    def hook_a(msg):
        order.append("a")
        return msg
    def hook_b(msg):
        order.append("b")
        return msg
    def hook_c(msg):
        order.append("c")
        return msg
    # Register in non-priority order
    hooks.register_incoming("p1", MessageType.CHAT, hook_b, priority=50)
    hooks.register_incoming("p2", MessageType.CHAT, hook_a, priority=10)  # earliest
    hooks.register_incoming("p3", MessageType.CHAT, hook_c, priority=90)  # latest
    msg = NetworkMessage(type=MessageType.CHAT)
    hooks.process_incoming(msg)
    assert order == ["a", "b", "c"]
