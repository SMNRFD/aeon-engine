"""Structures — buildings and placeable features on the world map.

Structures are static entities placed on the world map: houses, shops,
temples, inns, towers, dungeons entrances, shrines, ruins, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


class StructureType(IntEnum):
    HOUSE = 0
    SHOP = 1
    INN = 2
    TEMPLE = 3
    TOWER = 4
    SHRINE = 5
    RUIN = 6
    DUNGEON_ENTRANCE = 7
    CAVE_ENTRANCE = 8
    MINE_ENTRANCE = 9
    FORTRESS = 10
    CASTLE = 11
    FARM = 12
    MILL = 13
    BRIDGE = 14
    ROAD = 15
    WALL = 16
    GATE = 17
    DOCK = 18
    HARBOR = 19
    LIGHTHOUSE = 20
    CAMP = 21
    CEMETERY = 22
    GRAVE = 23
    FOUNTAIN = 24
    WELL = 25
    STATUE = 26
    ALTAR = 27
    PORTAL = 28
    OBELISK = 29
    TREEHOUSE = 30
    TREE_GROVE = 31
    WATCHTOWER = 32
    BARRACKS = 33
    STABLE = 34
    SMITHY = 35
    TAVERN = 36
    MARKET = 37
    BANK = 38
    GUILDHALL = 39
    LIBRARY = 40
    UNIVERSITY = 41
    HOSPITAL = 42
    PRISON = 43
    ARENA = 44
    THEATRE = 45
    GARDEN = 46
    ORCHARD = 47
    VINEYARD = 48
    QUARRY = 49
    SAWMILL = 50


@dataclass
class Structure:
    """A structure definition (the archetype)."""

    structure_type: StructureType
    name: str
    glyph: str
    color: int
    width: int = 1
    height: int = 1
    is_walkable: bool = True
    blocks_sight: bool = False
    description: str = ""
    services: list[str] = field(default_factory=list)  # "shop", "sleep", "bank", etc.
    capacity: int = 0  # inhabitants or visitors
    build_cost_copper: int = 0
    build_time_days: int = 0
    maintenance_per_month: int = 0
    tags: list[str] = field(default_factory=list)


class StructureLibrary:
    """Registry of structure types."""

    _structures: ClassVar[dict[int, Structure]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, structure: Structure) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._structures[int(structure.structure_type)] = structure

    @classmethod
    def get(cls, structure_type: StructureType) -> Optional[Structure]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._structures.get(int(structure_type))

    @classmethod
    def all(cls) -> list[Structure]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._structures.values())

    @classmethod
    def by_service(cls, service: str) -> list[Structure]:
        return [s for s in cls.all() if service in s.services]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for s in DEFAULT_STRUCTURES:
            cls._structures[int(s.structure_type)] = s
        cls._defaults_loaded = True


@dataclass
class StructurePlacement:
    """A structure placed on the world map."""

    placement_id: int
    structure_type: StructureType
    name: str
    x: int
    y: int
    z: int = 0
    owner_id: Optional[int] = None  # entity or faction id
    condition: float = 1.0  # 0..1
    inhabitants: list[int] = field(default_factory=list)
    inventory_id: Optional[int] = None  # shop stock
    is_locked: bool = False
    lock_difficulty: int = 0
    description: str = ""
    discovered_by: list[int] = field(default_factory=list)  # entity ids
    custom_data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "placement_id": self.placement_id,
            "structure_type": int(self.structure_type),
            "name": self.name,
            "x": self.x, "y": self.y, "z": self.z,
            "owner_id": self.owner_id, "condition": self.condition,
            "inhabitants": list(self.inhabitants),
            "inventory_id": self.inventory_id,
            "is_locked": self.is_locked, "lock_difficulty": self.lock_difficulty,
            "description": self.description,
            "discovered_by": list(self.discovered_by),
            "custom_data": dict(self.custom_data),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StructurePlacement":
        return cls(
            placement_id=data["placement_id"],
            structure_type=StructureType(data["structure_type"]),
            name=data["name"],
            x=data["x"], y=data["y"], z=data.get("z", 0),
            owner_id=data.get("owner_id"),
            condition=data.get("condition", 1.0),
            inhabitants=list(data.get("inhabitants", [])),
            inventory_id=data.get("inventory_id"),
            is_locked=data.get("is_locked", False),
            lock_difficulty=data.get("lock_difficulty", 0),
            description=data.get("description", ""),
            discovered_by=list(data.get("discovered_by", [])),
            custom_data=dict(data.get("custom_data", {})),
        )


DEFAULT_STRUCTURES: list[Structure] = [
    Structure(StructureType.HOUSE, "House", "⌂", 130,
              description="A simple dwelling.",
              capacity=5, build_cost_copper=500, build_time_days=30,
              maintenance_per_month=10, tags=["residential"]),
    Structure(StructureType.SHOP, "Shop", "$", 215,
              description="A merchant's shop.",
              services=["shop"], capacity=10, build_cost_copper=2000,
              build_time_days=60, maintenance_per_month=30, tags=["commerce"]),
    Structure(StructureType.INN, "Inn", "⌂", 215,
              description="A traveller's inn.",
              services=["sleep", "food", "drink", "rumors"],
              capacity=20, build_cost_copper=3000, build_time_days=90,
              maintenance_per_month=50, tags=["lodging", "food"]),
    Structure(StructureType.TAVERN, "Tavern", "🍺", 215,
              description="A lively tavern.",
              services=["drink", "food", "rumors", "quests"],
              capacity=30, build_cost_copper=2500, build_time_days=60,
              maintenance_per_month=40, tags=["food", "social"]),
    Structure(StructureType.TEMPLE, "Temple", "⛪", 255,
              description="A holy temple.",
              services=["heal", "blessing", "resurrection"],
              capacity=50, build_cost_copper=10000, build_time_days=365,
              maintenance_per_month=100, tags=["religious", "healing"]),
    Structure(StructureType.SHRINE, "Shrine", "⛩", 215,
              description="A small roadside shrine.",
              services=["blessing"], capacity=5,
              build_cost_copper=100, build_time_days=10,
              tags=["religious"]),
    Structure(StructureType.TOWER, "Tower", "☥", 165,
              description="A tall wizard's tower.",
              blocks_sight=False, capacity=10, build_cost_copper=5000,
              build_time_days=180, tags=["magical", "residential"]),
    Structure(StructureType.RUIN, "Ruin", "᚜", 240,
              description="Crumbling ruins of an old structure.",
              tags=["exploration"]),
    Structure(StructureType.DUNGEON_ENTRANCE, "Dungeon Entrance", ">", 196,
              description="A dark descent into the depths.",
              tags=["dungeon"]),
    Structure(StructureType.CAVE_ENTRANCE, "Cave Entrance", "○", 240,
              description="A yawning cave mouth.",
              tags=["cave"]),
    Structure(StructureType.FORTRESS, "Fortress", "⚰", 244,
              description="A military stronghold.",
              capacity=200, build_cost_copper=50000, build_time_days=730,
              maintenance_per_month=500, tags=["military", "defensive"]),
    Structure(StructureType.CASTLE, "Castle", "⚰", 220,
              description="A great castle.",
              capacity=500, build_cost_copper=200000, build_time_days=1825,
              maintenance_per_month=2000, tags=["military", "noble"]),
    Structure(StructureType.FARM, "Farm", "≈", 114,
              description="A working farm.",
              capacity=10, build_cost_copper=300, build_time_days=30,
              maintenance_per_month=5, tags=["agriculture"]),
    Structure(StructureType.MILL, "Mill", "✿", 130,
              description="A water- or wind-mill.",
              services=["grinding"], capacity=5,
              build_cost_copper=800, build_time_days=60,
              tags=["industry"]),
    Structure(StructureType.WELL, "Well", "○", 244,
              description="A stone well.",
              services=["water"], capacity=1, build_cost_copper=100,
              build_time_days=7, tags=["water"]),
    Structure(StructureType.FOUNTAIN, "Fountain", "⌬", 75,
              description="A decorative fountain.",
              services=["water"], capacity=1, build_cost_copper=500,
              build_time_days=20, tags=["water", "decorative"]),
    Structure(StructureType.BRIDGE, "Bridge", "=", 94,
              description="A bridge over water.",
              build_cost_copper=1000, build_time_days=60,
              tags=["infrastructure"]),
    Structure(StructureType.GATE, "Gate", "∩", 244,
              description="A gate in a wall.",
              blocks_sight=True, build_cost_copper=500,
              build_time_days=20, tags=["infrastructure", "defensive"]),
    Structure(StructureType.WALL, "Wall", "▓", 244,
              description="A defensive wall.",
              is_walkable=False, blocks_sight=True,
              build_cost_copper=200, build_time_days=10,
              tags=["defensive"]),
    Structure(StructureType.CAMP, "Camp", "⛺", 130,
              description="A temporary camp.",
              capacity=10, tags=["temporary"]),
    Structure(StructureType.CEMETERY, "Cemetery", "⚰", 240,
              description="A burial ground.",
              tags=["religious", "death"]),
    Structure(StructureType.STATUE, "Statue", "Ⓐ", 215,
              description="A statue of some forgotten hero.",
              tags=["decorative"]),
    Structure(StructureType.PORTAL, "Portal", "✦", 165,
              description="A shimmering magical portal.",
              services=["teleport"], tags=["magical"]),
    Structure(StructureType.SMITHY, "Smithy", "⚒", 130,
              description="A blacksmith's workshop.",
              services=["craft", "repair"], capacity=5,
              build_cost_copper=1500, build_time_days=60,
              maintenance_per_month=30, tags=["craft"]),
    Structure(StructureType.STABLE, "Stable", "⌂", 130,
              description="A stable for horses.",
              services=["mount"], capacity=20,
              build_cost_copper=800, build_time_days=30,
              tags=["animal"]),
    Structure(StructureType.MARKET, "Market", "▦", 215,
              description="A bustling open-air market.",
              services=["shop", "trade"], capacity=100,
              build_cost_copper=5000, build_time_days=120,
              maintenance_per_month=80, tags=["commerce"]),
    Structure(StructureType.BANK, "Bank", "Ⓑ", 215,
              description="A secure bank.",
              services=["bank", "loan"], capacity=10,
              build_cost_copper=10000, build_time_days=180,
              maintenance_per_month=100, tags=["finance"]),
    Structure(StructureType.GUILDHALL, "Guildhall", "Ⓖ", 215,
              description="A guild's meeting hall.",
              services=["guild", "quests"], capacity=50,
              build_cost_copper=8000, build_time_days=180,
              maintenance_per_month=80, tags=["social"]),
    Structure(StructureType.LIBRARY, "Library", "Ⓑ", 165,
              description="A library of books.",
              services=["research", "learn"], capacity=30,
              build_cost_copper=5000, build_time_days=180,
              maintenance_per_month=50, tags=["knowledge"]),
    Structure(StructureType.PRISON, "Prison", "⚒", 240,
              description="A grim prison.",
              capacity=50, build_cost_copper=3000, build_time_days=120,
              maintenance_per_month=40, tags=["justice"]),
    Structure(StructureType.ARENA, "Arena", "Ⓐ", 196,
              description="A combat arena.",
              services=["arena"], capacity=200,
              build_cost_copper=15000, build_time_days=365,
              maintenance_per_month=150, tags=["combat", "social"]),
    Structure(StructureType.LIGHTHOUSE, "Lighthouse", "Ⓘ", 215,
              description="A coastal lighthouse.",
              build_cost_copper=2000, build_time_days=120,
              tags=["navigation"]),
    Structure(StructureType.QUARRY, "Quarry", "⛏", 240,
              description="A stone quarry.",
              services=["mine_stone"], capacity=20,
              build_cost_copper=500, build_time_days=30,
              tags=["industry", "mining"]),
    Structure(StructureType.SAWMILL, "Sawmill", "⚐", 130,
              description="A lumber sawmill.",
              services=["mill_wood"], capacity=10,
              build_cost_copper=800, build_time_days=30,
              tags=["industry", "wood"]),
]
