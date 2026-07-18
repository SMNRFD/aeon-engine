"""Material catalogue — defines the base physical properties of materials.

Materials feed into item generation: a "sword" made of "iron" uses iron's
density, hardness, and value to compute weight, durability, and price.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Optional


@dataclass(frozen=True)
class Material:
    """A physical material used to craft items."""

    id: str
    name: str
    category: str  # metal, wood, leather, cloth, stone, bone, glass, organic
    density: float           # g/cm^3 — affects weight
    hardness: int            # 1..10 — affects durability and damage
    flexibility: float       # 0..1 — affects parry chance & break chance
    value_per_kg: int        # base value modifier (copper pieces per kg)
    color: int               # ANSI 256 colour
    rarity: float            # 0..1 — affects spawn weight
    magical_affinity: float  # 0..1 — how well it holds enchantments
    description: str = ""
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "density": self.density,
            "hardness": self.hardness,
            "flexibility": self.flexibility,
            "value_per_kg": self.value_per_kg,
            "color": self.color,
            "rarity": self.rarity,
            "magical_affinity": self.magical_affinity,
            "description": self.description,
            "tags": list(self.tags),
        }


class MaterialLibrary:
    """Registry of materials loaded from data files or defaults."""

    _materials: ClassVar[dict[str, Material]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, material: Material) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._materials[material.id] = material

    @classmethod
    def get(cls, material_id: str) -> Optional[Material]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._materials.get(material_id)

    @classmethod
    def all(cls) -> list[Material]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._materials.values())

    @classmethod
    def by_category(cls, category: str) -> list[Material]:
        return [m for m in cls.all() if m.category == category]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for m in MATERIALS:
            cls._materials[m.id] = m
        cls._defaults_loaded = True


# Default material catalogue — production data would load from JSON/TOML.
MATERIALS: list[Material] = [
    # ---- metals ----
    Material("copper", "Copper", "metal", 8.96, 3, 0.6, 5, 130, 0.6, 0.4,
             "A soft, reddish metal.", ("metal",)),
    Material("bronze", "Bronze", "metal", 8.8, 5, 0.5, 12, 136, 0.45, 0.5,
             "An alloy of copper and tin.", ("metal",)),
    Material("iron", "Iron", "metal", 7.87, 6, 0.4, 20, 244, 0.4, 0.55,
             "A common, sturdy metal.", ("metal",)),
    Material("steel", "Steel", "metal", 7.85, 7, 0.45, 40, 248, 0.3, 0.65,
             "Refined iron with carbon.", ("metal",)),
    Material("silver", "Silver", "metal", 10.49, 4, 0.5, 80, 250, 0.2, 0.9,
             "A precious metal, bane of the undead.", ("metal", "precious")),
    Material("gold", "Gold", "metal", 19.32, 3, 0.7, 200, 220, 0.05, 0.95,
             "A soft, lustrous precious metal.", ("metal", "precious")),
    Material("mithril", "Mithril", "metal", 4.5, 9, 0.7, 500, 75, 0.05, 1.0,
             "A fey silver-metal stronger than steel and lighter than air.",
             ("metal", "precious", "magical")),
    Material("adamant", "Adamant", "metal", 12.0, 10, 0.2, 800, 67, 0.02, 0.8,
             "An unbreakable green-black metal of the deep.", ("metal", "magical")),
    Material("orichalcum", "Orichalcum", "metal", 8.2, 8, 0.5, 600, 202, 0.1, 1.0,
             "An ancient Atlantean alloy humming with arcane power.",
             ("metal", "magical")),

    # ---- woods ----
    Material("oak", "Oak", "wood", 0.75, 4, 0.6, 3, 130, 0.7, 0.2,
             "Sturdy hardwood.", ("wood",)),
    Material("pine", "Pine", "wood", 0.5, 2, 0.7, 2, 142, 0.8, 0.15,
             "Soft, pale wood.", ("wood",)),
    Material("yew", "Yew", "wood", 0.67, 5, 0.55, 8, 130, 0.5, 0.7,
             "A flexible wood favoured by bowyers.", ("wood",)),
    Material("ebony", "Ebony", "wood", 1.2, 7, 0.4, 30, 232, 0.2, 0.5,
             "Black, dense exotic wood.", ("wood", "exotic")),
    Material("ironwood", "Ironwood", "wood", 1.1, 7, 0.4, 25, 130, 0.2, 0.6,
             "A wood hard enough to turn a blade.", ("wood", "exotic")),

    # ---- leather/cloth ----
    Material("leather", "Leather", "leather", 0.86, 2, 0.85, 4, 130, 0.7, 0.2,
             "Tanned animal hide.", ("leather",)),
    Material("boiled_leather", "Boiled Leather", "leather", 1.0, 4, 0.65, 8, 94,
             0.55, 0.25, "Hardened leather used for armour.", ("leather",)),
    Material("silk", "Silk", "cloth", 0.13, 1, 0.95, 30, 213, 0.1, 0.85,
             "A fine fabric woven by silkworms.", ("cloth", "luxury")),
    Material("linen", "Linen", "cloth", 0.3, 1, 0.9, 5, 230, 0.5, 0.3,
             "Coarse cloth woven from flax.", ("cloth",)),
    Material("wool", "Wool", "cloth", 0.4, 1, 0.9, 4, 137, 0.6, 0.25,
             "Warm woollen cloth.", ("cloth",)),

    # ---- stone ----
    Material("granite", "Granite", "stone", 2.75, 7, 0.05, 2, 243, 0.7, 0.05,
             "Hard igneous rock.", ("stone",)),
    Material("obsidian", "Obsidian", "stone", 2.6, 9, 0.0, 8, 232, 0.05, 0.7,
             "Volcanic glass that holds a razor edge.", ("stone", "exotic")),
    Material("flint", "Flint", "stone", 2.6, 8, 0.0, 2, 244, 0.8, 0.3,
             "A stone that sparks and chips sharply.", ("stone",)),
    Material("marble", "Marble", "stone", 2.7, 4, 0.1, 12, 255, 0.3, 0.3,
             "Pale, veined metamorphic stone.", ("stone",)),

    # ---- bone/glass/organic ----
    Material("bone", "Bone", "bone", 1.7, 5, 0.3, 3, 230, 0.7, 0.4,
             "Polished bone.", ("bone",)),
    Material("dragonbone", "Dragonbone", "bone", 2.5, 8, 0.3, 80, 215, 0.01, 1.0,
             "Bone from a dragon — virtually unbreakable.", ("bone", "magical")),
    Material("glass", "Glass", "glass", 2.5, 3, 0.0, 4, 75, 0.5, 0.6,
             "Fragile transparent glass.", ("glass",)),
    Material("crystal", "Crystal", "glass", 2.7, 6, 0.1, 40, 159, 0.05, 1.0,
             "Resonant magical crystal.", ("glass", "magical")),
]
