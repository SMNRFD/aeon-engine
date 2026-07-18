"""Sample plugin for the Aeon engine.

Implements a 'fishing' skill and a 'fish' command. Demonstrates:
* Plugin lifecycle hooks
* Command registration
* Skill use
* Item generation
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.commands.system import Command, CommandContext, CommandResult, Permission
from engine.core.ecs import Entity
from engine.core.events import Event, EventBus, Priority
from engine.items.generator import ItemGenerationParams
from engine.plugins.base import Plugin, PluginMetadata
from engine.skills.system import Skill, SkillLibrary
from engine.world.map import WorldMap
from engine.world.terrain import TerrainType


class FishingEvent(Event):
    """Fired when an entity catches a fish."""

    def __init__(self, entity_id: int, fish_type: str, weight: float) -> None:
        super().__init__()
        self.entity_id = entity_id
        self.fish_type = fish_type
        self.weight = weight


class FishingPlugin(Plugin):
    """Adds fishing skill and command."""

    metadata = PluginMetadata(
        name="fishing",
        version="0.1.0",
        description="Adds fishing skill and command.",
        author="Aeon Team",
        license="MIT",
        dependencies=[],
        tags=["gameplay", "skill"],
        load_order=10,
    )

    def on_load(self, engine) -> None:
        self.logger.info("Fishing plugin loading")
        # Register fishing skill
        SkillLibrary.register(Skill(
            id="fishing", name="Fishing",
            description="Catching fish from water.",
            category="survival", governing_attribute="perception",
            difficulty=0.9, base_xp=80, max_level=100, decay_rate=0.0001,
        ))

    def on_enable(self, engine) -> None:
        # Register the 'fish' command
        engine.register_command(
            "fish", _cmd_fish,
            description="Attempt to catch a fish.",
            usage="fish",
            aliases=["fishing"],
            permission=Permission.PLAYER,
            plugin=self.metadata.name,
        )
        # Subscribe to fishing events for stats
        if engine.event_bus:
            engine.event_bus.subscribe(FishingEvent, _on_fish_caught,
                                       priority=Priority.MONITOR,
                                       plugin=self.metadata.name)
        self.logger.info("Fishing plugin enabled")

    def on_disable(self, engine) -> None:
        self.logger.info("Fishing plugin disabled")
        if hasattr(engine, "commands"):
            engine.commands.unregister("fish")

    def on_unload(self, engine) -> None:
        self.logger.info("Fishing plugin unloaded")


def _cmd_fish(ctx: CommandContext) -> CommandResult:
    """Try to catch a fish."""
    if ctx.engine is None or ctx.player is None:
        return CommandResult(success=False, error="No engine or player.")
    from engine.entities.components import Position
    pos = ctx.world.get_component(ctx.player, Position)
    if pos is None:
        return CommandResult(success=False, error="No position.")
    # Check that player is adjacent to water
    world_map: WorldMap = ctx.engine.world_map
    if world_map is None:
        return CommandResult(success=False, error="No world map.")
    water_adjacent = False
    for n in world_map.neighbours(pos.x, pos.y):
        if n.terrain.is_liquid:
            water_adjacent = True
            break
    if not water_adjacent:
        return CommandResult(success=False, error="You need to be near water to fish.")
    # Roll a fishing check
    from engine.skills.system import SkillsSystem
    skills = SkillsSystem()
    skill_level = skills.get_level(ctx.player, "fishing")
    difficulty = 30
    result = skills.check(ctx.player, "fishing", difficulty, ctx.engine.rng)
    if not result.success:
        return CommandResult(success=True, output="You wait, but nothing bites...")
    # Success — generate a fish item
    fish_types = ["fish", "fish", "fish", "salmon", "trout", "rare_fish"]
    fish_type = ctx.engine.rng.choice(fish_types)
    params = ItemGenerationParams(
        archetype="bread",  # reuse consumable archetype
        material_id="organic",
    )
    item = ctx.engine.item_generator.generate(params, ctx.engine.items.next_id())
    item.name = fish_type.replace("_", " ").title()
    item.description = f"A fresh-caught {fish_type}."
    item.tags.append("food")
    item.add_property("food", 35.0)
    ctx.engine.items.register(item)
    inv = ctx.engine.inventories.get(ctx.player.id)
    if inv is None:
        return CommandResult(success=False, error="No inventory.")
    inv.add(item)
    # Award XP
    skills.add_xp(ctx.player, "fishing", 15, ctx.world)
    # Fire event
    ctx.engine.event_bus.dispatch(FishingEvent(ctx.player.id, fish_type, item.weight))
    return CommandResult(success=True,
                         output=f"You caught a {fish_type.replace('_', ' ')}!")


def _on_fish_caught(event: FishingEvent) -> None:
    """Monitor handler — log catches for stats."""
    import logging
    logging.getLogger("aeon.plugin.fishing").info(
        "Entity %d caught a %s (%.2f kg)",
        event.entity_id, event.fish_type, event.weight,
    )
