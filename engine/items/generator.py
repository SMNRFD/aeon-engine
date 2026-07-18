"""Procedural item generation — millions of unique combinations."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from engine.items.affixes import Affix, AffixLibrary
from engine.items.item import Item, ItemQuality, ItemRarity
from engine.items.materials import Material, MaterialLibrary
from engine.utils.rng import RNG


# Base item archetypes — data-driven in production.
@dataclass
class BaseItemArchetype:
    base_type: str          # "sword", "shield", "potion", ...
    name: str               # "sword", "longsword", "kite shield"
    category: str           # weapon, armor, consumable, misc, material
    weight_kg: float
    volume_l: float
    base_value: int
    durability: int
    icon: str
    color: int
    two_handed: bool = False
    default_material: str = "iron"
    allowed_material_categories: tuple[str, ...] = ()
    base_properties: dict[str, float] = field(default_factory=dict)
    description: str = ""


# Static archetype catalogue (production would load from JSON).
ARCHETYPES: dict[str, BaseItemArchetype] = {
    # ---- weapons ----
    "dagger": BaseItemArchetype(
        "dagger", "dagger", "weapon", 0.5, 0.3, 30, 60, "/", 244,
        False, "iron", ("metal", "bone", "obsidian"),
        {"damage": 4.0, "attack_speed": 1.2, "crit_chance": 0.05},
        "A short, quick blade.",
    ),
    "shortsword": BaseItemArchetype(
        "shortsword", "shortsword", "weapon", 1.2, 0.6, 60, 80, "/", 244,
        False, "iron", ("metal",),
        {"damage": 7.0, "attack_speed": 1.0, "crit_chance": 0.03},
        "A standard foot-soldier's blade.",
    ),
    "longsword": BaseItemArchetype(
        "longsword", "longsword", "weapon", 2.0, 1.0, 100, 100, "/", 244,
        False, "steel", ("metal",),
        {"damage": 10.0, "attack_speed": 0.9, "parry_chance": 0.1},
        "A versatile two-edged sword.",
    ),
    "greatsword": BaseItemArchetype(
        "greatsword", "greatsword", "weapon", 4.5, 2.0, 200, 120, "/", 244,
        True, "steel", ("metal",),
        {"damage": 16.0, "attack_speed": 0.7, "parry_chance": 0.15},
        "A massive two-handed blade.",
    ),
    "mace": BaseItemArchetype(
        "mace", "mace", "weapon", 2.5, 1.0, 80, 120, "!", 244,
        False, "iron", ("metal", "stone"),
        {"damage": 9.0, "attack_speed": 0.85, "armor_pen": 0.3},
        "A blunt crushing weapon.",
    ),
    "warhammer": BaseItemArchetype(
        "warhammer", "warhammer", "weapon", 4.0, 1.5, 150, 130, "!", 244,
        True, "steel", ("metal",),
        {"damage": 14.0, "attack_speed": 0.7, "armor_pen": 0.5},
        "A heavy hammer for smashing armour.",
    ),
    "axe": BaseItemArchetype(
        "axe", "axe", "weapon", 2.0, 0.8, 70, 100, "(", 244,
        False, "iron", ("metal",),
        {"damage": 8.0, "attack_speed": 0.95, "crit_mult": 0.2},
        "A simple chopping axe.",
    ),
    "battleaxe": BaseItemArchetype(
        "battleaxe", "battleaxe", "weapon", 3.5, 1.5, 130, 110, "(", 244,
        True, "steel", ("metal",),
        {"damage": 13.0, "attack_speed": 0.75, "crit_mult": 0.3},
        "A two-handed axe built for war.",
    ),
    "spear": BaseItemArchetype(
        "spear", "spear", "weapon", 2.5, 1.5, 60, 90, "/", 244,
        True, "iron", ("metal", "bone", "obsidian"),
        {"damage": 9.0, "attack_speed": 1.0, "reach": 2.0},
        "A long-reaching polearm.",
    ),
    "bow": BaseItemArchetype(
        "bow", "bow", "weapon", 1.5, 2.5, 90, 80, "}", 130,
        True, "yew", ("wood",),
        {"damage": 8.0, "attack_speed": 0.9, "range": 30.0, "ranged": 1.0},
        "A curved ranged weapon.",
    ),
    "crossbow": BaseItemArchetype(
        "crossbow", "crossbow", "weapon", 3.0, 2.0, 150, 90, "}", 130,
        True, "yew", ("wood",),
        {"damage": 12.0, "attack_speed": 0.5, "range": 40.0, "ranged": 1.0},
        "A mechanical bow with high penetration.",
    ),
    "staff": BaseItemArchetype(
        "staff", "staff", "weapon", 2.0, 1.5, 50, 80, "|", 130,
        True, "oak", ("wood",),
        {"damage": 4.0, "magic_power": 0.15, "mana_regen": 0.3},
        "A focus for arcane power.",
    ),
    "wand": BaseItemArchetype(
        "wand", "wand", "weapon", 0.3, 0.1, 200, 60, "/", 165,
        False, "crystal", ("glass", "bone"),
        {"magic_power": 0.3, "mana_regen": 0.5, "spell_cost_reduction": 0.1},
        "A slender magical focus.",
    ),

    # ---- armor ----
    "leather_armor": BaseItemArchetype(
        "leather_armor", "leather armour", "armor", 3.0, 5.0, 50, 80, "]", 130,
        False, "leather", ("leather",),
        {"armor": 4.0, "slot": 0.0},  # slot 0 = chest
        "Tanned hide armour.",
    ),
    "chainmail": BaseItemArchetype(
        "chainmail", "chainmail", "armor", 8.0, 6.0, 200, 120, "]", 244,
        False, "iron", ("metal",),
        {"armor": 7.0, "slot": 0.0},
        "Interlocking iron rings.",
    ),
    "plate_armor": BaseItemArchetype(
        "plate_armor", "plate armour", "armor", 15.0, 8.0, 500, 150, "]", 244,
        False, "steel", ("metal",),
        {"armor": 11.0, "slot": 0.0},
        "Full plate of shaped steel.",
    ),
    "helmet": BaseItemArchetype(
        "helmet", "helmet", "armor", 2.0, 1.5, 80, 80, "]", 244,
        False, "iron", ("metal",),
        {"armor": 3.0, "slot": 1.0},
        "Head protection.",
    ),
    "shield": BaseItemArchetype(
        "shield", "shield", "armor", 4.0, 3.0, 80, 100, "+", 130,
        False, "oak", ("wood", "metal"),
        {"armor": 3.0, "block_chance": 0.25},
        "A shield for blocking blows.",
    ),
    "boots": BaseItemArchetype(
        "boots", "boots", "armor", 1.5, 2.0, 40, 60, "]", 130,
        False, "leather", ("leather",),
        {"armor": 1.0, "slot": 3.0},
        "Footwear.",
    ),
    "cloak": BaseItemArchetype(
        "cloak", "cloak", "armor", 0.8, 1.0, 30, 40, "(", 130,
        False, "wool", ("cloth",),
        {"armor": 1.0, "stealth": 0.1},
        "A flowing cloak.",
    ),

    # ---- accessories ----
    "ring": BaseItemArchetype(
        "ring", "ring", "armor", 0.02, 0.01, 100, 999, "o", 215,
        False, "gold", ("metal",),
        {"slot": 4.0},
        "A small finger-ring.",
    ),
    "amulet": BaseItemArchetype(
        "amulet", "amulet", "armor", 0.1, 0.05, 150, 999, "o", 215,
        False, "gold", ("metal",),
        {"slot": 5.0},
        "An ornate amulet.",
    ),

    # ---- consumables ----
    "health_potion": BaseItemArchetype(
        "health_potion", "health potion", "consumable", 0.3, 0.3, 30, 999, "!", 196,
        False, "organic", ("organic",),
        {"heal": 30.0, "consumable": 1.0},
        "Restores 30 HP when consumed.",
    ),
    "mana_potion": BaseItemArchetype(
        "mana_potion", "mana potion", "consumable", 0.3, 0.3, 40, 999, "!", 33,
        False, "organic", ("organic",),
        {"restore_mana": 25.0, "consumable": 1.0},
        "Restores 25 MP when consumed.",
    ),
    "bread": BaseItemArchetype(
        "bread", "bread", "consumable", 0.4, 0.5, 5, 999, "%", 215,
        False, "organic", ("organic",),
        {"food": 25.0, "consumable": 1.0},
        "A loaf of bread. Reduces hunger.",
    ),
    "water_flask": BaseItemArchetype(
        "water_flask", "water flask", "consumable", 1.0, 1.0, 8, 999, "!", 33,
        False, "organic", ("organic",),
        {"drink": 30.0, "consumable": 1.0},
        "Reduces thirst.",
    ),

    # ---- materials/misc ----
    "gold_coin": BaseItemArchetype(
        "gold_coin", "gold coin", "misc", 0.005, 0.001, 10000, 999, "$", 220,
        False, "gold", ("metal",),
        {"currency": 1.0},
        "A standard gold coin (10000 cp).",
    ),
    "torch": BaseItemArchetype(
        "torch", "torch", "misc", 0.5, 0.3, 2, 60, "?", 215,
        False, "pine", ("wood",),
        {"light_radius": 6.0, "burn_time": 600.0},
        "A pitch-soaked torch.",
    ),
}


@dataclass
class ItemGenerationParams:
    archetype: Optional[str] = None
    material_id: Optional[str] = None
    rarity: Optional[ItemRarity] = None
    quality: Optional[ItemQuality] = None
    level: int = 1
    allow_affixes: bool = True
    max_affixes: int = 3
    enchanted_chance: float = 0.0


# Number of affixes by rarity
RARITY_AFFIX_COUNT: dict[ItemRarity, tuple[int, int]] = {
    ItemRarity.JUNK: (0, 0),
    ItemRarity.COMMON: (0, 1),
    ItemRarity.UNCOMMON: (1, 2),
    ItemRarity.RARE: (2, 3),
    ItemRarity.EPIC: (2, 3),
    ItemRarity.LEGENDARY: (3, 4),
    ItemRarity.MYTHIC: (4, 4),
}


class ItemGenerator:
    """Generates procedural items."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()

    def generate(self, params: ItemGenerationParams, item_id: int) -> Item:
        archetype_id = params.archetype or self.rng.choice(list(ARCHETYPES.keys()))
        archetype = ARCHETYPES[archetype_id]
        material = self._choose_material(archetype, params.material_id)
        rarity = params.rarity or self._roll_rarity()
        quality = params.quality or self._roll_quality(material)

        item = Item(
            id=item_id,
            base_type=archetype.base_type,
            name=archetype.name,
            material_id=material.id,
            quality=quality,
            rarity=rarity,
            level=params.level,
            weight=archetype.weight_kg * (material.density / 7.85),
            volume=archetype.volume_l,
            value=int(archetype.base_value * (material.value_per_kg / 20)
                      * quality.multiplier * (1 + rarity.value.__len__() * 0.5)),
            durability_max=int(archetype.durability
                               * (1 + material.hardness / 10)
                               * quality.multiplier),
            durability=int(archetype.durability
                           * (1 + material.hardness / 10)
                           * quality.multiplier),
            category=archetype.category,
            two_handed=archetype.two_handed,
            icon=archetype.icon,
            color=material.color,
            description=archetype.description,
            tags=[archetype.base_type, material.category],
        )

        # Apply base properties scaled by material and quality.
        for key, base_val in archetype.base_properties.items():
            if key == "slot":
                item.add_property(key, base_val, mode="set")
                continue
            scaled = self._scale_property(key, base_val, material, quality)
            item.add_property(key, scaled)

        # Roll affixes
        if params.allow_affixes:
            self._apply_affixes(item, archetype, rarity, params.max_affixes)

        # Roll enchantments
        if self.rng.chance(params.enchanted_chance or self._enchanted_chance(rarity)):
            self._apply_enchantment(item, rarity)

        # Update display name
        item.color = rarity.color
        return item

    # ----- helpers -----

    def _choose_material(self, archetype: BaseItemArchetype,
                         material_id: Optional[str]) -> Material:
        if material_id:
            m = MaterialLibrary.get(material_id)
            if m:
                return m
        allowed_cats = archetype.allowed_material_categories or ("metal", "wood")
        candidates = [m for m in MaterialLibrary.all() if m.category in allowed_cats]
        if not candidates:
            candidates = list(MaterialLibrary.all())
        weights = [(1.0 - m.rarity) ** 2 for m in candidates]
        return self.rng.weighted_choice(candidates, weights)

    def _roll_rarity(self) -> ItemRarity:
        roll = self.rng.random()
        if roll < 0.55:
            return ItemRarity.COMMON
        if roll < 0.82:
            return ItemRarity.UNCOMMON
        if roll < 0.94:
            return ItemRarity.RARE
        if roll < 0.985:
            return ItemRarity.EPIC
        if roll < 0.999:
            return ItemRarity.LEGENDARY
        return ItemRarity.MYTHIC

    def _roll_quality(self, material: Material) -> ItemQuality:
        # Better materials bias toward better quality.
        bias = material.hardness / 20.0
        roll = self.rng.random() + bias
        if roll < 0.15:
            return ItemRarity and ItemQuality.BROKEN
        if roll < 0.35:
            return ItemQuality.WORN
        if roll < 0.75:
            return ItemQuality.AVERAGE
        if roll < 0.92:
            return ItemQuality.FINE
        if roll < 0.99:
            return ItemQuality.EXCELLENT
        return ItemQuality.PRISTINE

    def _scale_property(self, key: str, base: float,
                        material: Material, quality: ItemQuality) -> float:
        quality_mult = quality.multiplier
        if key in ("damage",):
            return base * (0.7 + material.hardness / 10) * quality_mult
        if key in ("armor",):
            return base * (0.6 + material.hardness / 8) * quality_mult
        if key in ("attack_speed",):
            # Lighter materials are faster.
            return base * (1.0 + max(-0.3, (1.0 - material.density / 10.0) * 0.2))
        if key in ("durability_max",):
            return base * (1.0 + material.hardness / 10) * quality_mult
        if key in ("magic_power", "mana_regen"):
            return base * (0.5 + material.magical_affinity) * quality_mult
        return base * quality_mult

    def _apply_affixes(self, item: Item, archetype: BaseItemArchetype,
                       rarity: ItemRarity, max_affixes: int) -> None:
        lo, hi = RARITY_AFFIX_COUNT.get(rarity, (0, 0))
        n = min(max_affixes, self.rng.randint(lo, hi))
        if n <= 0:
            return
        # Half prefixes, half suffixes.
        n_prefix = n // 2
        n_suffix = n - n_prefix
        prefixes = AffixLibrary.prefixes_for(archetype.category)
        suffixes = AffixLibrary.suffixes_for(archetype.category)
        # Filter by tier appropriate to rarity.
        max_tier = {"junk": 0, "common": 1, "uncommon": 2, "rare": 3,
                    "epic": 4, "legendary": 5, "mythic": 5}[rarity.value]
        prefixes = [a for a in prefixes if a.tier <= max_tier]
        suffixes = [a for a in suffixes if a.tier <= max_tier]
        if prefixes and n_prefix:
            for affix in self.rng.sample(prefixes, min(n_prefix, len(prefixes))):
                item.prefixes.append(affix)
                self._apply_affix(item, affix)
        if suffixes and n_suffix:
            for affix in self.rng.sample(suffixes, min(n_suffix, len(suffixes))):
                item.suffixes.append(affix)
                self._apply_affix(item, affix)

    def _apply_affix(self, item: Item, affix: Affix) -> None:
        for stat, delta in affix.modifiers.items():
            mode = affix.mode.get(stat, "add")
            existing = item.properties.get(stat)
            if mode == "add":
                if existing:
                    existing.value += delta
                else:
                    item.add_property(stat, delta, mode="add")
            elif mode == "mul":
                if existing:
                    existing.value *= (1.0 + delta)
                else:
                    # No base value — set instead
                    item.add_property(stat, delta, mode="add")
            elif mode == "set":
                item.add_property(stat, delta, mode="set")

    def _enchanted_chance(self, rarity: ItemRarity) -> float:
        return {
            "junk": 0.0, "common": 0.01, "uncommon": 0.03, "rare": 0.10,
            "epic": 0.30, "legendary": 0.70, "mythic": 1.0,
        }[rarity.value]

    def _apply_enchantment(self, item: Item, rarity: ItemRarity) -> None:
        ench_type = self.rng.choice([
            "fire_damage", "cold_damage", "lightning_damage", "lifesteal",
            "regen", "magic_resist", "see_invisible", "luck",
        ])
        magnitude = (1.0 + (rarity.value.__len__() * 0.5)) * self.rng.uniform(0.5, 2.0)
        item.enchantments.append({
            "type": ench_type,
            "magnitude": round(magnitude, 2),
            "duration": "permanent",
        })
        item.append_history(f"Bears a permanent enchantment of {ench_type}.")
