"""Real-time combat — concurrent action resolution.

Unlike turn-based combat where each side alternates, real-time combat
resolves actions as they are issued, constrained by:
* Cooldowns per action type
* Cast times
* Global cooldowns
* Movement and positioning
* Action priority

This is the architecture used by MMORPGs and ARPGs.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Position, Health, Stats, Combat as CombatComp
from engine.combat.system import CombatSystem, AttackResult
from engine.combat.damage import Damage, DamageType
from engine.utils.rng import RNG


class ActionPriority(IntEnum):
    INSTANT = 0      # always resolves first
    FAST = 1         # quick reactions
    NORMAL = 2       # standard actions
    SLOW = 3         # heavy attacks, spells
    CHANNEL = 4      # ongoing effects


@dataclass
class CombatCooldown:
    """Per-entity cooldown tracking."""

    entity_id: int
    global_cooldown: float = 0.0       # seconds remaining
    action_cooldowns: dict[str, float] = field(default_factory=dict)  # action_id -> seconds

    def tick(self, dt: float) -> None:
        self.global_cooldown = max(0.0, self.global_cooldown - dt)
        for action_id in list(self.action_cooldowns.keys()):
            self.action_cooldowns[action_id] = max(0.0, self.action_cooldowns[action_id] - dt)
            if self.action_cooldowns[action_id] <= 0:
                del self.action_cooldowns[action_id]

    def can_act(self, action_id: Optional[str] = None) -> bool:
        if self.global_cooldown > 0:
            return False
        if action_id and action_id in self.action_cooldowns:
            if self.action_cooldowns[action_id] > 0:
                return False
        return True

    def start_cooldown(self, action_id: str, duration: float,
                       global_cd: float = 0.0) -> None:
        self.action_cooldowns[action_id] = duration
        self.global_cooldown = max(self.global_cooldown, global_cd)


@dataclass
class CombatAction:
    """A queued combat action."""

    action_id: str
    attacker_id: int
    target_id: Optional[int] = None
    target_position: Optional[tuple[int, int]] = None
    priority: ActionPriority = ActionPriority.NORMAL
    cast_time: float = 0.0       # seconds before action resolves
    cooldown_duration: float = 1.0
    global_cooldown: float = 0.5
    queued_at: float = 0.0       # when the action was queued
    resolves_at: float = 0.0     # when it should resolve
    damage: Optional[Damage] = None
    effect_id: Optional[str] = None  # status effect to apply
    effect_duration: float = 0.0
    effect_magnitude: float = 0.0
    movement: Optional[tuple[int, int]] = None  # if action moves the entity
    is_cancellable: bool = True
    cancelled: bool = False
    description: str = ""

    def __lt__(self, other: "CombatAction") -> bool:
        return (self.resolves_at, int(self.priority)) < (other.resolves_at, int(other.priority))


class CombatTimeline:
    """A priority queue of combat actions ordered by resolution time."""

    def __init__(self) -> None:
        self._heap: list[CombatAction] = []
        self._counter = 0

    def schedule(self, action: CombatAction, current_time: float) -> None:
        action.queued_at = current_time
        action.resolves_at = current_time + action.cast_time
        self._counter += 1
        heapq.heappush(self._heap, action)

    def pop_ready(self, current_time: float) -> list[CombatAction]:
        """Pop all actions that should resolve by current_time."""
        ready: list[CombatAction] = []
        while self._heap and self._heap[0].resolves_at <= current_time:
            action = heapq.heappop(self._heap)
            if not action.cancelled:
                ready.append(action)
        return ready

    def cancel_for_entity(self, entity_id: int) -> int:
        """Cancel all queued actions for an entity."""
        count = 0
        for action in self._heap:
            if action.attacker_id == entity_id and action.is_cancellable:
                action.cancelled = True
                count += 1
        return count

    def pending(self) -> list[CombatAction]:
        return [a for a in self._heap if not a.cancelled]

    def __len__(self) -> int:
        return len(self._heap)


class RealtimeCombatSystem:
    """Real-time combat resolution."""

    def __init__(self, rng: Optional[RNG] = None,
                 turn_based: Optional[CombatSystem] = None) -> None:
        self.rng = rng or RNG()
        self.turn_based = turn_based or CombatSystem(rng)
        self.timeline = CombatTimeline()
        self._cooldowns: dict[int, CombatCooldown] = {}
        self._current_time: float = 0.0
        self._action_history: list[tuple[float, CombatAction, AttackResult]] = []

    def get_cooldown(self, entity_id: int) -> CombatCooldown:
        if entity_id not in self._cooldowns:
            self._cooldowns[entity_id] = CombatCooldown(entity_id=entity_id)
        return self._cooldowns[entity_id]

    def can_act(self, entity_id: int, action_id: Optional[str] = None) -> bool:
        return self.get_cooldown(entity_id).can_act(action_id)

    # ---------- action queueing ----------

    def queue_attack(self, attacker: Entity, target: Entity,
                     action_id: str = "basic_attack",
                     cast_time: float = 0.5,
                     cooldown: float = 1.0,
                     global_cd: float = 0.5,
                     damage: Optional[Damage] = None) -> Optional[CombatAction]:
        """Queue an attack action."""
        cd = self.get_cooldown(attacker.id)
        if not cd.can_act(action_id):
            return None
        action = CombatAction(
            action_id=action_id,
            attacker_id=attacker.id,
            target_id=target.id,
            cast_time=cast_time,
            cooldown_duration=cooldown,
            global_cooldown=global_cd,
            damage=damage,
            description=f"{attacker.id} attacks {target.id}",
        )
        self.timeline.schedule(action, self._current_time)
        cd.start_cooldown(action_id, cooldown, global_cd)
        return action

    def queue_spell(self, caster: Entity, target: Optional[Entity],
                    action_id: str, cast_time: float = 1.5,
                    cooldown: float = 5.0,
                    damage: Optional[Damage] = None,
                    effect_id: Optional[str] = None,
                    effect_duration: float = 0.0,
                    effect_magnitude: float = 0.0) -> Optional[CombatAction]:
        cd = self.get_cooldown(caster.id)
        if not cd.can_act(action_id):
            return None
        action = CombatAction(
            action_id=action_id,
            attacker_id=caster.id,
            target_id=target.id if target else None,
            priority=ActionPriority.SLOW,
            cast_time=cast_time,
            cooldown_duration=cooldown,
            global_cooldown=1.0,
            damage=damage,
            effect_id=effect_id,
            effect_duration=effect_duration,
            effect_magnitude=effect_magnitude,
            description=f"{caster.id} casts {action_id}",
        )
        self.timeline.schedule(action, self._current_time)
        cd.start_cooldown(action_id, cooldown, 1.0)
        return action

    def queue_movement(self, entity: Entity, target_pos: tuple[int, int],
                       cast_time: float = 0.1) -> Optional[CombatAction]:
        cd = self.get_cooldown(entity.id)
        if not cd.can_act("move"):
            return None
        action = CombatAction(
            action_id="move",
            attacker_id=entity.id,
            target_position=target_pos,
            priority=ActionPriority.FAST,
            cast_time=cast_time,
            cooldown_duration=0.0,
            global_cooldown=0.0,
            movement=target_pos,
            description=f"{entity.id} moves to {target_pos}",
        )
        self.timeline.schedule(action, self._current_time)
        return action

    def cancel_actions(self, entity: Entity) -> int:
        return self.timeline.cancel_for_entity(entity.id)

    # ---------- update ----------

    def update(self, world: World, dt: float) -> list[AttackResult]:
        """Advance the combat timeline and resolve ready actions."""
        self._current_time += dt
        # Tick cooldowns
        for cd in self._cooldowns.values():
            cd.tick(dt)
        # Resolve ready actions
        results: list[AttackResult] = []
        for action in self.timeline.pop_ready(self._current_time):
            result = self._resolve_action(world, action)
            if result is not None:
                results.append(result)
                self._action_history.append((self._current_time, action, result))
        return results

    def _resolve_action(self, world: World, action: CombatAction) -> Optional[AttackResult]:
        """Resolve a single combat action."""
        attacker = self._find_entity(world, action.attacker_id)
        if attacker is None:
            return None
        # Movement action
        if action.movement is not None:
            pos = world.get_component(attacker, Position)
            if pos:
                pos.x = action.movement[0]
                pos.y = action.movement[1]
            return AttackResult(
                attacker=action.attacker_id, target=action.attacker_id,
                hit=True, damage=0.0, damage_type=DamageType.TRUE,
                crit=False, killed=False,
                message=f"{action.attacker_id} moved.",
            )
        # Attack/spell action
        if action.target_id is None:
            return None
        target = self._find_entity(world, action.target_id)
        if target is None:
            return None
        # Use the turn-based system to resolve the actual attack
        weapon = None
        combat_comp = world.get_component(attacker, CombatComp)
        if combat_comp and combat_comp.weapon_id is not None:
            # Look up weapon from item registry if available
            pass
        result = self.turn_based.attack(world, attacker, target, weapon)
        # Apply additional damage/effect if specified
        if action.damage and result.hit:
            target_health = world.get_component(target, Health)
            if target_health and not target_health.invulnerable:
                from engine.combat.damage import DamageCalculator
                target_stats = world.get_component(target, Stats)
                final = DamageCalculator.compute(action.damage, target_stats)
                target_health.current = max(0, int(target_health.current - final))
                result.damage += final
        # Apply status effect if specified
        if action.effect_id:
            from engine.combat.effects import StatusEffectSystem
            status_sys = StatusEffectSystem()
            status_sys.apply(world, target, action.effect_id,
                             duration=action.effect_duration,
                             magnitude=action.effect_magnitude,
                             source=action.attacker_id)
            result.status_effects_applied.append(action.effect_id)
        return result

    def _find_entity(self, world: World, entity_id: int) -> Optional[Entity]:
        for ent in list(world._components.keys()):
            if ent.id == entity_id:
                return ent
        return None

    # ---------- queries ----------

    def pending_actions(self) -> list[CombatAction]:
        return self.timeline.pending()

    def pending_for(self, entity_id: int) -> list[CombatAction]:
        return [a for a in self.timeline.pending() if a.attacker_id == entity_id]

    def action_history(self, limit: int = 50) -> list[tuple[float, CombatAction, AttackResult]]:
        return self._action_history[-limit:]

    def cooldown_remaining(self, entity_id: int, action_id: str) -> float:
        cd = self._cooldowns.get(entity_id)
        if cd is None:
            return 0.0
        return cd.action_cooldowns.get(action_id, 0.0)
