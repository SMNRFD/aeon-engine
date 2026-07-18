"""Tests for skills, magic, dialogue, quests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.core.ecs import World, Entity
from engine.entities.factory import EntityFactory
from engine.skills.system import SkillsSystem, SkillLibrary
from engine.magic.spells import SpellCaster, SpellLibrary
from engine.magic.spells import Mana
from engine.dialogue.system import DialogueEngine, DialogueLibrary
from engine.quests.system import QuestLibrary, QuestTracker, QuestGenerator
from engine.utils.rng import RNG


def test_skill_library_loaded():
    skills = SkillLibrary.all()
    assert len(skills) >= 50  # we have 58 skills


def test_skill_xp_and_level_up():
    world = World()
    factory = EntityFactory(world, RNG(42))
    e = factory.create_npc("Test")
    system = SkillsSystem()
    # Add XP
    level = system.add_xp(e, "swordsmanship", 200, world)
    assert level >= 1


def test_skill_check():
    world = World()
    factory = EntityFactory(world, RNG(42))
    e = factory.create_npc("Test")
    system = SkillsSystem()
    result = system.check(e, "swordsmanship", 50, RNG(42))
    assert isinstance(result.success, bool)
    assert isinstance(result.roll, float)


def test_spell_library():
    spells = SpellLibrary.all()
    assert len(spells) >= 10


def test_spell_cast_heal():
    world = World()
    factory = EntityFactory(world, RNG(42))
    caster = factory.create_npc("Caster")
    target = factory.create_npc("Target")
    # Add mana to caster
    from engine.magic.spells import Mana
    world.add_component(caster, Mana(current=100, maximum=100))
    from engine.entities.components import Health
    target_health = world.get_component(target, Health)
    target_health.current = 10
    target_health.maximum = 50
    spell = SpellLibrary.get("heal")
    assert spell is not None
    caster_sys = SpellCaster(rng=RNG(42))
    result = caster_sys.cast(world, caster, spell, target)
    assert result.success
    assert result.healing_done > 0
    assert target_health.current > 10


def test_spell_cast_insufficient_mana():
    world = World()
    factory = EntityFactory(world, RNG(42))
    caster = factory.create_npc("Caster")
    target = factory.create_npc("Target")
    world.add_component(caster, Mana(current=5, maximum=5))
    spell = SpellLibrary.get("fireball")  # costs 30
    caster_sys = SpellCaster(rng=RNG(42))
    result = caster_sys.cast(world, caster, spell, target)
    assert not result.success


def test_dialogue_library():
    trees = DialogueLibrary.all()
    assert len(trees) >= 2


def test_dialogue_start():
    world = World()
    factory = EntityFactory(world, RNG(42))
    player = factory.create_player()
    npc = factory.create_npc("NPC")
    tree = DialogueLibrary.get("commoner_greeting")
    engine = DialogueEngine(rng=RNG(42))
    ctx = engine.start(world, player, npc, tree)
    assert ctx.current_node_id == "start"
    assert len(ctx.history) > 0


def test_quest_generator():
    gen = QuestGenerator(RNG(42))
    q = gen.generate(level=5)
    assert q.name
    assert q.stages


def test_quest_tracker():
    tracker = QuestTracker()
    from engine.quests.system import QuestLibrary
    q = QuestLibrary.all()[0]
    tracker.start(q, current_tick=0.0)
    assert q.id in tracker.active
    tracker.advance_objective(q.id, q.start_stage, q.stages[q.start_stage].objectives[0].id, 5)
    assert tracker.objective_progress(q.id, q.start_stage,
                                      q.stages[q.start_stage].objectives[0].id) == 5
