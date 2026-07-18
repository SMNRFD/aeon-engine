"""Entity-Component-System (ECS) core.

A lean, fast, type-safe ECS implementation:

* `Component` — base class for all components (plain data + optional logic).
* `Entity` — a unique identifier wrapping a 64-bit id.
* `World` — the central registry that maps entities to component sets and
  powers component queries.

The world supports:
  * Component addition / removal / lookup in O(1) average time.
  * Fast queries via `World.view(...)` returning tuples of components.
  * Archetype-style grouping by component signature for iteration locality.
  * Entity tags for fast boolean classification (e.g. "player", "hostile").
  * Per-entity component mutation events (consumed by the EventBus).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional, Type, TypeVar

from engine.core.logging import get_logger


log = get_logger("ecs")

T = TypeVar("T")
ComponentT = TypeVar("ComponentT", bound="Component")


class Component:
    """Base class for all ECS components.

    Subclass to define a component type. Components are pure data containers
    with optional derived-property helpers. They are not behaviour.
    """

    __slots__ = ()


@dataclass(frozen=True)
class Entity:
    """A unique entity identifier."""

    id: int
    generation: int = 0

    def __int__(self) -> int:
        return (self.id << 16) | (self.generation & 0xFFFF)

    def __hash__(self) -> int:
        return hash((self.id, self.generation))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Entity):
            return self.id == other.id and self.generation == other.generation
        return NotImplemented

    def __str__(self) -> str:
        return f"Entity#{self.id}.{self.generation}"

    def __repr__(self) -> str:
        return str(self)


class System:
    """Base class for systems that operate on the world each tick.

    Systems implement `update(world, dt)` and may declare `required_components`
    for automatic iteration via `iterate(world)`.
    """

    required_components: tuple[Type[Component], ...] = ()

    def update(self, world: "World", dt: float) -> None:  # noqa: ARG002
        """Called once per simulation tick."""

    def iterate(self, world: "World") -> Iterator[tuple[Entity, tuple[Component, ...]]]:
        """Iterate over all entities matching `required_components`."""
        if not self.required_components:
            return iter(())
        return world.view(*self.required_components)


class World:
    """The central ECS registry."""

    def __init__(self) -> None:
        self._next_id: int = 1
        self._entities: dict[int, int] = {}  # id -> generation
        self._components: dict[Entity, dict[Type[Component], Component]] = {}
        self._by_type: dict[Type[Component], set[Entity]] = {}
        self._tags: dict[Entity, set[str]] = {}
        self._systems: list[System] = []
        self._listeners: dict[Type[Component], list[Callable[[Entity, str, Any], None]]] = {}
        self._dead: set[Entity] = set()
        log.debug("World initialised")

    # ---------- entity lifecycle ----------

    def create_entity(self) -> Entity:
        """Create a new entity and return its handle."""
        eid = self._next_id
        self._next_id += 1
        gen = 0
        self._entities[eid] = gen
        entity = Entity(eid, gen)
        self._components[entity] = {}
        self._tags[entity] = set()
        log.debug("Created %s", entity)
        return entity

    def destroy_entity(self, entity: Entity) -> None:
        """Destroy an entity and remove all its components."""
        if not self.is_alive(entity):
            return
        comps = self._components.pop(entity, {})
        for comp_type in list(comps):
            self._by_type.get(comp_type, set()).discard(entity)
        self._tags.pop(entity, None)
        self._dead.add(entity)
        # Mark as not alive by bumping the generation on the id.
        old_gen = self._entities.get(entity.id, 0)
        self._entities[entity.id] = old_gen + 1
        log.debug("Destroyed %s", entity)

    def is_alive(self, entity: Entity) -> bool:
        gen = self._entities.get(entity.id)
        return gen is not None and gen == entity.generation

    # ---------- components ----------

    def add_component(self, entity: Entity, component: Component) -> Component:
        """Attach a component to an entity. Replaces existing of same type."""
        if not self.is_alive(entity):
            raise ValueError(f"Entity {entity} is not alive")
        comp_type = type(component)
        if entity not in self._components:
            self._components[entity] = {}
        self._components[entity][comp_type] = component
        self._by_type.setdefault(comp_type, set()).add(entity)
        self._notify(entity, "add", comp_type, component)
        return component

    def remove_component(self, entity: Entity, comp_type: Type[ComponentT]) -> Optional[ComponentT]:
        """Remove and return a component from an entity."""
        if not self.is_alive(entity):
            return None
        comps = self._components.get(entity, {})
        comp = comps.pop(comp_type, None)
        if comp is not None:
            self._by_type.get(comp_type, set()).discard(entity)
            self._notify(entity, "remove", comp_type, comp)
        return comp  # type: ignore[return-value]

    def get_component(self, entity: Entity, comp_type: Type[ComponentT]) -> Optional[ComponentT]:
        """Return the component of `comp_type` on `entity`, or None."""
        if not self.is_alive(entity):
            return None
        comps = self._components.get(entity, {})
        return comps.get(comp_type)  # type: ignore[return-value]

    def has_component(self, entity: Entity, comp_type: Type[Component]) -> bool:
        if not self.is_alive(entity):
            return False
        return comp_type in self._components.get(entity, {})

    def get_components(self, entity: Entity) -> dict[Type[Component], Component]:
        """Return all components on an entity."""
        return dict(self._components.get(entity, {}))

    def entities_with(self, comp_type: Type[Component]) -> set[Entity]:
        """Return the set of entities that have a given component type."""
        return set(self._by_type.get(comp_type, set()))

    def view(self, *comp_types: Type[Component]) -> Iterator[tuple[Entity, tuple[Component, ...]]]:
        """Yield (entity, (comp1, comp2, ...)) for every entity that has all
        of the requested component types."""
        if not comp_types:
            return
        # Pick the rarest component type as the lead for performance.
        lead = min(comp_types, key=lambda t: len(self._by_type.get(t, set())))
        candidates = self._by_type.get(lead, set())
        rest = [t for t in comp_types if t is not lead]
        for entity in list(candidates):
            if not self.is_alive(entity):
                continue
            comps = self._components[entity]
            if all(t in comps for t in rest):
                yield entity, tuple(comps[t] for t in comp_types)

    # ---------- tags ----------

    def tag(self, entity: Entity, tag: str) -> None:
        if not self.is_alive(entity):
            return
        self._tags.setdefault(entity, set()).add(tag)

    def untag(self, entity: Entity, tag: str) -> None:
        if not self.is_alive(entity):
            return
        self._tags.get(entity, set()).discard(tag)

    def has_tag(self, entity: Entity, tag: str) -> bool:
        return tag in self._tags.get(entity, set())

    def entities_with_tag(self, tag: str) -> set[Entity]:
        return {e for e, tags in self._tags.items() if tag in tags and self.is_alive(e)}

    # ---------- systems ----------

    def add_system(self, system: System) -> None:
        self._systems.append(system)
        log.debug("Registered system %s", system.__class__.__name__)

    def remove_system(self, system: System) -> None:
        self._systems.remove(system)

    def update(self, dt: float) -> None:
        """Tick every system by `dt` seconds."""
        for system in self._systems:
            system.update(self, dt)

    # ---------- introspection ----------

    def entity_count(self) -> int:
        return len(self._components)

    def component_count(self, comp_type: Type[Component]) -> int:
        return len(self._by_type.get(comp_type, set()))

    # ---------- listeners ----------

    def on_component_change(
        self,
        comp_type: Type[Component],
        callback: Callable[[Entity, str, Any], None],
    ) -> None:
        """Register a callback fired when a component of `comp_type` is added/removed."""
        self._listeners.setdefault(comp_type, []).append(callback)

    def _notify(
        self,
        entity: Entity,
        action: str,
        comp_type: Type[Component],
        component: Component,
    ) -> None:
        for cb in self._listeners.get(comp_type, []):
            try:
                cb(entity, action, component)
            except Exception:  # noqa: BLE001
                log.exception("Component listener raised")


__all__ = ["Component", "Entity", "System", "World"]
