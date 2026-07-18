"""Concrete ECS components shared across subsystems."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from engine.core.ecs import Component
from engine.world.map import WorldPosition


@dataclass
class Identity(Component):
    """Name, description, and display glyph for any entity."""

    name: str = "Unknown"
    display_name: str = ""
    description: str = ""
    glyph: str = "?"
    color: int = 244  # ANSI 256 colour

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name


@dataclass
class Position(Component):
    """World position of an entity."""

    x: int = 0
    y: int = 0
    z: int = 0
    facing: int = 0  # 0=N, 1=NE, 2=E, ..., 7=NW

    def as_world_position(self) -> WorldPosition:
        return WorldPosition(self.x, self.y, self.z)

    def distance_to(self, other: "Position") -> float:
        import math
        return math.hypot(other.x - self.x, other.y - self.y)


@dataclass
class Health(Component):
    """Vital signs."""

    current: int = 100
    maximum: int = 100
    regeneration: float = 0.0  # hp per second
    invulnerable: bool = False


@dataclass
class Stats(Component):
    """Core attributes."""

    strength: int = 10
    agility: int = 10
    endurance: int = 10
    intelligence: int = 10
    willpower: int = 10
    charisma: int = 10
    perception: int = 10
    luck: int = 10

    def derived(self) -> dict[str, int]:
        """Return derived combat attributes."""
        return {
            "max_hp": 50 + self.endurance * 5 + self.strength * 2,
            "max_stamina": 40 + self.endurance * 4 + self.agility * 2,
            "max_mana": 20 + self.intelligence * 4 + self.willpower * 3,
            "carry_capacity": 30 + self.strength * 5,
            "initiative": self.agility + self.perception,
            "dodge": self.agility + self.luck // 2,
            "block_chance": min(40, self.endurance + self.strength // 2),
        }


@dataclass
class Faction(Component):
    """Faction membership for an entity."""

    faction_id: Optional[int] = None
    rank: int = 0
    reputation: int = 0  # -100..100
    title: str = ""


@dataclass
class Inventory(Component):
    """Back-link to an inventory owned by this entity (an Inventory instance)."""

    inventory_id: Optional[int] = None


@dataclass
class Skills(Component):
    """Per-entity skill levels keyed by skill id."""

    skills: dict[str, "SkillLevel"] = field(default_factory=dict)


@dataclass
class SkillLevel:
    level: int = 0
    xp: float = 0.0
    capped_at: int = 100


@dataclass
class Needs(Component):
    """Survival needs."""

    hunger: float = 0.0       # 0=satisfied, 100=starving
    thirst: float = 0.0
    fatigue: float = 0.0
    sleep: float = 0.0        # 0=rested, 100=exhausted
    sanity: float = 100.0     # 100=stable, 0=insane
    warmth: float = 37.0      # body temperature in Celsius
    morale: float = 75.0
    comfort: float = 50.0


@dataclass
class AI(Component):
    """AI controller descriptor."""

    controller: str = "wander"  # controller key
    state: str = "idle"
    target_id: Optional[int] = None
    goal: str = ""
    schedule_id: Optional[int] = None
    alertness: float = 0.0     # 0..1
    fear: float = 0.0
    anger: float = 0.0


@dataclass
class Combat(Component):
    """Combat-related state."""

    weapon_id: Optional[int] = None
    armor_ids: dict[str, Optional[int]] = field(default_factory=dict)
    in_combat: bool = False
    cooldown: float = 0.0
    status_effects: list["StatusEffect"] = field(default_factory=list)


@dataclass
class StatusEffect:
    name: str
    duration: float
    magnitude: float
    type: str  # "dot", "buff", "debuff", "control"
    source: Optional[str] = None


@dataclass
class Memory(Component):
    """Reference to an NPC memory store."""

    memories: list[dict] = field(default_factory=list)
    knowledge: dict[str, float] = field(default_factory=dict)


@dataclass
class Personality(Component):
    """Big-Five-style personality traits in [-1, 1]."""

    openness: float = 0.0
    conscientiousness: float = 0.0
    extraversion: float = 0.0
    agreeableness: float = 0.0
    neuroticism: float = 0.0
    courage: float = 0.0
    greed: float = 0.0
    curiosity: float = 0.0


@dataclass
class Relationships(Component):
    """Per-entity relationship table."""

    relations: dict[int, float] = field(default_factory=dict)  # target_entity_id -> [-1..1]


@dataclass
class Wealth(Component):
    """Liquid and asset wealth."""

    gold: int = 0
    silver: int = 0
    copper: int = 0
    debt: int = 0

    def total_copper(self) -> int:
        return self.copper + self.silver * 100 + self.gold * 10000 - self.debt


@dataclass
class QuestLog(Component):
    """Active and completed quests."""

    active: list[int] = field(default_factory=list)
    completed: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)


@dataclass
class Race(Component):
    """Species / race descriptor."""

    race_id: str = "human"
    size: str = "medium"  # tiny, small, medium, large, huge
    age: int = 0
    max_age: int = 80
    diet: str = "omnivore"
    tags: list[str] = field(default_factory=list)


@dataclass
class Tag(Component):
    """Free-form tags used by AI and gameplay rules."""

    tags: list[str] = field(default_factory=list)


@dataclass
class Player(Component):
    """Marks an entity as the player-controlled avatar."""

    is_local: bool = True
    play_time_seconds: float = 0.0


__all__ = [
    "Identity", "Position", "Health", "Stats", "Faction", "Inventory",
    "Skills", "SkillLevel", "Needs", "AI", "Combat", "StatusEffect",
    "Memory", "Personality", "Relationships", "Wealth", "QuestLog",
    "Race", "Tag", "Player",
]
