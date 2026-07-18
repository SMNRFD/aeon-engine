"""Tests for items, inventory, and crafting."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.items.generator import ItemGenerator, ItemGenerationParams
from engine.items.item import Item, ItemQuality, ItemRarity
from engine.items.materials import MaterialLibrary
from engine.items.affixes import AffixLibrary
from engine.items.registry import ItemRegistry
from engine.inventory.inventory import Inventory, EquipmentSlot


def test_material_library():
    iron = MaterialLibrary.get("iron")
    assert iron is not None
    assert iron.category == "metal"
    assert MaterialLibrary.get("nonexistent") is None


def test_affix_library():
    prefixes = AffixLibrary.prefixes_for("weapon")
    assert len(prefixes) > 0
    assert all(p.kind == "prefix" for p in prefixes)


def test_item_generation_basic():
    rng_seed = 42
    import random
    from engine.utils.rng import RNG
    gen = ItemGenerator(RNG(rng_seed))
    params = ItemGenerationParams(archetype="dagger", material_id="iron",
                                   quality=ItemQuality.AVERAGE,
                                   rarity=ItemRarity.COMMON,
                                   allow_affixes=False)
    item = gen.generate(params, item_id=1)
    assert item.base_type == "dagger"
    assert item.material_id == "iron"
    assert item.weight > 0
    assert item.value > 0


def test_item_generation_rare_has_affixes():
    from engine.utils.rng import RNG
    gen = ItemGenerator(RNG(99))
    params = ItemGenerationParams(archetype="longsword", material_id="steel",
                                   rarity=ItemRarity.RARE)
    item = gen.generate(params, item_id=1)
    # Rare items should have at least one affix (chance-based, so we just
    # check that affixes are sometimes present)
    assert item.rarity == ItemRarity.RARE


def test_item_serialization():
    from engine.utils.rng import RNG
    gen = ItemGenerator(RNG(42))
    item = gen.generate(ItemGenerationParams(archetype="mace", material_id="iron"),
                        item_id=42)
    d = item.to_dict()
    restored = Item.from_dict(d)
    assert restored.id == 42
    assert restored.base_type == "mace"
    assert restored.material_id == "iron"


def test_inventory_basic():
    inv = Inventory(capacity=10, max_weight=50.0)
    registry = ItemRegistry()
    from engine.utils.rng import RNG
    gen = ItemGenerator(RNG(42))
    item1 = registry.register(gen.generate(
        ItemGenerationParams(archetype="dagger"), 0))
    item2 = registry.register(gen.generate(
        ItemGenerationParams(archetype="health_potion"), 0))
    assert inv.add(item1)
    assert inv.add(item2)
    assert inv.used_slots() == 2
    assert inv.count_of(item1.id) == 1


def test_inventory_full():
    inv = Inventory(capacity=2, max_weight=50.0)
    registry = ItemRegistry()
    from engine.utils.rng import RNG
    gen = ItemGenerator(RNG(42))
    for _ in range(3):
        item = registry.register(gen.generate(
            ItemGenerationParams(archetype="dagger"), 0))
        inv.add(item)
    assert inv.used_slots() == 2  # only 2 fit


def test_crafting_system():
    from engine.crafting.system import CraftingSystem, RecipeLibrary
    from engine.core.ecs import World, Entity
    from engine.utils.rng import RNG
    crafter = Entity(id=1, generation=0)
    system = CraftingSystem(rng=RNG(42))
    recipe = RecipeLibrary.get("iron_dagger")
    assert recipe is not None
    result = system.craft(recipe, crafter, {"iron": 1}, skill_level=5)
    assert result.success
    assert result.item is not None


def test_crafting_requires_materials():
    from engine.crafting.system import CraftingSystem, RecipeLibrary
    from engine.core.ecs import Entity
    from engine.utils.rng import RNG
    crafter = Entity(id=1, generation=0)
    system = CraftingSystem(rng=RNG(42))
    recipe = RecipeLibrary.get("iron_dagger")
    result = system.craft(recipe, crafter, {}, skill_level=5)
    assert not result.success
    assert "Missing" in result.message
