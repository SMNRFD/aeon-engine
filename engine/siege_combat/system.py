"""Siege combat system.

Models assaults on fortifications:
* Siege engines (catapults, trebuchets, ballistae, battering rams, siege towers)
* Wall sections with HP
* Gates with HP and lock difficulty
* Defenders on walls (ranged advantage)
* Attackers at the base (vulnerable)
* Breaches, escalades, sapping

A siege has multiple phases:
* Investment — surrounding the fortification
* Bombardment — siege engines fire
* Assault — infantry attacks walls/gates
* Breach — entering through destroyed sections
* Surrender — defenders capitulate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class SiegeEngineType(IntEnum):
    CATAPULT = 0
    TREBUCHET = 1
    BALLISTA = 2
    BATTERING_RAM = 3
    SIEGE_TOWER = 4
    MANGONEL = 5
    CANNON = 6
    MORTAR = 7


class SiegeState(IntEnum):
    INVESTMENT = 0     # surrounding the fortification
    BOMBARDMENT = 1    # siege engines firing
    ASSAULT = 2        # infantry attacking
    BREACH = 3         # entered through breach
    SURRENDER = 4      # defenders gave up
    LIFTED = 5         # attackers gave up


# Siege engine stats
SIEGE_ENGINE_STATS: dict[SiegeEngineType, dict[str, Any]] = {
    SiegeEngineType.CATAPULT: {
        "damage": 50, "range": 30, "fire_rate": 0.2,
        "crew": 4, "build_time_hours": 12, "cost_copper": 500,
    },
    SiegeEngineType.TREBUCHET: {
        "damage": 100, "range": 50, "fire_rate": 0.1,
        "crew": 6, "build_time_hours": 24, "cost_copper": 1500,
    },
    SiegeEngineType.BALLISTA: {
        "damage": 30, "range": 40, "fire_rate": 0.5,
        "crew": 3, "build_time_hours": 8, "cost_copper": 300,
    },
    SiegeEngineType.BATTERING_RAM: {
        "damage": 40, "range": 1, "fire_rate": 1.0,
        "crew": 8, "build_time_hours": 6, "cost_copper": 200,
    },
    SiegeEngineType.SIEGE_TOWER: {
        "damage": 0, "range": 1, "fire_rate": 0.0,
        "crew": 20, "build_time_hours": 48, "cost_copper": 2000,
    },
    SiegeEngineType.MANGONEL: {
        "damage": 40, "range": 25, "fire_rate": 0.3,
        "crew": 4, "build_time_hours": 10, "cost_copper": 400,
    },
    SiegeEngineType.CANNON: {
        "damage": 80, "range": 60, "fire_rate": 0.4,
        "crew": 4, "build_time_hours": 4, "cost_copper": 1000,
    },
    SiegeEngineType.MORTAR: {
        "damage": 120, "range": 80, "fire_rate": 0.2,
        "crew": 5, "build_time_hours": 6, "cost_copper": 1500,
    },
}


@dataclass
class SiegeEngine:
    """A siege engine."""

    engine_id: int
    engine_type: SiegeEngineType
    name: str
    hp: int = 100
    hp_max: int = 100
    crew_count: int = 4
    crew_max: int = 4
    is_operational: bool = True
    ammo_remaining: int = 100
    target_wall_section: Optional[int] = None

    @property
    def damage(self) -> int:
        return SIEGE_ENGINE_STATS.get(self.engine_type, {}).get("damage", 0)

    @property
    def range(self) -> int:
        return SIEGE_ENGINE_STATS.get(self.engine_type, {}).get("range", 0)

    @property
    def fire_rate(self) -> float:
        return SIEGE_ENGINE_STATS.get(self.engine_type, {}).get("fire_rate", 0)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["engine_type"] = int(self.engine_type)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SiegeEngine":
        d = dict(data)
        d["engine_type"] = SiegeEngineType(d.get("engine_type", 0))
        return cls(**d)


@dataclass
class WallSection:
    """A section of fortification wall."""

    section_id: int
    name: str
    hp: int = 1000
    hp_max: int = 1000
    height: int = 10  # metres
    thickness: int = 2  # metres
    defenders: int = 0
    is_breached: bool = False
    is_gate: bool = False
    lock_difficulty: int = 0  # for gates

    @property
    def is_destroyed(self) -> bool:
        return self.hp <= 0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "WallSection":
        return cls(**data)


@dataclass
class Siege:
    """An ongoing siege."""

    siege_id: int
    attacker_faction_id: int
    defender_faction_id: int
    fortification_name: str
    state: SiegeState = SiegeState.INVESTMENT
    started_tick: float = 0.0
    duration_days: float = 0.0
    wall_sections: list[WallSection] = field(default_factory=list)
    siege_engines: list[SiegeEngine] = field(default_factory=list)
    attacker_troops: int = 0
    defender_troops: int = 0
    attacker_casualties: int = 0
    defender_casualties: int = 0
    attacker_morale: float = 75.0
    defender_morale: float = 75.0
    supplies_remaining_days: float = 30.0  # for defenders
    breaches: list[int] = field(default_factory=list)  # section_ids with breaches

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["state"] = int(self.state)
        d["wall_sections"] = [s.to_dict() for s in self.wall_sections]
        d["siege_engines"] = [e.to_dict() for e in self.siege_engines]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Siege":
        d = dict(data)
        d["state"] = SiegeState(d.get("state", 0))
        d["wall_sections"] = [WallSection.from_dict(s) for s in d.get("wall_sections", [])]
        d["siege_engines"] = [SiegeEngine.from_dict(e) for e in d.get("siege_engines", [])]
        return cls(**d)


class SiegeCombatSystem:
    """Manages siege combat."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._sieges: dict[int, Siege] = {}
        self._next_siege_id: int = 1
        self._next_engine_id: int = 1
        self._next_section_id: int = 1

    def create_siege(self, attacker_faction_id: int, defender_faction_id: int,
                     fortification_name: str,
                     wall_count: int = 4,
                     defender_troops: int = 100,
                     attacker_troops: int = 200,
                     current_tick: float = 0.0) -> Siege:
        """Start a new siege."""
        siege = Siege(
            siege_id=self._next_siege_id,
            attacker_faction_id=attacker_faction_id,
            defender_faction_id=defender_faction_id,
            fortification_name=fortification_name,
            started_tick=current_tick,
            attacker_troops=attacker_troops,
            defender_troops=defender_troops,
        )
        # Create wall sections
        for i in range(wall_count):
            section = WallSection(
                section_id=self._next_section_id,
                name=f"Wall Section {chr(65 + i)}",
            )
            self._next_section_id += 1
            siege.wall_sections.append(section)
        # Add a gate (last section)
        gate = WallSection(
            section_id=self._next_section_id,
            name="Main Gate",
            is_gate=True,
            hp=500, hp_max=500,
            lock_difficulty=15,
        )
        self._next_section_id += 1
        siege.wall_sections.append(gate)
        self._next_siege_id += 1
        self._sieges[siege.siege_id] = siege
        return siege

    def add_siege_engine(self, siege_id: int,
                         engine_type: SiegeEngineType,
                         name: str = "") -> Optional[SiegeEngine]:
        siege = self._sieges.get(siege_id)
        if siege is None:
            return None
        engine = SiegeEngine(
            engine_id=self._next_engine_id,
            engine_type=engine_type,
            name=name or f"{engine_type.name.title()} #{self._next_engine_id}",
            crew_count=SIEGE_ENGINE_STATS[engine_type]["crew"],
            crew_max=SIEGE_ENGINE_STATS[engine_type]["crew"],
        )
        self._next_engine_id += 1
        siege.siege_engines.append(engine)
        return engine

    def bombard(self, siege_id: int, dt_hours: float = 1.0) -> dict[str, Any]:
        """Siege engines fire on walls."""
        siege = self._sieges.get(siege_id)
        if siege is None:
            return {"error": "Siege not found"}
        if siege.state == SiegeState.SURRENDER or siege.state == SiegeState.LIFTED:
            return {"error": "Siege is over"}
        total_damage = 0
        sections_destroyed: list[str] = []
        for engine in siege.siege_engines:
            if not engine.is_operational or engine.ammo_remaining <= 0:
                continue
            # Fire rate determines shots per hour
            shots = int(engine.fire_rate * dt_hours * 10)
            for _ in range(shots):
                if engine.ammo_remaining <= 0:
                    break
                engine.ammo_remaining -= 1
                # Pick a random wall section
                if not siege.wall_sections:
                    break
                target = self.rng.choice(siege.wall_sections)
                if target.is_destroyed:
                    continue
                # Hit chance
                if not self.rng.chance(0.6):
                    continue
                target.hp = max(0, target.hp - engine.damage)
                total_damage += engine.damage
                if target.is_destroyed and target.section_id not in siege.breaches:
                    siege.breaches.append(target.section_id)
                    sections_destroyed.append(target.name)
        return {
            "total_damage": total_damage,
            "sections_destroyed": sections_destroyed,
            "breaches": len(siege.breaches),
        }

    def assault(self, siege_id: int, troops_committed: int) -> dict[str, Any]:
        """Launch an infantry assault on the walls."""
        siege = self._sieges.get(siege_id)
        if siege is None:
            return {"error": "Siege not found"}
        siege.state = SiegeState.ASSAULT
        # Defenders have advantage
        defense_ratio = siege.defender_troops / max(1, troops_committed)
        # For each wall section, attackers try to scale
        attacker_losses = 0
        defender_losses = 0
        sections_captured = 0
        for section in siege.wall_sections:
            if section.is_destroyed:
                # Breach — easier to assault
                attacker_loss = int(troops_committed * 0.05 * self.rng.uniform(0.5, 1.5))
                defender_loss = int(section.defenders * 0.1 * self.rng.uniform(0.5, 1.5))
            else:
                # Wall — harder
                attacker_loss = int(troops_committed * 0.1 * self.rng.uniform(0.8, 1.5))
                defender_loss = int(section.defenders * 0.05 * self.rng.uniform(0.5, 1.0))
            attacker_losses += attacker_loss
            defender_losses += defender_loss
            siege.attacker_troops = max(0, siege.attacker_troops - attacker_loss)
            siege.defender_troops = max(0, siege.defender_troops - defender_loss)
            section.defenders = max(0, section.defenders - defender_loss)
            if section.defenders == 0:
                sections_captured += 1
        siege.attacker_casualties += attacker_losses
        siege.defender_casualties += defender_losses
        siege.attacker_morale = max(0, siege.attacker_morale - attacker_losses * 0.1)
        siege.defender_morale = max(0, siege.defender_morale - defender_losses * 0.1)
        # Check for surrender
        if siege.defender_morale < 20 or siege.defender_troops < 10:
            siege.state = SiegeState.SURRENDER
        if siege.attacker_morale < 20 or siege.attacker_troops < 10:
            siege.state = SiegeState.LIFTED
        return {
            "attacker_losses": attacker_losses,
            "defender_losses": defender_losses,
            "sections_captured": sections_captured,
            "state": siege.state.name,
        }

    def update(self, dt_days: float) -> None:
        """Advance all sieges."""
        for siege in self._sieges.values():
            if siege.state in (SiegeState.SURRENDER, SiegeState.LIFTED):
                continue
            siege.duration_days += dt_days
            # Defenders consume supplies
            siege.supplies_remaining_days = max(0, siege.supplies_remaining_days - dt_days)
            # If out of supplies, morale drops
            if siege.supplies_remaining_days <= 0:
                siege.defender_morale = max(0, siege.defender_morale - 5 * dt_days)
            # If supplies very low, surrender chance
            if siege.supplies_remaining_days <= 5 and self.rng.chance(0.1 * dt_days):
                siege.state = SiegeState.SURRENDER
            # Attacker disease and desertion
            if siege.duration_days > 30:
                siege.attacker_troops = max(0, siege.attacker_troops - int(2 * dt_days))
                siege.attacker_morale = max(0, siege.attacker_morale - 0.5 * dt_days)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sieges": {str(sid): s.to_dict() for sid, s in self._sieges.items()},
            "next_siege_id": self._next_siege_id,
            "next_engine_id": self._next_engine_id,
            "next_section_id": self._next_section_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SiegeCombatSystem":
        sys = cls()
        sys._sieges = {
            int(sid): Siege.from_dict(s) for sid, s in data.get("sieges", {}).items()
        }
        sys._next_siege_id = data.get("next_siege_id", 1)
        sys._next_engine_id = data.get("next_engine_id", 1)
        sys._next_section_id = data.get("next_section_id", 1)
        return sys
