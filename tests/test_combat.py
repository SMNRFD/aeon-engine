"""Tests for combat."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.core.ecs import World
from engine.combat.system import CombatSystem
from engine.combat.damage import Damage, DamageType, DamageCalculator
from engine.entities.components import Health, Stats, Combat as CombatComp
from engine.entities.factory import EntityFactory
from engine.utils.rng import RNG


def test_damage_calculation_basic():
    damage = Damage(amount=20, type=DamageType.SLASHING)
    stats = Stats(endurance=10)
    final = DamageCalculator.compute(damage, target_stats=stats, target_armor=10.0)
    assert 0 < final < 20


def test_damage_resistance():
    damage = Damage(amount=50, type=DamageType.FIRE)
    final = DamageCalculator.compute(
        damage, target_stats=None, target_resistances={DamageType.FIRE: 0.5},
    )
    assert final == 25.0


def test_true_damage_bypasses():
    damage = Damage(amount=50, type=DamageType.TRUE)
    final = DamageCalculator.compute(
        damage, target_stats=None, target_armor=100, target_resistances={DamageType.TRUE: 0.9},
    )
    assert final == 50


def test_attack_resolves():
    world = World()
    factory = EntityFactory(world, RNG(123))
    attacker = factory.create_creature("Test", "t", 100, x=0, y=0, hp=50, aggressive=True)
    target = factory.create_creature("Target", "x", 100, x=1, y=0, hp=50, aggressive=False)
    rng = RNG(42)
    combat = CombatSystem(rng, item_registry=None)
    result = combat.attack(world, attacker, target)
    assert result.attacker == attacker.id
    assert result.target == target.id


def test_full_combat_terminates():
    world = World()
    factory = EntityFactory(world, RNG(123))
    # Two creatures with low HP
    a = factory.create_creature("A", "a", 100, x=0, y=0, hp=20, aggressive=True)
    t = factory.create_creature("B", "b", 100, x=1, y=0, hp=20, aggressive=True)
    rng = RNG(42)
    combat = CombatSystem(rng, item_registry=None)
    result = combat.resolve_combat(world, a, t, max_rounds=20)
    assert result.winner is not None
    assert result.rounds >= 1


def test_status_effects():
    from engine.combat.effects import StatusEffectSystem
    world = World()
    factory = EntityFactory(world, RNG(123))
    e = factory.create_creature("Test", "t", 100, x=0, y=0, hp=50)
    sys_effects = StatusEffectSystem()
    sys_effects.apply(world, e, "burning", duration=2.0, magnitude=5.0)
    # Tick once
    sys_effects.update(world, dt=0.5)
    health = world.get_component(e, Health)
    # Burning should have dealt damage
    assert health.current < 50
