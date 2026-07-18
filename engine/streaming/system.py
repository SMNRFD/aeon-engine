"""Streaming world system — chunk-based loading for infinite worlds.

Instead of generating the entire world at once, the world is divided
into chunks that are loaded/unloaded dynamically based on player position.

Features:
* Chunks are NxN tiles (default 32x32)
* Only chunks near the player are loaded
* Chunks are unloaded when far away (configurable distance)
* Chunk generation is deterministic (seeded by chunk coordinates)
* Chunks can be cached to disk for faster reload
* Background streaming thread can pre-generate chunks
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from engine.core.logging import get_logger
from engine.utils.rng import RNG
from engine.world.map import WorldMap, Tile


log = get_logger("streaming")


@dataclass
class Chunk:
    """A square region of the world."""

    chunk_x: int
    chunk_y: int
    size: int = 32
    tiles: list[list[Tile]] = field(default_factory=list)
    is_loaded: bool = False
    is_generating: bool = False
    last_accessed: float = 0.0
    entities: list[int] = field(default_factory=list)

    @property
    def world_x(self) -> int:
        return self.chunk_x * self.size

    @property
    def world_y(self) -> int:
        return self.chunk_y * self.size

    def get_tile(self, local_x: int, local_y: int) -> Optional[Tile]:
        if 0 <= local_x < self.size and 0 <= local_y < self.size:
            return self.tiles[local_y][local_x]
        return None

    def set_tile(self, local_x: int, local_y: int, tile: Tile) -> None:
        if 0 <= local_x < self.size and 0 <= local_y < self.size:
            self.tiles[local_y][local_x] = tile


class ChunkLoader:
    """Loads chunks from generation or disk."""

    def __init__(self, seed: int, chunk_size: int = 32) -> None:
        self.seed = seed
        self.chunk_size = chunk_size
        self._disk_cache_path: Optional[str] = None

    def generate_chunk(self, chunk_x: int, chunk_y: int) -> Chunk:
        """Generate a chunk deterministically."""
        # Use a seed derived from chunk coordinates for deterministic generation
        chunk_seed = self.seed ^ (chunk_x * 73856093) ^ (chunk_y * 19349663)
        rng = RNG(chunk_seed)
        chunk = Chunk(
            chunk_x=chunk_x, chunk_y=chunk_y, size=self.chunk_size,
            is_loaded=True, last_accessed=time.time(),
        )
        # Simple placeholder generation — in production this would use
        # the full WorldGenerator with the chunk-seeded RNG.
        from engine.world.terrain import Terrain, TerrainType
        from engine.world.biome import biome_for
        for y in range(self.chunk_size):
            row: list[Tile] = []
            for x in range(self.chunk_size):
                wx = chunk.world_x + x
                wy = chunk.world_y + y
                # Simple noise-based heightmap
                elevation = (
                    math.sin(wx * 0.1) * 0.3
                    + math.cos(wy * 0.1) * 0.3
                    + rng.uniform(-0.2, 0.2)
                )
                temperature = 20.0 - abs(wy) * 0.5
                moisture = rng.uniform(0.3, 0.7)
                biome = biome_for(elevation, temperature, moisture)
                terrain = Terrain.get({
                    "deep_ocean": TerrainType.DEEP_OCEAN,
                    "ocean": TerrainType.OCEAN,
                    "shallow_water": TerrainType.SHALLOW_WATER,
                    "grass": TerrainType.GRASS,
                    "forest": TerrainType.FOREST,
                    "mountain": TerrainType.MOUNTAIN,
                    "snow": TerrainType.SNOW,
                    "desert": TerrainType.DESERT,
                }.get(biome.biome_type.value, TerrainType.GRASS))
                tile = Tile(
                    x=wx, y=wy,
                    elevation=elevation,
                    temperature=temperature,
                    moisture=moisture,
                    terrain_type=terrain.terrain_type,
                    biome_type=biome.biome_type.value,
                )
                row.append(tile)
            chunk.tiles.append(row)
        return chunk

    def load_chunk(self, chunk_x: int, chunk_y: int) -> Chunk:
        """Load a chunk from cache or generate it."""
        # In production, check disk cache first
        return self.generate_chunk(chunk_x, chunk_y)

    def save_chunk(self, chunk: Chunk) -> None:
        """Save a chunk to disk cache (no-op stub)."""
        pass


class ChunkManager:
    """Manages loaded chunks with LRU eviction."""

    def __init__(self, loader: ChunkLoader,
                 max_loaded: int = 64) -> None:
        self.loader = loader
        self.max_loaded = max_loaded
        self._chunks: OrderedDict[tuple[int, int], Chunk] = OrderedDict()
        self._lock = threading.RLock()
        self._load_count: int = 0
        self._eviction_count: int = 0

    def get_chunk(self, chunk_x: int, chunk_y: int) -> Chunk:
        """Get a chunk, loading it if necessary."""
        key = (chunk_x, chunk_y)
        with self._lock:
            if key in self._chunks:
                # Move to end (most recently used)
                self._chunks.move_to_end(key)
                chunk = self._chunks[key]
                chunk.last_accessed = time.time()
                return chunk
            # Need to load
            chunk = self.loader.load_chunk(chunk_x, chunk_y)
            self._chunks[key] = chunk
            self._load_count += 1
            # Evict if over capacity
            while len(self._chunks) > self.max_loaded:
                evicted_key, evicted_chunk = self._chunks.popitem(last=False)
                evicted_chunk.is_loaded = False
                self.loader.save_chunk(evicted_chunk)
                self._eviction_count += 1
            return chunk

    def unload_chunk(self, chunk_x: int, chunk_y: int) -> bool:
        """Unload a specific chunk."""
        key = (chunk_x, chunk_y)
        with self._lock:
            if key in self._chunks:
                chunk = self._chunks.pop(key)
                chunk.is_loaded = False
                self.loader.save_chunk(chunk)
                self._eviction_count += 1
                return True
            return False

    def is_loaded(self, chunk_x: int, chunk_y: int) -> bool:
        with self._lock:
            return (chunk_x, chunk_y) in self._chunks

    def loaded_chunks(self) -> list[Chunk]:
        with self._lock:
            return list(self._chunks.values())

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "loaded": len(self._chunks),
                "max": self.max_loaded,
                "load_count": self._load_count,
                "eviction_count": self._eviction_count,
            }


class StreamingCoordinator:
    """Coordinates streaming around a focal point (the player)."""

    def __init__(self, manager: ChunkManager,
                 view_distance: int = 3,
                 unload_distance: int = 5,
                 async_loading: bool = True) -> None:
        self.manager = manager
        self.view_distance = view_distance
        self.unload_distance = unload_distance
        self.async_loading = async_loading
        self._current_center: tuple[int, int] = (0, 0)
        self._load_queue: list[tuple[int, int]] = []
        self._load_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.RLock()

    def update_center(self, world_x: int, world_y: int) -> None:
        """Update the focal point in world coordinates."""
        chunk_size = self.manager.loader.chunk_size
        new_cx = world_x // chunk_size
        new_cy = world_y // chunk_size
        if (new_cx, new_cy) == self._current_center:
            return
        self._current_center = (new_cx, new_cy)
        self._update_loading()

    def _update_loading(self) -> None:
        """Load/unload chunks based on current center."""
        cx, cy = self._current_center
        # Determine which chunks should be loaded
        should_load: set[tuple[int, int]] = set()
        for dx in range(-self.view_distance, self.view_distance + 1):
            for dy in range(-self.view_distance, self.view_distance + 1):
                # Circular falloff
                if dx * dx + dy * dy <= self.view_distance * self.view_distance:
                    should_load.add((cx + dx, cy + dy))
        # Queue loading
        with self._lock:
            for chunk_pos in should_load:
                if not self.manager.is_loaded(*chunk_pos):
                    self._load_queue.append(chunk_pos)
        # Unload far chunks
        loaded = self.manager.loaded_chunks()
        for chunk in loaded:
            dist = max(abs(chunk.chunk_x - cx), abs(chunk.chunk_y - cy))
            if dist > self.unload_distance:
                self.manager.unload_chunk(chunk.chunk_x, chunk.chunk_y)
        # Load chunks — synchronously if async is off, otherwise spawn a thread
        if self.async_loading and self._load_queue and not self._running:
            self._start_load_thread()
        elif not self.async_loading:
            # Load synchronously
            while self._load_queue:
                chunk_pos = self._load_queue.pop(0)
                try:
                    self.manager.get_chunk(*chunk_pos)
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed to load chunk %s: %s", chunk_pos, exc)

    def _start_load_thread(self) -> None:
        self._running = True
        self._load_thread = threading.Thread(target=self._load_worker, daemon=True)
        self._load_thread.start()

    def _load_worker(self) -> None:
        """Background chunk loader."""
        while True:
            with self._lock:
                if not self._load_queue:
                    self._running = False
                    return
                chunk_pos = self._load_queue.pop(0)
            try:
                self.manager.get_chunk(*chunk_pos)
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to load chunk %s: %s", chunk_pos, exc)

    def get_tile(self, world_x: int, world_y: int) -> Optional[Tile]:
        """Get a tile from the streaming world."""
        chunk_size = self.manager.loader.chunk_size
        cx = world_x // chunk_size
        cy = world_y // chunk_size
        local_x = world_x % chunk_size
        local_y = world_y % chunk_size
        # Handle negative modulo
        if local_x < 0:
            cx -= 1
            local_x += chunk_size
        if local_y < 0:
            cy -= 1
            local_y += chunk_size
        if not self.manager.is_loaded(cx, cy):
            return None
        chunk = self.manager.get_chunk(cx, cy)
        return chunk.get_tile(local_x, local_y)

    def stats(self) -> dict[str, Any]:
        return {
            "manager": self.manager.stats(),
            "queue_size": len(self._load_queue),
            "center": self._current_center,
            "view_distance": self.view_distance,
            "unload_distance": self.unload_distance,
        }


class StreamingWorld:
    """A streaming world that combines chunk management with a WorldMap-like interface."""

    def __init__(self, seed: int, chunk_size: int = 32,
                 view_distance: int = 3,
                 max_loaded: int = 64) -> None:
        self.loader = ChunkLoader(seed=seed, chunk_size=chunk_size)
        self.manager = ChunkManager(loader=self.loader, max_loaded=max_loaded)
        self.coordinator = StreamingCoordinator(manager=self.manager,
                                                  view_distance=view_distance)

    @property
    def width(self) -> int:
        # Theoretical infinite
        return 1_000_000

    @property
    def height(self) -> int:
        return 1_000_000

    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        return self.coordinator.get_tile(x, y)

    def update_center(self, x: int, y: int) -> None:
        self.coordinator.update_center(x, y)

    def stats(self) -> dict[str, Any]:
        return self.coordinator.stats()

    def iter_loaded_tiles(self):
        """Iterate over all tiles in loaded chunks."""
        for chunk in self.manager.loaded_chunks():
            for row in chunk.tiles:
                for tile in row:
                    yield tile

    def iter_visible(self):
        """Iterate over visible (loaded) tiles."""
        for tile in self.iter_loaded_tiles():
            if tile.is_visible:
                yield tile

    def in_bounds(self, x: int, y: int) -> bool:
        return -500_000 <= x <= 500_000 and -500_000 <= y <= 500_000

    def neighbours(self, x: int, y: int, include_diagonal: bool = True) -> list[Tile]:
        out: list[Tile] = []
        deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        if include_diagonal:
            deltas += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
        for dx, dy in deltas:
            t = self.get_tile(x + dx, y + dy)
            if t is not None:
                out.append(t)
        return out

    def reset_visibility(self) -> None:
        for tile in self.iter_loaded_tiles():
            tile.is_visible = False
