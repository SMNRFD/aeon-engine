"""Terrain types — data-driven terrain catalog.

Each terrain type defines:
* glyph — terminal display character
* color — ANSI colour code
* movement_cost — multiplier on movement time
* is_walkable — can land entities enter this tile
* is_liquid — counts as water/lava/etc.
* is_solid — blocks movement and sight
* elevation_offset — base elevation contribution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


class TerrainType(Enum):
    DEEP_OCEAN = "deep_ocean"
    OCEAN = "ocean"
    SHALLOW_WATER = "shallow_water"
    BEACH = "beach"
    GRASS = "grass"
    FOREST = "forest"
    DENSE_FOREST = "dense_forest"
    HILLS = "hills"
    MOUNTAIN = "mountain"
    HIGH_MOUNTAIN = "high_mountain"
    SNOW = "snow"
    DESERT = "desert"
    SAVANNA = "savanna"
    SWAMP = "swamp"
    JUNGLE = "jungle"
    TUNDRA = "tundra"
    WETLAND = "wetland"
    LAVA = "lava"
    ROAD = "road"
    BRIDGE = "bridge"
    RIVER = "river"
    ICE = "ice"


@dataclass(frozen=True)
class Terrain:
    terrain_type: TerrainType
    glyph: str
    color: int          # ANSI 256-colour code
    movement_cost: float = 1.0
    is_walkable: bool = True
    is_liquid: bool = False
    is_solid: bool = False
    blocks_sight: bool = False
    elevation_offset: float = 0.0
    fertility: float = 0.0
    description: str = ""

    _registry: ClassVar[dict[TerrainType, "Terrain"]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, terrain: "Terrain") -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._registry[terrain.terrain_type] = terrain

    @classmethod
    def get(cls, terrain_type: TerrainType) -> "Terrain":
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._registry[terrain_type]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        defaults: list[Terrain] = [
            Terrain(TerrainType.DEEP_OCEAN,    "~",  18, 99.0, False, True,  False, False, -0.6, 0.0, "Deep, dark water."),
            Terrain(TerrainType.OCEAN,         "~",  27, 99.0, False, True,  False, False, -0.4, 0.0, "Open ocean."),
            Terrain(TerrainType.SHALLOW_WATER, "~",  39, 4.0,  True,  True,  False, False, -0.2, 0.0, "Shallow coastal waters."),
            Terrain(TerrainType.RIVER,         "=",  33, 3.0,  True,  True,  False, False, -0.15, 0.2, "A flowing river."),
            Terrain(TerrainType.BEACH,         ".",  222, 1.2, True,  False, False, False, 0.05, 0.1, "Sandy beach."),
            Terrain(TerrainType.GRASS,         '"',  114, 1.0, True,  False, False, False, 0.1, 0.7, "Lush grassland."),
            Terrain(TerrainType.SAVANNA,       '"',  186, 1.0, True,  False, False, False, 0.15, 0.4, "Dry savanna grass."),
            Terrain(TerrainType.FOREST,        "T",  22,  1.5, True,  False, False, True,  0.2, 0.6, "Dappled forest."),
            Terrain(TerrainType.DENSE_FOREST,  "♠",  28,  2.5, True,  False, False, True,  0.25, 0.5, "Dense old-growth forest."),
            Terrain(TerrainType.JUNGLE,        "♣",  34,  2.8, True,  False, False, True,  0.2, 0.9, "Steaming jungle."),
            Terrain(TerrainType.HILLS,         "∧",  101, 1.3, True,  False, False, False, 0.35, 0.4, "Rolling hills."),
            Terrain(TerrainType.MOUNTAIN,      "▲",  243, 2.5, True,  False, True,  True,  0.55, 0.1, "Rocky mountain slopes."),
            Terrain(TerrainType.HIGH_MOUNTAIN, "▲",  252, 99.0, False, False, True, True, 0.75, 0.0, "Sheer mountain peak."),
            Terrain(TerrainType.SNOW,          "❄",  255, 2.0, True,  False, False, False, 0.6, 0.0, "Snowfield."),
            Terrain(TerrainType.DESERT,        ".",  215, 1.4, True,  False, False, False, 0.0, 0.0, "Sand dunes."),
            Terrain(TerrainType.TUNDRA,        "·",  152, 1.6, True,  False, False, False, 0.05, 0.1, "Frozen tundra."),
            Terrain(TerrainType.SWAMP,         "≈",  64,  2.2, True,  False, False, False, 0.0, 0.6, "Murky swamp."),
            Terrain(TerrainType.WETLAND,       "≈",  72,  1.8, True,  False, False, False, 0.05, 0.7, "Marshy wetland."),
            Terrain(TerrainType.LAVA,          "~",  196, 99.0, False, True,  False, False, 0.5, 0.0, "Glowing molten lava."),
            Terrain(TerrainType.ROAD,         "#",   137, 0.7, True,  False, False, False, 0.0, 0.0, "Paved road."),
            Terrain(TerrainType.BRIDGE,       "=",   94,  0.7, True,  False, False, False, 0.0, 0.0, "Wooden bridge."),
            Terrain(TerrainType.ICE,          "◊",   153, 1.4, True,  False, False, False, -0.1, 0.0, "Slippery ice."),
        ]
        for t in defaults:
            cls._registry[t.terrain_type] = t
        cls._defaults_loaded = True
