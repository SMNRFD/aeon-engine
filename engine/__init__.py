"""
Aeon Engine — A production-grade text-based open-world RPG engine.

A modular, plugin-driven, event-driven simulation engine inspired by
Dwarf Fortress, Cataclysm DDA, Caves of Qud, Rimworld, Starsector,
Project Zomboid, Crusader Kings, Mount & Blade, Kenshi, EVE Online,
Noita, Minecraft, Terraria, Ultima, and traditional roguelikes.

The engine is organised into isolated subsystems under `engine/`:

* `core`       — ECS, events, config, logging, game clock
* `plugins`    — dynamic plugin loading, hot reload, sandboxing
* `world`      — procedural terrain, biomes, pathfinding, spatial index
* `entities`   — ECS components and entity factory
* `npc`        — AI, needs, memory, schedule, personality
* `items`      — procedural items, materials, affixes
* `inventory`  — inventory and equipment management
* `combat`     — turn-based combat, damage, status effects
* `skills`     — skill progression and decay
* `crafting`   — recipes, research, experimentation
* `magic`      — spell schools, procedural spell crafting
* `dialogue`   — dialogue trees, persuasion, rumors
* `quests`     — dynamic, branching, procedural quests
* `economy`    — markets, trade routes, banking, inflation
* `factions`   — diplomacy, wars, laws, reputation
* `weather`    — seasonal climate and weather simulation
* `survival`   — hunger, thirst, fatigue, disease, sanity
* `commands`   — command parser, aliases, macros, permissions
* `serialization` — versioned saves with migration and integrity
* `localization` — i18n with pluralization and RTL
* `render`     — terminal rendering primitives
* `ui`         — screens, panels, themes
* `utils`      — RNG, math, helpers
* `network`    — client/server-ready networking hooks
"""

__version__ = "0.1.0"
__engine_name__ = "Aeon"

from engine.core.config import EngineConfig, get_config
from engine.core.events import EventBus, Event
from engine.core.ecs import Entity, Component, World
from engine.core.clock import GameClock
from engine.core.logging import get_logger, configure_logging

__all__ = [
    "EngineConfig",
    "get_config",
    "EventBus",
    "Event",
    "Entity",
    "Component",
    "World",
    "GameClock",
    "get_logger",
    "configure_logging",
    "__version__",
    "__engine_name__",
]
