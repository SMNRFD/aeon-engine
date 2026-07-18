"""Rune system — magical glyphs inscribed on items.

Runes are permanent magical effects bound to items via inscription:
* Fire Rune — adds fire damage
* Frost Rune — adds cold damage
* Lightning Rune — adds lightning damage
* Protection Rune — adds armor
* Healing Rune — gradual HP regen
* Mana Rune — gradual MP regen
* Stealth Rune — reduces visibility
* Strength Rune — boosts strength
* Speed Rune — boosts agility
* Warding Rune — magic resistance

Runes can be combined for compound effects. Inscribing requires:
* The rune knowledge (learned via skill)
* A runic reagent (consumed)
* A blank item slot (each item has limited rune slots)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


class RuneType(IntEnum):
    FIRE = 0
    FROST = 1
    LIGHTNING = 2
    PROTECTION = 3
    HEALING = 4
    MANA = 5
    STEALTH = 6
    STRENGTH = 7
    SPEED = 8
    WARDING = 9
    SHARPNESS = 10
    WEIGHT = 11
    HUNGER = 12
    LIGHT = 13
    SOUND = 14
    VOID = 15
    LIFE = 16
    DEATH = 17
    CHAOS = 18
    ORDER = 19


@dataclass
class Rune:
    """A rune definition."""

    rune_id: str
    name: str
    rune_type: RuneType
    description: str = ""
    base_power: float = 1.0
    rarity: float = 0.5  # 0=common, 1=very rare
    reagent_required: str = ""
    reagent_count: int = 1
    skill_required: str = "rune_carving"
    skill_level_required: int = 1
    compatible_item_categories: list[str] = field(default_factory=list)  # empty = all
    color: int = 196
    glyph: str = "ᚱ"
    effects: dict[str, float] = field(default_factory=dict)
    # Effects: e.g. {"fire_damage": 5.0, "burn_chance": 0.2}

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["rune_type"] = int(self.rune_type)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Rune":
        d = dict(data)
        d["rune_type"] = RuneType(d.get("rune_type", 0))
        return cls(**d)


class RuneLibrary:
    """Registry of runes."""

    _runes: ClassVar[dict[str, Rune]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, rune: Rune) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._runes[rune.rune_id] = rune

    @classmethod
    def get(cls, rune_id: str) -> Optional[Rune]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._runes.get(rune_id)

    @classmethod
    def all(cls) -> list[Rune]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._runes.values())

    @classmethod
    def by_type(cls, rune_type: RuneType) -> list[Rune]:
        return [r for r in cls.all() if r.rune_type == rune_type]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for r in DEFAULT_RUNES:
            cls._runes[r.rune_id] = r
        cls._defaults_loaded = True


@dataclass
class RuneInscription:
    """A rune inscribed on an item."""

    rune_id: str
    inscribed_at: float = 0.0
    inscribed_by: Optional[int] = None
    power: float = 1.0  # multiplier on rune's base_power
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "RuneInscription":
        return cls(**data)


class RuneSystem:
    """Manages rune inscription and effects."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        # item_id -> list of inscriptions
        self._inscriptions: dict[int, list[RuneInscription]] = {}

    def inscribe(self, item_id: int, rune: Rune,
                 inscribed_by: Optional[int] = None,
                 skill_level: int = 1,
                 current_tick: float = 0.0) -> tuple[bool, str, Optional[RuneInscription]]:
        """Inscribe a rune on an item."""
        # Check skill level
        if skill_level < rune.skill_level_required:
            return False, f"Requires {rune.skill_level_required} {rune.skill_required}", None
        # Add inscription
        # Power scales with skill level
        power = rune.base_power * (1.0 + (skill_level - rune.skill_level_required) * 0.1)
        inscription = RuneInscription(
            rune_id=rune.rune_id,
            inscribed_at=current_tick,
            inscribed_by=inscribed_by,
            power=power,
        )
        self._inscriptions.setdefault(item_id, []).append(inscription)
        return True, f"Inscribed {rune.name} on item {item_id}", inscription

    def inscriptions_on(self, item_id: int) -> list[RuneInscription]:
        return self._inscriptions.get(item_id, [])

    def remove_inscription(self, item_id: int, rune_id: str) -> bool:
        inscriptions = self._inscriptions.get(item_id, [])
        for i, insc in enumerate(inscriptions):
            if insc.rune_id == rune_id:
                inscriptions.pop(i)
                return True
        return False

    def clear_inscriptions(self, item_id: int) -> int:
        count = len(self._inscriptions.get(item_id, []))
        self._inscriptions.pop(item_id, None)
        return count

    def total_effects(self, item_id: int) -> dict[str, float]:
        """Aggregate all rune effects on an item."""
        effects: dict[str, float] = {}
        for insc in self._inscriptions.get(item_id, []):
            if not insc.is_active:
                continue
            rune = RuneLibrary.get(insc.rune_id)
            if rune is None:
                continue
            for effect, magnitude in rune.effects.items():
                effects[effect] = effects.get(effect, 0.0) + magnitude * insc.power
        return effects

    def to_dict(self) -> dict[str, Any]:
        return {
            "inscriptions": {
                str(item_id): [i.to_dict() for i in inscs]
                for item_id, inscs in self._inscriptions.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RuneSystem":
        sys = cls()
        for item_id_str, inscs_data in data.get("inscriptions", {}).items():
            sys._inscriptions[int(item_id_str)] = [
                RuneInscription.from_dict(i) for i in inscs_data
            ]
        return sys


# ---------- Default runes ----------

DEFAULT_RUNES: list[Rune] = [
    Rune("rune_fire", "Rune of Fire", RuneType.FIRE,
         "Adds fire damage to attacks.",
         base_power=1.0, rarity=0.3,
         reagent_required="fire_crystal", reagent_count=1,
         skill_level_required=5,
         color=196, glyph="ᚠ",
         effects={"fire_damage": 5.0, "burn_chance": 0.2}),
    Rune("rune_frost", "Rune of Frost", RuneType.FROST,
         "Adds cold damage to attacks.",
         base_power=1.0, rarity=0.3,
         reagent_required="frost_crystal", reagent_count=1,
         skill_level_required=5,
         color=75, glyph="ᛁ",
         effects={"cold_damage": 5.0, "slow_chance": 0.3}),
    Rune("rune_lightning", "Rune of Lightning", RuneType.LIGHTNING,
         "Adds lightning damage to attacks.",
         base_power=1.0, rarity=0.4,
         reagent_required="storm_crystal", reagent_count=1,
         skill_level_required=8,
         color=165, glyph="ᛚ",
         effects={"lightning_damage": 6.0, "stun_chance": 0.15}),
    Rune("rune_protection", "Rune of Protection", RuneType.PROTECTION,
         "Increases armor.",
         base_power=1.0, rarity=0.2,
         reagent_required="iron_ore", reagent_count=2,
         skill_level_required=3,
         compatible_item_categories=["armor"],
         color=244, glyph="ᛈ",
         effects={"armor": 5.0}),
    Rune("rune_healing", "Rune of Healing", RuneType.HEALING,
         "Gradually restores HP to wearer.",
         base_power=1.0, rarity=0.5,
         reagent_required="rare_herb", reagent_count=3,
         skill_level_required=10,
         compatible_item_categories=["armor"],
         color=41, glyph="ᚺ",
         effects={"hp_regen": 1.0}),
    Rune("rune_mana", "Rune of Mana", RuneType.MANA,
         "Gradually restores MP to wearer.",
         base_power=1.0, rarity=0.5,
         reagent_required="magic_crystal", reagent_count=1,
         skill_level_required=10,
         compatible_item_categories=["armor", "weapon"],
         color=33, glyph="ᛗ",
         effects={"mana_regen": 1.0}),
    Rune("rune_stealth", "Rune of Stealth", RuneType.STEALTH,
         "Reduces visibility of the wearer.",
         base_power=1.0, rarity=0.6,
         reagent_required="shadow_dust", reagent_count=2,
         skill_level_required=12,
         color=90, glyph="ᛋ",
         effects={"stealth_bonus": 0.3}),
    Rune("rune_strength", "Rune of Strength", RuneType.STRENGTH,
         "Boosts the wearer's strength.",
         base_power=1.0, rarity=0.3,
         reagent_required="iron_ore", reagent_count=3,
         skill_level_required=5,
         color=130, glyph="ᚦ",
         effects={"strength": 3.0}),
    Rune("rune_speed", "Rune of Speed", RuneType.SPEED,
         "Boosts the wearer's agility.",
         base_power=1.0, rarity=0.4,
         reagent_required="wind_essence", reagent_count=1,
         skill_level_required=7,
         color=255, glyph="ᛉ",
         effects={"agility": 3.0, "attack_speed": 0.1}),
    Rune("rune_warding", "Rune of Warding", RuneType.WARDING,
         "Grants magic resistance.",
         base_power=1.0, rarity=0.4,
         reagent_required="magic_crystal", reagent_count=2,
         skill_level_required=8,
         color=75, glyph="ᚹ",
         effects={"magic_resist": 0.15}),
    Rune("rune_sharpness", "Rune of Sharpness", RuneType.SHARPNESS,
         "Increases weapon damage.",
         base_power=1.0, rarity=0.2,
         reagent_required="iron_ore", reagent_count=2,
         skill_level_required=3,
         compatible_item_categories=["weapon"],
         color=244, glyph="ᚲ",
         effects={"damage": 3.0, "crit_chance": 0.05}),
    Rune("rune_light", "Rune of Light", RuneType.LIGHT,
         "Illuminates the area around the wearer.",
         base_power=1.0, rarity=0.1,
         reagent_required="sunstone", reagent_count=1,
         skill_level_required=1,
         color=255, glyph="ᛜ",
         effects={"light_radius": 6.0}),
    Rune("rune_void", "Rune of the Void", RuneType.VOID,
         "A rare rune that bypasses armor.",
         base_power=2.0, rarity=0.9,
         reagent_required="void_essence", reagent_count=1,
         skill_level_required=30,
         color=232, glyph="ᛟ",
         effects={"true_damage": 8.0}),
    Rune("rune_life", "Rune of Life", RuneType.LIFE,
         "A powerful rune of vitality.",
         base_power=2.0, rarity=0.8,
         reagent_required="phoenix_feather", reagent_count=1,
         skill_level_required=25,
         color=41, glyph="ᛒ",
         effects={"max_hp": 30.0, "hp_regen": 2.0}),
    Rune("rune_death", "Rune of Death", RuneType.DEATH,
         "A forbidden rune that drains life.",
         base_power=2.0, rarity=0.9,
         reagent_required="soul_gem", reagent_count=1,
         skill_level_required=30,
         color=88, glyph="ᛞ",
         effects={"necrotic_damage": 10.0, "lifesteal": 0.2}),
    Rune("rune_chaos", "Rune of Chaos", RuneType.CHAOS,
         "An unstable rune with random effects.",
         base_power=1.5, rarity=0.7,
         reagent_required="chaos_shard", reagent_count=1,
         skill_level_required=20,
         color=165, glyph="ᚷ",
         effects={"random_damage": 15.0}),
    Rune("rune_order", "Rune of Order", RuneType.ORDER,
         "A stabilizing rune that resists chaos.",
         base_power=1.5, rarity=0.7,
         reagent_required="order_rune_stone", reagent_count=1,
         skill_level_required=20,
         color=255, glyph="ᛟ",
         effects={"chaos_resist": 0.5, "stability": 10.0}),
]
