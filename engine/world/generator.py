"""Procedural world generator using value-noise + simulated erosion.

The generator produces:
* A heightmap via multi-octave value noise.
* A temperature map from latitude + altitude.
* A moisture map from a separate noise field.
* Rivers traced from high to low elevation.
* Roads connecting generated settlements.

No third-party noise library is used — we implement deterministic value
noise so saves remain reproducible across machines.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from engine.core.logging import get_logger
from engine.utils.rng import RNG
from engine.world.biome import biome_for
from engine.world.map import WorldMap, Tile, WorldPosition
from engine.world.terrain import Terrain, TerrainType


log = get_logger("world.gen")


# ---------- value noise ----------

def _fade(t: float) -> float:
    return t * t * t * (t * (t * 6 - 15) + 10)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


class ValueNoise:
    """Deterministic 2D value noise with smooth interpolation."""

    def __init__(self, seed: int, scale: int = 256) -> None:
        self.rng = RNG(seed)
        self.scale = scale
        self._table: list[float] = [self.rng.random() for _ in range(scale * scale)]

    def _value(self, ix: int, iy: int) -> float:
        ix %= self.scale
        iy %= self.scale
        return self._table[iy * self.scale + ix]

    def sample(self, x: float, y: float) -> float:
        x = x * self.scale
        y = y * self.scale
        x0 = int(math.floor(x))
        y0 = int(math.floor(y))
        x1 = x0 + 1
        y1 = y0 + 1
        sx = _fade(x - x0)
        sy = _fade(y - y0)
        v00 = self._value(x0, y0)
        v10 = self._value(x1, y0)
        v01 = self._value(x0, y1)
        v11 = self._value(x1, y1)
        ix0 = _lerp(v00, v10, sx)
        ix1 = _lerp(v01, v11, sx)
        return _lerp(ix0, ix1, sy)

    def fractal(self, x: float, y: float, octaves: int = 4,
                persistence: float = 0.5, lacunarity: float = 2.0,
                base_frequency: float = 1.0) -> float:
        total = 0.0
        amplitude = 1.0
        frequency = base_frequency
        max_value = 0.0
        for _ in range(octaves):
            total += self.sample(x * frequency, y * frequency) * amplitude
            max_value += amplitude
            amplitude *= persistence
            frequency *= lacunarity
        return total / max_value


# ---------- generator ----------

@dataclass
class WorldGenParams:
    seed: int = 0xBEEF
    width: int = 128
    height: int = 96
    sea_level: float = 0.42
    mountain_level: float = 0.78
    temperature_noise_scale: float = 4.0
    moisture_noise_scale: float = 3.5
    enable_rivers: bool = True
    river_count: int = 24
    enable_roads: bool = True
    settlement_count: int = 6


class WorldGenerator:
    """Generates a complete WorldMap from parameters."""

    def __init__(self, params: WorldGenParams) -> None:
        self.params = params
        self.height_noise = ValueNoise(seed=params.seed, scale=256)
        self.moisture_noise = ValueNoise(seed=params.seed ^ 0xC0FFEE, scale=256)
        self.temperature_noise = ValueNoise(seed=params.seed ^ 0xABCDEF, scale=256)
        self.rng = RNG(params.seed ^ 0xDEADBEEF)

    def generate(self) -> WorldMap:
        log.info("Generating world %dx%d (seed=%d)",
                 self.params.width, self.params.height, self.params.seed)
        world = WorldMap(self.params.width, self.params.height, self.params.seed)

        # 1. Heightmap
        self._generate_heightmap(world)
        # 2. Temperature & moisture
        self._generate_climate(world)
        # 3. Biomes & terrain
        self._assign_biomes(world)
        # 4. Rivers
        if self.params.enable_rivers:
            self._generate_rivers(world)
        # 5. Settlements & roads
        settlements = self._place_settlements(world)
        if self.params.enable_roads and len(settlements) >= 2:
            self._generate_roads(world, settlements)
        # 6. Encounter rates
        self._assign_encounter_rates(world)

        # Choose a sensible spawn: near a settlement, on walkable terrain.
        if settlements:
            sx, sy = settlements[0]
            world.spawn_point = WorldPosition(sx, sy)
        else:
            world.spawn_point = WorldPosition(self.params.width // 2,
                                              self.params.height // 2)
        log.info("World generation complete")
        return world

    # ----- steps -----

    def _generate_heightmap(self, world: WorldMap) -> None:
        cx, cy = self.params.width / 2, self.params.height / 2
        max_d = math.hypot(cx, cy)
        for y in range(self.params.height):
            for x in range(self.params.width):
                nx, ny = x / self.params.width, y / self.params.height
                h = self.height_noise.fractal(nx, ny, octaves=6, base_frequency=3.0)
                # Island-falloff so edges become ocean.
                d = math.hypot(x - cx, y - cy) / max_d
                h = h - 0.55 * d ** 1.8
                # Normalize to -1..1 roughly
                h = max(-1.0, min(1.0, h * 1.4))
                tile = world.get_tile(x, y)
                if tile:
                    tile.elevation = h

    def _generate_climate(self, world: WorldMap) -> None:
        for y in range(self.params.height):
            for x in range(self.params.width):
                tile = world.get_tile(x, y)
                if tile is None:
                    continue
                # Temperature: latitude-based with noise and altitude falloff.
                latitude = abs(y - self.params.height / 2) / (self.params.height / 2)
                base_temp = 35.0 - 50.0 * latitude
                noise = self.temperature_noise.fractal(
                    x / self.params.width, y / self.params.height,
                    octaves=3, base_frequency=self.params.temperature_noise_scale,
                )
                tile.temperature = base_temp + (noise - 0.5) * 12.0
                # Altitude cools by ~6.5 C per km; map -1..1 elevation to -3..5km.
                altitude_km = max(0.0, tile.elevation) * 5.0
                tile.temperature -= altitude_km * 6.5

                moist = self.moisture_noise.fractal(
                    x / self.params.width, y / self.params.height,
                    octaves=4, base_frequency=self.params.moisture_noise_scale,
                )
                # Coasts get a bit more rain.
                if tile.elevation > -0.2 and tile.elevation < 0.1:
                    moist = min(1.0, moist + 0.15)
                tile.moisture = max(0.0, min(1.0, moist))

    def _assign_biomes(self, world: WorldMap) -> None:
        for tile in world.iter_tiles():
            biome = biome_for(tile.elevation, tile.temperature, tile.moisture)
            tile.biome_type = biome.biome_type.value
            tile.terrain_type = self._pick_terrain(biome.biome_type.value, tile)

    def _pick_terrain(self, biome_name: str, tile: Tile) -> TerrainType:
        from engine.world.biome import get_biome, BiomeType
        # Map biome_name back to BiomeType
        try:
            bt = BiomeType(biome_name)
        except ValueError:
            return TerrainType.GRASS
        biome = get_biome(bt)
        weights = list(biome.base_terrain_chance.items())
        # Adjust for elevation
        if tile.elevation > 0.6:
            weights = [("mountain", 0.7), ("high_mountain", 0.2), ("hills", 0.1)]
        choice = self.rng.weighted_choice(
            [w[0] for w in weights], [w[1] for w in weights]
        )
        try:
            return TerrainType(choice)
        except ValueError:
            return TerrainType.GRASS

    def _generate_rivers(self, world: WorldMap) -> None:
        """Trace simple rivers from high elevations downhill to the sea."""
        placed = 0
        attempts = 0
        max_attempts = self.params.river_count * 20
        while placed < self.params.river_count and attempts < max_attempts:
            attempts += 1
            x = self.rng.randint(2, self.params.width - 3)
            y = self.rng.randint(2, self.params.height - 3)
            tile = world.get_tile(x, y)
            if tile is None or tile.elevation < self.params.mountain_level - 0.05:
                continue
            # Walk downhill
            path: list[tuple[int, int]] = []
            cx, cy = x, y
            for _ in range(200):
                path.append((cx, cy))
                tile = world.get_tile(cx, cy)
                if tile is None:
                    break
                if tile.elevation < self.params.sea_level:
                    break
                # Find lowest neighbour
                neighbours = world.neighbours(cx, cy)
                if not neighbours:
                    break
                lowest = min(neighbours, key=lambda t: t.elevation)
                if lowest.elevation >= tile.elevation:
                    # No descent possible — pick a random downhill-ish direction
                    break
                cx, cy = lowest.x, lowest.y
            # Carve river
            if len(path) >= 5:
                for px, py in path:
                    t = world.get_tile(px, py)
                    if t and t.elevation >= self.params.sea_level - 0.05:
                        if t.terrain_type not in (TerrainType.MOUNTAIN,
                                                  TerrainType.HIGH_MOUNTAIN):
                            t.terrain_type = TerrainType.RIVER
                placed += 1
        log.debug("Generated %d rivers (%d attempts)", placed, attempts)

    def _place_settlements(self, world: WorldMap) -> list[tuple[int, int]]:
        """Place settlements on walkable tiles near water."""
        candidates: list[Tile] = []
        for tile in world.iter_tiles():
            if (tile.terrain.is_walkable
                    and tile.terrain.terrain_type != TerrainType.RIVER
                    and tile.elevation > self.params.sea_level
                    and tile.elevation < self.params.mountain_level):
                # Has water neighbour?
                has_water = any(
                    n.terrain.is_liquid for n in world.neighbours(tile.x, tile.y)
                )
                if has_water:
                    candidates.append(tile)
        if not candidates:
            return []
        self.rng.shuffle(candidates)
        chosen: list[tuple[int, int]] = []
        for tile in candidates:
            if len(chosen) >= self.params.settlement_count:
                break
            # Spread out — reject if too close to existing
            if any(math.hypot(tile.x - cx, tile.y - cy) < 15 for cx, cy in chosen):
                continue
            chosen.append((tile.x, tile.y))
            # Mark as a road tile for now (settlements are larger structures
            # handled by the world simulation's structure layer).
            tile.terrain_type = TerrainType.ROAD
            tile.encounter_rate = 0.0
        log.debug("Placed %d settlements", len(chosen))
        return chosen

    def _generate_roads(self, world: WorldMap, settlements: list[tuple[int, int]]) -> None:
        """Connect settlements with roads using a simple greedy MST."""
        if len(settlements) < 2:
            return
        from engine.world.pathfinding import AStarPathfinder
        pathfinder = AStarPathfinder(world)
        connected = [settlements[0]]
        unconnected = settlements[1:]
        while unconnected:
            best_pair: Optional[tuple[tuple[int, int], tuple[int, int]]] = None
            best_dist = float("inf")
            for s in connected:
                for u in unconnected:
                    d = math.hypot(s[0] - u[0], s[1] - u[1])
                    if d < best_dist:
                        best_dist = d
                        best_pair = (s, u)
            if best_pair is None:
                break
            start, end = best_pair
            path = pathfinder.find_path(start, end, allow_road_penalty=False)
            if path:
                for px, py in path:
                    t = world.get_tile(px, py)
                    if t and t.terrain.is_walkable and t.terrain.terrain_type != TerrainType.RIVER:
                        if t.terrain.terrain_type not in (TerrainType.ROAD, TerrainType.BRIDGE):
                            # Don't pave over dense forests or mountains
                            if t.terrain.terrain_type in (TerrainType.DENSE_FOREST,
                                                          TerrainType.JUNGLE,
                                                          TerrainType.SWAMP):
                                continue
                            t.terrain_type = TerrainType.ROAD
            connected.append(end)
            unconnected.remove(end)

    def _assign_encounter_rates(self, world: WorldMap) -> None:
        """Higher encounter rates in wilder biomes."""
        wild_factor = {
            "jungle": 0.18, "tropical_rainforest": 0.20, "swamp": 0.15,
            "boreal_forest": 0.12, "dense_forest": 0.10, "forest": 0.06,
            "savanna": 0.08, "grassland": 0.04, "tundra": 0.06,
            "hot_desert": 0.07, "cold_desert": 0.05, "alpine": 0.08,
            "mountain": 0.05,
        }
        for tile in world.iter_tiles():
            tile.encounter_rate = wild_factor.get(tile.biome_type, 0.02)
            if tile.terrain.terrain_type == TerrainType.ROAD:
                tile.encounter_rate *= 0.3
