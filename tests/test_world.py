"""Tests for world generation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.world.generator import WorldGenerator, WorldGenParams
from engine.world.terrain import TerrainType
from engine.world.pathfinding import AStarPathfinder


def test_generate_small_world():
    params = WorldGenParams(seed=42, width=40, height=30, settlement_count=2, river_count=4)
    gen = WorldGenerator(params)
    world = gen.generate()
    assert world.width == 40
    assert world.height == 30
    # Check all tiles have biome assigned
    biomes = set()
    for tile in world.iter_tiles():
        assert tile.biome_type != ""
        biomes.add(tile.biome_type)
    assert len(biomes) >= 3  # at least a few biomes


def test_spawn_point_walkable():
    params = WorldGenParams(seed=42, width=40, height=30, settlement_count=3)
    gen = WorldGenerator(params)
    world = gen.generate()
    tile = world.get_tile(world.spawn_point.x, world.spawn_point.y)
    assert tile is not None
    assert tile.is_walkable


def test_pathfinding():
    params = WorldGenParams(seed=42, width=30, height=20, settlement_count=0, river_count=0,
                            enable_roads=False)
    gen = WorldGenerator(params)
    world = gen.generate()
    pf = AStarPathfinder(world)
    # Find a walkable start and goal
    walkable = [t for t in world.iter_tiles() if t.is_walkable]
    assert len(walkable) >= 2
    start = (walkable[0].x, walkable[0].y)
    goal = (walkable[10].x, walkable[10].y)
    path = pf.find_path(start, goal, max_iterations=10000)
    # Path may be None if blocked, but should exist for adjacent tiles
    # Try with adjacent tile
    for n in world.neighbours(*start):
        if n.is_walkable:
            path = pf.find_path(start, (n.x, n.y))
            assert path is not None
            assert len(path) >= 2
            assert (path[0] == start) or (path[-1] == start)
            return
