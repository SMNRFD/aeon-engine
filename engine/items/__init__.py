"""Item system — materials, affixes, procedural item generation."""

from engine.items.materials import Material, MaterialLibrary, MATERIALS
from engine.items.affixes import (
    Affix, AffixLibrary, PREFIXES, SUFFIXES,
)
from engine.items.item import Item, ItemRarity, ItemQuality, ItemProperty
from engine.items.generator import ItemGenerator, ItemGenerationParams
from engine.items.registry import ItemRegistry

__all__ = [
    "Material", "MaterialLibrary", "MATERIALS",
    "Affix", "AffixLibrary", "PREFIXES", "SUFFIXES",
    "Item", "ItemRarity", "ItemQuality", "ItemProperty",
    "ItemGenerator", "ItemGenerationParams",
    "ItemRegistry",
]
