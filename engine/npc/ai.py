"""AI controllers — behaviour-tree-style decision makers."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from engine.core.ecs import Entity, World
from engine.core.logging import get_logger
from engine.entities.components import (
    AI as AIComponent, Health, Identity, Needs, Personality, Position, Stats, Combat,
)
from engine.npc.memory import NPCMemory
from engine.npc.needs import NeedType, NeedsSystem
from engine.npc.personality import PersonalitySystem
from engine.npc.schedule import Schedule, schedule_for_occupation
from engine.utils.rng import RNG


log = get_logger("ai")


@dataclass
class AIContext:
    """Information made available to AI controllers each tick."""

    world: World
    entity: Entity
    rng: RNG
    current_tick: int
    current_hour: int
    current_minute: int
    nearby_entities: list[tuple[Entity, float]] = field(default_factory=list)  # (entity, distance)
    visible_tiles: list[tuple[int, int]] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AIAction:
    """An action chosen by the AI."""

    type: str  # "move", "attack", "talk", "wait", "use_item", "flee", "investigate", "work"
    target_entity: Optional[int] = None
    target_position: Optional[tuple[int, int]] = None
    item_id: Optional[int] = None
    duration: float = 0.0
    reasoning: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class AIController:
    """Base class for AI controllers."""

    name: str = "base"

    def decide(self, ctx: AIContext) -> AIAction:
        raise NotImplementedError


class WanderAI(AIController):
    """A simple wandering AI for wild creatures."""

    name = "wander"

    def __init__(self) -> None:
        self._wander_cooldown: dict[int, float] = {}

    def decide(self, ctx: AIContext) -> AIAction:
        ai = ctx.world.get_component(ctx.entity, AIComponent)
        if ai and ai.target_id is not None:
            # Has a target — attack if in range
            target = next((e for e, _ in ctx.nearby_entities if e.id == ai.target_id), None)
            if target is None:
                ai.target_id = None
            else:
                t_pos = ctx.world.get_component(target, Position)
                my_pos = ctx.world.get_component(ctx.entity, Position)
                if t_pos and my_pos:
                    d = math.hypot(t_pos.x - my_pos.x, t_pos.y - my_pos.y)
                    if d <= 1.5:
                        return AIAction(type="attack", target_entity=target.id,
                                        reasoning="attacking prey")
                    else:
                        return AIAction(type="move",
                                        target_position=(t_pos.x, t_pos.y),
                                        reasoning="chasing prey")
        # Look for hostile targets (entities tagged "player" or "humanoid")
        for other, dist in ctx.nearby_entities:
            if dist > 8.0:
                continue
            if ctx.world.has_tag(other, "player"):
                if ai:
                    ai.target_id = other.id
                return AIAction(type="attack", target_entity=other.id,
                                reasoning="player nearby")
        # Wander
        if ctx.rng.chance(0.3):
            my_pos = ctx.world.get_component(ctx.entity, Position)
            if my_pos:
                dx, dy = ctx.rng.choice([(-1, 0), (1, 0), (0, -1), (0, 1),
                                         (-1, -1), (1, 1), (-1, 1), (1, -1)])
                return AIAction(type="move",
                                target_position=(my_pos.x + dx, my_pos.y + dy),
                                reasoning="wandering")
        return AIAction(type="wait", duration=0.5, reasoning="idling")


class AggressiveAI(WanderAI):
    """Actively hunts hostiles within a wider range."""

    name = "aggressive"

    def decide(self, ctx: AIContext) -> AIAction:
        ai = ctx.world.get_component(ctx.entity, AIComponent)
        # Check nearby for hostiles
        for other, dist in ctx.nearby_entities:
            if dist > 12.0:
                continue
            if ctx.world.has_tag(other, "player") or ctx.world.has_tag(other, "humanoid"):
                if ai:
                    ai.target_id = other.id
                    ai.alertness = 1.0
                return AIAction(type="attack", target_entity=other.id,
                                reasoning="spotted enemy")
        return super().decide(ctx)


class CivilianAI(AIController):
    """Goal-driven AI for civilians — schedules, needs, relationships."""

    name = "civilian"

    def __init__(self) -> None:
        self._schedules: dict[int, Schedule] = {}
        self._goal_cooldown: dict[int, float] = {}

    def decide(self, ctx: AIContext) -> AIAction:
        ai = ctx.world.get_component(ctx.entity, AIComponent)
        needs = ctx.world.get_component(ctx.entity, Needs)
        personality = ctx.world.get_component(ctx.entity, Personality)
        position = ctx.world.get_component(ctx.entity, Position)

        # Critical needs come first.
        if needs:
            if needs.hunger > 80:
                return AIAction(type="use_item", reasoning="starving — looking for food",
                                data={"need": "food"})
            if needs.thirst > 80:
                return AIAction(type="use_item", reasoning="desperate for water",
                                data={"need": "water"})
            if needs.sleep > 85:
                return AIAction(type="wait", duration=2.0, reasoning="about to collapse from exhaustion",
                                data={"need": "sleep"})

        # Flee from hostiles.
        for other, dist in ctx.nearby_entities:
            if dist > 6.0:
                continue
            if ctx.world.has_tag(other, "hostile"):
                if personality and PersonalitySystem.bravery(personality) < 0.3:
                    if position:
                        # Move away from threat
                        op = ctx.world.get_component(other, Position)
                        if op:
                            dx = position.x - op.x
                            dy = position.y - op.y
                            mag = max(1.0, math.hypot(dx, dy))
                            return AIAction(type="move",
                                            target_position=(
                                                int(position.x + dx / mag * 3),
                                                int(position.y + dy / mag * 3),
                                            ),
                                            reasoning="fleeing from a hostile")
                else:
                    return AIAction(type="attack", target_entity=other.id,
                                    reasoning="defending against a hostile")

        # Schedule-driven behaviour.
        schedule = self._schedules.get(ctx.entity.id)
        if schedule is None:
            schedule = schedule_for_occupation("commoner", ctx.rng)
            self._schedules[ctx.entity.id] = schedule

        entry = schedule.activity_at(ctx.current_hour)
        if entry:
            if entry.activity == "sleep":
                return AIAction(type="wait", duration=2.0, reasoning="sleeping",
                                data={"location_tag": entry.location_tag})
            if entry.activity == "eat":
                return AIAction(type="use_item", reasoning="eating",
                                data={"need": "food"})
            if entry.activity == "work":
                return AIAction(type="work", duration=2.0, reasoning=entry.activity,
                                data={"location_tag": entry.location_tag})
            if entry.activity == "wander":
                if position and ctx.rng.chance(0.4):
                    dx, dy = ctx.rng.choice([(-1, 0), (1, 0), (0, -1), (0, 1)])
                    return AIAction(type="move",
                                    target_position=(position.x + dx, position.y + dy),
                                    reasoning="strolling")

        # Greet nearby friendly NPCs occasionally
        if personality and PersonalitySystem.sociability(personality) > 0.6:
            for other, dist in ctx.nearby_entities:
                if dist > 2.0:
                    continue
                if ctx.world.has_tag(other, "npc") and other.id != ctx.entity.id:
                    if ctx.rng.chance(0.1):
                        return AIAction(type="talk", target_entity=other.id,
                                        reasoning="greeting a neighbour")

        return AIAction(type="wait", duration=0.5, reasoning="idling")


class PlayerAI(AIController):
    """Player AI — does nothing; player input is handled by the command system."""

    name = "player"

    def decide(self, ctx: AIContext) -> AIAction:
        return AIAction(type="wait", duration=0.0, reasoning="awaiting player input")


class AIRegistry:
    """Registry of AI controllers keyed by name."""

    def __init__(self) -> None:
        self._controllers: dict[str, AIController] = {}

    def register(self, controller: AIController) -> None:
        self._controllers[controller.name] = controller

    def get(self, name: str) -> Optional[AIController]:
        return self._controllers.get(name)

    def all(self) -> list[AIController]:
        return list(self._controllers.values())


def default_registry() -> AIRegistry:
    """Create a registry with the standard AI controllers."""
    r = AIRegistry()
    r.register(WanderAI())
    r.register(AggressiveAI())
    r.register(CivilianAI())
    r.register(PlayerAI())
    return r
