"""Crafting — recipes, materials, quality rolls, research."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.items.item import Item, ItemQuality
from engine.items.generator import ItemGenerator, ItemGenerationParams
from engine.utils.rng import RNG


@dataclass
class Recipe:
    """A crafting recipe."""

    id: str
    name: str
    skill_id: str
    skill_level_required: int = 0
    result_archetype: str = ""
    result_material_id: Optional[str] = None
    result_quality: Optional[ItemQuality] = None
    materials: dict[str, int] = field(default_factory=dict)  # material_id -> count
    tools: list[str] = field(default_factory=list)
    base_time: float = 30.0  # seconds of in-game work
    base_xp: int = 25
    difficulty: float = 1.0
    success_chance_base: float = 0.9
    tags: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class CraftingResult:
    success: bool
    item: Optional[Item] = None
    xp_gained: int = 0
    materials_consumed: dict[str, int] = field(default_factory=dict)
    message: str = ""
    critical_success: bool = False
    critical_failure: bool = False


class RecipeLibrary:
    """Registry of recipes."""

    _recipes: ClassVar[dict[str, Recipe]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, recipe: Recipe) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._recipes[recipe.id] = recipe

    @classmethod
    def get(cls, recipe_id: str) -> Optional[Recipe]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._recipes.get(recipe_id)

    @classmethod
    def all(cls) -> list[Recipe]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._recipes.values())

    @classmethod
    def by_skill(cls, skill_id: str) -> list[Recipe]:
        return [r for r in cls.all() if r.skill_id == skill_id]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for r in DEFAULT_RECIPES:
            cls._recipes[r.id] = r
        cls._defaults_loaded = True


class CraftingSystem:
    """Resolves crafting actions."""

    def __init__(self, item_generator: Optional[ItemGenerator] = None,
                 rng: Optional[RNG] = None) -> None:
        self.item_generator = item_generator or ItemGenerator()
        self.rng = rng or RNG()

    def craft(self, recipe: Recipe, crafter: Entity, available_materials: dict[str, int],
              skill_level: int, *, item_id: int = 0) -> CraftingResult:
        # Check level
        if skill_level < recipe.skill_level_required:
            return CraftingResult(
                success=False, message=f"Need {recipe.skill_level_required} {recipe.skill_id}.",
            )
        # Check materials
        for mat_id, count in recipe.materials.items():
            if available_materials.get(mat_id, 0) < count:
                return CraftingResult(
                    success=False, message=f"Missing material: {mat_id}.",
                )
        # Roll success
        chance = recipe.success_chance_base + (skill_level - recipe.skill_level_required) * 0.02
        chance = min(0.99, max(0.05, chance))
        roll = self.rng.random()
        if roll > chance:
            # Failure consumes half materials
            consumed = {m: c // 2 for m, c in recipe.materials.items()}
            return CraftingResult(
                success=False, materials_consumed=consumed, xp_gained=recipe.base_xp // 4,
                message="Crafting failed — materials ruined.",
            )
        # Critical success?
        crit_success = roll < 0.05
        crit_fail = False
        # Generate the result item
        params = ItemGenerationParams(
            archetype=recipe.result_archetype,
            material_id=recipe.result_material_id,
            quality=recipe.result_quality or (ItemQuality.EXCELLENT if crit_success else None),
            level=max(1, skill_level // 10),
            allow_affixes=crit_success,
            max_affixes=1 if crit_success else 0,
            enchanted_chance=0.1 if crit_success else 0.0,
        )
        item = self.item_generator.generate(params, item_id)
        if crit_success:
            item.append_history(f"Masterfully crafted by entity {crafter.id}.")
        else:
            item.append_history(f"Crafted by entity {crafter.id}.")
        item.add_owner(crafter.id)
        xp = recipe.base_xp + (recipe.skill_level_required * 2)
        if crit_success:
            xp *= 2
        return CraftingResult(
            success=True, item=item, xp_gained=xp,
            materials_consumed=dict(recipe.materials),
            critical_success=crit_success, critical_failure=crit_fail,
            message=f"Successfully crafted {item.display_name}!",
        )


# Default recipes — production would load from JSON.
DEFAULT_RECIPES: list[Recipe] = [
    Recipe("iron_dagger", "Iron Dagger", "smithing", 1, "dagger", "iron",
           None, {"iron": 1}, ["anvil", "hammer"], 30, 25, 1.0, 0.9, [],
           "A simple iron dagger."),
    Recipe("steel_longsword", "Steel Longsword", "smithing", 25, "longsword", "steel",
           None, {"steel": 3}, ["anvil", "hammer"], 90, 100, 1.2, 0.8, [],
           "A well-balanced steel longsword."),
    Recipe("leather_armor", "Leather Armour", "tailoring", 5, "leather_armor", "leather",
           None, {"leather": 4}, ["needle"], 60, 40, 1.0, 0.9, [],
           "Tanned leather armour."),
    Recipe("oak_bow", "Oak Bow", "woodworking", 8, "bow", "oak",
           None, {"oak": 2}, ["knife"], 75, 50, 1.1, 0.85, [],
           "A sturdy oak bow."),
    Recipe("health_potion", "Health Potion", "alchemy", 3, "health_potion",
           None, {}, ["alembic"], 20, 30, 1.0, 0.85, [],
           "A restorative potion."),
    Recipe("mana_potion", "Mana Potion", "alchemy", 5, "mana_potion",
           None, {}, ["alembic"], 25, 35, 1.0, 0.85, [],
           "A mana-restoring potion."),
    Recipe("bread", "Bread", "cooking", 1, "bread",
           None, {}, ["oven"], 15, 10, 0.8, 0.95, [],
           "A loaf of bread."),
    Recipe("iron_helmet", "Iron Helmet", "smithing", 10, "helmet", "iron",
           None, {"iron": 2}, ["anvil", "hammer"], 45, 50, 1.1, 0.85, [],
           "A protective iron helm."),
    Recipe("chainmail", "Chainmail", "smithing", 35, "chainmail", "iron",
           None, {"iron": 8}, ["anvil", "hammer"], 180, 200, 1.4, 0.7, [],
           "Interlocking iron rings."),
    Recipe("torch", "Torch", "woodworking", 0, "torch", "pine",
           None, {"pine": 1}, [], 5, 5, 0.7, 0.98, [],
           "A simple pitch torch."),
]
