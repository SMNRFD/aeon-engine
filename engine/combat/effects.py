"""Status effects — DoTs, buffs, debuffs, and crowd control."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Combat as CombatComponent, Health, Stats


class EffectType(Enum):
    DOT = "dot"          # damage over time
    HOT = "hot"          # healing over time
    BUFF = "buff"        # stat increase
    DEBUFF = "debuff"    # stat decrease
    CONTROL = "control"  # stun, fear, freeze, etc.


@dataclass
class StatusEffectInstance:
    """A runtime status effect on an entity."""

    name: str
    type: EffectType
    duration: float                # seconds remaining
    magnitude: float = 0.0
    tick_interval: float = 1.0
    tick_timer: float = 0.0
    damage_type: Optional[str] = None
    stat_modifiers: dict[str, float] = field(default_factory=dict)
    source: Optional[int] = None
    stacks: int = 1
    max_stacks: int = 1
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name, "type": self.type.value, "duration": self.duration,
            "magnitude": self.magnitude, "tick_interval": self.tick_interval,
            "tick_timer": self.tick_timer, "damage_type": self.damage_type,
            "stat_modifiers": dict(self.stat_modifiers), "source": self.source,
            "stacks": self.stacks, "max_stacks": self.max_stacks, "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StatusEffectInstance":
        return cls(
            name=data["name"], type=EffectType(data["type"]),
            duration=data["duration"], magnitude=data.get("magnitude", 0.0),
            tick_interval=data.get("tick_interval", 1.0),
            tick_timer=data.get("tick_timer", 0.0),
            damage_type=data.get("damage_type"),
            stat_modifiers=dict(data.get("stat_modifiers", {})),
            source=data.get("source"), stacks=data.get("stacks", 1),
            max_stacks=data.get("max_stacks", 1), data=data.get("data", {}),
        )


class StatusEffectSystem:
    """Applies and ticks status effects on entities."""

    # Convenience presets
    PRESETS: dict[str, dict] = {
        "bleeding": {"type": "dot", "magnitude": 2.0, "damage_type": "true",
                     "tick_interval": 1.0, "duration": 5.0},
        "poison": {"type": "dot", "magnitude": 1.5, "damage_type": "poison",
                   "tick_interval": 1.0, "duration": 8.0},
        "burning": {"type": "dot", "magnitude": 3.0, "damage_type": "fire",
                    "tick_interval": 0.5, "duration": 4.0},
        "frozen": {"type": "control", "duration": 2.0, "stat_modifiers": {"agility": -10}},
        "stunned": {"type": "control", "duration": 1.5},
        "fear": {"type": "control", "duration": 3.0, "stat_modifiers": {"willpower": -5}},
        "blessed": {"type": "buff", "duration": 30.0,
                    "stat_modifiers": {"strength": 2, "endurance": 2}},
        "hasted": {"type": "buff", "duration": 10.0,
                   "stat_modifiers": {"agility": 4}},
        "weakened": {"type": "debuff", "duration": 8.0,
                     "stat_modifiers": {"strength": -3}},
        "regenerating": {"type": "hot", "magnitude": 5.0, "tick_interval": 1.0,
                         "duration": 6.0},
    }

    def apply(self, world: World, entity: Entity, effect_name: str, *,
              duration: Optional[float] = None, magnitude: Optional[float] = None,
              source: Optional[int] = None) -> Optional[StatusEffectInstance]:
        preset = self.PRESETS.get(effect_name)
        if preset is None:
            return None
        comp = world.get_component(entity, CombatComponent)
        if comp is None:
            return None
        # Look for an existing instance to stack
        for existing in comp.status_effects:
            if existing.name == effect_name:
                if existing.stacks < existing.max_stacks:
                    existing.stacks += 1
                    existing.duration = max(existing.duration, preset["duration"])
                    return existing
                else:
                    existing.duration = preset["duration"]
                    return existing
        # New instance
        effect = StatusEffectInstance(
            name=effect_name,
            type=EffectType(preset["type"]),
            duration=duration or preset.get("duration", 5.0),
            magnitude=magnitude if magnitude is not None else preset.get("magnitude", 0.0),
            tick_interval=preset.get("tick_interval", 1.0),
            damage_type=preset.get("damage_type"),
            stat_modifiers=dict(preset.get("stat_modifiers", {})),
            source=source,
            max_stacks=preset.get("max_stacks", 1),
        )
        comp.status_effects.append(effect)
        return effect

    def remove(self, world: World, entity: Entity, effect_name: str) -> bool:
        comp = world.get_component(entity, CombatComponent)
        if comp is None:
            return False
        before = len(comp.status_effects)
        comp.status_effects = [e for e in comp.status_effects if e.name != effect_name]
        return len(comp.status_effects) < before

    def update(self, world: World, dt: float) -> None:
        """Tick status effects on all combat-enabled entities."""
        for entity, (combat, health) in world.view(CombatComponent, Health):
            if not combat.status_effects:
                continue
            remaining: list[StatusEffectInstance] = []
            for effect in combat.status_effects:
                effect.duration -= dt
                if effect.duration <= 0:
                    continue
                if effect.type in (EffectType.DOT, EffectType.HOT):
                    effect.tick_timer -= dt
                    while effect.tick_timer <= 0:
                        effect.tick_timer += effect.tick_interval
                        if effect.type == EffectType.DOT:
                            health.current = max(0, int(health.current - effect.magnitude * effect.stacks))
                        else:
                            health.current = min(health.maximum,
                                                 int(health.current + effect.magnitude * effect.stacks))
                remaining.append(effect)
            combat.status_effects = remaining

    def active_stat_modifiers(self, world: World, entity: Entity) -> dict[str, float]:
        """Aggregate stat modifiers from all active effects."""
        out: dict[str, float] = {}
        comp = world.get_component(entity, CombatComponent)
        if comp is None:
            return out
        for effect in comp.status_effects:
            for stat, val in effect.stat_modifiers.items():
                out[stat] = out.get(stat, 0.0) + val * effect.stacks
        return out

    def is_controlled(self, world: World, entity: Entity) -> bool:
        """True if entity is stunned/frozen/etc. and cannot act."""
        comp = world.get_component(entity, CombatComponent)
        if comp is None:
            return False
        return any(e.type == EffectType.CONTROL for e in comp.status_effects)
