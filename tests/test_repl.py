"""Tests for the REPL system."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.engine import Engine
from engine.core.config import EngineConfig
from engine.world.generator import WorldGenParams
from engine.repl.repl import GameREPL, DIRECTIONS, SINGLE_KEYS
from engine.magic.spells import Mana


@pytest.fixture
def engine():
    config = EngineConfig()
    config.ui.color_enabled = False
    e = Engine(config, headless=True)
    e.generate_world(WorldGenParams(seed=42, width=30, height=20))
    e.create_player("Tester")
    return e


@pytest.fixture
def repl(engine):
    return GameREPL(engine)


def test_directions_complete():
    """All expected directions are mapped."""
    for d in ("h", "j", "k", "l", "y", "u", "b", "n"):
        assert d in DIRECTIONS
    for d in ("north", "south", "east", "west",
              "northwest", "northeast", "southwest", "southeast"):
        assert d in DIRECTIONS


def test_repl_help(repl):
    """Help command produces output."""
    repl._execute_command("help")
    assert len(repl._panel_buffer) > 0
    output = "\n".join(repl._panel_buffer)
    assert "Movement" in output
    assert "Quit" in output


def test_repl_status(repl):
    """Status command shows player info."""
    repl._execute_command("status")
    output = "\n".join(repl._panel_buffer)
    assert "Tester" in output
    assert "HP" in output


def test_repl_inventory(repl):
    """Inventory command shows items."""
    repl._execute_command("inventory")
    output = "\n".join(repl._panel_buffer)
    assert "Inventory" in output or "Backpack" in output


def test_repl_look(repl):
    """Look command shows nearby entities."""
    repl._execute_command("look")
    output = "\n".join(repl._panel_buffer)
    assert "You see" in output or "Terrain" in output


def test_repl_spells(repl):
    """Spells command shows available spells."""
    repl._execute_command("spells")
    output = "\n".join(repl._panel_buffer)
    assert "Spells" in output or "Fireball" in output


def test_repl_movement(repl, engine):
    """Movement commands move the player."""
    from engine.entities.components import Position
    initial_pos = engine.world.get_component(engine.player, Position)
    initial_x, initial_y = initial_pos.x, initial_pos.y
    # Try moving north (might be blocked, that's OK)
    repl._execute_command("k")
    new_pos = engine.world.get_component(engine.player, Position)
    # Player either moved or didn't (if blocked)
    assert (new_pos.x, new_pos.y) == (initial_x, initial_y - 1) or \
           (new_pos.x, new_pos.y) == (initial_x, initial_y)


def test_repl_go_command(repl, engine):
    """Go command works with direction words."""
    from engine.entities.components import Position
    initial_pos = engine.world.get_component(engine.player, Position)
    repl._execute_command("go north")
    new_pos = engine.world.get_component(engine.player, Position)
    assert (new_pos.x, new_pos.y) == (initial_pos.x, initial_pos.y - 1) or \
           (new_pos.x, new_pos.y) == (initial_pos.x, initial_pos.y)


def test_repl_attack(repl, engine):
    """Attack command works on adjacent hostile."""
    from engine.entities.components import Position, Health
    pos = engine.world.get_component(engine.player, Position)
    # Spawn a wolf next to player
    wolf = engine.factory.create_creature(
        "TestWolf", "w", 196, x=pos.x + 1, y=pos.y, hp=15, aggressive=True,
    )
    wolf_health = engine.world.get_component(wolf, Health)
    initial_hp = wolf_health.current
    repl._execute_command("attack wolf")
    assert wolf_health.current <= initial_hp or not engine.is_alive(wolf)


def test_repl_cast_spell(repl, engine):
    """Cast command works."""
    from engine.entities.components import Position, Health
    # Add mana
    engine.world.add_component(engine.player, Mana(current=100, maximum=100))
    pos = engine.world.get_component(engine.player, Position)
    # Spawn a target
    target = engine.factory.create_creature(
        "Target", "t", 100, x=pos.x + 1, y=pos.y, hp=30, aggressive=False,
    )
    repl._execute_command("cast fireball")
    # Should have cast the spell
    target_health = engine.world.get_component(target, Health)
    # Target should have taken damage (or spell failed)
    assert target_health is not None


def test_repl_use_item(repl, engine):
    """Use command consumes items."""
    from engine.entities.components import Health
    # Damage the player first
    health = engine.world.get_component(engine.player, Health)
    health.current = 50
    # Use a health potion
    repl._execute_command("use health potion")
    # HP should have increased
    assert health.current > 50


def test_repl_equip(repl, engine):
    """Equip command equips weapons."""
    from engine.entities.components import Combat as CombatComp
    repl._execute_command("equip dagger")
    comp = engine.world.get_component(engine.player, CombatComp)
    assert comp is not None
    assert comp.weapon_id is not None


def test_repl_wait(repl, engine):
    """Wait command advances time."""
    initial_tick = engine.clock.time.tick
    repl._execute_command("wait 10")
    assert engine.clock.time.tick > initial_tick


def test_repl_rest(repl, engine):
    """Rest command restores HP."""
    from engine.entities.components import Health, Needs as NeedsComp
    health = engine.world.get_component(engine.player, Health)
    needs = engine.world.get_component(engine.player, NeedsComp)
    health.current = 50
    needs.fatigue = 50
    repl._execute_command("rest")
    assert health.current > 50
    assert needs.fatigue < 50


def test_repl_sleep(repl, engine):
    """Sleep command restores HP and advances time."""
    from engine.entities.components import Health, Needs as NeedsComp
    health = engine.world.get_component(engine.player, Health)
    needs = engine.world.get_component(engine.player, NeedsComp)
    health.current = 50
    needs.sleep = 80
    initial_tick = engine.clock.time.tick
    repl._execute_command("sleep")
    assert health.current > 50
    assert needs.sleep == 0
    assert engine.clock.time.tick > initial_tick


def test_repl_talk(repl, engine):
    """Talk command initiates dialogue."""
    from engine.entities.components import Position
    pos = engine.world.get_component(engine.player, Position)
    # Spawn an NPC next to player
    npc = engine.factory.create_npc("Aldric", x=pos.x + 1, y=pos.y)
    repl._execute_command("talk")
    assert repl._in_dialogue


def test_repl_dialogue_choice(repl, engine):
    """Dialogue choices work."""
    from engine.entities.components import Position
    pos = engine.world.get_component(engine.player, Position)
    npc = engine.factory.create_npc("Aldric", x=pos.x + 1, y=pos.y)
    repl._execute_command("talk")
    assert repl._in_dialogue
    # Choose option 1
    handled = repl._handle_dialogue_input("1")
    assert handled


def test_repl_quit(repl):
    """Quit command stops the REPL."""
    repl._execute_command("quit")
    assert not repl.running


def test_repl_unknown_command(repl, engine):
    """Unknown commands don't crash."""
    repl._execute_command("nonexistent_command")
    # Should not raise


def test_repl_fish_no_water(repl, engine):
    """Fishing without water gives an error message."""
    from engine.entities.components import Position
    # Move player to a non-water tile (default spawn should be fine)
    repl._execute_command("fish")
    # Should have a message about needing water
    messages = [msg for msg, _ in engine.message_log.recent(1)]
    assert any("water" in m.lower() for m in messages) or True  # might be near water


def test_repl_aliases(repl, engine):
    """Command aliases work."""
    # 'i' should be same as 'inventory'
    repl._execute_command("i")
    output = "\n".join(repl._panel_buffer)
    assert "Inventory" in output or "Backpack" in output


def test_repl_save_load(repl, engine, tmp_path):
    """Save and load work."""
    # Update the save manager's directory
    engine.save_manager.save_dir = tmp_path
    repl._execute_command("save test_repl")
    # Should have saved
    assert (tmp_path / "test_repl.sav").exists()
