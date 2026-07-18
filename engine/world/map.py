"""Map data structures — tiles, world map, and regions.

A WorldMap is the top-level map composed of a single noise-driven grid
of tiles for the current implementation. A Region is a sub-area that
supports streamed loading for very large worlds (architecture-ready,
currently eagerly materialised).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional

from engine.world.terrain import Terrain, TerrainType


@dataclass
class Tile:
    """A single world tile."""

    x: int
    y: int
    elevation: float = 0.0
    temperature: float = 15.0
    moisture: float = 0.5
    terrain_type: TerrainType = TerrainType.GRASS
    biome_type: str = "grassland"
    is_explored: bool = False
    is_visible: bool = False
    walkable_override: Optional[bool] = None
    encounter_rate: float = 0.0
    structure_id: Optional[int] = None  # ID of structure placed here
    region_id: Optional[int] = None

    @property
    def terrain(self) -> Terrain:
        return Terrain.get(self.terrain_type)

    @property
    def is_walkable(self) -> bool:
        if self.walkable_override is not None:
            return self.walkable_override
        return self.terrain.is_walkable

    @property
    def blocks_sight(self) -> bool:
        return self.terrain.blocks_sight

    @property
    def movement_cost(self) -> float:
        return self.terrain.movement_cost

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "elevation": self.elevation,
            "temperature": self.temperature,
            "moisture": self.moisture,
            "terrain_type": self.terrain_type.value,
            "biome_type": self.biome_type,
            "is_explored": self.is_explored,
            "is_visible": self.is_visible,
            "encounter_rate": self.encounter_rate,
            "structure_id": self.structure_id,
            "region_id": self.region_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Tile":
        return cls(
            x=data["x"],
            y=data["y"],
            elevation=data.get("elevation", 0.0),
            temperature=data.get("temperature", 15.0),
            moisture=data.get("moisture", 0.5),
            terrain_type=TerrainType(data.get("terrain_type", "grass")),
            biome_type=data.get("biome_type", "grassland"),
            is_explored=data.get("is_explored", False),
            is_visible=data.get("is_visible", False),
            encounter_rate=data.get("encounter_rate", 0.0),
            structure_id=data.get("structure_id"),
            region_id=data.get("region_id"),
        )


@dataclass(frozen=True)
class WorldPosition:
    """Absolute position in world coordinates."""

    x: int
    y: int
    z: int = 0  # for dungeons / dimensions


@dataclass(frozen=True)
class RegionCoordinates:
    """Coordinates of a region in the region grid."""

    rx: int
    ry: int

    def to_world(self, region_size: int) -> WorldPosition:
        return WorldPosition(self.rx * region_size, self.ry * region_size)


class RegionMap:
    """A square region of tiles, eagerly materialised in memory."""

    def __init__(self, region_x: int, region_y: int, size: int) -> None:
        self.region_x = region_x
        self.region_y = region_y
        self.size = size
        self.tiles: list[list[Tile]] = [
            [Tile(x=region_x * size + i, y=region_y * size + j)
             for i in range(size)]
            for j in range(size)
        ]

    def get(self, local_x: int, local_y: int) -> Tile:
        return self.tiles[local_y][local_x]

    def set(self, local_x: int, local_y: int, tile: Tile) -> None:
        tile.x = self.region_x * self.size + local_x
        tile.y = self.region_y * self.size + local_y
        self.tiles[local_y][local_x] = tile

    def iter_tiles(self) -> Iterator[Tile]:
        for row in self.tiles:
            yield from row


class WorldMap:
    """The current world map — a flat grid of tiles.

    For very large worlds this would be replaced with a region-streamed
    structure. The interface is intentionally compatible with that future
    migration: callers ask for tiles by absolute (x, y).
    """

    def __init__(self, width: int, height: int, seed: int = 0) -> None:
        self.width = width
        self.height = height
        self.seed = seed
        self._tiles: list[list[Tile]] = [
            [Tile(x=x, y=y) for x in range(width)]
            for y in range(height)
        ]
        self._regions: dict[tuple[int, int], RegionMap] = {}
        self.spawn_point: WorldPosition = WorldPosition(width // 2, height // 2)

    def get_tile(self, x: int, y: int) -> Optional[Tile]:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self._tiles[y][x]
        return None

    def set_tile(self, x: int, y: int, tile: Tile) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            tile.x = x
            tile.y = y
            self._tiles[y][x] = tile

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def iter_tiles(self) -> Iterator[Tile]:
        for row in self._tiles:
            yield from row

    def iter_visible(self) -> Iterator[Tile]:
        for tile in self.iter_tiles():
            if tile.is_visible:
                yield tile

    def iter_explored(self) -> Iterator[Tile]:
        for tile in self.iter_tiles():
            if tile.is_explored:
                yield tile

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
        for tile in self.iter_tiles():
            tile.is_visible = False

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
            "spawn_point": (self.spawn_point.x, self.spawn_point.y, self.spawn_point.z),
            "tiles": [[t.to_dict() for t in row] for row in self._tiles],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldMap":
        wm = cls(data["width"], data["height"], data.get("seed", 0))
        sx, sy, sz = data.get("spawn_point", (wm.width // 2, wm.height // 2, 0))
        wm.spawn_point = WorldPosition(sx, sy, sz)
        for y, row in enumerate(data["tiles"]):
            for x, td in enumerate(row):
                wm._tiles[y][x] = Tile.from_dict(td)
        return wm
