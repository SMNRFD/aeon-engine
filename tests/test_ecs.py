"""Tests for the ECS core."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest
from engine.core.ecs import Component, Entity, World


class Health(Component):
    def __init__(self, current: int = 100, maximum: int = 100):
        self.current = current
        self.maximum = maximum


class Position(Component):
    def __init__(self, x: int = 0, y: int = 0):
        self.x = x
        self.y = y


class Name(Component):
    def __init__(self, value: str = ""):
        self.value = value


def test_create_entity():
    world = World()
    e = world.create_entity()
    assert e.id == 1
    assert world.is_alive(e)


def test_destroy_entity():
    world = World()
    e = world.create_entity()
    assert world.is_alive(e)
    world.destroy_entity(e)
    assert not world.is_alive(e)


def test_add_remove_component():
    world = World()
    e = world.create_entity()
    health = Health(current=50, maximum=80)
    world.add_component(e, health)
    assert world.has_component(e, Health)
    assert world.get_component(e, Health).current == 50
    removed = world.remove_component(e, Health)
    assert removed is not None
    assert not world.has_component(e, Health)


def test_entities_with():
    world = World()
    e1 = world.create_entity()
    e2 = world.create_entity()
    e3 = world.create_entity()
    world.add_component(e1, Health())
    world.add_component(e2, Health())
    world.add_component(e3, Position())
    entities = world.entities_with(Health)
    assert len(entities) == 2
    assert e1 in entities
    assert e2 in entities


def test_view():
    world = World()
    e1 = world.create_entity()
    world.add_component(e1, Health(current=50))
    world.add_component(e1, Position(x=5))
    e2 = world.create_entity()
    world.add_component(e2, Health())
    e3 = world.create_entity()
    world.add_component(e3, Position())
    results = list(world.view(Health, Position))
    assert len(results) == 1
    entity, comps = results[0]
    assert entity == e1
    assert isinstance(comps[0], Health)
    assert isinstance(comps[1], Position)


def test_tags():
    world = World()
    e = world.create_entity()
    world.tag(e, "player")
    assert world.has_tag(e, "player")
    assert e in world.entities_with_tag("player")
    world.untag(e, "player")
    assert not world.has_tag(e, "player")


def test_component_listener():
    world = World()
    events = []
    world.on_component_change(Health, lambda e, action, c: events.append((e, action, c)))
    e = world.create_entity()
    h = Health()
    world.add_component(e, h)
    assert len(events) == 1
    assert events[0][1] == "add"
    world.remove_component(e, Health)
    assert len(events) == 2
    assert events[1][1] == "remove"


def test_dead_entity_not_in_views():
    world = World()
    e = world.create_entity()
    world.add_component(e, Health())
    world.add_component(e, Position())
    world.destroy_entity(e)
    results = list(world.view(Health, Position))
    assert len(results) == 0
