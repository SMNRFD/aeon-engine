"""NPC memory — short and long-term event recall, plus knowledge graph."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.ecs import Entity
from engine.entities.components import Memory as MemoryComponent


class MemoryImportance(IntEnum):
    TRIVIAL = 0
    MINOR = 1
    NORMAL = 2
    IMPORTANT = 3
    CRITICAL = 4


@dataclass
class MemoryEntry:
    """A single memory record."""

    id: int
    timestamp: float       # in-game tick when remembered
    description: str
    category: str          # "conversation", "combat", "transaction", "observation", "event"
    importance: MemoryImportance = MemoryImportance.NORMAL
    entities: list[int] = field(default_factory=list)  # entity ids involved
    location: Optional[tuple[int, int]] = None
    emotional_valence: float = 0.0   # -1..1
    decay_rate: float = 0.001
    last_recalled: float = 0.0
    recall_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def recall(self, current_tick: float) -> None:
        self.last_recalled = current_tick
        self.recall_count += 1
        # Recalling reinforces the memory.
        self.decay_rate *= 0.95

    def strength(self, current_tick: float) -> float:
        """How strongly the NPC remembers this (0..1)."""
        elapsed = max(0.0, current_tick - self.last_recalled)
        s = 1.0 - elapsed * self.decay_rate
        # Important memories decay slower.
        s *= (1.0 + self.importance.value * 0.2)
        return max(0.0, min(1.0, s))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "timestamp": self.timestamp, "description": self.description,
            "category": self.category, "importance": self.importance.value,
            "entities": self.entities, "location": self.location,
            "emotional_valence": self.emotional_valence,
            "decay_rate": self.decay_rate, "last_recalled": self.last_recalled,
            "recall_count": self.recall_count, "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            id=data["id"], timestamp=data["timestamp"], description=data["description"],
            category=data["category"],
            importance=MemoryImportance(data.get("importance", 2)),
            entities=data.get("entities", []),
            location=tuple(data["location"]) if data.get("location") else None,
            emotional_valence=data.get("emotional_valence", 0.0),
            decay_rate=data.get("decay_rate", 0.001),
            last_recalled=data.get("last_recalled", 0.0),
            recall_count=data.get("recall_count", 0),
            details=data.get("details", {}),
        )


class NPCMemory:
    """Memory store for an NPC. Persists via the MemoryComponent."""

    def __init__(self) -> None:
        self._memories: list[MemoryEntry] = []
        self._next_id: int = 1
        self._knowledge: dict[str, float] = {}  # topic -> familiarity 0..1
        self._relations: dict[int, float] = {}  # entity_id -> opinion -1..1
        self._rumors: list[str] = []

    def add_memory(self, description: str, category: str, *,
                   importance: MemoryImportance = MemoryImportance.NORMAL,
                   entities: Optional[list[int]] = None,
                   location: Optional[tuple[int, int]] = None,
                   emotional_valence: float = 0.0,
                   details: Optional[dict] = None,
                   current_tick: float = 0.0) -> MemoryEntry:
        entry = MemoryEntry(
            id=self._next_id, timestamp=current_tick, description=description,
            category=category, importance=importance,
            entities=list(entities or []), location=location,
            emotional_valence=emotional_valence, details=details or {},
        )
        self._next_id += 1
        self._memories.append(entry)
        # Cap memory size — keep most important + most recent.
        if len(self._memories) > 200:
            self._forget()
        return entry

    def _forget(self) -> None:
        # Forget the weakest memories.
        self._memories.sort(key=lambda m: (m.importance.value, m.recall_count), reverse=True)
        self._memories = self._memories[:150]

    def recall_about(self, entity_id: int, current_tick: float,
                     limit: int = 5) -> list[MemoryEntry]:
        relevant = [m for m in self._memories if entity_id in m.entities]
        relevant.sort(key=lambda m: (m.importance.value, m.strength(current_tick)), reverse=True)
        for m in relevant[:limit]:
            m.recall(current_tick)
        return relevant[:limit]

    def recent_memories(self, current_tick: float, limit: int = 10) -> list[MemoryEntry]:
        sorted_mems = sorted(self._memories, key=lambda m: m.timestamp, reverse=True)
        return sorted_mems[:limit]

    def learn_knowledge(self, topic: str, amount: float = 0.2) -> None:
        self._knowledge[topic] = min(1.0, self._knowledge.get(topic, 0.0) + amount)

    def knows(self, topic: str, threshold: float = 0.1) -> bool:
        return self._knowledge.get(topic, 0.0) >= threshold

    def knowledge_level(self, topic: str) -> float:
        return self._knowledge.get(topic, 0.0)

    def adjust_relation(self, entity_id: int, delta: float) -> float:
        cur = self._relations.get(entity_id, 0.0)
        new = max(-1.0, min(1.0, cur + delta))
        self._relations[entity_id] = new
        return new

    def relation_to(self, entity_id: int) -> float:
        return self._relations.get(entity_id, 0.0)

    def add_rumor(self, rumor: str) -> None:
        if rumor not in self._rumors:
            self._rumors.append(rumor)
            if len(self._rumors) > 30:
                self._rumors = self._rumors[-30:]

    def to_dict(self) -> dict:
        return {
            "memories": [m.to_dict() for m in self._memories],
            "next_id": self._next_id,
            "knowledge": dict(self._knowledge),
            "relations": {str(k): v for k, v in self._relations.items()},
            "rumors": list(self._rumors),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NPCMemory":
        m = cls()
        m._memories = [MemoryEntry.from_dict(d) for d in data.get("memories", [])]
        m._next_id = data.get("next_id", 1)
        m._knowledge = dict(data.get("knowledge", {}))
        m._relations = {int(k): v for k, v in data.get("relations", {}).items()}
        m._rumors = list(data.get("rumors", []))
        return m


def attach_memory(world, entity: Entity, memory: NPCMemory) -> None:
    """Persist an NPCMemory into the entity's Memory component."""
    comp = world.get_component(entity, MemoryComponent)
    if comp is None:
        comp = MemoryComponent()
        world.add_component(entity, comp)
    # Store the full memory state as a dict in the first slot.
    comp.memories = [memory.to_dict()]
    comp.knowledge = dict(memory._knowledge)


def load_memory(world, entity: Entity) -> NPCMemory:
    comp = world.get_component(entity, MemoryComponent)
    if comp is None or not comp.memories:
        return NPCMemory()
    return NPCMemory.from_dict(comp.memories[0])
