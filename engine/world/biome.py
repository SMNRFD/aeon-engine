"""Biome classification — maps (elevation, temperature, moisture) to biomes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BiomeType(Enum):
    OCEAN = "ocean"
    TROPICAL_RAINFOREST = "tropical_rainforest"
    TROPICAL_SEASONAL_FOREST = "tropical_seasonal_forest"
    SAVANNA = "savanna"
    HOT_DESERT = "hot_desert"
    COLD_DESERT = "cold_desert"
    GRASSLAND = "grassland"
    TEMPERATE_FOREST = "temperate_forest"
    TEMPERATE_RAINFOREST = "temperate_rainforest"
    BOREAL_FOREST = "boreal_forest"
    TUNDRA = "tundra"
    ALPINE = "alpine"
    SNOW = "snow"
    MOUNTAIN = "mountain"
    WETLAND = "wetland"


@dataclass(frozen=True)
class Biome:
    biome_type: BiomeType
    name: str
    base_terrain_chance: dict[str, float]
    flora: list[str]
    fauna: list[str]
    average_temperature: float   # Celsius
    average_rainfall: float      # mm/year
    color: int


_BIOMES: dict[BiomeType, Biome] = {}
_BIOMES_LOADED: bool = False


def _register(b: Biome) -> None:
    _BIOMES[b.biome_type] = b


def _init_biomes() -> None:
    global _BIOMES_LOADED
    if _BIOMES_LOADED:
        return
    _BIOMES_LOADED = True
    _register(Biome(
        BiomeType.OCEAN, "Ocean",
        {"deep_ocean": 0.7, "ocean": 0.25, "shallow_water": 0.05},
        ["kelp", "coral"],
        ["fish", "shark", "whale"],
        18.0, 1000, 27,
    ))
    _register(Biome(
        BiomeType.TROPICAL_RAINFOREST, "Tropical Rainforest",
        {"jungle": 0.8, "dense_forest": 0.15, "river": 0.05},
        ["mahogany", "orchid", "fern"],
        ["jaguar", "monkey", "parrot"],
        27.0, 2500, 34,
    ))
    _register(Biome(
        BiomeType.TROPICAL_SEASONAL_FOREST, "Tropical Seasonal Forest",
        {"forest": 0.6, "jungle": 0.3, "grass": 0.1},
        ["teak", "bamboo"],
        ["tiger", "deer"],
        25.0, 1500, 70,
    ))
    _register(Biome(
        BiomeType.SAVANNA, "Savanna",
        {"savanna": 0.8, "grass": 0.15, "forest": 0.05},
        ["acacia", "grass"],
        ["elephant", "lion", "zebra"],
        24.0, 700, 186,
    ))
    _register(Biome(
        BiomeType.HOT_DESERT, "Hot Desert",
        {"desert": 0.95, "savanna": 0.04, "hills": 0.01},
        ["cactus", "date_palm"],
        ["camel", "scorpion", "lizard"],
        30.0, 100, 215,
    ))
    _register(Biome(
        BiomeType.COLD_DESERT, "Cold Desert",
        {"desert": 0.85, "tundra": 0.1, "hills": 0.05},
        ["sagebrush"],
        ["snake", "fox"],
        12.0, 200, 187,
    ))
    _register(Biome(
        BiomeType.GRASSLAND, "Grassland",
        {"grass": 0.85, "forest": 0.1, "hills": 0.05},
        ["wheat_grass", "oak"],
        ["bison", "wolf", "rabbit"],
        15.0, 600, 114,
    ))
    _register(Biome(
        BiomeType.TEMPERATE_FOREST, "Temperate Forest",
        {"forest": 0.7, "grass": 0.2, "dense_forest": 0.1},
        ["oak", "maple", "birch"],
        ["deer", "bear", "fox"],
        12.0, 900, 22,
    ))
    _register(Biome(
        BiomeType.TEMPERATE_RAINFOREST, "Temperate Rainforest",
        {"dense_forest": 0.7, "forest": 0.2, "wetland": 0.1},
        ["redwood", "fern", "moss"],
        ["elk", "cougar"],
        10.0, 2200, 28,
    ))
    _register(Biome(
        BiomeType.BOREAL_FOREST, "Boreal Forest",
        {"forest": 0.7, "snow": 0.2, "hills": 0.1},
        ["spruce", "fir", "pine"],
        ["moose", "wolf", "lynx"],
        0.0, 500, 29,
    ))
    _register(Biome(
        BiomeType.TUNDRA, "Tundra",
        {"tundra": 0.85, "snow": 0.1, "hills": 0.05},
        ["lichen", "dwarf_willow"],
        ["caribou", "arctic_fox"],
        -10.0, 250, 152,
    ))
    _register(Biome(
        BiomeType.ALPINE, "Alpine",
        {"mountain": 0.7, "snow": 0.2, "high_mountain": 0.1},
        ["alpine_grass"],
        ["mountain_goat", "eagle"],
        -5.0, 800, 252,
    ))
    _register(Biome(
        BiomeType.SNOW, "Snow",
        {"snow": 0.9, "ice": 0.05, "tundra": 0.05},
        [],
        ["penguin", "seal"],
        -20.0, 400, 255,
    ))
    _register(Biome(
        BiomeType.MOUNTAIN, "Mountain",
        {"mountain": 0.7, "high_mountain": 0.2, "hills": 0.1},
        ["pine"],
        ["eagle", "ibex"],
        5.0, 800, 243,
    ))
    _register(Biome(
        BiomeType.WETLAND, "Wetland",
        {"wetland": 0.6, "swamp": 0.3, "river": 0.1},
        ["cypress", "reed"],
        ["frog", "heron", "alligator"],
        18.0, 1500, 72,
    ))


def biome_for(elevation: float, temperature: float, moisture: float) -> Biome:
    """Classify a tile into a biome based on elevation (-1..1), temperature
    (Celsius) and moisture (0..1)."""
    _init_biomes()
    if elevation < -0.1:
        return _BIOMES[BiomeType.OCEAN]
    if elevation > 0.7:
        if temperature < -10:
            return _BIOMES[BiomeType.SNOW]
        if temperature < 0:
            return _BIOMES[BiomeType.ALPINE]
        return _BIOMES[BiomeType.MOUNTAIN]
    if elevation > 0.4:
        if temperature < 0:
            return _BIOMES[BiomeType.ALPINE]
        return _BIOMES[BiomeType.MOUNTAIN]
    if temperature < -5:
        return _BIOMES[BiomeType.TUNDRA]
    if temperature < 5:
        if moisture > 0.5:
            return _BIOMES[BiomeType.BOREAL_FOREST]
        return _BIOMES[BiomeType.COLD_DESERT]
    if temperature < 20:
        if moisture < 0.2:
            return _BIOMES[BiomeType.COLD_DESERT]
        if moisture < 0.4:
            return _BIOMES[BiomeType.GRASSLAND]
        if moisture < 0.7:
            return _BIOMES[BiomeType.TEMPERATE_FOREST]
        if moisture < 0.85:
            return _BIOMES[BiomeType.TEMPERATE_RAINFOREST]
        return _BIOMES[BiomeType.WETLAND]
    # Tropical
    if moisture < 0.2:
        return _BIOMES[BiomeType.HOT_DESERT]
    if moisture < 0.4:
        return _BIOMES[BiomeType.SAVANNA]
    if moisture < 0.6:
        return _BIOMES[BiomeType.TROPICAL_SEASONAL_FOREST]
    return _BIOMES[BiomeType.TROPICAL_RAINFOREST]


def get_biome(biome_type: BiomeType) -> Biome:
    _init_biomes()
    return _BIOMES[biome_type]


def all_biomes() -> list[Biome]:
    _init_biomes()
    return list(_BIOMES.values())
