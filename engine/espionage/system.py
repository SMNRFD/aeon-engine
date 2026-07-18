"""Espionage system — spies, missions, sabotage, assassination, intelligence.

Spies are entities that can be assigned missions to infiltrate, sabotage,
assassinate, or gather intelligence against rival factions or kingdoms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class MissionType(IntEnum):
    GATHER_INTEL = 0
    SABOTAGE = 1
    ASSASSINATE = 2
    INCITE_REBELLION = 3
    STEAL_TECH = 4
    FRAME_FACTION = 5
    SPREAD_RUMOR = 6
    INFILTRATE = 7
    EXTRACT = 8
    COUNTERINTELLIGENCE = 9


class MissionResult(IntEnum):
    PENDING = 0
    SUCCESS = 1
    PARTIAL_SUCCESS = 2
    FAILURE = 3
    DISCOVERED = 4
    SPY_CAPTURED = 5
    SPY_KILLED = 6


@dataclass
class Spy:
    """A spy entity."""

    spy_id: int
    entity_id: int
    name: str
    faction_id: Optional[int] = None
    skill_stealth: int = 5
    skill_deception: int = 5
    skill_perception: int = 5
    cover_identity: str = ""
    cover_quality: float = 0.5  # 0..1
    suspicion_level: float = 0.0  # 0..1 (target faction's suspicion)
    current_mission_id: Optional[int] = None
    status: str = "available"  # available, on_mission, captured, dead, extracted
    recruited_tick: float = 0.0
    successful_missions: int = 0
    failed_missions: int = 0
    known_intel: list[int] = field(default_factory=list)  # intel_ids

    def to_dict(self) -> dict[str, Any]:
        return {
            "spy_id": self.spy_id, "entity_id": self.entity_id,
            "name": self.name, "faction_id": self.faction_id,
            "skill_stealth": self.skill_stealth,
            "skill_deception": self.skill_deception,
            "skill_perception": self.skill_perception,
            "cover_identity": self.cover_identity,
            "cover_quality": self.cover_quality,
            "suspicion_level": self.suspicion_level,
            "current_mission_id": self.current_mission_id,
            "status": self.status, "recruited_tick": self.recruited_tick,
            "successful_missions": self.successful_missions,
            "failed_missions": self.failed_missions,
            "known_intel": list(self.known_intel),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Spy":
        return cls(**data)


@dataclass
class Mission:
    """An espionage mission."""

    mission_id: int
    mission_type: MissionType
    spy_id: int
    target_faction_id: Optional[int] = None
    target_entity_id: Optional[int] = None
    target_kingdom_id: Optional[int] = None
    target_location: Optional[tuple[int, int]] = None
    description: str = ""
    difficulty: float = 1.0  # 0.5 easy .. 5.0 very hard
    duration_days: float = 7.0
    started_tick: float = 0.0
    ends_tick: Optional[float] = None
    result: MissionResult = MissionResult.PENDING
    rewards: dict[str, Any] = field(default_factory=dict)
    consequences: list[str] = field(default_factory=list)
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "mission_type": int(self.mission_type),
            "spy_id": self.spy_id,
            "target_faction_id": self.target_faction_id,
            "target_entity_id": self.target_entity_id,
            "target_kingdom_id": self.target_kingdom_id,
            "target_location": self.target_location,
            "description": self.description,
            "difficulty": self.difficulty,
            "duration_days": self.duration_days,
            "started_tick": self.started_tick,
            "ends_tick": self.ends_tick,
            "result": int(self.result),
            "rewards": dict(self.rewards),
            "consequences": list(self.consequences),
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Mission":
        d = dict(data)
        d["mission_type"] = MissionType(d.get("mission_type", 0))
        d["result"] = MissionResult(d.get("result", 0))
        if d.get("target_location"):
            d["target_location"] = tuple(d["target_location"])
        return cls(**d)


class EspionageSystem:
    """Manages spies and their missions."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._spies: dict[int, Spy] = {}
        self._missions: dict[int, Mission] = {}
        self._next_spy_id: int = 1
        self._next_mission_id: int = 1

    def recruit_spy(self, entity_id: int, name: str,
                    faction_id: Optional[int] = None,
                    stealth: int = 5, deception: int = 5,
                    perception: int = 5,
                    current_tick: float = 0.0) -> Spy:
        spy = Spy(
            spy_id=self._next_spy_id, entity_id=entity_id,
            name=name, faction_id=faction_id,
            skill_stealth=stealth, skill_deception=deception,
            skill_perception=perception,
            recruited_tick=current_tick,
        )
        self._next_spy_id += 1
        self._spies[spy.spy_id] = spy
        return spy

    def assign_mission(self, spy_id: int, mission_type: MissionType,
                       target_faction_id: Optional[int] = None,
                       target_entity_id: Optional[int] = None,
                       target_kingdom_id: Optional[int] = None,
                       target_location: Optional[tuple[int, int]] = None,
                       difficulty: float = 1.0,
                       duration_days: float = 7.0,
                       current_tick: float = 0.0,
                       description: str = "") -> Optional[Mission]:
        spy = self._spies.get(spy_id)
        if spy is None or spy.status != "available":
            return None
        mission = Mission(
            mission_id=self._next_mission_id,
            mission_type=mission_type, spy_id=spy_id,
            target_faction_id=target_faction_id,
            target_entity_id=target_entity_id,
            target_kingdom_id=target_kingdom_id,
            target_location=target_location,
            difficulty=difficulty, duration_days=duration_days,
            started_tick=current_tick,
            ends_tick=current_tick + duration_days * 24 * 3600,  # convert days to seconds
            description=description,
        )
        self._next_mission_id += 1
        self._missions[mission.mission_id] = mission
        spy.current_mission_id = mission.mission_id
        spy.status = "on_mission"
        return mission

    def resolve_mission(self, mission_id: int, current_tick: float = 0.0) -> MissionResult:
        """Resolve a mission's outcome."""
        mission = self._missions.get(mission_id)
        if mission is None or not mission.is_active:
            return MissionResult.PENDING
        spy = self._spies.get(mission.spy_id)
        if spy is None:
            mission.result = MissionResult.FAILURE
            mission.is_active = False
            return mission.result
        # Compute success chance
        skill_avg = (spy.skill_stealth + spy.skill_deception + spy.skill_perception) / 3
        base_chance = 50 + skill_avg * 3 - mission.difficulty * 10
        # Suspicion penalty
        base_chance -= spy.suspicion_level * 30
        # Cover quality bonus
        base_chance += spy.cover_quality * 10
        base_chance = max(5, min(95, base_chance))
        roll = self.rng.random() * 100
        if roll < base_chance * 0.7:
            mission.result = MissionResult.SUCCESS
            spy.successful_missions += 1
            spy.suspicion_level = max(0.0, spy.suspicion_level - 0.1)
        elif roll < base_chance:
            mission.result = MissionResult.PARTIAL_SUCCESS
            spy.successful_missions += 1
        elif roll < base_chance + 20:
            mission.result = MissionResult.FAILURE
            spy.failed_missions += 1
            spy.suspicion_level = min(1.0, spy.suspicion_level + 0.2)
        elif roll < base_chance + 30:
            mission.result = MissionResult.DISCOVERED
            spy.failed_missions += 1
            spy.suspicion_level = 1.0
        elif roll < base_chance + 35:
            mission.result = MissionResult.SPY_CAPTURED
            spy.status = "captured"
        else:
            mission.result = MissionResult.SPY_KILLED
            spy.status = "dead"
        mission.is_active = False
        spy.current_mission_id = None
        if spy.status == "on_mission":
            spy.status = "available"
        # Apply consequences
        self._apply_consequences(mission, spy)
        return mission.result

    def _apply_consequences(self, mission: Mission, spy: Spy) -> None:
        """Apply mission consequences to the world."""
        if mission.result == MissionResult.SUCCESS:
            if mission.mission_type == MissionType.GATHER_INTEL:
                spy.known_intel.append(mission.mission_id)
                mission.rewards["intel_gathered"] = True
            elif mission.mission_type == MissionType.SABOTAGE:
                mission.consequences.append("target_production_reduced")
            elif mission.mission_type == MissionType.ASSASSINATE:
                mission.consequences.append("target_killed")
            elif mission.mission_type == MissionType.INCITE_REBELLION:
                mission.consequences.append("rebellion_started")
            elif mission.mission_type == MissionType.STEAL_TECH:
                mission.rewards["tech_stolen"] = True
            elif mission.mission_type == MissionType.SPREAD_RUMOR:
                mission.consequences.append("reputation_damaged")
        elif mission.result in (MissionResult.DISCOVERED, MissionResult.SPY_CAPTURED,
                                 MissionResult.SPY_KILLED):
            mission.consequences.append("diplomatic_incident")
            if mission.target_faction_id is not None:
                mission.consequences.append(f"faction_{mission.target_faction_id}_angered")

    def update(self, dt_days: float, current_tick: float = 0.0) -> list[MissionResult]:
        """Advance all active missions."""
        results: list[MissionResult] = []
        for mission in list(self._missions.values()):
            if not mission.is_active:
                continue
            if mission.ends_tick is not None and current_tick >= mission.ends_tick:
                results.append(self.resolve_mission(mission.mission_id, current_tick))
        return results

    def spies(self) -> list[Spy]:
        return list(self._spies.values())

    def missions(self) -> list[Mission]:
        return list(self._missions.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "spies": {str(sid): s.to_dict() for sid, s in self._spies.items()},
            "missions": {str(mid): m.to_dict() for mid, m in self._missions.items()},
            "next_spy_id": self._next_spy_id,
            "next_mission_id": self._next_mission_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EspionageSystem":
        sys = cls()
        sys._spies = {int(sid): Spy.from_dict(s) for sid, s in data.get("spies", {}).items()}
        sys._missions = {int(mid): Mission.from_dict(m) for mid, m in data.get("missions", {}).items()}
        sys._next_spy_id = data.get("next_spy_id", 1)
        sys._next_mission_id = data.get("next_mission_id", 1)
        return sys
