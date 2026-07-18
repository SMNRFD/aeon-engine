"""Life simulation — birth, marriage, children, death, inheritance, education, careers.

Each NPC has a LifeSimulator that tracks their life stage, family ties,
education, career, and major life events. The simulator advances over
time, triggering events at appropriate ages.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import (
    Identity, Race, Stats, Wealth, Personality, Health, Relationships,
)
from engine.utils.rng import RNG


class LifeStage(IntEnum):
    INFANT = 0       # 0-3
    CHILD = 1        # 4-12
    TEEN = 2         # 13-17
    YOUNG_ADULT = 3  # 18-25
    ADULT = 4        # 26-50
    MIDDLE_AGED = 5  # 51-65
    ELDER = 6        # 66-80
    ANCIENT = 7      # 80+

    @property
    def label(self) -> str:
        return ["Infant", "Child", "Teen", "Young Adult",
                "Adult", "Middle-Aged", "Elder", "Ancient"][self]

    @classmethod
    def for_age(cls, age: int) -> "LifeStage":
        if age < 4: return cls.INFANT
        if age < 13: return cls.CHILD
        if age < 18: return cls.TEEN
        if age < 26: return cls.YOUNG_ADULT
        if age < 51: return cls.ADULT
        if age < 66: return cls.MIDDLE_AGED
        if age < 80: return cls.ELDER
        return cls.ANCIENT


@dataclass
class FamilyMember:
    """A reference to a family member."""

    entity_id: int
    relation: str  # "father", "mother", "spouse", "child", "sibling", "grandparent"
    name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"entity_id": self.entity_id, "relation": self.relation, "name": self.name}

    @classmethod
    def from_dict(cls, data: dict) -> "FamilyMember":
        return cls(entity_id=data["entity_id"], relation=data["relation"],
                   name=data.get("name", ""))


@dataclass
class Family:
    """A family unit."""

    family_id: int
    surname: str = ""
    members: list[FamilyMember] = field(default_factory=list)
    home_location: Optional[tuple[int, int]] = None
    wealth_class: str = "commoner"  # peasant, commoner, merchant, noble, royal
    founded_tick: float = 0.0
    lineage: list[int] = field(default_factory=list)  # ancestor entity_ids

    def add_member(self, member: FamilyMember) -> None:
        # Avoid duplicates
        for m in self.members:
            if m.entity_id == member.entity_id and m.relation == member.relation:
                return
        self.members.append(member)

    def remove_member(self, entity_id: int) -> None:
        self.members = [m for m in self.members if m.entity_id != entity_id]

    def get_relation(self, entity_id: int) -> Optional[str]:
        for m in self.members:
            if m.entity_id == entity_id:
                return m.relation
        return None

    def relatives(self, relation: str) -> list[int]:
        return [m.entity_id for m in self.members if m.relation == relation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id, "surname": self.surname,
            "members": [m.to_dict() for m in self.members],
            "home_location": self.home_location,
            "wealth_class": self.wealth_class,
            "founded_tick": self.founded_tick,
            "lineage": list(self.lineage),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Family":
        return cls(
            family_id=data["family_id"],
            surname=data.get("surname", ""),
            members=[FamilyMember.from_dict(m) for m in data.get("members", [])],
            home_location=tuple(data["home_location"]) if data.get("home_location") else None,
            wealth_class=data.get("wealth_class", "commoner"),
            founded_tick=data.get("founded_tick", 0.0),
            lineage=list(data.get("lineage", [])),
        )


@dataclass
class Marriage:
    """A marriage between two entities."""

    spouse_a: int
    spouse_b: int
    married_tick: float
    location: Optional[tuple[int, int]] = None
    children_ids: list[int] = field(default_factory=list)
    divorced: bool = False
    divorced_tick: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "spouse_a": self.spouse_a, "spouse_b": self.spouse_b,
            "married_tick": self.married_tick, "location": self.location,
            "children_ids": list(self.children_ids),
            "divorced": self.divorced, "divorced_tick": self.divorced_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Marriage":
        return cls(
            spouse_a=data["spouse_a"], spouse_b=data["spouse_b"],
            married_tick=data["married_tick"],
            location=tuple(data["location"]) if data.get("location") else None,
            children_ids=list(data.get("children_ids", [])),
            divorced=data.get("divorced", False),
            divorced_tick=data.get("divorced_tick"),
        )


@dataclass
class LifeEvent:
    """A major life event."""

    kind: str  # "birth", "marriage", "childbirth", "divorce", "death",
               # "education_started", "education_completed", "job_started",
               # "job_lost", "promotion", "house_bought", "migration",
               # "crime_committed", "crime_victimised", "war_conscripted",
               # "war_returned", "religious_conversion"
    tick: float
    description: str = ""
    involved_entities: list[int] = field(default_factory=list)
    location: Optional[tuple[int, int]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "tick": self.tick, "description": self.description,
            "involved_entities": list(self.involved_entities),
            "location": self.location,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LifeEvent":
        return cls(
            kind=data["kind"], tick=data["tick"],
            description=data.get("description", ""),
            involved_entities=list(data.get("involved_entities", [])),
            location=tuple(data["location"]) if data.get("location") else None,
        )


@dataclass
class Inheritance:
    """An inheritance passed on death."""

    deceased_id: int
    heirs: list[tuple[int, float]] = field(default_factory=list)  # (heir_id, fraction)
    items: list[int] = field(default_factory=list)
    gold: int = 0
    silver: int = 0
    copper: int = 0
    distributed: bool = False

    def distribute(self, world: World) -> None:
        """Distribute wealth among heirs proportionally."""
        if self.distributed:
            return
        for heir_id, fraction in self.heirs:
            heir = Entity(id=heir_id, generation=0)
            # Find the actual entity
            for ent in list(world._components.keys()):
                if ent.id == heir_id:
                    heir = ent
                    break
            wealth = world.get_component(heir, Wealth)
            if wealth is None:
                wealth = Wealth()
                world.add_component(heir, wealth)
            wealth.gold += int(self.gold * fraction)
            wealth.silver += int(self.silver * fraction)
            wealth.copper += int(self.copper * fraction)
        self.distributed = True


# ---------- Education ----------

@dataclass
class EducationSystem:
    """Tracks education and skills acquired through formal study."""

    school_id: str
    name: str
    location: Optional[tuple[int, int]] = None
    specialties: list[str] = field(default_factory=list)  # skill ids
    tuition_copper: int = 1000
    min_age: int = 7
    max_age: int = 25
    duration_years: float = 4.0
    reputation: float = 0.0  # -100..100

    def can_enroll(self, age: int) -> bool:
        return self.min_age <= age <= self.max_age


# ---------- Job Market ----------

@dataclass
class JobPosting:
    """A job posting in the world."""

    job_id: int
    title: str
    employer_id: Optional[int] = None  # faction_id or entity_id
    faction_id: Optional[int] = None
    location: Optional[tuple[int, int]] = None
    salary_copper_per_month: int = 0
    required_skills: dict[str, int] = field(default_factory=dict)
    required_level: int = 1
    description: str = ""
    filled: bool = False
    holder_id: Optional[int] = None
    posted_tick: float = 0.0


class JobMarket:
    """A job market tracking open positions and applications."""

    def __init__(self) -> None:
        self._postings: dict[int, JobPosting] = {}
        self._next_id: int = 1

    def post(self, posting: JobPosting) -> JobPosting:
        if posting.job_id == 0:
            posting.job_id = self._next_id
            self._next_id += 1
        else:
            self._next_id = max(self._next_id, posting.job_id + 1)
        self._postings[posting.job_id] = posting
        return posting

    def available(self, skill_levels: dict[str, int],
                  level: int) -> list[JobPosting]:
        out: list[JobPosting] = []
        for p in self._postings.values():
            if p.filled:
                continue
            if p.required_level > level:
                continue
            ok = all(skill_levels.get(s, 0) >= v
                     for s, v in p.required_skills.items())
            if ok:
                out.append(p)
        return out

    def apply(self, posting_id: int, applicant_id: int) -> bool:
        posting = self._postings.get(posting_id)
        if posting is None or posting.filled:
            return False
        posting.filled = True
        posting.holder_id = applicant_id
        return True

    def all(self) -> list[JobPosting]:
        return list(self._postings.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "next_id": self._next_id,
            "postings": {str(pid): p.__dict__ for pid, p in self._postings.items()},
        }


# ---------- Life Simulator ----------

class LifeSimulator:
    """Per-entity life simulator."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._families: dict[int, Family] = {}
        self._marriages: list[Marriage] = []
        self._events: dict[int, list[LifeEvent]] = {}  # entity_id -> events
        self._next_family_id: int = 1
        self.job_market = JobMarket()
        self.schools: dict[str, EducationSystem] = {}
        self._init_default_schools()

    def _init_default_schools(self) -> None:
        self.schools = {
            "academy_of_arcana": EducationSystem(
                "academy_of_arcana", "Academy of Arcana",
                specialties=["arcana", "evocation", "alchemy"],
                tuition_copper=5000, duration_years=6.0,
            ),
            "war_college": EducationSystem(
                "war_college", "War College",
                specialties=["swordsmanship", "tactics", "leadership"],
                tuition_copper=3000, duration_years=4.0,
            ),
            "merchants_guild_school": EducationSystem(
                "merchants_guild_school", "Merchants' Guild School",
                specialties=["barter", "appraisal", "history"],
                tuition_copper=1500, duration_years=3.0,
            ),
            "temple_seminary": EducationSystem(
                "temple_seminary", "Temple Seminary",
                specialties=["religion", "medicine", "persuasion"],
                tuition_copper=800, duration_years=5.0,
            ),
            "craftsman_apprentice": EducationSystem(
                "craftsman_apprentice", "Craftsman Apprenticeship",
                specialties=["smithing", "tailoring", "woodworking"],
                tuition_copper=200, duration_years=7.0, min_age=10,
            ),
        }

    # ---------- families ----------

    def create_family(self, founder: Entity, surname: str,
                      wealth_class: str = "commoner",
                      current_tick: float = 0.0) -> Family:
        family = Family(
            family_id=self._next_family_id,
            surname=surname,
            wealth_class=wealth_class,
            founded_tick=current_tick,
        )
        family.lineage.append(founder.id)
        self._next_family_id += 1
        self._families[family.family_id] = family
        return family

    def family_of(self, entity_id: int) -> Optional[Family]:
        for fam in self._families.values():
            if any(m.entity_id == entity_id for m in fam.members):
                return fam
        return None

    def add_family_member(self, family_id: int, member: FamilyMember) -> None:
        fam = self._families.get(family_id)
        if fam is not None:
            fam.add_member(member)

    # ---------- marriage ----------

    def can_marry(self, world: World, entity: Entity) -> bool:
        race = world.get_component(entity, Race)
        if race is None or race.age < 18:
            return False
        # Already married?
        for m in self._marriages:
            if (m.spouse_a == entity.id or m.spouse_b == entity.id) and not m.divorced:
                return False
        return True

    def marry(self, world: World, spouse_a: Entity, spouse_b: Entity,
              current_tick: float = 0.0,
              location: Optional[tuple[int, int]] = None) -> Optional[Marriage]:
        if not self.can_marry(world, spouse_a) or not self.can_marry(world, spouse_b):
            return None
        marriage = Marriage(
            spouse_a=spouse_a.id, spouse_b=spouse_b.id,
            married_tick=current_tick, location=location,
        )
        self._marriages.append(marriage)
        self._record_event(spouse_a.id, LifeEvent(
            "marriage", current_tick,
            f"Married entity #{spouse_b.id}.",
            involved_entities=[spouse_a.id, spouse_b.id],
            location=location,
        ))
        self._record_event(spouse_b.id, LifeEvent(
            "marriage", current_tick,
            f"Married entity #{spouse_a.id}.",
            involved_entities=[spouse_a.id, spouse_b.id],
            location=location,
        ))
        # Update relationship component
        for ent in [spouse_a, spouse_b]:
            rel = world.get_component(ent, Relationships)
            if rel is None:
                rel = Relationships()
                world.add_component(ent, rel)
        rel_a = world.get_component(spouse_a, Relationships)
        rel_b = world.get_component(spouse_b, Relationships)
        if rel_a: rel_a.relations[spouse_b.id] = 1.0
        if rel_b: rel_b.relations[spouse_a.id] = 1.0
        return marriage

    def divorce(self, world: World, marriage: Marriage,
                current_tick: float = 0.0) -> None:
        marriage.divorced = True
        marriage.divorced_tick = current_tick
        self._record_event(marriage.spouse_a, LifeEvent(
            "divorce", current_tick,
            f"Divorced entity #{marriage.spouse_b}.",
        ))
        self._record_event(marriage.spouse_b, LifeEvent(
            "divorce", current_tick,
            f"Divorced entity #{marriage.spouse_a}.",
        ))

    def marriage_of(self, entity_id: int) -> Optional[Marriage]:
        for m in self._marriages:
            if (m.spouse_a == entity_id or m.spouse_b == entity_id) and not m.divorced:
                return m
        return None

    # ---------- childbirth ----------

    def birth_child(self, world: World, parent_a: Entity, parent_b: Entity,
                    child: Entity, current_tick: float = 0.0) -> None:
        marriage = self.marriage_of(parent_a.id)
        if marriage:
            marriage.children_ids.append(child.id)
        # Add to family
        family = self.family_of(parent_a.id) or self.family_of(parent_b.id)
        if family:
            surname = family.surname
            family.add_member(FamilyMember(
                entity_id=child.id, relation="child", name=surname,
            ))
        self._record_event(child.id, LifeEvent(
            "birth", current_tick,
            f"Born to parents {parent_a.id} and {parent_b.id}.",
            involved_entities=[parent_a.id, parent_b.id, child.id],
        ))
        # Parents get a "childbirth" event too
        self._record_event(parent_a.id, LifeEvent(
            "childbirth", current_tick,
            f"Had a child (entity #{child.id}).",
            involved_entities=[child.id],
        ))
        self._record_event(parent_b.id, LifeEvent(
            "childbirth", current_tick,
            f"Had a child (entity #{child.id}).",
            involved_entities=[child.id],
        ))
        # Inherit some stats from parents
        stats_a = world.get_component(parent_a, Stats)
        stats_b = world.get_component(parent_b, Stats)
        child_stats = world.get_component(child, Stats)
        if stats_a and stats_b and child_stats:
            for attr in ("strength", "agility", "endurance", "intelligence",
                         "willpower", "charisma", "perception", "luck"):
                parent_avg = (getattr(stats_a, attr) + getattr(stats_b, attr)) / 2
                mutated = parent_avg + self.rng.gauss(0, 1.5)
                setattr(child_stats, attr, max(3, int(mutated)))

    # ---------- death & inheritance ----------

    def on_death(self, world: World, deceased: Entity,
                 current_tick: float = 0.0) -> Optional[Inheritance]:
        """Process death: distribute wealth to heirs, dissolve marriage."""
        inheritance: Optional[Inheritance] = None
        wealth = world.get_component(deceased, Wealth)
        if wealth:
            # Determine heirs: spouse gets 50%, children split remainder.
            heirs: list[tuple[int, float]] = []
            marriage = self.marriage_of(deceased.id)
            if marriage:
                spouse_id = (marriage.spouse_b if marriage.spouse_a == deceased.id
                             else marriage.spouse_a)
                heirs.append((spouse_id, 0.5))
            # Children
            child_ids = marriage.children_ids if marriage else []
            child_share = 0.5 / max(1, len(child_ids))
            for cid in child_ids:
                heirs.append((cid, child_share))
            inheritance = Inheritance(
                deceased_id=deceased.id,
                heirs=heirs,
                gold=wealth.gold, silver=wealth.silver, copper=wealth.copper,
            )
            inheritance.distribute(world)
        # End marriage
        if marriage:
            marriage.divorced = True
            marriage.divorced_tick = current_tick
        # Remove from family
        family = self.family_of(deceased.id)
        if family:
            family.remove_member(deceased.id)
        # Record death event
        self._record_event(deceased.id, LifeEvent(
            "death", current_tick, "Died.",
        ))
        return inheritance

    # ---------- events ----------

    def _record_event(self, entity_id: int, event: LifeEvent) -> None:
        self._events.setdefault(entity_id, []).append(event)
        if len(self._events[entity_id]) > 100:
            self._events[entity_id] = self._events[entity_id][-100:]

    def events_of(self, entity_id: int) -> list[LifeEvent]:
        return list(self._events.get(entity_id, []))

    # ---------- simulation ----------

    def update(self, world: World, dt_years: float, current_tick: float = 0.0) -> None:
        """Advance the life of all entities with Race components."""
        for entity, (race, identity) in world.view(Race, Identity):
            old_age = race.age
            race.age += dt_years
            new_stage = LifeStage.for_age(int(race.age))
            old_stage = LifeStage.for_age(int(old_age))
            if new_stage != old_stage:
                self._record_event(entity.id, LifeEvent(
                    "life_stage", current_tick,
                    f"Entered {new_stage.label} stage ({int(race.age)} years old).",
                ))
            # Death by old age
            if race.age >= race.max_age:
                health = world.get_component(entity, Health)
                if health:
                    health.current = 0
                self.on_death(world, entity, current_tick)
            # Random death chance for elders
            elif race.age > 60 and self.rng.chance(0.0005 * dt_years * (race.age - 60)):
                health = world.get_component(entity, Health)
                if health:
                    health.current = 0
                self.on_death(world, entity, current_tick)

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "families": {str(fid): f.to_dict() for fid, f in self._families.items()},
            "marriages": [m.to_dict() for m in self._marriages],
            "events": {str(eid): [e.to_dict() for e in evts]
                       for eid, evts in self._events.items()},
            "next_family_id": self._next_family_id,
            "job_market": self.job_market.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LifeSimulator":
        sim = cls()
        sim._families = {
            int(fid): Family.from_dict(f) for fid, f in data.get("families", {}).items()
        }
        sim._marriages = [Marriage.from_dict(m) for m in data.get("marriages", [])]
        sim._events = {
            int(eid): [LifeEvent.from_dict(e) for e in evts]
            for eid, evts in data.get("events", {}).items()
        }
        sim._next_family_id = data.get("next_family_id", 1)
        return sim
