"""Affix system — prefixes and suffixes that modify item properties."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional


@dataclass(frozen=True)
class Affix:
    """A modifier attached to an item — prefix or suffix."""

    id: str
    name: str
    kind: str  # "prefix" or "suffix"
    tier: int  # 1..5
    weight: float = 1.0  # spawn weight
    item_categories: tuple[str, ...] = ()  # weapon, armor, ring, ...
    modifiers: dict[str, float] = field(default_factory=dict)  # stat -> delta or multiplier
    mode: dict[str, str] = field(default_factory=dict)  # "add" or "mul" per stat
    description: str = ""

    def apply(self, base_value: dict[str, float]) -> dict[str, float]:
        out = dict(base_value)
        for stat, delta in self.modifiers.items():
            mode = self.mode.get(stat, "add")
            if mode == "add":
                out[stat] = out.get(stat, 0.0) + delta
            elif mode == "mul":
                out[stat] = out.get(stat, 0.0) * (1.0 + delta)
            elif mode == "set":
                out[stat] = delta
        return out

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "kind": self.kind, "tier": self.tier,
            "weight": self.weight, "item_categories": list(self.item_categories),
            "modifiers": dict(self.modifiers), "mode": dict(self.mode),
            "description": self.description,
        }


class AffixLibrary:
    """Registry of affixes."""

    _affixes: ClassVar[dict[str, Affix]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, affix: Affix) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._affixes[affix.id] = affix

    @classmethod
    def get(cls, affix_id: str) -> Optional[Affix]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._affixes.get(affix_id)

    @classmethod
    def all(cls) -> list[Affix]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._affixes.values())

    @classmethod
    def prefixes(cls) -> list[Affix]:
        return [a for a in cls.all() if a.kind == "prefix"]

    @classmethod
    def suffixes(cls) -> list[Affix]:
        return [a for a in cls.all() if a.kind == "suffix"]

    @classmethod
    def prefixes_for(cls, category: str) -> list[Affix]:
        return [a for a in cls.prefixes()
                if not a.item_categories or category in a.item_categories]

    @classmethod
    def suffixes_for(cls, category: str) -> list[Affix]:
        return [a for a in cls.suffixes()
                if not a.item_categories or category in a.item_categories]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for a in PREFIXES + SUFFIXES:
            cls._affixes[a.id] = a
        cls._defaults_loaded = True


# ---- Prefix catalogue ----

PREFIXES: list[Affix] = [
    # Weapon damage prefixes
    Affix("sharp", "Sharp", "prefix", 1, 5.0, ("weapon",),
          {"damage": 2.0, "penetration": 1.0}, {"damage": "add", "penetration": "add"},
          "Edges honed to a fine point."),
    Affix("keen", "Keen", "prefix", 2, 3.0, ("weapon",),
          {"damage": 4.0, "crit_chance": 0.05}, {"damage": "add", "crit_chance": "add"},
          "A weapon that bites deep."),
    Affix("brutal", "Brutal", "prefix", 3, 1.5, ("weapon",),
          {"damage": 8.0, "crit_mult": 0.5}, {"damage": "add", "crit_mult": "add"},
          "Built for crushing blows."),
    Affix("vicious", "Vicious", "prefix", 4, 0.6, ("weapon",),
          {"damage": 12.0, "crit_chance": 0.1, "crit_mult": 0.3},
          {"damage": "add", "crit_chance": "add", "crit_mult": "add"},
          "Mercilessly deadly."),
    Affix("legendary", "Legendary", "prefix", 5, 0.1, ("weapon", "armor"),
          {"damage": 20.0, "armor": 5.0, "crit_chance": 0.15, "crit_mult": 0.7},
          {"damage": "add", "armor": "add", "crit_chance": "add", "crit_mult": "add"},
          "A relic of mythic proportion."),

    # Armor prefixes
    Affix("sturdy", "Sturdy", "prefix", 1, 5.0, ("armor",),
          {"armor": 2.0, "durability_max": 0.2}, {"armor": "add", "durability_max": "mul"},
          "Solidly constructed."),
    Affix("reinforced", "Reinforced", "prefix", 2, 3.0, ("armor",),
          {"armor": 4.0, "weight": 0.1}, {"armor": "add", "weight": "mul"},
          "Banded with extra protection."),
    Affix("blessed", "Blessed", "prefix", 3, 1.5, ("armor", "weapon"),
          {"armor": 3.0, "magic_resist": 0.1, "mana_regen": 0.5},
          {"armor": "add", "magic_resist": "add", "mana_regen": "add"},
          "Touched by a higher power."),

    # Magic prefixes
    Affix("flaming", "Flaming", "prefix", 3, 1.2, ("weapon",),
          {"damage": 6.0, "fire_damage": 4.0},
          {"damage": "add", "fire_damage": "add"},
          "Wreathed in flame."),
    Affix("frostbound", "Frostbound", "prefix", 3, 1.2, ("weapon",),
          {"damage": 4.0, "cold_damage": 4.0, "slow_chance": 0.2},
          {"damage": "add", "cold_damage": "add", "slow_chance": "add"},
          "Eternal ice coats the blade."),
    Affix("shocking", "Shocking", "prefix", 3, 1.2, ("weapon",),
          {"damage": 4.0, "lightning_damage": 4.0, "stun_chance": 0.1},
          {"damage": "add", "lightning_damage": "add", "stun_chance": "add"},
          "Crackles with electric power."),
    Affix("venomous", "Venomous", "prefix", 3, 1.5, ("weapon",),
          {"damage": 2.0, "poison_chance": 0.4, "poison_duration": 4.0},
          {"damage": "add", "poison_chance": "add", "poison_duration": "add"},
          "Dripping with toxic venom."),

    # Quality prefixes (general)
    Affix("fine", "Fine", "prefix", 1, 6.0, (),
          {"damage": 1.0, "armor": 1.0}, {"damage": "add", "armor": "add"},
          "Well-crafted."),
    Affix("superior", "Superior", "prefix", 2, 4.0, (),
          {"damage": 3.0, "armor": 2.0, "durability_max": 0.15},
          {"damage": "add", "armor": "add", "durability_max": "mul"},
          "Master-quality workmanship."),
    Affix("masterwork", "Masterwork", "prefix", 4, 0.5, (),
          {"damage": 6.0, "armor": 5.0, "durability_max": 0.3, "value": 1.0},
          {"damage": "add", "armor": "add", "durability_max": "mul", "value": "mul"},
          "Crafted by a master artisan."),
]


SUFFIXES: list[Affix] = [
    # Weapon suffixes
    Affix("of_slaying", "of Slaying", "suffix", 2, 3.0, ("weapon",),
          {"damage": 3.0, "crit_chance": 0.05},
          {"damage": "add", "crit_chance": "add"},
          "Particularly deadly in combat."),
    Affix("of_wrath", "of Wrath", "suffix", 3, 1.5, ("weapon",),
          {"damage": 6.0, "crit_mult": 0.4, "strength": 2.0},
          {"damage": "add", "crit_mult": "add", "strength": "add"},
          "Fills the wielder with battle-rage."),
    Affix("of_swiftness", "of Swiftness", "suffix", 2, 3.0, ("weapon", "armor"),
          {"agility": 3.0, "attack_speed": 0.15, "weight": -0.1},
          {"agility": "add", "attack_speed": "add", "weight": "mul"},
          "Light as a feather."),

    # Defensive suffixes
    Affix("of_warding", "of Warding", "suffix", 2, 3.0, ("armor",),
          {"armor": 2.0, "magic_resist": 0.1},
          {"armor": "add", "magic_resist": "add"},
          "Shields against magic."),
    Affix("of_vitality", "of Vitality", "suffix", 3, 1.5, ("armor",),
          {"endurance": 3.0, "max_hp": 20.0},
          {"endurance": "add", "max_hp": "add"},
          "Bolsters the body."),
    Affix("of_fortitude", "of Fortitude", "suffix", 4, 0.6, ("armor",),
          {"endurance": 5.0, "max_hp": 40.0, "armor": 3.0},
          {"endurance": "add", "max_hp": "add", "armor": "add"},
          "Unbreakable resilience."),

    # Stat suffixes
    Affix("of_strength", "of Strength", "suffix", 1, 5.0, (),
          {"strength": 2.0}, {"strength": "add"},
          "Increases the wearer's strength."),
    Affix("of_agility", "of Agility", "suffix", 1, 5.0, (),
          {"agility": 2.0}, {"agility": "add"},
          "Increases the wearer's agility."),
    Affix("of_intellect", "of Intellect", "suffix", 1, 5.0, (),
          {"intelligence": 2.0}, {"intelligence": "add"},
          "Sharpens the mind."),
    Affix("of_willpower", "of Willpower", "suffix", 1, 5.0, (),
          {"willpower": 2.0}, {"willpower": "add"},
          "Bolsters the will."),
    Affix("of_charisma", "of Charisma", "suffix", 1, 5.0, (),
          {"charisma": 2.0}, {"charisma": "add"},
          "Improves social presence."),

    # Magic suffixes
    Affix("of_mana", "of Mana", "suffix", 2, 4.0, (),
          {"max_mana": 15.0, "mana_regen": 0.3},
          {"max_mana": "add", "mana_regen": "add"},
          "Stores arcane energy."),
    Affix("of_fire", "of Fire", "suffix", 3, 1.0, ("weapon",),
          {"fire_damage": 5.0, "burn_chance": 0.3},
          {"fire_damage": "add", "burn_chance": "add"},
          "Imbued with elemental fire."),
    Affix("of_the_magus", "of the Magus", "suffix", 4, 0.4, (),
          {"intelligence": 4.0, "max_mana": 30.0, "mana_regen": 0.8,
           "magic_power": 0.2},
          {"intelligence": "add", "max_mana": "add", "mana_regen": "add",
           "magic_power": "add"},
          "A treasure of mages."),
]
