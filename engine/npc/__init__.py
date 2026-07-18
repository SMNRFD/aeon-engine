"""NPC AI subsystem — needs, memory, schedule, personality, decision-making."""

from engine.npc.needs import NeedsSystem, NeedType
from engine.npc.memory import NPCMemory, MemoryEntry
from engine.npc.schedule import Schedule, ScheduleEntry, TimeOfDay
from engine.npc.personality import PersonalitySystem, PersonalityTrait
from engine.npc.ai import (
    AIController, AIContext, AIAction,
    WanderAI, CivilianAI, AggressiveAI, PlayerAI, AIRegistry,
)

__all__ = [
    "NeedsSystem", "NeedType",
    "NPCMemory", "MemoryEntry",
    "Schedule", "ScheduleEntry", "TimeOfDay",
    "PersonalitySystem", "PersonalityTrait",
    "AIController", "AIContext", "AIAction", "AIDecision",
    "WanderAI", "CivilianAI", "AggressiveAI", "PlayerAI", "AIRegistry",
]
