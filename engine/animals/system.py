"""Animal simulation — species, populations, migration, reproduction, evolution, domestication.

Each species has its own population tracked over the world map. Animals
migrate seasonally, reproduce based on food availability, evolve over
generations, and can be domesticated into livestock.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.utils.rng import RNG
from engine.world.map import WorldMap


class AnimalType(IntEnum):
    PREDATOR = 0
    HERBIVORE = 1
    OMNIVORE = 2
    SCAVENGER = 3
    INSECT = 4
    FISH = 5
    BIRD = 6
    REPTILE = 7
    MAGICAL = 8


@dataclass
class AnimalSpecies:
    """A species definition."""

    id: str
    name: str
    animal_type: AnimalType
    base_hp: int = 20
    base_strength: int = 8
    base_agility: int = 10
    base_speed: float = 1.0
    size: str = "medium"  # tiny, small, medium, large, huge
    diet: str = "carnivore"  # carnivore, herbivore, omnivore
    habitat_biomes: list[str] = field(default_factory=list)
    aggression: float = 0.3  # 0..1
    intelligence: float = 0.1  # 0..1
    magical: bool = False
    tamable: bool = False
    domesticatable: bool = False
    mountable: bool = False
    milkable: bool = False
    shearable: bool = False
    egg_laying: bool = False
    reproduction_rate: float = 0.2  # per month
    max_age: int = 15
    migration_pattern: str = "sedentary"  # sedentary, seasonal, nomadic
    predator_of: list[str] = field(default_factory=list)
    prey_of: list[str] = field(default_factory=list)
    value_copper: int = 5
    color: int = 244
    glyph: str = "a"
    tags: list[str] = field(default_factory=list)
    description: str = ""


class AnimalLibrary:
    """Registry of animal species."""

    _species: ClassVar[dict[str, AnimalSpecies]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, species: AnimalSpecies) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._species[species.id] = species

    @classmethod
    def get(cls, species_id: str) -> Optional[AnimalSpecies]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._species.get(species_id)

    @classmethod
    def all(cls) -> list[AnimalSpecies]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._species.values())

    @classmethod
    def by_type(cls, animal_type: AnimalType) -> list[AnimalSpecies]:
        return [s for s in cls.all() if s.animal_type == animal_type]

    @classmethod
    def by_biome(cls, biome: str) -> list[AnimalSpecies]:
        return [s for s in cls.all() if biome in s.habitat_biomes or not s.habitat_biomes]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for s in DEFAULT_SPECIES:
            cls._species[s.id] = s
        cls._defaults_loaded = True


@dataclass
class MigrationPattern:
    """A seasonal migration route."""

    species_id: str
    route: list[tuple[int, int]]  # waypoints
    season_start: int = 0  # 0=spring, 1=summer, 2=autumn, 3=winter
    speed_per_day: float = 5.0
    current_waypoint: int = 0
    active: bool = False


@dataclass
class AnimalPopulation:
    """A regional population of a species."""

    species_id: str
    region_id: int
    location: tuple[int, int]
    count: int = 0
    max_count: int = 100  # carrying capacity
    food_available: float = 1.0  # 0..1
    last_reproduction_tick: float = 0.0
    avg_strength: float = 0.0
    avg_agility: float = 0.0
    generation: int = 0
    traits: dict[str, float] = field(default_factory=dict)  # evolved traits

    def reproduce(self, dt_months: float, rng: RNG) -> int:
        """Returns the number of new births."""
        rate = AnimalLibrary.get(self.species_id).reproduction_rate if AnimalLibrary.get(self.species_id) else 0.2
        # Carrying capacity constraint
        capacity_factor = 1.0 - (self.count / max(1, self.max_count))
        births = int(self.count * rate * dt_months * capacity_factor * self.food_available)
        births = max(0, min(births, self.max_count - self.count))
        self.count += births
        return births

    def starve(self, dt_months: float, rng: RNG) -> int:
        """Returns the number of deaths from starvation."""
        if self.food_available > 0.5:
            return 0
        deaths = int(self.count * (1.0 - self.food_available) * 0.1 * dt_months)
        self.count = max(0, self.count - deaths)
        return deaths

    def evolve(self, dt_months: float, rng: RNG) -> None:
        """Apply micro-evolution to the population over generations."""
        self.generation += int(dt_months * 12)
        species = AnimalLibrary.get(self.species_id)
        if species is None:
            return
        # Slight trait drift based on selection pressure
        for trait in ("strength", "agility", "endurance"):
            current = self.traits.get(trait, 0.5)
            mutation = rng.gauss(0, 0.01)
            # Selection: low food favours efficiency (lower strength, higher endurance)
            if self.food_available < 0.5 and trait == "endurance":
                mutation += 0.005
            self.traits[trait] = max(0.0, min(1.0, current + mutation))
        self.avg_strength = species.base_strength * (0.8 + self.traits.get("strength", 0.5) * 0.4)
        self.avg_agility = species.base_agility * (0.8 + self.traits.get("agility", 0.5) * 0.4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "species_id": self.species_id, "region_id": self.region_id,
            "location": self.location, "count": self.count,
            "max_count": self.max_count, "food_available": self.food_available,
            "last_reproduction_tick": self.last_reproduction_tick,
            "avg_strength": self.avg_strength, "avg_agility": self.avg_agility,
            "generation": self.generation, "traits": dict(self.traits),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnimalPopulation":
        return cls(
            species_id=data["species_id"], region_id=data["region_id"],
            location=tuple(data["location"]),
            count=data.get("count", 0),
            max_count=data.get("max_count", 100),
            food_available=data.get("food_available", 1.0),
            last_reproduction_tick=data.get("last_reproduction_tick", 0.0),
            avg_strength=data.get("avg_strength", 0.0),
            avg_agility=data.get("avg_agility", 0.0),
            generation=data.get("generation", 0),
            traits=dict(data.get("traits", {})),
        )


class DomesticationState:
    """Tracks domestication progress of a species by an entity/faction."""

    def __init__(self) -> None:
        # (species_id, owner_id) -> progress 0..1
        self._progress: dict[tuple[str, int], float] = {}
        self._domesticated: set[tuple[str, int]] = set()

    def tame_attempt(self, species_id: str, owner_id: int,
                     skill_level: int, rng: RNG) -> tuple[bool, float]:
        """Attempt to tame a creature. Returns (success, progress_delta)."""
        species = AnimalLibrary.get(species_id)
        if species is None or not species.tamable:
            return False, 0.0
        key = (species_id, owner_id)
        current = self._progress.get(key, 0.0)
        delta = min(1.0 - current, 0.05 + skill_level * 0.005)
        success = rng.chance(0.3 + skill_level * 0.02)
        if success:
            self._progress[key] = min(1.0, current + delta)
            if self._progress[key] >= 1.0:
                self._domesticated.add(key)
        return success, delta if success else 0.0

    def is_domesticated(self, species_id: str, owner_id: int) -> bool:
        return (species_id, owner_id) in self._domesticated

    def progress(self, species_id: str, owner_id: int) -> float:
        return self._progress.get((species_id, owner_id), 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "progress": {f"{k[0]}:{k[1]}": v for k, v in self._progress.items()},
            "domesticated": [f"{s}:{o}" for s, o in self._domesticated],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DomesticationState":
        ds = cls()
        for key_str, val in data.get("progress", {}).items():
            species_id, owner_id = key_str.split(":")
            ds._progress[(species_id, int(owner_id))] = val
        for key_str in data.get("domesticated", []):
            species_id, owner_id = key_str.split(":")
            ds._domesticated.add((species_id, int(owner_id)))
        return ds


class LivestockManager:
    """Manages livestock owned by entities/factions."""

    def __init__(self) -> None:
        # (owner_id, species_id) -> count
        self._herds: dict[tuple[int, str], int] = {}

    def add_livestock(self, owner_id: int, species_id: str, count: int = 1) -> None:
        key = (owner_id, species_id)
        self._herds[key] = self._herds.get(key, 0) + count

    def remove_livestock(self, owner_id: int, species_id: str, count: int = 1) -> int:
        key = (owner_id, species_id)
        cur = self._herds.get(key, 0)
        removed = min(cur, count)
        self._herds[key] = cur - removed
        if self._herds[key] <= 0:
            del self._herds[key]
        return removed

    def count(self, owner_id: int, species_id: str) -> int:
        return self._herds.get((owner_id, species_id), 0)

    def herd_of(self, owner_id: int) -> dict[str, int]:
        return {sid: c for (oid, sid), c in self._herds.items() if oid == owner_id}

    def milk_yield_per_month(self, owner_id: int) -> int:
        """Returns litres of milk produced per game-month."""
        total = 0
        for (oid, sid), count in self._herds.items():
            if oid != owner_id:
                continue
            species = AnimalLibrary.get(sid)
            if species and species.milkable:
                total += count * 10  # 10 litres per milkable animal per month
        return total

    def egg_yield_per_month(self, owner_id: int) -> int:
        total = 0
        for (oid, sid), count in self._herds.items():
            if oid != owner_id:
                continue
            species = AnimalLibrary.get(sid)
            if species and species.egg_laying:
                total += count * 20
        return total

    def to_dict(self) -> dict[str, Any]:
        return {f"{k[0]}:{k[1]}": v for k, v in self._herds.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "LivestockManager":
        lm = cls()
        for key_str, val in data.items():
            owner_id, species_id = key_str.split(":")
            lm._herds[(int(owner_id), species_id)] = val
        return lm


class AnimalSimulator:
    """Top-level animal simulation coordinator."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self.populations: list[AnimalPopulation] = []
        self.migrations: list[MigrationPattern] = []
        self.domestication = DomesticationState()
        self.livestock = LivestockManager()

    def seed_population(self, species_id: str, region_id: int,
                        location: tuple[int, int], count: int) -> AnimalPopulation:
        species = AnimalLibrary.get(species_id)
        if species is None:
            raise ValueError(f"Unknown species: {species_id}")
        pop = AnimalPopulation(
            species_id=species_id, region_id=region_id, location=location,
            count=count, max_count=count * 10,
            avg_strength=species.base_strength,
            avg_agility=species.base_agility,
        )
        self.populations.append(pop)
        return pop

    def populate_world(self, world_map: WorldMap) -> None:
        """Seed initial animal populations across the world."""
        biomes_seen: dict[str, list[tuple[int, int]]] = {}
        for tile in world_map.iter_tiles():
            biomes_seen.setdefault(tile.biome_type, []).append((tile.x, tile.y))
        for species in AnimalLibrary.all():
            habitat = species.habitat_biomes or list(biomes_seen.keys())
            for biome in habitat:
                if biome not in biomes_seen:
                    continue
                # Place 1-3 populations per biome
                samples = min(3, len(biomes_seen[biome]) // 100 + 1)
                for _ in range(samples):
                    location = self.rng.choice(biomes_seen[biome])
                    count = self.rng.randint(5, 20)
                    self.seed_population(species.id, 0, location, count)

    def update(self, dt_months: float, current_tick: float = 0.0) -> None:
        """Advance all animal populations."""
        for pop in self.populations:
            # Food availability fluctuates
            pop.food_available = max(0.1, min(1.0,
                pop.food_available + self.rng.gauss(0, 0.05)))
            pop.reproduce(dt_months, self.rng)
            pop.starve(dt_months, self.rng)
            pop.evolve(dt_months, self.rng)

    def hunt(self, species_id: str, region_id: int, hunters: int,
             skill_level: int) -> int:
        """Hunt animals of a species. Returns the number killed."""
        for pop in self.populations:
            if pop.species_id != species_id or pop.region_id != region_id:
                continue
            # Success rate based on skill and population density
            success_rate = 0.3 + skill_level * 0.02
            killed = 0
            for _ in range(hunters):
                if self.rng.chance(success_rate) and pop.count > 0:
                    killed += 1
                    pop.count -= 1
            return killed
        return 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "populations": [p.to_dict() for p in self.populations],
            "migrations": [
                {"species_id": m.species_id, "route": m.route,
                 "season_start": m.season_start, "speed_per_day": m.speed_per_day,
                 "current_waypoint": m.current_waypoint, "active": m.active}
                for m in self.migrations
            ],
            "domestication": self.domestication.to_dict(),
            "livestock": self.livestock.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnimalSimulator":
        sim = cls()
        sim.populations = [AnimalPopulation.from_dict(p) for p in data.get("populations", [])]
        sim.migrations = [
            MigrationPattern(
                species_id=m["species_id"], route=[tuple(w) for w in m["route"]],
                season_start=m.get("season_start", 0),
                speed_per_day=m.get("speed_per_day", 5.0),
                current_waypoint=m.get("current_waypoint", 0),
                active=m.get("active", False),
            )
            for m in data.get("migrations", [])
        ]
        sim.domestication = DomesticationState.from_dict(data.get("domestication", {}))
        sim.livestock = LivestockManager.from_dict(data.get("livestock", {}))
        return sim


# ---------- Default species catalogue ----------

DEFAULT_SPECIES: list[AnimalSpecies] = [
    # Predators
    AnimalSpecies("wolf", "Wolf", AnimalType.PREDATOR, 25, 8, 14, 1.2,
                  "medium", "carnivore", ["boreal_forest", "temperate_forest", "grassland", "tundra"],
                  0.6, 0.4, tamable=True, domesticatable=True,
                  reproduction_rate=0.25, max_age=12,
                  migration_pattern="seasonal", predator_of=["deer", "rabbit", "sheep"],
                  value_copper=15, color=240, glyph="w", description="Pack-hunting canid."),
    AnimalSpecies("bear", "Bear", AnimalType.PREDATOR, 80, 16, 8, 0.8,
                  "large", "omnivore", ["boreal_forest", "temperate_forest", "mountain", "alpine"],
                  0.5, 0.5, tamable=False, reproduction_rate=0.1, max_age=25,
                  predator_of=["deer", "fish", "rabbit"],
                  value_copper=80, color=130, glyph="B", description="Powerful omnivore."),
    AnimalSpecies("lion", "Lion", AnimalType.PREDATOR, 60, 14, 12, 1.0,
                  "large", "carnivore", ["savanna", "grassland"],
                  0.7, 0.5, reproduction_rate=0.15, max_age=18,
                  predator_of=["deer", "zebra", "antelope"],
                  value_copper=120, color=215, glyph="L", description="Pride-hunting great cat."),
    AnimalSpecies("tiger", "Tiger", AnimalType.PREDATOR, 70, 16, 14, 1.1,
                  "large", "carnivore", ["tropical_rainforest", "tropical_seasonal_forest"],
                  0.6, 0.5, reproduction_rate=0.12, max_age=20,
                  predator_of=["deer", "boar"],
                  value_copper=150, color=208, glyph="T", description="Solitary apex predator."),
    AnimalSpecies("shark", "Shark", AnimalType.PREDATOR, 50, 12, 12, 1.5,
                  "large", "carnivore", ["ocean"],
                  0.8, 0.2, reproduction_rate=0.05, max_age=30,
                  predator_of=["fish"],
                  value_copper=50, color=243, glyph="s", description="Ocean apex predator."),
    # Herbivores
    AnimalSpecies("deer", "Deer", AnimalType.HERBIVORE, 18, 4, 14, 1.3,
                  "medium", "herbivore", ["temperate_forest", "boreal_forest", "grassland"],
                  0.2, 0.3, tamable=False, reproduction_rate=0.3, max_age=15,
                  migration_pattern="seasonal", prey_of=["wolf", "bear", "lion", "tiger"],
                  value_copper=20, color=130, glyph="d", description="Skittish forest herbivore."),
    AnimalSpecies("rabbit", "Rabbit", AnimalType.HERBIVORE, 4, 1, 12, 1.0,
                  "small", "herbivore", ["grassland", "temperate_forest", "savanna"],
                  0.1, 0.2, tamable=True, domesticatable=True, reproduction_rate=0.8, max_age=8,
                  prey_of=["wolf", "fox", "eagle", "snake"],
                  value_copper=3, color=255, glyph="r", description="Prolific breeder."),
    AnimalSpecies("horse", "Horse", AnimalType.HERBIVORE, 50, 10, 14, 1.6,
                  "large", "herbivore", ["grassland", "savanna"],
                  0.3, 0.5, tamable=True, domesticatable=True, mountable=True,
                  reproduction_rate=0.15, max_age=25,
                  prey_of=["wolf", "lion"],
                  value_copper=200, color=130, glyph="h", description="Mountable steed."),
    AnimalSpecies("cow", "Cow", AnimalType.HERBIVORE, 60, 12, 6, 0.6,
                  "large", "herbivore", ["grassland"],
                  0.1, 0.4, domesticatable=True, milkable=True,
                  reproduction_rate=0.2, max_age=20,
                  value_copper=150, color=244, glyph="c", description="Milkable bovine."),
    AnimalSpecies("sheep", "Sheep", AnimalType.HERBIVORE, 30, 5, 8, 0.7,
                  "medium", "herbivore", ["grassland", "hills"],
                  0.1, 0.3, domesticatable=True, shearable=True, milkable=True,
                  reproduction_rate=0.3, max_age=12,
                  prey_of=["wolf"],
                  value_copper=40, color=255, glyph="s", description="Wool-bearing ruminant."),
    AnimalSpecies("pig", "Pig", AnimalType.OMNIVORE, 40, 8, 6, 0.6,
                  "medium", "omnivore", ["temperate_forest", "grassland"],
                  0.2, 0.4, domesticatable=True,
                  reproduction_rate=0.4, max_age=15,
                  value_copper=60, color=208, glyph="p", description="Intelligent omnivore."),
    AnimalSpecies("chicken", "Chicken", AnimalType.HERBIVORE, 3, 1, 8, 0.5,
                  "small", "herbivore", ["grassland", "savanna"],
                  0.1, 0.2, domesticatable=True, egg_laying=True,
                  reproduction_rate=0.6, max_age=8,
                  prey_of=["fox", "snake", "eagle"],
                  value_copper=5, color=215, glyph="c", description="Egg-laying fowl."),
    # Birds
    AnimalSpecies("eagle", "Eagle", AnimalType.PREDATOR, 15, 5, 16, 1.8,
                  "small", "carnivore", ["mountain", "alpine", "hills"],
                  0.4, 0.5, reproduction_rate=0.1, max_age=20,
                  predator_of=["rabbit", "fish", "chicken"],
                  value_copper=50, color=215, glyph="e", description="Soaring raptor."),
    AnimalSpecies("owl", "Owl", AnimalType.PREDATOR, 8, 3, 14, 1.2,
                  "small", "carnivore", ["temperate_forest", "boreal_forest"],
                  0.3, 0.5, reproduction_rate=0.15, max_age=15,
                  predator_of=["rabbit", "rat"],
                  value_copper=30, color=255, glyph="o", description="Nocturnal hunter."),
    # Reptiles
    AnimalSpecies("snake", "Snake", AnimalType.PREDATOR, 8, 3, 10, 0.8,
                  "small", "carnivore", ["hot_desert", "savanna", "tropical_rainforest"],
                  0.4, 0.2, reproduction_rate=0.2, max_age=12,
                  predator_of=["rabbit", "rat", "chicken"],
                  value_copper=10, color=41, glyph="s", description="Legless reptile."),
    # Fish
    AnimalSpecies("fish", "Fish", AnimalType.FISH, 2, 1, 8, 1.0,
                  "tiny", "carnivore", ["ocean", "river", "lake"],
                  0.0, 0.05, reproduction_rate=0.7, max_age=5,
                  value_copper=2, color=33, glyph="f", description="Aquatic vertebrate."),
    # Insects
    AnimalSpecies("bee", "Bee", AnimalType.INSECT, 1, 0, 8, 0.5,
                  "tiny", "herbivore", ["grassland", "temperate_forest"],
                  0.1, 0.1, domesticatable=True,
                  reproduction_rate=0.5, max_age=1,
                  value_copper=1, color=215, glyph="b", description="Honey-producing insect."),
    # Magical
    AnimalSpecies("unicorn", "Unicorn", AnimalType.MAGICAL, 80, 14, 16, 1.5,
                  "large", "herbivore", ["temperate_forest", "temperate_rainforest"],
                  0.2, 0.8, magical=True, tamable=True, mountable=True,
                  reproduction_rate=0.05, max_age=50,
                  value_copper=2000, color=255, glyph="U",
                  description="Rare magical horned equine."),
    AnimalSpecies("dragon", "Dragon", AnimalType.MAGICAL, 300, 30, 12, 1.5,
                  "huge", "carnivore", ["mountain", "high_mountain", "volcano"],
                  0.9, 0.9, magical=True, tamable=False,
                  reproduction_rate=0.02, max_age=500,
                  predator_of=["cow", "horse", "human"],
                  value_copper=10000, color=196, glyph="D",
                  description="Ancient fire-breathing apex predator."),
    AnimalSpecies("phoenix", "Phoenix", AnimalType.MAGICAL, 60, 12, 18, 2.0,
                  "medium", "carnivore", ["volcano", "hot_desert"],
                  0.5, 0.9, magical=True,
                  reproduction_rate=0.01, max_age=1000,
                  value_copper=5000, color=215, glyph="P",
                  description="Reborn-from-ashes firebird."),
    AnimalSpecies("griffin", "Griffin", AnimalType.MAGICAL, 90, 16, 16, 1.7,
                  "large", "carnivore", ["mountain", "hills"],
                  0.6, 0.7, magical=True, tamable=True, mountable=True,
                  reproduction_rate=0.04, max_age=80,
                  value_copper=3000, color=215, glyph="G",
                  description="Lion-eagle hybrid."),
    # Scavengers
    AnimalSpecies("rat", "Rat", AnimalType.SCAVENGER, 3, 1, 10, 0.8,
                  "tiny", "omnivore", ["grassland", "temperate_forest", "wetland"],
                  0.2, 0.3, reproduction_rate=0.9, max_age=4,
                  prey_of=["owl", "snake", "cat"],
                  value_copper=1, color=240, glyph="r", description="Prolific pest."),
    AnimalSpecies("vulture", "Vulture", AnimalType.SCAVENGER, 12, 4, 10, 1.2,
                  "small", "carnivore", ["savanna", "hot_desert"],
                  0.2, 0.3, reproduction_rate=0.1, max_age=25,
                  value_copper=10, color=240, glyph="v", description="Carrion-eater."),
]
