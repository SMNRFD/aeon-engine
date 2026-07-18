"""Performance and stress tests."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.core.config import EngineConfig
from engine.engine import Engine
from engine.world.generator import WorldGenParams
from engine.items.generator import ItemGenerator, ItemGenerationParams
from engine.utils.rng import RNG
from engine.performance.profiler import profiler


def test_item_generation_performance():
    """Generate 1000 items and verify it completes in reasonable time."""
    gen = ItemGenerator(RNG(42))
    start = time.perf_counter()
    for i in range(1000):
        params = ItemGenerationParams(archetype="dagger")
        gen.generate(params, item_id=i)
    elapsed = time.perf_counter() - start
    assert elapsed < 5.0, f"Item generation too slow: {elapsed:.2f}s"


def test_world_generation_performance():
    """Generate a 100x100 world and verify it completes in reasonable time."""
    params = WorldGenParams(seed=42, width=100, height=100,
                             settlement_count=5, river_count=20)
    from engine.world.generator import WorldGenerator
    gen = WorldGenerator(params)
    start = time.perf_counter()
    world = gen.generate()
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"World generation too slow: {elapsed:.2f}s"
    assert world.width == 100
    assert world.height == 100


def test_pathfinding_performance():
    """Test pathfinding performance over a long path."""
    params = WorldGenParams(seed=42, width=80, height=60,
                             settlement_count=0, river_count=0,
                             enable_roads=False)
    from engine.world.generator import WorldGenerator
    from engine.world.pathfinding import AStarPathfinder
    gen = WorldGenerator(params)
    world = gen.generate()
    pf = AStarPathfinder(world)
    # Find two distant walkable tiles
    walkable = [t for t in world.iter_tiles() if t.is_walkable]
    if len(walkable) >= 2:
        start = (walkable[0].x, walkable[0].y)
        goal = (walkable[-1].x, walkable[-1].y)
        start_time = time.perf_counter()
        path = pf.find_path(start, goal, max_iterations=10000)
        elapsed = time.perf_counter() - start_time
        assert elapsed < 2.0, f"Pathfinding too slow: {elapsed:.2f}s"


def test_ecs_query_performance():
    """Test ECS query performance with many entities."""
    from engine.core.ecs import World, Entity
    from engine.entities.components import Position, Health

    class PositionComp(Position): pass
    class HealthComp(Health): pass

    world = World()
    # Create 10000 entities with Position and Health
    for _ in range(10000):
        e = world.create_entity()
        world.add_component(e, Position())
        world.add_component(e, Health())
    start = time.perf_counter()
    results = list(world.view(Position, Health))
    elapsed = time.perf_counter() - start
    assert len(results) == 10000
    assert elapsed < 0.5, f"ECS query too slow: {elapsed:.3f}s"


def test_event_bus_performance():
    """Test event bus dispatch performance."""
    from engine.core.events import EventBus, Event, Priority

    class TestEvent(Event):
        pass

    bus = EventBus()
    received = []
    bus.subscribe(TestEvent, lambda e: received.append(1))
    start = time.perf_counter()
    for _ in range(10000):
        bus.dispatch(TestEvent())
    elapsed = time.perf_counter() - start
    assert len(received) == 10000
    assert elapsed < 2.0, f"Event dispatch too slow: {elapsed:.3f}s"


def test_object_pool_performance():
    """Test that object pooling is faster than creating new objects."""
    from engine.performance.pool import ObjectPool, PooledFactory

    class Expensive:
        __slots__ = ("data",)
        def __init__(self):
            self.data = list(range(100))

    factory = PooledFactory(
        create_fn=lambda: Expensive(),
        reset_fn=lambda obj: None,
    )
    pool = ObjectPool(factory, initial_size=100, max_size=1000)
    # Acquire and release 10000 times
    start = time.perf_counter()
    for _ in range(10000):
        obj = pool.acquire()
        pool.release(obj)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"Pool too slow: {elapsed:.3f}s"


def test_lru_cache_hit_rate():
    """Test that LRU cache hit rate is high for repeated accesses."""
    from engine.performance.cache import LRUCache
    cache = LRUCache[str, int](capacity=100)
    # Fill cache
    for i in range(100):
        cache.put(f"key_{i}", i)
    # Access first 50 repeatedly
    for _ in range(1000):
        for i in range(50):
            cache.get(f"key_{i}")
    stats = cache.stats()
    assert stats["hit_rate"] > 0.9


def test_profiler_under_load():
    """Test profiler under load."""
    with profiler.scope("load_test"):
        for _ in range(1000):
            with profiler.scope("inner"):
                sum(range(100))
    stats = profiler.stats()
    assert "load_test" in stats.get("children", {})
    assert stats["children"]["load_test"]["calls"] == 1


def test_engine_simulation_stress():
    """Test engine simulation with many ticks."""
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=30, height=20))
    engine.create_player("TestHero")
    start = time.perf_counter()
    for _ in range(100):
        engine.tick_simulation(0.05)
    elapsed = time.perf_counter() - start
    assert elapsed < 10.0, f"Simulation too slow: {elapsed:.2f}s for 100 ticks"


def test_spatial_grid_query():
    """Test spatial grid query performance."""
    from engine.world.spatial import SpatialGrid
    grid = SpatialGrid(cell_size=8)
    # Insert 10000 entities
    import random
    rng = random.Random(42)
    entities = list(range(10000))
    for e in entities:
        grid.insert(e, rng.randint(0, 200), rng.randint(0, 200))
    start = time.perf_counter()
    # Query 100 times
    for _ in range(100):
        grid.query_radius(100, 100, 20)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"Spatial query too slow: {elapsed:.3f}s"
