"""Item class and item properties — the runtime representation of any item."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from engine.items.affixes import Affix
from engine.items.materials import Material


class ItemRarity(Enum):
    JUNK = "junk"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"

    @property
    def color(self) -> int:
        return {
            "junk": 240, "common": 244, "uncommon": 41, "rare": 33,
            "epic": 165, "legendary": 215, "mythic": 196,
        }[self.value]


class ItemQuality(Enum):
    BROKEN = "broken"
    WORN = "worn"
    AVERAGE = "average"
    FINE = "fine"
    EXCELLENT = "excellent"
    PRISTINE = "pristine"

    @property
    def multiplier(self) -> float:
        return {
            "broken": 0.4, "worn": 0.7, "average": 1.0,
            "fine": 1.15, "excellent": 1.35, "pristine": 1.6,
        }[self.value]


@dataclass
class ItemProperty:
    """A single key-value property of an item."""

    key: str
    value: float
    mode: str = "add"  # "add" or "mul"

    def __str__(self) -> str:
        if self.value >= 0:
            return f"+{self._format_value()} {self._label()}"
        return f"{self._format_value()} {self._label()}"

    def _format_value(self) -> str:
        if abs(self.value - round(self.value)) < 1e-6:
            return str(int(round(self.value)))
        return f"{self.value:.1f}"

    def _label(self) -> str:
        return self.key.replace("_", " ").title()


@dataclass
class Item:
    """A single instantiated item."""

    id: int
    base_type: str             # e.g. "sword", "shield", "potion"
    name: str
    material_id: str
    quality: ItemQuality = ItemQuality.AVERAGE
    rarity: ItemRarity = ItemRarity.COMMON
    level: int = 1
    weight: float = 0.0         # kg
    volume: float = 0.0         # litres
    value: int = 0              # copper pieces
    durability_max: int = 100
    durability: int = 100
    properties: dict[str, ItemProperty] = field(default_factory=dict)
    prefixes: list[Affix] = field(default_factory=list)
    suffixes: list[Affix] = field(default_factory=list)
    enchantments: list[dict] = field(default_factory=list)
    sockets: list[Optional[dict]] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    owners: list[int] = field(default_factory=list)  # entity IDs
    identified: bool = True
    stackable: bool = False
    stack_count: int = 1
    tags: list[str] = field(default_factory=list)
    category: str = "misc"      # weapon, armor, consumable, misc, material, ...
    two_handed: bool = False
    icon: str = "?"
    color: int = 244
    description: str = ""

    # ----- derived -----

    @property
    def material(self) -> Optional[Material]:
        from engine.items.materials import MaterialLibrary
        return MaterialLibrary.get(self.material_id)

    @property
    def display_name(self) -> str:
        parts = []
        if self.quality != ItemQuality.AVERAGE:
            parts.append(self.quality.value.title())
        for affix in self.prefixes:
            parts.append(affix.name)
        parts.append(self.name)
        for affix in self.suffixes:
            parts.append(affix.name)
        return " ".join(parts)

    @property
    def is_broken(self) -> bool:
        return self.durability <= 0

    @property
    def total_weight(self) -> float:
        return self.weight * max(1, self.stack_count)

    @property
    def total_value(self) -> int:
        return self.value * max(1, self.stack_count)

    def damage(self, amount: int) -> None:
        self.durability = max(0, self.durability - amount)

    def repair(self, amount: Optional[int] = None) -> None:
        if amount is None:
            self.durability = self.durability_max
        else:
            self.durability = min(self.durability_max, self.durability + amount)

    def add_owner(self, entity_id: int) -> None:
        if entity_id not in self.owners:
            self.owners.append(entity_id)

    def append_history(self, entry: str) -> None:
        self.history.append(entry)
        if len(self.history) > 50:
            self.history = self.history[-50:]

    def property_value(self, key: str, default: float = 0.0) -> float:
        prop = self.properties.get(key)
        return prop.value if prop else default

    def add_property(self, key: str, value: float, mode: str = "add") -> None:
        self.properties[key] = ItemProperty(key=key, value=value, mode=mode)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "base_type": self.base_type,
            "name": self.name,
            "material_id": self.material_id,
            "quality": self.quality.value,
            "rarity": self.rarity.value,
            "level": self.level,
            "weight": self.weight,
            "volume": self.volume,
            "value": self.value,
            "durability_max": self.durability_max,
            "durability": self.durability,
            "properties": {k: {"value": v.value, "mode": v.mode}
                           for k, v in self.properties.items()},
            "prefixes": [a.id for a in self.prefixes],
            "suffixes": [a.id for a in self.suffixes],
            "enchantments": self.enchantments,
            "sockets": self.sockets,
            "history": self.history,
            "owners": self.owners,
            "identified": self.identified,
            "stackable": self.stackable,
            "stack_count": self.stack_count,
            "tags": self.tags,
            "category": self.category,
            "two_handed": self.two_handed,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Item":
        item = cls(
            id=data["id"],
            base_type=data["base_type"],
            name=data["name"],
            material_id=data["material_id"],
        )
        item.quality = ItemQuality(data.get("quality", "average"))
        item.rarity = ItemRarity(data.get("rarity", "common"))
        item.level = data.get("level", 1)
        item.weight = data.get("weight", 0.0)
        item.volume = data.get("volume", 0.0)
        item.value = data.get("value", 0)
        item.durability_max = data.get("durability_max", 100)
        item.durability = data.get("durability", 100)
        item.enchantments = data.get("enchantments", [])
        item.sockets = data.get("sockets", [])
        item.history = data.get("history", [])
        item.owners = data.get("owners", [])
        item.identified = data.get("identified", True)
        item.stackable = data.get("stackable", False)
        item.stack_count = data.get("stack_count", 1)
        item.tags = data.get("tags", [])
        item.category = data.get("category", "misc")
        item.two_handed = data.get("two_handed", False)
        item.icon = data.get("icon", "?")
        item.color = data.get("color", 244)
        item.description = data.get("description", "")
        for k, v in data.get("properties", {}).items():
            item.properties[k] = ItemProperty(key=k,
                                              value=v["value"],
                                              mode=v.get("mode", "add"))
        # Affixes resolved from registry.
        from engine.items.affixes import AffixLibrary
        for affix_id in data.get("prefixes", []):
            a = AffixLibrary.get(affix_id)
            if a:
                item.prefixes.append(a)
        for affix_id in data.get("suffixes", []):
            a = AffixLibrary.get(affix_id)
            if a:
                item.suffixes.append(a)
        return item
