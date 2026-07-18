"""Multi-dimensional world system.

Supports travel between:
* Planets within a solar system
* Moons orbiting planets
* Star systems within a galaxy
* Galaxies within the universe
* Alternate dimensions (shadow realm, fae wilds, elemental planes, etc.)
* Floating islands in the sky
* Underground civilizations
* Ancient ruins across dimensions

Each dimension has its own world map, terrain, biomes, and inhabitants.
Players can travel between dimensions via portals, spells, or artifacts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


class DimensionType(IntEnum):
    MATERIAL = 0       # the "real" world
    SHADOW = 1         # mirror dimension
    FAE_WILDS = 2      # realm of fae and elves
    ELEMENTAL_FIRE = 3
    ELEMENTAL_WATER = 4
    ELEMENTAL_AIR = 5
    ELEMENTAL_EARTH = 6
    ABYSS = 7          # demon realm
    HEAVEN = 8         # celestial realm
    DREAM = 9          # dream world
    MIRROR = 10        # reflection dimension
    TIME = 11          # time-distorted dimension
    VOID = 12          # the void between dimensions
    UNDERWORLD = 13    # realm of the dead
    CHAOS = 14         # raw chaos


@dataclass
class Dimension:
    """A dimension within the multiverse."""

    dimension_id: int
    name: str
    dimension_type: DimensionType
    description: str = ""
    gravity: float = 1.0       # 1.0 = earth-normal
    time_flow: float = 1.0     # 1.0 = real-time; 0.5 = half speed; 2.0 = double
    ambient_magic: float = 0.5  # 0..1 magic density
    ambient_light: float = 0.5  # 0..1
    danger_level: int = 1
    portals_to: list[int] = field(default_factory=list)  # connected dimension_ids
    parent_dimension_id: Optional[int] = None
    planets: list[int] = field(default_factory=list)
    color: int = 244
    glyph: str = "D"
    is_accessible: bool = True
    requires_artifact: Optional[str] = None  # artifact_id needed to enter
    requires_spell: Optional[str] = None     # spell_id needed to enter
    min_level: int = 1
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension_id": self.dimension_id, "name": self.name,
            "dimension_type": int(self.dimension_type),
            "description": self.description,
            "gravity": self.gravity, "time_flow": self.time_flow,
            "ambient_magic": self.ambient_magic,
            "ambient_light": self.ambient_light,
            "danger_level": self.danger_level,
            "portals_to": list(self.portals_to),
            "parent_dimension_id": self.parent_dimension_id,
            "planets": list(self.planets),
            "color": self.color, "glyph": self.glyph,
            "is_accessible": self.is_accessible,
            "requires_artifact": self.requires_artifact,
            "requires_spell": self.requires_spell,
            "min_level": self.min_level,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Dimension":
        d = dict(data)
        d["dimension_type"] = DimensionType(d.get("dimension_type", 0))
        return cls(**d)


@dataclass
class Planet:
    """A planet within a solar system."""

    planet_id: int
    name: str
    dimension_id: int = 0
    planet_type: str = "terrestrial"  # terrestrial, gas_giant, ice, desert, ocean, lava
    radius_km: float = 6371.0
    gravity: float = 1.0
    atmosphere: str = "breathable"  # breathable, thin, toxic, none
    average_temperature: float = 15.0
    moons: list[int] = field(default_factory=list)
    orbit_distance_au: float = 1.0  # distance from star
    orbital_period_days: float = 365.25
    rotation_period_hours: float = 24.0
    population: int = 0
    tech_level: int = 1  # 1=medieval, 5=modern, 10=stellar
    color: int = 33
    glyph: str = "O"
    description: str = ""
    has_rings: bool = False
    is_colonizable: bool = True
    resources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "Planet":
        return cls(**data)


@dataclass
class Moon:
    """A moon orbiting a planet."""

    moon_id: int
    name: str
    parent_planet_id: int
    radius_km: float = 1737.0
    gravity: float = 0.16
    atmosphere: str = "none"
    orbital_period_days: float = 27.3
    color: int = 255
    glyph: str = "o"
    description: str = ""
    has_colony: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "Moon":
        return cls(**data)


@dataclass
class Galaxy:
    """A galaxy containing many star systems."""

    galaxy_id: int
    name: str
    galaxy_type: str = "spiral"  # spiral, elliptical, irregular, lenticular
    star_count: int = 100_000_000_000
    diameter_ly: float = 100_000.0  # light-years
    age_billion_years: float = 13.6
    color: int = 165
    glyph: str = "G"
    description: str = ""
    star_systems: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "Galaxy":
        return cls(**data)


@dataclass
class FloatingIsland:
    """A floating island in the sky."""

    island_id: int
    name: str
    dimension_id: int
    location: tuple[float, float, float]  # x, y, altitude
    size_km: float = 1.0
    altitude_km: float = 2.0
    biome: str = "sky_forest"
    has_population: bool = False
    population: int = 0
    has_docking: bool = True  # airships can dock
    description: str = ""
    color: int = 75
    glyph: str = "ƒ"

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["location"] = list(self.location)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FloatingIsland":
        d = dict(data)
        d["location"] = tuple(d["location"])
        return cls(**d)


@dataclass
class UndergroundCivilization:
    """An underground civilization."""

    civilization_id: int
    name: str
    dimension_id: int
    depth_m: float = 500.0
    extent_km: float = 10.0
    species: str = "dwarf"  # dwarf, drow, deep_gnome, mind_flayer, aboleth
    population: int = 0
    tech_level: int = 3
    magic_level: float = 0.5
    is_hostile: bool = False
    is_discovered: bool = False
    description: str = ""
    entrance_locations: list[tuple[int, int]] = field(default_factory=list)
    color: int = 90
    glyph: str = "U"

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["entrance_locations"] = [list(l) for l in self.entrance_locations]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "UndergroundCivilization":
        d = dict(data)
        d["entrance_locations"] = [tuple(l) for l in d.get("entrance_locations", [])]
        return cls(**d)


@dataclass
class AncientRuins:
    """Ancient ruins of a long-forgotten civilization."""

    ruins_id: int
    name: str
    dimension_id: int
    location: tuple[int, int]
    civilization_name: str = "The Forgotten"
    age_years: int = 10_000
    danger_level: int = 10
    has_treasure: bool = True
    has_guardian: bool = True
    guardian_type: str = "construct"
    is_explored: bool = False
    description: str = ""
    artifacts: list[str] = field(default_factory=list)
    color: int = 130
    glyph: str = "R"

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["location"] = list(self.location)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AncientRuins":
        d = dict(data)
        d["location"] = tuple(d["location"])
        return cls(**d)


class DimensionManager:
    """Manages all dimensions, planets, and cosmic structures."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._dimensions: dict[int, Dimension] = {}
        self._planets: dict[int, Planet] = {}
        self._moons: dict[int, Moon] = {}
        self._galaxies: dict[int, Galaxy] = {}
        self._floating_islands: dict[int, FloatingIsland] = {}
        self._underground_civs: dict[int, UndergroundCivilization] = {}
        self._ancient_ruins: dict[int, AncientRuins] = {}
        self._next_dimension_id: int = 1
        self._next_planet_id: int = 1
        self._next_moon_id: int = 1
        self._next_galaxy_id: int = 1
        self._next_island_id: int = 1
        self._next_civ_id: int = 1
        self._next_ruins_id: int = 1
        self._init_defaults()

    def _init_defaults(self) -> None:
        # Register default dimensions
        for d in DEFAULT_DIMENSIONS:
            d.dimension_id = self._next_dimension_id
            self._next_dimension_id += 1
            self._dimensions[d.dimension_id] = d
        # Register default planets in the material dimension
        material_dim = next((d for d in self._dimensions.values()
                              if d.dimension_type == DimensionType.MATERIAL), None)
        if material_dim:
            for p in DEFAULT_PLANETS:
                p.planet_id = self._next_planet_id
                p.dimension_id = material_dim.dimension_id
                self._next_planet_id += 1
                self._planets[p.planet_id] = p
                material_dim.planets.append(p.planet_id)
        # Register default galaxies
        for g in DEFAULT_GALAXIES:
            g.galaxy_id = self._next_galaxy_id
            self._next_galaxy_id += 1
            self._galaxies[g.galaxy_id] = g

    # ---------- dimensions ----------

    def create_dimension(self, name: str, dimension_type: DimensionType,
                         **kwargs: Any) -> Dimension:
        dim = Dimension(
            dimension_id=self._next_dimension_id,
            name=name, dimension_type=dimension_type, **kwargs,
        )
        self._next_dimension_id += 1
        self._dimensions[dim.dimension_id] = dim
        return dim

    def dimension(self, dimension_id: int) -> Optional[Dimension]:
        return self._dimensions.get(dimension_id)

    def all_dimensions(self) -> list[Dimension]:
        return list(self._dimensions.values())

    def dimensions_of_type(self, dim_type: DimensionType) -> list[Dimension]:
        return [d for d in self._dimensions.values() if d.dimension_type == dim_type]

    # ---------- planets ----------

    def create_planet(self, name: str, dimension_id: int,
                      **kwargs: Any) -> Planet:
        planet = Planet(
            planet_id=self._next_planet_id,
            name=name, dimension_id=dimension_id, **kwargs,
        )
        self._next_planet_id += 1
        self._planets[planet.planet_id] = planet
        dim = self._dimensions.get(dimension_id)
        if dim:
            dim.planets.append(planet.planet_id)
        return planet

    def planet(self, planet_id: int) -> Optional[Planet]:
        return self._planets.get(planet_id)

    def all_planets(self) -> list[Planet]:
        return list(self._planets.values())

    # ---------- moons ----------

    def create_moon(self, name: str, parent_planet_id: int,
                    **kwargs: Any) -> Moon:
        moon = Moon(
            moon_id=self._next_moon_id,
            name=name, parent_planet_id=parent_planet_id, **kwargs,
        )
        self._next_moon_id += 1
        self._moons[moon.moon_id] = moon
        planet = self._planets.get(parent_planet_id)
        if planet:
            planet.moons.append(moon.moon_id)
        return moon

    def moon(self, moon_id: int) -> Optional[Moon]:
        return self._moons.get(moon_id)

    # ---------- galaxies ----------

    def create_galaxy(self, name: str, **kwargs: Any) -> Galaxy:
        galaxy = Galaxy(galaxy_id=self._next_galaxy_id, name=name, **kwargs)
        self._next_galaxy_id += 1
        self._galaxies[galaxy.galaxy_id] = galaxy
        return galaxy

    def galaxy(self, galaxy_id: int) -> Optional[Galaxy]:
        return self._galaxies.get(galaxy_id)

    def all_galaxies(self) -> list[Galaxy]:
        return list(self._galaxies.values())

    # ---------- floating islands ----------

    def create_floating_island(self, name: str, dimension_id: int,
                               location: tuple[float, float, float],
                               **kwargs: Any) -> FloatingIsland:
        island = FloatingIsland(
            island_id=self._next_island_id,
            name=name, dimension_id=dimension_id,
            location=location, **kwargs,
        )
        self._next_island_id += 1
        self._floating_islands[island.island_id] = island
        return island

    def floating_island(self, island_id: int) -> Optional[FloatingIsland]:
        return self._floating_islands.get(island_id)

    def all_floating_islands(self) -> list[FloatingIsland]:
        return list(self._floating_islands.values())

    # ---------- underground civilizations ----------

    def create_underground_civilization(self, name: str, dimension_id: int,
                                          **kwargs: Any) -> UndergroundCivilization:
        civ = UndergroundCivilization(
            civilization_id=self._next_civ_id,
            name=name, dimension_id=dimension_id, **kwargs,
        )
        self._next_civ_id += 1
        self._underground_civs[civ.civilization_id] = civ
        return civ

    def underground_civilization(self, civ_id: int) -> Optional[UndergroundCivilization]:
        return self._underground_civs.get(civ_id)

    def all_underground_civilizations(self) -> list[UndergroundCivilization]:
        return list(self._underground_civs.values())

    # ---------- ancient ruins ----------

    def create_ancient_ruins(self, name: str, dimension_id: int,
                              location: tuple[int, int],
                              **kwargs: Any) -> AncientRuins:
        ruins = AncientRuins(
            ruins_id=self._next_ruins_id,
            name=name, dimension_id=dimension_id,
            location=location, **kwargs,
        )
        self._next_ruins_id += 1
        self._ancient_ruins[ruins.ruins_id] = ruins
        return ruins

    def ancient_ruins(self, ruins_id: int) -> Optional[AncientRuins]:
        return self._ancient_ruins.get(ruins_id)

    def all_ancient_ruins(self) -> list[AncientRuins]:
        return list(self._ancient_ruins.values())

    # ---------- travel ----------

    def can_travel(self, from_dim_id: int, to_dim_id: int) -> tuple[bool, str]:
        """Check if travel between dimensions is possible."""
        from_dim = self._dimensions.get(from_dim_id)
        to_dim = self._dimensions.get(to_dim_id)
        if from_dim is None or to_dim is None:
            return False, "Dimension not found."
        if not to_dim.is_accessible:
            return False, f"{to_dim.name} is not accessible."
        if to_dim_id not in from_dim.portals_to:
            return False, f"No portal from {from_dim.name} to {to_dim.name}."
        if to_dim.requires_artifact:
            return False, f"Requires artifact: {to_dim.requires_artifact}"
        if to_dim.requires_spell:
            return False, f"Requires spell: {to_dim.requires_spell}"
        return True, ""

    def open_portal(self, from_dim_id: int, to_dim_id: int) -> bool:
        """Open a portal between two dimensions (bidirectional)."""
        from_dim = self._dimensions.get(from_dim_id)
        to_dim = self._dimensions.get(to_dim_id)
        if from_dim is None or to_dim is None:
            return False
        if to_dim_id not in from_dim.portals_to:
            from_dim.portals_to.append(to_dim_id)
        if from_dim_id not in to_dim.portals_to:
            to_dim.portals_to.append(from_dim_id)
        return True

    def close_portal(self, from_dim_id: int, to_dim_id: int) -> bool:
        from_dim = self._dimensions.get(from_dim_id)
        to_dim = self._dimensions.get(to_dim_id)
        if from_dim is None or to_dim is None:
            return False
        if to_dim_id in from_dim.portals_to:
            from_dim.portals_to.remove(to_dim_id)
        if from_dim_id in to_dim.portals_to:
            to_dim.portals_to.remove(from_dim_id)
        return True

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimensions": {str(d.dimension_id): d.to_dict()
                           for d in self._dimensions.values()},
            "planets": {str(p.planet_id): p.to_dict()
                        for p in self._planets.values()},
            "moons": {str(m.moon_id): m.to_dict()
                      for m in self._moons.values()},
            "galaxies": {str(g.galaxy_id): g.to_dict()
                         for g in self._galaxies.values()},
            "floating_islands": {str(i.island_id): i.to_dict()
                                  for i in self._floating_islands.values()},
            "underground_civs": {str(c.civilization_id): c.to_dict()
                                  for c in self._underground_civs.values()},
            "ancient_ruins": {str(r.ruins_id): r.to_dict()
                               for r in self._ancient_ruins.values()},
            "next_dimension_id": self._next_dimension_id,
            "next_planet_id": self._next_planet_id,
            "next_moon_id": self._next_moon_id,
            "next_galaxy_id": self._next_galaxy_id,
            "next_island_id": self._next_island_id,
            "next_civ_id": self._next_civ_id,
            "next_ruins_id": self._next_ruins_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DimensionManager":
        mgr = cls()
        mgr._dimensions = {
            int(did): Dimension.from_dict(d) for did, d in data.get("dimensions", {}).items()
        }
        mgr._planets = {
            int(pid): Planet.from_dict(p) for pid, p in data.get("planets", {}).items()
        }
        mgr._moons = {
            int(mid): Moon.from_dict(m) for mid, m in data.get("moons", {}).items()
        }
        mgr._galaxies = {
            int(gid): Galaxy.from_dict(g) for gid, g in data.get("galaxies", {}).items()
        }
        mgr._floating_islands = {
            int(iid): FloatingIsland.from_dict(i) for iid, i in data.get("floating_islands", {}).items()
        }
        mgr._underground_civs = {
            int(cid): UndergroundCivilization.from_dict(c)
            for cid, c in data.get("underground_civs", {}).items()
        }
        mgr._ancient_ruins = {
            int(rid): AncientRuins.from_dict(r)
            for rid, r in data.get("ancient_ruins", {}).items()
        }
        mgr._next_dimension_id = data.get("next_dimension_id", 1)
        mgr._next_planet_id = data.get("next_planet_id", 1)
        mgr._next_moon_id = data.get("next_moon_id", 1)
        mgr._next_galaxy_id = data.get("next_galaxy_id", 1)
        mgr._next_island_id = data.get("next_island_id", 1)
        mgr._next_civ_id = data.get("next_civ_id", 1)
        mgr._next_ruins_id = data.get("next_ruins_id", 1)
        return mgr


# ---------- Defaults ----------

DEFAULT_DIMENSIONS: list[Dimension] = [
    Dimension(
        dimension_id=0, name="Material Plane",
        dimension_type=DimensionType.MATERIAL,
        description="The mortal world, home to most life.",
        gravity=1.0, time_flow=1.0, ambient_magic=0.3,
        ambient_light=0.7, danger_level=1,
        color=33, glyph="M",
        is_accessible=True, min_level=1,
        tags=["material", "mortal"],
    ),
    Dimension(
        dimension_id=0, name="Shadowfell",
        dimension_type=DimensionType.SHADOW,
        description="A dark mirror of the material plane, drained of color and life.",
        gravity=1.0, time_flow=0.5, ambient_magic=0.6,
        ambient_light=0.2, danger_level=8,
        portals_to=[], color=90, glyph="S",
        is_accessible=True, min_level=15,
        tags=["shadow", "dark"],
    ),
    Dimension(
        dimension_id=0, name="Feywild",
        dimension_type=DimensionType.FAE_WILDS,
        description="A vibrant realm of eternal twilight, home to fae and elves.",
        gravity=0.8, time_flow=2.0, ambient_magic=0.9,
        ambient_light=0.6, danger_level=6,
        portals_to=[], color=41, glyph="F",
        is_accessible=True, min_level=10,
        tags=["fae", "magical"],
    ),
    Dimension(
        dimension_id=0, name="Plane of Fire",
        dimension_type=DimensionType.ELEMENTAL_FIRE,
        description="An endless expanse of flame and molten rock.",
        gravity=0.9, time_flow=1.0, ambient_magic=1.0,
        ambient_light=1.0, danger_level=15,
        portals_to=[], color=196, glyph="P",
        is_accessible=True, min_level=25,
        requires_spell="planar_travel",
        tags=["elemental", "fire"],
    ),
    Dimension(
        dimension_id=0, name="Plane of Water",
        dimension_type=DimensionType.ELEMENTAL_WATER,
        description="An infinite ocean with no surface or floor.",
        gravity=1.1, time_flow=1.0, ambient_magic=1.0,
        ambient_light=0.3, danger_level=12,
        portals_to=[], color=33, glyph="P",
        is_accessible=True, min_level=20,
        requires_spell="planar_travel",
        tags=["elemental", "water"],
    ),
    Dimension(
        dimension_id=0, name="Plane of Air",
        dimension_type=DimensionType.ELEMENTAL_AIR,
        description="Endless sky with floating islands of cloud and stone.",
        gravity=0.3, time_flow=1.0, ambient_magic=1.0,
        ambient_light=0.9, danger_level=10,
        portals_to=[], color=255, glyph="P",
        is_accessible=True, min_level=18,
        requires_spell="planar_travel",
        tags=["elemental", "air"],
    ),
    Dimension(
        dimension_id=0, name="Plane of Earth",
        dimension_type=DimensionType.ELEMENTAL_EARTH,
        description="Solid rock extending in all directions, tunnelled by elementals.",
        gravity=1.5, time_flow=1.0, ambient_magic=1.0,
        ambient_light=0.1, danger_level=14,
        portals_to=[], color=130, glyph="P",
        is_accessible=True, min_level=22,
        requires_spell="planar_travel",
        tags=["elemental", "earth"],
    ),
    Dimension(
        dimension_id=0, name="The Abyss",
        dimension_type=DimensionType.ABYSS,
        description="A layered hell of demons and chaos.",
        gravity=1.2, time_flow=0.3, ambient_magic=1.0,
        ambient_light=0.2, danger_level=30,
        portals_to=[], color=88, glyph="A",
        is_accessible=True, min_level=40,
        requires_artifact="abyssal_key",
        tags=["abyss", "evil", "demonic"],
    ),
    Dimension(
        dimension_id=0, name="Celestial Heavens",
        dimension_type=DimensionType.HEAVEN,
        description="The radiant realm of angels and the divine.",
        gravity=0.7, time_flow=2.0, ambient_magic=1.0,
        ambient_light=1.0, danger_level=25,
        portals_to=[], color=255, glyph="H",
        is_accessible=True, min_level=35,
        requires_artifact="celestial_chariot",
        tags=["heaven", "good", "divine"],
    ),
    Dimension(
        dimension_id=0, name="Dreamlands",
        dimension_type=DimensionType.DREAM,
        description="The realm of dreams, where reality bends to thought.",
        gravity=0.5, time_flow=10.0, ambient_magic=0.8,
        ambient_light=0.5, danger_level=5,
        portals_to=[], color=165, glyph="D",
        is_accessible=True, min_level=8,
        requires_spell="dream_walk",
        tags=["dream", "psychic"],
    ),
    Dimension(
        dimension_id=0, name="The Void",
        dimension_type=DimensionType.VOID,
        description="The nothingness between dimensions.",
        gravity=0.0, time_flow=0.0, ambient_magic=0.0,
        ambient_light=0.0, danger_level=50,
        portals_to=[], color=232, glyph="V",
        is_accessible=False, min_level=100,
        requires_artifact="voidcompass",
        tags=["void", "forbidden"],
    ),
    Dimension(
        dimension_id=0, name="Underworld",
        dimension_type=DimensionType.UNDERWORLD,
        description="The realm of the dead, where all souls eventually journey.",
        gravity=1.0, time_flow=0.1, ambient_magic=0.7,
        ambient_light=0.2, danger_level=20,
        portals_to=[], color=58, glyph="U",
        is_accessible=True, min_level=30,
        requires_spell="death_gate",
        tags=["underworld", "death"],
    ),
]

DEFAULT_PLANETS: list[Planet] = [
    Planet(
        planet_id=0, name="Aethon",
        planet_type="terrestrial",
        radius_km=6371.0, gravity=1.0,
        atmosphere="breathable",
        average_temperature=15.0,
        orbit_distance_au=1.0,
        orbital_period_days=365.25,
        rotation_period_hours=24.0,
        population=10_000_000,
        tech_level=3,
        color=33, glyph="O",
        description="The main world, home to the mortal races.",
        resources=["iron", "copper", "gold", "wood", "stone", "crystal"],
    ),
    Planet(
        planet_id=0, name="Pyralis",
        planet_type="lava",
        radius_km=4500.0, gravity=0.8,
        atmosphere="toxic",
        average_temperature=800.0,
        orbit_distance_au=0.4,
        orbital_period_days=88.0,
        rotation_period_hours=1408.0,
        population=0, tech_level=0,
        color=196, glyph="O",
        description="A scorched lava-world close to the sun.",
        resources=["sulphur", "obsidian", "mithril", "fire_crystal"],
        is_colonizable=False,
    ),
    Planet(
        planet_id=0, name="Galadria",
        planet_type="ocean",
        radius_km=7200.0, gravity=1.1,
        atmosphere="breathable",
        average_temperature=12.0,
        orbit_distance_au=1.2,
        orbital_period_days=440.0,
        rotation_period_hours=26.0,
        population=500_000,
        tech_level=4,
        color=33, glyph="O",
        description="A vast water-world with floating cities.",
        resources=["fish", "pearls", "coral", "deep_crystal"],
        has_rings=False,
    ),
    Planet(
        planet_id=0, name="Króll",
        planet_type="ice",
        radius_km=5200.0, gravity=0.9,
        atmosphere="thin",
        average_temperature=-50.0,
        orbit_distance_au=5.0,
        orbital_period_days=3650.0,
        rotation_period_hours=30.0,
        population=50_000,
        tech_level=2,
        color=255, glyph="O",
        description="A frozen ice-world with deep frozen oceans.",
        resources=["ice", "frost_crystal", "ancient_remains"],
        has_rings=True,
    ),
    Planet(
        planet_id=0, name="Verdant",
        planet_type="terrestrial",
        radius_km=8000.0, gravity=1.3,
        atmosphere="breathable",
        average_temperature=25.0,
        orbit_distance_au=1.5,
        orbital_period_days=500.0,
        rotation_period_hours=28.0,
        population=5_000_000,
        tech_level=2,
        color=41, glyph="O",
        description="A lush jungle world teeming with life.",
        resources=["rare_herbs", "exotic_wood", "venom", "crystal"],
    ),
]

DEFAULT_GALAXIES: list[Galaxy] = [
    Galaxy(
        galaxy_id=0, name="The Milky Way",
        galaxy_type="spiral",
        star_count=200_000_000_000,
        diameter_ly=100_000.0,
        age_billion_years=13.6,
        color=255, glyph="G",
        description="The home galaxy.",
    ),
    Galaxy(
        galaxy_id=0, name="Andromeda",
        galaxy_type="spiral",
        star_count=1_000_000_000_000,
        diameter_ly=220_000.0,
        age_billion_years=10.0,
        color=165, glyph="G",
        description="A nearby spiral galaxy.",
    ),
    Galaxy(
        galaxy_id=0, name="Triangulum",
        galaxy_type="spiral",
        star_count=40_000_000_000,
        diameter_ly=60_000.0,
        age_billion_years=12.0,
        color=75, glyph="G",
        description="The third-largest in the local group.",
    ),
]
