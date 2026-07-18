"""Reputation system — multi-dimensional reputation tracking.

Tracks reputation across 10 dimensions per entity:
* GLOBAL     — overall world-wide reputation
* REGIONAL   — per-region reputation (region_id -> value)
* FACTION    — per-faction reputation (faction_id -> value)
* NPC        — per-NPC personal relationship (entity_id -> value)
* CRIMINAL   — crime-related reputation (negative = wanted)
* HEROIC     — heroic deeds (positive = beloved hero)
* POLITICAL  — political capital
* RELIGIOUS  — standing with religious organisations
* ECONOMIC   — merchant standing
* MILITARY   — military standing

Each reputation value is a float in [-100, 100] where:
* -100..-70 : Hated, kill on sight
* -70..-30  : Hostile
* -30..-10  : Wary
* -10..10   : Neutral
* 10..30    : Friendly
* 30..70    : Honoured
* 70..100   : Exalted

Reputation decays slowly toward 0 over time, can be modified by events,
and unlocks gameplay consequences (shop prices, guard reactions, quest
availability, dialogue options, etc.).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.ecs import Entity
from engine.utils.rng import RNG


class ReputationType(IntEnum):
    GLOBAL = 0
    REGIONAL = 1
    FACTION = 2
    NPC = 3
    CRIMINAL = 4
    HEROIC = 5
    POLITICAL = 6
    RELIGIOUS = 7
    ECONOMIC = 8
    MILITARY = 9


class ReputationLevel(IntEnum):
    EXALTED = 6
    HONOURED = 5
    FRIENDLY = 4
    NEUTRAL = 3
    WARY = 2
    HOSTILE = 1
    HATED = 0

    @property
    def label(self) -> str:
        return ["Hated", "Hostile", "Wary", "Neutral",
                "Friendly", "Honoured", "Exalted"][self]


def reputation_level(value: float) -> ReputationLevel:
    if value <= -70: return ReputationLevel.HATED
    if value < -30: return ReputationLevel.HOSTILE
    if value < -10: return ReputationLevel.WARY
    if value < 10:  return ReputationLevel.NEUTRAL
    if value < 30:  return ReputationLevel.FRIENDLY
    if value < 70:  return ReputationLevel.HONOURED
    return ReputationLevel.EXALTED


# Per-type decay rates (per game-hour).
DECAY_RATES: dict[ReputationType, float] = {
    ReputationType.GLOBAL: 0.001,
    ReputationType.REGIONAL: 0.002,
    ReputationType.FACTION: 0.0015,
    ReputationType.NPC: 0.0005,  # personal relationships decay slowly
    ReputationType.CRIMINAL: 0.003,  # crimes are "forgotten" faster
    ReputationType.HEROIC: 0.0005,  # heroism remembered long
    ReputationType.POLITICAL: 0.002,
    ReputationType.RELIGIOUS: 0.001,
    ReputationType.ECONOMIC: 0.002,
    ReputationType.MILITARY: 0.001,
}


@dataclass
class ReputationRecord:
    """A single reputation entry for an entity in a context."""

    entity_id: int
    type: ReputationType
    target_id: Optional[int]   # region_id / faction_id / npc_id / None for global
    value: float = 0.0
    last_change_tick: float = 0.0
    history: list[tuple[float, float, str]] = field(default_factory=list)  # (tick, delta, reason)

    def apply(self, delta: float, reason: str, current_tick: float) -> None:
        old = self.value
        self.value = max(-100.0, min(100.0, self.value + delta))
        self.last_change_tick = current_tick
        self.history.append((current_tick, self.value - old, reason))
        if len(self.history) > 50:
            self.history = self.history[-50:]

    def decay(self, dt_hours: float) -> None:
        rate = DECAY_RATES.get(self.type, 0.001)
        if self.value > 0:
            self.value = max(0.0, self.value - rate * dt_hours)
        elif self.value < 0:
            self.value = min(0.0, self.value + rate * dt_hours)

    def level(self) -> ReputationLevel:
        return reputation_level(self.value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "type": int(self.type),
            "target_id": self.target_id,
            "value": self.value,
            "last_change_tick": self.last_change_tick,
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReputationRecord":
        return cls(
            entity_id=data["entity_id"],
            type=ReputationType(data["type"]),
            target_id=data.get("target_id"),
            value=data.get("value", 0.0),
            last_change_tick=data.get("last_change_tick", 0.0),
            history=[tuple(h) for h in data.get("history", [])],
        )


@dataclass
class ReputationEvent:
    """An event that triggered a reputation change."""

    entity_id: int
    type: ReputationType
    target_id: Optional[int]
    delta: float
    reason: str
    tick: float


class ReputationSystem:
    """Tracks and updates reputation for all entities.

    Storage is keyed by (entity_id, type, target_id) for O(1) lookups.
    """

    def __init__(self) -> None:
        self._records: dict[tuple[int, int, Optional[int]], ReputationRecord] = {}

    # ---------- queries ----------

    def get(self, entity_id: int, rep_type: ReputationType,
            target_id: Optional[int] = None) -> float:
        record = self._records.get((entity_id, int(rep_type), target_id))
        return record.value if record else 0.0

    def get_record(self, entity_id: int, rep_type: ReputationType,
                   target_id: Optional[int] = None) -> ReputationRecord:
        key = (entity_id, int(rep_type), target_id)
        if key not in self._records:
            self._records[key] = ReputationRecord(
                entity_id=entity_id, type=rep_type, target_id=target_id,
            )
        return self._records[key]

    def level(self, entity_id: int, rep_type: ReputationType,
              target_id: Optional[int] = None) -> ReputationLevel:
        return reputation_level(self.get(entity_id, rep_type, target_id))

    def all_for_entity(self, entity_id: int) -> list[ReputationRecord]:
        return [r for (eid, _, _), r in self._records.items() if eid == entity_id]

    def all_for_faction(self, faction_id: int) -> list[ReputationRecord]:
        return [r for r in self._records.values()
                if r.type == ReputationType.FACTION and r.target_id == faction_id]

    # ---------- mutations ----------

    def adjust(self, entity_id: int, rep_type: ReputationType,
               delta: float, reason: str = "", current_tick: float = 0.0,
               target_id: Optional[int] = None) -> float:
        record = self.get_record(entity_id, rep_type, target_id)
        record.apply(delta, reason, current_tick)
        return record.value

    def set(self, entity_id: int, rep_type: ReputationType, value: float,
            reason: str = "", current_tick: float = 0.0,
            target_id: Optional[int] = None) -> None:
        record = self.get_record(entity_id, rep_type, target_id)
        delta = value - record.value
        record.apply(delta, reason, current_tick)

    # ---------- decay ----------

    def update(self, dt_hours: float) -> None:
        for record in self._records.values():
            record.decay(dt_hours)

    # ---------- convenience ----------

    def is_wanted(self, entity_id: int, region_id: Optional[int] = None) -> bool:
        """True if the entity is wanted by the law in the given region (or any region)."""
        if region_id is not None:
            return self.get(entity_id, ReputationType.CRIMINAL, region_id) <= -30
        return any(r.value <= -30 for r in self.all_for_entity(entity_id)
                   if r.type == ReputationType.CRIMINAL)

    def is_hero(self, entity_id: int) -> bool:
        return self.get(entity_id, ReputationType.HEROIC) >= 50

    def shop_discount(self, entity_id: int, faction_id: Optional[int] = None) -> float:
        """Returns a discount multiplier 0..1 based on economic reputation."""
        rep = self.get(entity_id, ReputationType.ECONOMIC, faction_id)
        # 100 reputation = 20% discount, -100 = 20% surcharge
        return max(0.8, min(1.2, 1.0 - rep / 500.0))

    def guard_reaction(self, entity_id: int, region_id: Optional[int] = None) -> str:
        """Returns 'attack', 'arrest', 'watch', 'ignore', 'salute'."""
        criminal = self.get(entity_id, ReputationType.CRIMINAL, region_id)
        heroic = self.get(entity_id, ReputationType.HEROIC)
        if criminal <= -70: return "attack"
        if criminal <= -30: return "arrest"
        if criminal <= -10: return "watch"
        if heroic >= 50:    return "salute"
        return "ignore"

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [
                {"key": [k[0], k[1], k[2]], "record": r.to_dict()}
                for k, r in self._records.items()
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ReputationSystem":
        sys = cls()
        for entry in data.get("records", []):
            key = entry["key"]
            record = ReputationRecord.from_dict(entry["record"])
            sys._records[(key[0], key[1], key[2])] = record
        return sys

    def __len__(self) -> int:
        return len(self._records)
