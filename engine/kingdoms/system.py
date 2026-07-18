"""Kingdom system — top-level political entities above factions.

A Kingdom owns territory, has a ruler, laws, taxes, military, and a
succession system. Multiple factions can exist within a kingdom.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


class KingdomType(IntEnum):
    MONARCHY = 0       # hereditary ruler
    REPUBLIC = 1       # elected representatives
    THEOCRACY = 2      # religious leader
    OLIGARCHY = 3      # small ruling council
    TRIBAL = 4         # chieftain-based
    EMPIRE = 5         # multi-ethnic conquered territories
    CITY_STATE = 6     # single city autonomous
    CONFEDERATION = 7  # loose alliance of states


class SuccessionLaw(IntEnum):
    PRIMOGENITURE = 0     # eldest child inherits
    ULTIMOGENITURE = 1    # youngest child inherits
    SENIORITY = 2         # eldest sibling/relative inherits
    ELECTION = 3          # nobles elect a ruler
    TANISTRY = 4          # aristocracy chooses from candidates
    MATRILINEAL = 5       # eldest daughter inherits
    PARTIBLE = 6          # territory divided among children
    MERITOCRATIC = 7      # most capable inherits


@dataclass
class Territory:
    """A piece of land owned by a kingdom."""

    territory_id: int
    name: str
    location: tuple[int, int]
    size: int = 100       # square km
    population: int = 0
    fertility: float = 0.5  # 0..1
    development: float = 0.2  # 0..1
    has_capital: bool = False
    resources: list[str] = field(default_factory=list)
    is_contested: bool = False
    contested_by: Optional[int] = None  # kingdom_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "territory_id": self.territory_id, "name": self.name,
            "location": self.location, "size": self.size,
            "population": self.population, "fertility": self.fertility,
            "development": self.development, "has_capital": self.has_capital,
            "resources": list(self.resources),
            "is_contested": self.is_contested, "contested_by": self.contested_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Territory":
        return cls(
            territory_id=data["territory_id"], name=data["name"],
            location=tuple(data["location"]), size=data.get("size", 100),
            population=data.get("population", 0),
            fertility=data.get("fertility", 0.5),
            development=data.get("development", 0.2),
            has_capital=data.get("has_capital", False),
            resources=list(data.get("resources", [])),
            is_contested=data.get("is_contested", False),
            contested_by=data.get("contested_by"),
        )


@dataclass
class Politician:
    """A political figure in a kingdom."""

    politician_id: int
    name: str
    kingdom_id: int
    title: str = "Citizen"
    faction_id: Optional[int] = None
    popularity: float = 50.0  # 0..100
    wealth: int = 0
    influence: float = 0.0   # 0..100
    ambition: float = 0.5    # 0..1
    corruption: float = 0.0  # 0..1
    is_ruler: bool = False
    is_heir: bool = False
    birth_tick: float = 0.0
    death_tick: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "politician_id": self.politician_id, "name": self.name,
            "kingdom_id": self.kingdom_id, "title": self.title,
            "faction_id": self.faction_id, "popularity": self.popularity,
            "wealth": self.wealth, "influence": self.influence,
            "ambition": self.ambition, "corruption": self.corruption,
            "is_ruler": self.is_ruler, "is_heir": self.is_heir,
            "birth_tick": self.birth_tick, "death_tick": self.death_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Politician":
        return cls(**data)


@dataclass
class Election:
    """An election in a republic or other elected system."""

    election_id: int
    kingdom_id: int
    candidates: list[int] = field(default_factory=list)  # politician_ids
    votes: dict[int, int] = field(default_factory=dict)  # politician_id -> votes
    winner_id: Optional[int] = None
    started_tick: float = 0.0
    ended_tick: Optional[float] = None
    is_active: bool = False


@dataclass
class Kingdom:
    """A kingdom definition."""

    id: int
    name: str
    description: str
    color: int
    kingdom_type: KingdomType = KingdomType.MONARCHY
    succession_law: SuccessionLaw = SuccessionLaw.PRIMOGENITURE
    ruler_id: Optional[int] = None
    capital_territory_id: Optional[int] = None
    founded_tick: float = 0.0
    territories: list[int] = field(default_factory=list)
    factions: list[int] = field(default_factory=list)
    population: int = 0
    treasury: int = 0
    tax_rate: float = 0.15
    military_strength: int = 0
    stability: float = 50.0    # 0..100
    prestige: float = 0.0      # 0..100
    legitimacy: float = 50.0   # 0..100
    technology_level: int = 1
    culture: str = "default"
    state_religion: Optional[str] = None
    official_language: str = "common"
    laws: dict[str, int] = field(default_factory=dict)
    alliances: list[int] = field(default_factory=list)  # other kingdom_ids
    rivals: list[int] = field(default_factory=list)
    at_war_with: list[int] = field(default_factory=list)
    heir_ids: list[int] = field(default_factory=list)
    politicians: list[int] = field(default_factory=list)
    history: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["kingdom_type"] = int(self.kingdom_type)
        d["succession_law"] = int(self.succession_law)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Kingdom":
        data = dict(data)
        if "kingdom_type" in data:
            data["kingdom_type"] = KingdomType(data["kingdom_type"])
        if "succession_law" in data:
            data["succession_law"] = SuccessionLaw(data["succession_law"])
        return cls(**data)


class KingdomLibrary:
    """Registry of kingdoms."""

    _kingdoms: ClassVar[dict[int, Kingdom]] = {}
    _next_id: ClassVar[int] = 1
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, kingdom: Kingdom) -> Kingdom:
        if not cls._defaults_loaded:
            cls._init_defaults()
        if kingdom.id == 0:
            kingdom.id = cls._next_id
            cls._next_id += 1
        else:
            cls._next_id = max(cls._next_id, kingdom.id + 1)
        cls._kingdoms[kingdom.id] = kingdom
        return kingdom

    @classmethod
    def get(cls, kingdom_id: int) -> Optional[Kingdom]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._kingdoms.get(kingdom_id)

    @classmethod
    def all(cls) -> list[Kingdom]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._kingdoms.values())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        cls._defaults_loaded = True
        for k in DEFAULT_KINGDOMS:
            if k.id == 0:
                k.id = cls._next_id
                cls._next_id += 1
            else:
                cls._next_id = max(cls._next_id, k.id + 1)
            cls._kingdoms[k.id] = k


class KingdomSystem:
    """Manages kingdom politics, succession, and wars."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._territories: dict[int, Territory] = {}
        self._politicians: dict[int, Politician] = {}
        self._elections: list[Election] = []
        self._next_territory_id: int = 1
        self._next_politician_id: int = 1
        self._next_election_id: int = 1

    # ---------- territories ----------

    def create_territory(self, name: str, location: tuple[int, int],
                         **kwargs: Any) -> Territory:
        territory = Territory(
            territory_id=self._next_territory_id,
            name=name, location=location, **kwargs,
        )
        self._next_territory_id += 1
        self._territories[territory.territory_id] = territory
        return territory

    def territory(self, territory_id: int) -> Optional[Territory]:
        return self._territories.get(territory_id)

    # ---------- politicians ----------

    def create_politician(self, name: str, kingdom_id: int,
                          **kwargs: Any) -> Politician:
        politician = Politician(
            politician_id=self._next_politician_id,
            name=name, kingdom_id=kingdom_id, **kwargs,
        )
        self._next_politician_id += 1
        self._politicians[politician.politician_id] = politician
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom:
            kingdom.politicians.append(politician.politician_id)
        return politician

    def politician(self, politician_id: int) -> Optional[Politician]:
        return self._politicians.get(politician_id)

    def ruler_of(self, kingdom_id: int) -> Optional[Politician]:
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom is None or kingdom.ruler_id is None:
            return None
        return self._politicians.get(kingdom.ruler_id)

    # ---------- succession ----------

    def determine_heir(self, kingdom_id: int) -> Optional[int]:
        """Determine the heir to a kingdom based on succession law."""
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom is None:
            return None
        # Get all politicians of this kingdom
        candidates = [self._politicians[pid] for pid in kingdom.politicians
                      if pid in self._politicians
                      and self._politicians[pid].death_tick is None]
        if not candidates:
            return None
        law = kingdom.succession_law
        if law == SuccessionLaw.ELECTION:
            # Hold an election
            winner = max(candidates, key=lambda p: p.popularity + p.influence)
            return winner.politician_id
        if law == SuccessionLaw.MERITOCRATIC:
            return max(candidates,
                       key=lambda p: p.influence + p.popularity / 2).politician_id
        if law == SuccessionLaw.MATRILINEAL:
            # Filter for female (we'd need gender data — assume any candidate)
            female_candidates = [c for c in candidates if "female" in c.__dict__.get("tags", [])]
            pool = female_candidates or candidates
            return max(pool, key=lambda p: p.birth_tick).politician_id  # eldest
        if law == SuccessionLaw.ULTIMOGENITURE:
            return min(candidates, key=lambda p: p.birth_tick).politician_id
        if law == SuccessionLaw.SENIORITY:
            return max(candidates, key=lambda p: p.birth_tick).politician_id
        if law == SuccessionLaw.PARTIBLE:
            # Kingdom splits — return the eldest, others become independent
            return max(candidates, key=lambda p: p.birth_tick).politician_id
        if law == SuccessionLaw.TANISTRY:
            # Elected from eligible bloodline members
            eligible = [c for c in candidates if c.influence > 20]
            pool = eligible or candidates
            return max(pool, key=lambda p: p.popularity).politician_id
        # PRIMOGENITURE (default)
        return max(candidates, key=lambda p: p.birth_tick).politician_id

    def on_ruler_death(self, kingdom_id: int, current_tick: float = 0.0) -> Optional[int]:
        """Process succession when the ruler dies."""
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom is None:
            return None
        old_ruler_id = kingdom.ruler_id
        if old_ruler_id is not None:
            old_ruler = self._politicians.get(old_ruler_id)
            if old_ruler:
                old_ruler.death_tick = current_tick
                old_ruler.is_ruler = False
        heir_id = self.determine_heir(kingdom_id)
        if heir_id is None:
            # Kingdom falls into chaos
            kingdom.stability = max(0, kingdom.stability - 30)
            kingdom.legitimacy = max(0, kingdom.legitimacy - 40)
            kingdom.history.append(f"Tick {current_tick:.0f}: Ruler died with no heir — chaos!")
            return None
        heir = self._politicians[heir_id]
        heir.is_ruler = True
        heir.is_heir = False
        kingdom.ruler_id = heir_id
        kingdom.history.append(
            f"Tick {current_tick:.0f}: {heir.name} ascended to the throne."
        )
        # Determine new heir
        new_heir_id = self._determine_next_heir(kingdom_id, exclude_id=heir_id)
        kingdom.heir_ids = [new_heir_id] if new_heir_id else []
        if new_heir_id and new_heir_id in self._politicians:
            self._politicians[new_heir_id].is_heir = True
        return heir_id

    def _determine_next_heir(self, kingdom_id: int,
                             exclude_id: Optional[int] = None) -> Optional[int]:
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom is None:
            return None
        candidates = [self._politicians[pid] for pid in kingdom.politicians
                      if pid in self._politicians
                      and self._politicians[pid].death_tick is None
                      and pid != exclude_id]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.birth_tick).politician_id

    # ---------- politics ----------

    def hold_election(self, kingdom_id: int, current_tick: float = 0.0) -> Optional[int]:
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom is None:
            return None
        candidates = [p for p in self._politicians.values()
                      if p.kingdom_id == kingdom_id and p.death_tick is None]
        if not candidates:
            return None
        election = Election(
            election_id=self._next_election_id,
            kingdom_id=kingdom_id,
            candidates=[c.politician_id for c in candidates],
            started_tick=current_tick,
            is_active=True,
        )
        self._next_election_id += 1
        # Vote: each politician votes based on popularity + influence
        for voter in candidates:
            best = max(candidates,
                       key=lambda c: c.popularity + c.influence + self.rng.uniform(-5, 5))
            election.votes[best.politician_id] = election.votes.get(best.politician_id, 0) + 1
        winner_id = max(election.votes, key=lambda k: election.votes[k])
        election.winner_id = winner_id
        election.ended_tick = current_tick
        election.is_active = False
        self._elections.append(election)
        # Old ruler steps down
        if kingdom.ruler_id is not None:
            old_ruler = self._politicians.get(kingdom.ruler_id)
            if old_ruler:
                old_ruler.is_ruler = False
        # New ruler takes power
        winner = self._politicians[winner_id]
        winner.is_ruler = True
        kingdom.ruler_id = winner_id
        kingdom.history.append(
            f"Tick {current_tick:.0f}: {winner.name} won election with {election.votes[winner_id]} votes."
        )
        return winner_id

    def adjust_stability(self, kingdom_id: int, delta: float) -> float:
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom is None:
            return 0.0
        kingdom.stability = max(0.0, min(100.0, kingdom.stability + delta))
        return kingdom.stability

    def adjust_legitimacy(self, kingdom_id: int, delta: float) -> float:
        kingdom = KingdomLibrary.get(kingdom_id)
        if kingdom is None:
            return 0.0
        kingdom.legitimacy = max(0.0, min(100.0, kingdom.legitimacy + delta))
        return kingdom.legitimacy

    # ---------- war & diplomacy ----------

    def declare_war(self, attacker_id: int, defender_id: int,
                    current_tick: float = 0.0) -> bool:
        attacker = KingdomLibrary.get(attacker_id)
        defender = KingdomLibrary.get(defender_id)
        if attacker is None or defender is None:
            return False
        if defender_id in attacker.at_war_with:
            return False
        attacker.at_war_with.append(defender_id)
        defender.at_war_with.append(attacker_id)
        attacker.stability = max(0, attacker.stability - 5)
        defender.stability = max(0, defender.stability - 5)
        attacker.history.append(f"Tick {current_tick:.0f}: Declared war on {defender.name}.")
        defender.history.append(f"Tick {current_tick:.0f}: Attacked by {attacker.name}.")
        return True

    def make_peace(self, kingdom_a: int, kingdom_b: int,
                   current_tick: float = 0.0) -> bool:
        a = KingdomLibrary.get(kingdom_a)
        b = KingdomLibrary.get(kingdom_b)
        if a is None or b is None:
            return False
        if kingdom_b in a.at_war_with:
            a.at_war_with.remove(kingdom_b)
        if kingdom_a in b.at_war_with:
            b.at_war_with.remove(kingdom_a)
        a.history.append(f"Tick {current_tick:.0f}: Made peace with {b.name}.")
        b.history.append(f"Tick {current_tick:.0f}: Made peace with {a.name}.")
        return True

    def form_alliance(self, kingdom_a: int, kingdom_b: int,
                      current_tick: float = 0.0) -> bool:
        a = KingdomLibrary.get(kingdom_a)
        b = KingdomLibrary.get(kingdom_b)
        if a is None or b is None:
            return False
        if kingdom_b not in a.alliances:
            a.alliances.append(kingdom_b)
        if kingdom_a not in b.alliances:
            b.alliances.append(kingdom_a)
        a.history.append(f"Tick {current_tick:.0f}: Allied with {b.name}.")
        b.history.append(f"Tick {current_tick:.0f}: Allied with {a.name}.")
        return True

    def annex_territory(self, kingdom_id: int, territory_id: int) -> bool:
        kingdom = KingdomLibrary.get(kingdom_id)
        territory = self._territories.get(territory_id)
        if kingdom is None or territory is None:
            return False
        # Remove from previous owner
        for other in KingdomLibrary.all():
            if territory_id in other.territories and other.id != kingdom_id:
                other.territories.remove(territory_id)
                other.stability = max(0, other.stability - 10)
        if territory_id not in kingdom.territories:
            kingdom.territories.append(territory_id)
        territory.is_contested = False
        territory.contested_by = None
        return True

    # ---------- simulation ----------

    def update(self, dt_months: float, current_tick: float = 0.0) -> None:
        """Advance kingdom simulation."""
        for kingdom in KingdomLibrary.all():
            # Tax income
            income = int(kingdom.population * kingdom.tax_rate * 0.5 * dt_months)
            kingdom.treasury += income
            # Stability drifts toward legitimacy
            target = kingdom.legitimacy
            kingdom.stability += (target - kingdom.stability) * 0.01 * dt_months
            # Random events
            if self.rng.chance(0.001 * dt_months):
                # Rebellion chance
                if kingdom.stability < 30:
                    kingdom.stability = max(0, kingdom.stability - 10)
                    kingdom.history.append(
                        f"Tick {current_tick:.0f}: Rebellion erupts! Stability drops."
                    )
            # Ruler death from old age
            if kingdom.ruler_id is not None:
                ruler = self._politicians.get(kingdom.ruler_id)
                if ruler is not None:
                    age = current_tick - ruler.birth_tick
                    # Convert ticks to years: assume 1 year = 365*20*10 = 73000 ticks
                    age_years = age / 73000.0
                    if age_years > 70 and self.rng.chance(0.01 * dt_months):
                        self.on_ruler_death(kingdom.id, current_tick)

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "territories": {str(tid): t.to_dict() for tid, t in self._territories.items()},
            "politicians": {str(pid): p.to_dict() for pid, p in self._politicians.items()},
            "elections": [
                {"election_id": e.election_id, "kingdom_id": e.kingdom_id,
                 "candidates": e.candidates, "votes": {str(k): v for k, v in e.votes.items()},
                 "winner_id": e.winner_id, "started_tick": e.started_tick,
                 "ended_tick": e.ended_tick, "is_active": e.is_active}
                for e in self._elections
            ],
            "next_territory_id": self._next_territory_id,
            "next_politician_id": self._next_politician_id,
            "next_election_id": self._next_election_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KingdomSystem":
        sys = cls()
        sys._territories = {
            int(tid): Territory.from_dict(t) for tid, t in data.get("territories", {}).items()
        }
        sys._politicians = {
            int(pid): Politician.from_dict(p) for pid, p in data.get("politicians", {}).items()
        }
        sys._elections = [
            Election(
                election_id=e["election_id"], kingdom_id=e["kingdom_id"],
                candidates=e.get("candidates", []),
                votes={int(k): v for k, v in e.get("votes", {}).items()},
                winner_id=e.get("winner_id"), started_tick=e.get("started_tick", 0.0),
                ended_tick=e.get("ended_tick"), is_active=e.get("is_active", False),
            )
            for e in data.get("elections", [])
        ]
        sys._next_territory_id = data.get("next_territory_id", 1)
        sys._next_politician_id = data.get("next_politician_id", 1)
        sys._next_election_id = data.get("next_election_id", 1)
        return sys


# ---------- Default kingdoms ----------

DEFAULT_KINGDOMS: list[Kingdom] = [
    Kingdom(
        id=0, name="Kingdom of Aldor", description="The principal human kingdom of the central plains.",
        color=33, kingdom_type=KingdomType.MONARCHY, succession_law=SuccessionLaw.PRIMOGENITURE,
        founded_tick=0.0, population=50000, treasury=500000, tax_rate=0.15,
        military_strength=2000, stability=70.0, prestige=60.0, legitimacy=80.0,
        technology_level=4, culture="aldorian", state_religion="light",
        official_language="common", laws={"theft": 5, "murder": 10, "treason": 10},
        tags=["human", "civilized"],
    ),
    Kingdom(
        id=0, name="Dwarven Confederation of Khazad",
        description="A confederation of mountain-holds ruled by a council of thanes.",
        color=130, kingdom_type=KingdomType.CONFEDERATION, succession_law=SuccessionLaw.ELECTION,
        founded_tick=0.0, population=15000, treasury=800000, tax_rate=0.10,
        military_strength=1500, stability=85.0, prestige=70.0, legitimacy=75.0,
        technology_level=6, culture="dwarven", state_religion="ancestors",
        official_language="dwarven", laws={"theft": 8, "murder": 10},
        tags=["dwarven", "mountain"],
    ),
    Kingdom(
        id=0, name="Sylvan Realm of the Elves",
        description="An ancient elven kingdom hidden within the deep forests.",
        color=41, kingdom_type=KingdomType.MONARCHY, succession_law=SuccessionLaw.MATRILINEAL,
        founded_tick=0.0, population=8000, treasury=300000, tax_rate=0.05,
        military_strength=800, stability=90.0, prestige=85.0, legitimacy=95.0,
        technology_level=7, culture="elven", state_religion="nature",
        official_language="sylvan", laws={"deforestation": 10},
        tags=["elven", "forest", "magical"],
    ),
    Kingdom(
        id=0, name="Tribal Lands of the Steppes",
        description="Nomadic horse-lord tribes united under a Great Khan.",
        color=215, kingdom_type=KingdomType.TRIBAL, succession_law=SuccessionLaw.TANISTRY,
        founded_tick=0.0, population=20000, treasury=100000, tax_rate=0.08,
        military_strength=3000, stability=60.0, prestige=50.0, legitimacy=55.0,
        technology_level=2, culture="steppe_nomad", state_religion="sky_spirits",
        official_language="steppe", tags=["human", "nomadic"],
    ),
    Kingdom(
        id=0, name="Theocratic State of Sunholme",
        description="A theocracy ruled by the high priests of the Sun God.",
        color=215, kingdom_type=KingdomType.THEOCRACY, succession_law=SuccessionLaw.ELECTION,
        founded_tick=0.0, population=25000, treasury=200000, tax_rate=0.20,
        military_strength=1200, stability=65.0, prestige=70.0, legitimacy=70.0,
        technology_level=4, culture="sunholme", state_religion="sun_god",
        official_language="common", laws={"heresy": 10, "necromancy": 10},
        tags=["human", "religious"],
    ),
    Kingdom(
        id=0, name="Free City of Mercadia",
        description="A wealthy merchant republic on the southern coast.",
        color=202, kingdom_type=KingdomType.REPUBLIC, succession_law=SuccessionLaw.ELECTION,
        founded_tick=0.0, population=35000, treasury=1500000, tax_rate=0.12,
        military_strength=2000, stability=75.0, prestige=80.0, legitimacy=70.0,
        technology_level=5, culture="mercantile", state_religion="fortune",
        official_language="common", laws={"fraud": 7, "smuggling": 6},
        tags=["human", "merchant", "coastal"],
    ),
    Kingdom(
        id=0, name="Orcish Hordes of the Wastes",
        description="A loose confederation of orc clans from the eastern wastes.",
        color=64, kingdom_type=KingdomType.TRIBAL, succession_law=SuccessionLaw.MERITOCRATIC,
        founded_tick=0.0, population=40000, treasury=20000, tax_rate=0.05,
        military_strength=5000, stability=40.0, prestige=30.0, legitimacy=35.0,
        technology_level=2, culture="orcish", state_religion="war_god",
        official_language="orcish", tags=["orcish", "barbaric"],
    ),
    Kingdom(
        id=0, name="Undying Empire of Vec",
        description="A necromantic empire ruled by an ancient lich-king.",
        color=90, kingdom_type=KingdomType.EMPIRE, succession_law=SuccessionLaw.PRIMOGENITURE,
        founded_tick=0.0, population=100000, treasury=400000, tax_rate=0.25,
        military_strength=8000, stability=50.0, prestige=60.0, legitimacy=40.0,
        technology_level=5, culture="undead", state_religion="vec",
        official_language="common", laws={"necromancy": 0, "life_magic": 10},
        tags=["undead", "magical", "evil"],
    ),
]
