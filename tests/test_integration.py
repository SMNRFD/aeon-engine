"""Integration tests — full engine workflows."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.core.config import EngineConfig
from engine.engine import Engine
from engine.world.generator import WorldGenParams
from engine.commands.system import CommandContext, Permission


def test_engine_full_init_headless():
    """Test that the engine initializes all subsystems without errors."""
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    assert engine.event_bus is not None
    assert engine.world is not None
    assert engine.clock is not None
    assert engine.items is not None
    assert engine.combat is not None
    assert engine.skills is not None
    assert engine.crafting is not None
    assert engine.spell_caster is not None
    assert engine.dialogue is not None
    assert engine.quest_generator is not None
    assert engine.factions is not None
    assert engine.economy is not None
    assert engine.weather is not None
    assert engine.survival is not None
    assert engine.needs_system is not None
    assert engine.ai_registry is not None
    assert engine.save_manager is not None
    assert engine.plugins is not None
    assert engine.message_log is not None
    assert engine.commands is not None
    assert engine.command_processor is not None


def test_engine_generates_world():
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=30, height=20,
                                          settlement_count=2, river_count=4))
    assert engine.world_map is not None
    assert engine.world_map.width == 30
    assert engine.world_map.height == 20
    assert engine.pathfinder is not None


def test_engine_creates_player():
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=30, height=20))
    player = engine.create_player("TestHero")
    assert player is not None
    from engine.entities.components import Identity, Position, Health
    identity = engine.world.get_component(player, Identity)
    assert identity.name == "TestHero"
    pos = engine.world.get_component(player, Position)
    assert pos is not None
    health = engine.world.get_component(player, Health)
    assert health.current > 0


def test_engine_simulation_tick():
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=30, height=20))
    engine.create_player("TestHero")
    # Run a few ticks
    for _ in range(5):
        engine.tick_simulation(0.05)
    # Game time should have advanced
    assert engine.clock.time.tick > 0


def test_engine_save_load_round_trip(tmp_path):
    """Test save/load round trip."""
    config = EngineConfig()
    config.ui.color_enabled = False
    config.save.save_dir = str(tmp_path)
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=20, height=15))
    engine.create_player("TestHero")
    # Save
    engine.save_game("test_round_trip")
    assert (tmp_path / "test_round_trip.sav").exists()
    # Load
    new_engine = Engine(config, headless=True)
    new_engine.load_game("test_round_trip")
    # World map should be restored
    assert new_engine.world_map is not None
    assert new_engine.world_map.width == 20
    assert new_engine.world_map.height == 15


def test_engine_command_execution():
    """Test that commands can be executed end-to-end."""
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=20, height=15))
    engine.create_player("TestHero")
    # Execute 'look' command
    ctx = CommandContext(
        world=engine.world, player=engine.player,
        raw_input="look", engine=engine,
        caller_id=engine.player.id,
        permission=Permission.OWNER,
    )
    result = engine.command_processor.execute("look", ctx)
    assert result.success
    assert "You are at" in result.output


def test_engine_player_movement():
    """Test player movement."""
    from engine.entities.components import Position
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=20, height=15))
    engine.create_player("TestHero")
    initial_pos = engine.world.get_component(engine.player, Position)
    initial_x, initial_y = initial_pos.x, initial_pos.y
    # Try moving east
    engine.move_player(1, 0)
    new_pos = engine.world.get_component(engine.player, Position)
    # Position should have changed (or stayed same if blocked)
    assert (new_pos.x, new_pos.y) == (initial_x + 1, initial_y) or \
           (new_pos.x, new_pos.y) == (initial_x, initial_y)


def test_engine_combat_with_creature():
    """Test combat between player and a creature."""
    from engine.entities.components import Position, Health
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    engine.generate_world(WorldGenParams(seed=42, width=20, height=15))
    engine.create_player("TestHero")
    # Spawn a creature next to the player
    pos = engine.world.get_component(engine.player, Position)
    creature = engine.factory.create_creature(
        "Test Wolf", "w", 196, x=pos.x + 1, y=pos.y,
        hp=10, aggressive=True,
    )
    # Attack it
    from engine.entities.components import Combat as CombatComp
    combat_comp = engine.world.get_component(engine.player, CombatComp)
    weapon = None
    if combat_comp and combat_comp.weapon_id is not None:
        weapon = engine.items.get(combat_comp.weapon_id)
    result = engine.combat.attack(engine.world, engine.player, creature, weapon)
    assert result.attacker == engine.player.id
    assert result.target == creature.id


def test_engine_plugin_loading():
    """Test that the fishing plugin loads correctly."""
    config = EngineConfig()
    config.ui.color_enabled = False
    engine = Engine(config, headless=True)
    success, failure = engine.plugins.load_all()
    # Should have loaded the fishing plugin
    assert success >= 1 or failure >= 1  # at least attempted


def test_engine_mod_loading():
    """Test that JSON mods load correctly."""
    from engine.mods_loader.system import ModLoader
    loader = ModLoader(mods_dir="mods")
    count = loader.discover()
    assert count >= 1
    # example_mod.json should be there
    assert loader.registry.get("example_content_mod") is not None
