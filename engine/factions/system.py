"""Faction system — diplomacy, laws, taxes, wars."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import ClassVar, Optional

from engine.core.ecs import Entity
from engine.utils.rng import RNG


class DiplomaticStance(IntEnum):
    WAR = -2
    HOSTILE = -1
    NEUTRAL = 0
    FRIENDLY = 1
    ALLIED = 2
    VASSAL = 3  # one-way subordinate


@dataclass
class FactionRelation:
    """A bilateral relationship between two factions."""

    faction_a: int
    faction_b: int
    stance: DiplomaticStance = DiplomaticStance.NEUTRAL
    trust: float = 0.0       # -100..100
    trade_agreement: bool = False
    non_aggression_pact: bool = False
    mutual_defense: bool = False
    tribute: int = 0         # cp per game-month paid from B to A
    duration: float = 0.0    # how long the current stance has held
    last_change: float = 0.0


@dataclass
class War:
    """An ongoing war."""

    attacker: int
    defender: int
    start_tick: float
    war_score: float = 0.0  # -100..100; positive = attacker winning
    battles: int = 0
    casualties_attacker: int = 0
    casualties_defender: int = 0
    goal: str = "conquest"  # "conquest", "humiliate", "liberate", "raid"


@dataclass
class Faction:
    """A faction definition."""

    id: int
    name: str
    description: str
    color: int
    type: str = "kingdom"  # kingdom, guild, religion, bandit, mercenary, merchant, secret
    leader_id: Optional[int] = None
    capital: Optional[tuple[int, int]] = None
    founded_tick: float = 0.0
    population: int = 0
    military_strength: int = 0
    treasury: int = 0       # copper
    income_per_month: int = 0
    laws: dict[str, int] = field(default_factory=dict)  # law_id -> severity
    taxes: dict[str, float] = field(default_factory=dict)  # type -> rate
    religion: Optional[str] = None
    culture: Optional[str] = None
    technology_level: int = 1
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "color": self.color, "type": self.type, "leader_id": self.leader_id,
            "capital": self.capital, "founded_tick": self.founded_tick,
            "population": self.population, "military_strength": self.military_strength,
            "treasury": self.treasury, "income_per_month": self.income_per_month,
            "laws": dict(self.laws), "taxes": dict(self.taxes),
            "religion": self.religion, "culture": self.culture,
            "technology_level": self.technology_level, "tags": self.tags,
        }


class FactionLibrary:
    """Registry of factions."""

    _factions: ClassVar[dict[int, Faction]] = {}
    _next_id: ClassVar[int] = 1
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, faction: Faction) -> Faction:
        if not cls._defaults_loaded:
            cls._init_defaults()
        if faction.id == 0:
            faction.id = cls._next_id
            cls._next_id += 1
        else:
            cls._next_id = max(cls._next_id, faction.id + 1)
        cls._factions[faction.id] = faction
        return faction

    @classmethod
    def get(cls, faction_id: int) -> Optional[Faction]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._factions.get(faction_id)

    @classmethod
    def all(cls) -> list[Faction]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._factions.values())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        cls._defaults_loaded = True
        for f in DEFAULT_FACTIONS:
            if f.id == 0:
                f.id = cls._next_id
                cls._next_id += 1
            else:
                cls._next_id = max(cls._next_id, f.id + 1)
            cls._factions[f.id] = f


class FactionSystem:
    """Manages faction relations, wars, and politics."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._relations: dict[tuple[int, int], FactionRelation] = {}
        self._wars: list[War] = []

    def get_relation(self, a: int, b: int) -> FactionRelation:
        if a == b:
            return FactionRelation(a, b, DiplomaticStance.ALLIED, 100.0)
        key = (min(a, b), max(a, b))
        if key not in self._relations:
            self._relations[key] = FactionRelation(key[0], key[1])
        return self._relations[key]

    def set_stance(self, a: int, b: int, stance: DiplomaticStance, current_tick: float = 0.0) -> None:
        rel = self.get_relation(a, b)
        if rel.stance != stance:
            rel.stance = stance
            rel.last_change = current_tick
            rel.duration = 0.0
            if stance == DiplomaticStance.WAR:
                self._wars.append(War(attacker=a, defender=b, start_tick=current_tick))

    def make_peace(self, a: int, b: int, current_tick: float = 0.0) -> None:
        rel = self.get_relation(a, b)
        rel.stance = DiplomaticStance.NEUTRAL
        rel.last_change = current_tick
        rel.duration = 0.0
        self._wars = [w for w in self._wars
                      if not ((w.attacker == a and w.defender == b)
                              or (w.attacker == b and w.defender == a))]

    def adjust_trust(self, a: int, b: int, delta: float) -> float:
        rel = self.get_relation(a, b)
        rel.trust = max(-100.0, min(100.0, rel.trust + delta))
        # Stance auto-adjustment at trust extremes
        if rel.trust > 60 and rel.stance < DiplomaticStance.FRIENDLY:
            rel.stance = DiplomaticStance.FRIENDLY
        elif rel.trust < -60 and rel.stance > DiplomaticStance.HOSTILE:
            rel.stance = DiplomaticStance.HOSTILE
        return rel.trust

    def declare_war(self, attacker: int, defender: int,
                    current_tick: float = 0.0, goal: str = "conquest") -> None:
        self.set_stance(attacker, defender, DiplomaticStance.WAR, current_tick)
        for w in self._wars:
            if w.attacker == attacker and w.defender == defender:
                w.goal = goal
                return

    def active_wars(self) -> list[War]:
        return list(self._wars)

    def wars_involving(self, faction_id: int) -> list[War]:
        return [w for w in self._wars
                if w.attacker == faction_id or w.defender == faction_id]

    def update_war_score(self, attacker: int, defender: int, delta: float,
                         casualties: tuple[int, int] = (0, 0)) -> None:
        for w in self._wars:
            if w.attacker == attacker and w.defender == defender:
                w.war_score = max(-100.0, min(100.0, w.war_score + delta))
                w.battles += 1
                w.casualties_attacker += casualties[0]
                w.casualties_defender += casualties[1]
                # Auto-peace if war score extreme
                if w.war_score >= 100 or w.war_score <= -100:
                    self.make_peace(attacker, defender)
                return

    def update(self, dt: float) -> None:
        """Tick faction relations."""
        for rel in self._relations.values():
            rel.duration += dt
        # Slowly drift trust toward 0
        for rel in self._relations.values():
            if rel.stance == DiplomaticStance.NEUTRAL:
                rel.trust *= (1.0 - 0.0001 * dt)

    # ---------- Laws & Taxes ----------

    @staticmethod
    def set_law(faction: Faction, law_id: str, severity: int) -> None:
        faction.laws[law_id] = max(0, min(10, severity))

    @staticmethod
    def set_tax(faction: Faction, tax_type: str, rate: float) -> None:
        faction.taxes[tax_type] = max(0.0, min(1.0, rate))

    @staticmethod
    def monthly_income(faction: Faction) -> int:
        base = faction.population * 2 + faction.income_per_month
        for tax_type, rate in faction.taxes.items():
            base = int(base * (1.0 + rate * 0.1))
        return base

    @staticmethod
    def apply_monthly_tick(faction: Faction) -> None:
        faction.treasury += FactionSystem.monthly_income(faction)


# ---------- Default factions ----------

DEFAULT_FACTIONS: list[Faction] = [
    Faction(id=0, name="Kingdom of Aldor", description="The principal human kingdom.",
            color=33, type="kingdom", population=50000, military_strength=2000,
            treasury=500000, income_per_month=8000, technology_level=4,
            religion="light", culture="aldorian",
            laws={"theft": 5, "murder": 10, "treason": 10},
            taxes={"income": 0.15, "trade": 0.10, "property": 0.05},
            tags=["human", "civilized"]),
    Faction(id=0, name="Iron Brotherhood", description="A guild of master smiths.",
            color=244, type="guild", population=800, military_strength=100,
            treasury=50000, income_per_month=2000, technology_level=6,
            laws={"theft": 8},
            taxes={"trade": 0.05},
            tags=["craft", "dwarven"]),
    Faction(id=0, name="Crimson Hand", description="A notorious bandit organisation.",
            color=196, type="bandit", population=300, military_strength=150,
            treasury=20000, income_per_month=500, technology_level=2,
            laws={}, taxes={},
            tags=["criminal", "violent"]),
    Faction(id=0, name="Order of the Silver Flame",
            description="A religious order devoted to the light.",
            color=250, type="religion", population=1200, military_strength=400,
            treasury=80000, income_per_month=1500, technology_level=5,
            religion="light", culture="devout",
            laws={"heresy": 10, "necromancy": 10},
            taxes={}, tags=["religious", "good"]),
    Faction(id=0, name="Mage's Conclave",
            description="A council of wizards and scholars.",
            color=165, type="guild", population=200, military_strength=50,
            treasury=120000, income_per_month=3000, technology_level=8,
            laws={"forbidden_magic": 7},
            taxes={}, tags=["arcane", "scholarly"]),
    Faction(id=0, name="Free Merchants' Guild",
            description="A powerful trading company spanning the realm.",
            color=215, type="merchant", population=2000, military_strength=300,
            treasury=300000, income_per_month=6000, technology_level=5,
            laws={"fraud": 5}, taxes={"trade": 0.02},
            tags=["trade", "wealthy"]),
]
