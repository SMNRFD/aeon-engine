"""Rebellion and civil war system.

Models internal conflicts within factions and kingdoms:
* Peasant revolts — driven by high taxes, low stability, famine
* Noble rebellions — driven by low legitimacy, succession disputes
* Religious schisms — driven by heresy, doctrinal disputes
* Independence movements — driven by cultural/ethnic differences
* Succession crises — driven by unclear or contested succession
* Civil wars — large-scale conflicts between rival claimants
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class RebellionType(IntEnum):
    PEASANT_REVOLT = 0
    NOBLE_REBELLION = 1
    RELIGIOUS_SCHISM = 2
    INDEPENDENCE_MOVEMENT = 3
    MILITARY_COUP = 4
    SLAVE_REVOLT = 5
    MERCHANT_REVOLT = 6
    SUCCESSION_CRISIS = 7


class RebellionState(IntEnum):
    BREWING = 0       # unrest building
    ACTIVE = 1        # rebellion in progress
    SUPPRESSED = 2    # defeated
    SUCCESSFUL = 3    # rebels won
    NEGOTIATED = 4    # settled peacefully
    FADED = 5         # lost popular support


@dataclass
class Rebellion:
    """An ongoing rebellion."""

    rebellion_id: int
    name: str
    rebellion_type: RebellionType
    faction_id: int         # the faction being rebelled against
    rebel_leader_id: Optional[int] = None
    rebel_faction_id: Optional[int] = None  # the new faction if successful
    state: RebellionState = RebellionState.BREWING
    started_tick: float = 0.0
    duration_days: float = 0.0
    rebel_strength: int = 100
    loyalist_strength: int = 200
    rebel_morale: float = 60.0
    loyalist_morale: float = 60.0
    popular_support: float = 0.3  # 0..1 of population supporting rebels
    grievances: list[str] = field(default_factory=list)
    demands: list[str] = field(default_factory=list)
    battles_fought: int = 0
    rebel_casualties: int = 0
    loyalist_casualties: int = 0
    is_civil_war: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["rebellion_type"] = int(self.rebellion_type)
        d["state"] = int(self.state)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Rebellion":
        d = dict(data)
        d["rebellion_type"] = RebellionType(d.get("rebellion_type", 0))
        d["state"] = RebellionState(d.get("state", 0))
        return cls(**d)


@dataclass
class CivilWar:
    """A large-scale civil war."""

    civil_war_id: int
    faction_id: int
    claimant_a_id: int      # one claimant to the throne
    claimant_b_id: int      # the other claimant
    claimant_a_strength: int = 500
    claimant_b_strength: int = 500
    claimant_a_territory: list[int] = field(default_factory=list)
    claimant_b_territory: list[int] = field(default_factory=list)
    started_tick: float = 0.0
    duration_days: float = 0.0
    battles: int = 0
    casualties_a: int = 0
    casualties_b: int = 0
    war_score: float = 0.0  # -100..100; positive = A winning
    is_active: bool = True
    cause: str = ""         # succession dispute, religious schism, etc.

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["claimant_a_territory"] = list(self.claimant_a_territory)
        d["claimant_b_territory"] = list(self.claimant_b_territory)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CivilWar":
        return cls(**data)


@dataclass
class SuccessionCrisis:
    """A succession crisis in a kingdom."""

    crisis_id: int
    kingdom_id: int
    deceased_ruler_id: Optional[int] = None
    claimants: list[int] = field(default_factory=list)  # politician IDs
    has_clear_heir: bool = False
    clear_heir_id: Optional[int] = None
    started_tick: float = 0.0
    resolved_tick: Optional[float] = None
    resolution: str = ""  # "heir_succeeded", "civil_war", "election", "usurpation"
    winner_id: Optional[int] = None
    is_resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "SuccessionCrisis":
        return cls(**data)


class RebellionSystem:
    """Manages rebellions, civil wars, and succession crises."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._rebellions: dict[int, Rebellion] = {}
        self._civil_wars: dict[int, CivilWar] = {}
        self._crises: dict[int, SuccessionCrisis] = {}
        self._next_rebellion_id: int = 1
        self._next_civil_war_id: int = 1
        self._next_crisis_id: int = 1

    # ---------- rebellions ----------

    def start_rebellion(self, name: str, rebellion_type: RebellionType,
                        faction_id: int,
                        grievances: Optional[list[str]] = None,
                        demands: Optional[list[str]] = None,
                        rebel_strength: int = 100,
                        loyalist_strength: int = 200,
                        current_tick: float = 0.0) -> Rebellion:
        rebellion = Rebellion(
            rebellion_id=self._next_rebellion_id,
            name=name, rebellion_type=rebellion_type,
            faction_id=faction_id,
            started_tick=current_tick,
            rebel_strength=rebel_strength,
            loyalist_strength=loyalist_strength,
            grievances=list(grievances or []),
            demands=list(demands or []),
            is_civil_war=rebellion_type in (RebellionType.NOBLE_REBELLION,
                                              RebellionType.SUCCESSION_CRISIS),
        )
        self._next_rebellion_id += 1
        self._rebellions[rebellion.rebellion_id] = rebellion
        return rebellion

    def suppress_rebellion(self, rebellion_id: int,
                            current_tick: float = 0.0) -> bool:
        rebellion = self._rebellions.get(rebellion_id)
        if rebellion is None or rebellion.state != RebellionState.ACTIVE:
            return False
        # Loyalists win if they have significantly more strength
        if rebellion.loyalist_strength > rebellion.rebel_strength * 1.5:
            rebellion.state = RebellionState.SUPPRESSED
            rebellion.duration_days = (current_tick - rebellion.started_tick) / 86400
            return True
        return False

    def negotiate_settlement(self, rebellion_id: int,
                              current_tick: float = 0.0) -> bool:
        rebellion = self._rebellions.get(rebellion_id)
        if rebellion is None:
            return False
        rebellion.state = RebellionState.NEGOTIATED
        return True

    def battle(self, rebellion_id: int) -> dict[str, Any]:
        """Resolve a battle in a rebellion."""
        rebellion = self._rebellions.get(rebellion_id)
        if rebellion is None:
            return {"error": "Rebellion not found"}
        rebellion.state = RebellionState.ACTIVE
        # Compute relative strength
        total = rebellion.rebel_strength + rebellion.loyalist_strength
        rebel_chance = rebellion.rebel_strength / max(1, total)
        # Apply morale modifiers
        rebel_chance *= (rebellion.rebel_morale / 100)
        loyalist_chance = (1 - rebel_chance) * (rebellion.loyalist_morale / 100)
        # Random factor
        roll = self.rng.random() * (rebel_chance + loyalist_chance)
        rebel_wins = roll < rebel_chance
        # Casualties
        rebel_losses = int(rebellion.rebel_strength * self.rng.uniform(0.05, 0.2))
        loyalist_losses = int(rebellion.loyalist_strength * self.rng.uniform(0.05, 0.2))
        rebellion.rebel_strength = max(0, rebellion.rebel_strength - rebel_losses)
        rebellion.loyalist_strength = max(0, rebellion.loyalist_strength - loyalist_losses)
        rebellion.rebel_casualties += rebel_losses
        rebellion.loyalist_casualties += loyalist_losses
        rebellion.battles_fought += 1
        # Morale changes
        if rebel_wins:
            rebellion.rebel_morale = min(100, rebellion.rebel_morale + 5)
            rebellion.loyalist_morale = max(0, rebellion.loyalist_morale - 5)
        else:
            rebellion.rebel_morale = max(0, rebellion.rebel_morale - 5)
            rebellion.loyalist_morale = min(100, rebellion.loyalist_morale + 5)
        # Check end conditions
        if rebellion.rebel_strength <= 0:
            rebellion.state = RebellionState.SUPPRESSED
        elif rebellion.loyalist_strength <= 0:
            rebellion.state = RebellionState.SUCCESSFUL
        elif rebellion.rebel_morale < 10:
            rebellion.state = RebellionState.FADED
        return {
            "rebel_wins": rebel_wins,
            "rebel_losses": rebel_losses,
            "loyalist_losses": loyalist_losses,
            "state": rebellion.state.name,
        }

    # ---------- civil wars ----------

    def start_civil_war(self, faction_id: int, claimant_a: int,
                        claimant_b: int, cause: str = "",
                        current_tick: float = 0.0) -> CivilWar:
        cw = CivilWar(
            civil_war_id=self._next_civil_war_id,
            faction_id=faction_id,
            claimant_a_id=claimant_a,
            claimant_b_id=claimant_b,
            started_tick=current_tick,
            cause=cause,
        )
        self._next_civil_war_id += 1
        self._civil_wars[cw.civil_war_id] = cw
        return cw

    def civil_war_battle(self, cw_id: int) -> dict[str, Any]:
        cw = self._civil_wars.get(cw_id)
        if cw is None or not cw.is_active:
            return {"error": "Civil war not found or inactive"}
        total = cw.claimant_a_strength + cw.claimant_b_strength
        a_chance = cw.claimant_a_strength / max(1, total)
        a_wins = self.rng.chance(a_chance)
        a_losses = int(cw.claimant_a_strength * self.rng.uniform(0.05, 0.15))
        b_losses = int(cw.claimant_b_strength * self.rng.uniform(0.05, 0.15))
        cw.claimant_a_strength = max(0, cw.claimant_a_strength - a_losses)
        cw.claimant_b_strength = max(0, cw.claimant_b_strength - b_losses)
        cw.casualties_a += a_losses
        cw.casualties_b += b_losses
        cw.battles += 1
        if a_wins:
            cw.war_score = min(100, cw.war_score + 10)
        else:
            cw.war_score = max(-100, cw.war_score - 10)
        # End conditions
        if cw.claimant_a_strength <= 0 or cw.war_score <= -100:
            cw.is_active = False
        elif cw.claimant_b_strength <= 0 or cw.war_score >= 100:
            cw.is_active = False
        return {
            "a_wins": a_wins,
            "a_losses": a_losses,
            "b_losses": b_losses,
            "war_score": cw.war_score,
            "is_active": cw.is_active,
        }

    # ---------- succession crises ----------

    def trigger_succession_crisis(self, kingdom_id: int,
                                   claimants: list[int],
                                   current_tick: float = 0.0) -> SuccessionCrisis:
        crisis = SuccessionCrisis(
            crisis_id=self._next_crisis_id,
            kingdom_id=kingdom_id,
            claimants=list(claimants),
            started_tick=current_tick,
        )
        self._next_crisis_id += 1
        self._crises[crisis.crisis_id] = crisis
        return crisis

    def resolve_crisis(self, crisis_id: int, resolution: str,
                        winner_id: Optional[int] = None,
                        current_tick: float = 0.0) -> bool:
        crisis = self._crises.get(crisis_id)
        if crisis is None or crisis.is_resolved:
            return False
        crisis.resolution = resolution
        crisis.winner_id = winner_id
        crisis.is_resolved = True
        crisis.resolved_tick = current_tick
        return True

    # ---------- update ----------

    def update(self, dt_days: float, current_tick: float = 0.0) -> None:
        """Advance all conflicts."""
        for rebellion in self._rebellions.values():
            if rebellion.state not in (RebellionState.BREWING, RebellionState.ACTIVE):
                continue
            rebellion.duration_days += dt_days
            # Random events
            if self.rng.chance(0.05 * dt_days):
                self.battle(rebellion.rebellion_id)
            # Popular support drift
            if rebellion.state == RebellionState.BREWING:
                rebellion.popular_support = min(1.0, rebellion.popular_support + 0.01 * dt_days)
                if rebellion.popular_support > 0.5:
                    rebellion.state = RebellionState.ACTIVE
        for cw in self._civil_wars.values():
            if not cw.is_active:
                continue
            cw.duration_days += dt_days
            if self.rng.chance(0.1 * dt_days):
                self.civil_war_battle(cw.civil_war_id)

    def rebellions(self) -> list[Rebellion]:
        return list(self._rebellions.values())

    def civil_wars(self) -> list[CivilWar]:
        return list(self._civil_wars.values())

    def crises(self) -> list[SuccessionCrisis]:
        return list(self._crises.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "rebellions": {str(rid): r.to_dict() for rid, r in self._rebellions.items()},
            "civil_wars": {str(cwid): cw.to_dict() for cwid, cw in self._civil_wars.items()},
            "crises": {str(cid): c.to_dict() for cid, c in self._crises.items()},
            "next_rebellion_id": self._next_rebellion_id,
            "next_civil_war_id": self._next_civil_war_id,
            "next_crisis_id": self._next_crisis_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RebellionSystem":
        sys = cls()
        sys._rebellions = {
            int(rid): Rebellion.from_dict(r) for rid, r in data.get("rebellions", {}).items()
        }
        sys._civil_wars = {
            int(cwid): CivilWar.from_dict(cw) for cwid, cw in data.get("civil_wars", {}).items()
        }
        sys._crises = {
            int(cid): SuccessionCrisis.from_dict(c) for cid, c in data.get("crises", {}).items()
        }
        sys._next_rebellion_id = data.get("next_rebellion_id", 1)
        sys._next_civil_war_id = data.get("next_civil_war_id", 1)
        sys._next_crisis_id = data.get("next_crisis_id", 1)
        return sys
