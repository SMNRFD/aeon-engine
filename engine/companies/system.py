"""Companies and guilds — economic organisations.

Companies are profit-driven organisations that own assets, employ workers,
and produce goods. Guilds are craft/skill-based organisations that regulate
their members' profession.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


class CompanyType(IntEnum):
    MERCHANT = 0
    MINING = 1
    SMITHING = 2
    FORESTRY = 3
    FISHING = 4
    FARMING = 5
    SHIPPING = 6
    BANKING = 7
    MERCENARY = 8
    BUILDING = 9
    ALCHEMICAL = 10
    TEXTILE = 11
    BREWING = 12
    QUARRYING = 13
    TRANSPORT = 14


@dataclass
class CompanyMember:
    """A member of a company."""

    entity_id: int
    role: str = "worker"  # owner, manager, worker, apprentice
    salary_copper_per_month: int = 50
    joined_tick: float = 0.0
    skill_bonus: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id, "role": self.role,
            "salary_copper_per_month": self.salary_copper_per_month,
            "joined_tick": self.joined_tick, "skill_bonus": self.skill_bonus,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompanyMember":
        return cls(
            entity_id=data["entity_id"], role=data.get("role", "worker"),
            salary_copper_per_month=data.get("salary_copper_per_month", 50),
            joined_tick=data.get("joined_tick", 0.0),
            skill_bonus=data.get("skill_bonus", 0.0),
        )


@dataclass
class Company:
    """A trading or production company."""

    company_id: int
    name: str
    company_type: CompanyType
    owner_id: Optional[int] = None
    founded_tick: float = 0.0
    members: list[CompanyMember] = field(default_factory=list)
    treasury: int = 0
    assets: dict[str, int] = field(default_factory=dict)  # asset_id -> count
    monthly_revenue: int = 0
    monthly_expenses: int = 0
    reputation: float = 0.0  # -100..100
    market_share: float = 0.0  # 0..1
    headquarters: Optional[tuple[int, int]] = None
    locations: list[tuple[int, int]] = field(default_factory=list)
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def add_member(self, member: CompanyMember) -> None:
        # Replace existing membership for the same entity
        self.members = [m for m in self.members if m.entity_id != member.entity_id]
        self.members.append(member)

    def remove_member(self, entity_id: int) -> None:
        self.members = [m for m in self.members if m.entity_id != entity_id]

    def member_count(self) -> int:
        return len(self.members)

    def monthly_profit(self) -> int:
        return self.monthly_revenue - self.monthly_expenses

    def to_dict(self) -> dict[str, Any]:
        return {
            "company_id": self.company_id, "name": self.name,
            "company_type": int(self.company_type),
            "owner_id": self.owner_id, "founded_tick": self.founded_tick,
            "members": [m.to_dict() for m in self.members],
            "treasury": self.treasury, "assets": dict(self.assets),
            "monthly_revenue": self.monthly_revenue,
            "monthly_expenses": self.monthly_expenses,
            "reputation": self.reputation, "market_share": self.market_share,
            "headquarters": self.headquarters,
            "locations": [list(l) for l in self.locations],
            "description": self.description, "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Company":
        return cls(
            company_id=data["company_id"], name=data["name"],
            company_type=CompanyType(data.get("company_type", 0)),
            owner_id=data.get("owner_id"),
            founded_tick=data.get("founded_tick", 0.0),
            members=[CompanyMember.from_dict(m) for m in data.get("members", [])],
            treasury=data.get("treasury", 0),
            assets=dict(data.get("assets", {})),
            monthly_revenue=data.get("monthly_revenue", 0),
            monthly_expenses=data.get("monthly_expenses", 0),
            reputation=data.get("reputation", 0.0),
            market_share=data.get("market_share", 0.0),
            headquarters=tuple(data["headquarters"]) if data.get("headquarters") else None,
            locations=[tuple(l) for l in data.get("locations", [])],
            description=data.get("description", ""),
            tags=list(data.get("tags", [])),
        )


@dataclass
class GuildMember:
    """A member of a craft guild."""

    entity_id: int
    rank: str = "apprentice"  # apprentice, journeyman, master, guildmaster
    joined_tick: float = 0.0
    skill_level: int = 0
    dues_paid: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id, "rank": self.rank,
            "joined_tick": self.joined_tick, "skill_level": self.skill_level,
            "dues_paid": self.dues_paid,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GuildMember":
        return cls(
            entity_id=data["entity_id"], rank=data.get("rank", "apprentice"),
            joined_tick=data.get("joined_tick", 0.0),
            skill_level=data.get("skill_level", 0),
            dues_paid=data.get("dues_paid", 0),
        )


@dataclass
class Guild:
    """A craft or trade guild."""

    guild_id: int
    name: str
    skill_id: str
    description: str = ""
    founded_tick: float = 0.0
    members: list[GuildMember] = field(default_factory=list)
    treasury: int = 0
    monthly_dues: int = 50
    headquarters: Optional[tuple[int, int]] = None
    requirements: dict[str, int] = field(default_factory=dict)
    benefits: list[str] = field(default_factory=list)
    reputation: float = 0.0

    def add_member(self, member: GuildMember) -> None:
        self.members = [m for m in self.members if m.entity_id != member.entity_id]
        self.members.append(member)

    def to_dict(self) -> dict[str, Any]:
        return {
            "guild_id": self.guild_id, "name": self.name,
            "skill_id": self.skill_id, "description": self.description,
            "founded_tick": self.founded_tick,
            "members": [m.to_dict() for m in self.members],
            "treasury": self.treasury, "monthly_dues": self.monthly_dues,
            "headquarters": self.headquarters,
            "requirements": dict(self.requirements),
            "benefits": list(self.benefits),
            "reputation": self.reputation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Guild":
        return cls(
            guild_id=data["guild_id"], name=data["name"],
            skill_id=data["skill_id"], description=data.get("description", ""),
            founded_tick=data.get("founded_tick", 0.0),
            members=[GuildMember.from_dict(m) for m in data.get("members", [])],
            treasury=data.get("treasury", 0),
            monthly_dues=data.get("monthly_dues", 50),
            headquarters=tuple(data["headquarters"]) if data.get("headquarters") else None,
            requirements=dict(data.get("requirements", {})),
            benefits=list(data.get("benefits", [])),
            reputation=data.get("reputation", 0.0),
        )


@dataclass
class Employment:
    """An employment record."""

    employer_id: int  # company_id
    employee_id: int  # entity_id
    role: str = "worker"
    salary_copper_per_month: int = 50
    hired_tick: float = 0.0
    contract_months: int = 12
    is_active: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "employer_id": self.employer_id, "employee_id": self.employee_id,
            "role": self.role, "salary_copper_per_month": self.salary_copper_per_month,
            "hired_tick": self.hired_tick, "contract_months": self.contract_months,
            "is_active": self.is_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Employment":
        return cls(**data)


class CompanySystem:
    """Manages companies, guilds, and employment."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._companies: dict[int, Company] = {}
        self._guilds: dict[int, Guild] = {}
        self._employments: list[Employment] = []
        self._next_company_id: int = 1
        self._next_guild_id: int = 1
        self._init_defaults()

    def _init_defaults(self) -> None:
        for c in DEFAULT_COMPANIES:
            c.company_id = self._next_company_id
            self._next_company_id += 1
            self._companies[c.company_id] = c
        for g in DEFAULT_GUILDS:
            g.guild_id = self._next_guild_id
            self._next_guild_id += 1
            self._guilds[g.guild_id] = g

    def create_company(self, name: str, company_type: CompanyType,
                       owner_id: Optional[int] = None,
                       current_tick: float = 0.0,
                       **kwargs: Any) -> Company:
        company = Company(
            company_id=self._next_company_id, name=name,
            company_type=company_type, owner_id=owner_id,
            founded_tick=current_tick, **kwargs,
        )
        self._next_company_id += 1
        self._companies[company.company_id] = company
        return company

    def create_guild(self, name: str, skill_id: str,
                     current_tick: float = 0.0,
                     **kwargs: Any) -> Guild:
        guild = Guild(
            guild_id=self._next_guild_id, name=name,
            skill_id=skill_id, founded_tick=current_tick, **kwargs,
        )
        self._next_guild_id += 1
        self._guilds[guild.guild_id] = guild
        return guild

    def employ(self, company_id: int, entity_id: int, role: str = "worker",
               salary: int = 50, contract_months: int = 12,
               current_tick: float = 0.0) -> Optional[Employment]:
        company = self._companies.get(company_id)
        if company is None:
            return None
        employment = Employment(
            employer_id=company_id, employee_id=entity_id, role=role,
            salary_copper_per_month=salary, hired_tick=current_tick,
            contract_months=contract_months,
        )
        self._employments.append(employment)
        company.add_member(CompanyMember(
            entity_id=entity_id, role=role,
            salary_copper_per_month=salary, joined_tick=current_tick,
        ))
        return employment

    def fire(self, company_id: int, entity_id: int) -> bool:
        company = self._companies.get(company_id)
        if company is None:
            return False
        company.remove_member(entity_id)
        for e in self._employments:
            if e.employer_id == company_id and e.employee_id == entity_id and e.is_active:
                e.is_active = False
        return True

    def update(self, dt_months: float) -> None:
        """Process monthly payroll."""
        for company in self._companies.values():
            payroll = sum(m.salary_copper_per_month for m in company.members)
            company.monthly_expenses = payroll
            company.treasury += int(company.monthly_revenue * dt_months)
            company.treasury -= int(payroll * dt_months)
        for guild in self._guilds.values():
            dues = sum(guild.monthly_dues for _ in guild.members)
            guild.treasury += int(dues * dt_months)

    def companies(self) -> list[Company]:
        return list(self._companies.values())

    def guilds(self) -> list[Guild]:
        return list(self._guilds.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "companies": {str(cid): c.to_dict() for cid, c in self._companies.items()},
            "guilds": {str(gid): g.to_dict() for gid, g in self._guilds.items()},
            "employments": [e.to_dict() for e in self._employments],
            "next_company_id": self._next_company_id,
            "next_guild_id": self._next_guild_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompanySystem":
        sys = cls()
        sys._companies = {
            int(cid): Company.from_dict(c) for cid, c in data.get("companies", {}).items()
        }
        sys._guilds = {
            int(gid): Guild.from_dict(g) for gid, g in data.get("guilds", {}).items()
        }
        sys._employments = [Employment.from_dict(e) for e in data.get("employments", [])]
        sys._next_company_id = data.get("next_company_id", 1)
        sys._next_guild_id = data.get("next_guild_id", 1)
        return sys


DEFAULT_COMPANIES: list[Company] = [
    Company(
        company_id=0, name="Aldor Trading Company",
        company_type=CompanyType.MERCHANT,
        treasury=200000, monthly_revenue=8000, monthly_expenses=3000,
        reputation=40.0, market_share=0.15,
        description="The largest trading company in Aldor.",
        tags=["human", "merchant"],
    ),
    Company(
        company_id=0, name="Khazad Mining Cooperative",
        company_type=CompanyType.MINING,
        treasury=500000, monthly_revenue=12000, monthly_expenses=5000,
        reputation=60.0, market_share=0.30,
        description="A dwarven mining cooperative that controls most iron ore.",
        tags=["dwarven", "mining"],
    ),
    Company(
        company_id=0, name="Sylvan Forestry Guild",
        company_type=CompanyType.FORESTRY,
        treasury=80000, monthly_revenue=4000, monthly_expenses=1500,
        reputation=70.0, market_share=0.20,
        description="An elven forestry collective.",
        tags=["elven", "forestry"],
    ),
    Company(
        company_id=0, name="Mercadia Bank",
        company_type=CompanyType.BANKING,
        treasury=2000000, monthly_revenue=20000, monthly_expenses=8000,
        reputation=80.0, market_share=0.40,
        description="The most powerful bank in the southern coast.",
        tags=["human", "banking"],
    ),
    Company(
        company_id=0, name="Crimson Sail Shipping",
        company_type=CompanyType.SHIPPING,
        treasury=300000, monthly_revenue=15000, monthly_expenses=7000,
        reputation=50.0, market_share=0.25,
        description="A maritime shipping company.",
        tags=["human", "shipping"],
    ),
    Company(
        company_id=0, name="Iron Brotherhood Mercenaries",
        company_type=CompanyType.MERCENARY,
        treasury=150000, monthly_revenue=10000, monthly_expenses=6000,
        reputation=60.0, market_share=0.20,
        description="A renowned mercenary company.",
        tags=["dwarven", "military"],
    ),
]


DEFAULT_GUILDS: list[Guild] = [
    Guild(
        guild_id=0, name="Smiths' Guild", skill_id="smithing",
        treasury=50000, monthly_dues=100,
        requirements={"smithing": 5},
        benefits=["workshop_access", "discount_materials", "guild_quests"],
        reputation=70.0,
        description="The guild of master smiths.",
    ),
    Guild(
        guild_id=0, name="Mages' Conclave", skill_id="evocation",
        treasury=200000, monthly_dues=200,
        requirements={"evocation": 10},
        benefits=["library_access", "spell_research", "discount_reagents"],
        reputation=80.0,
        description="The guild of arcane scholars.",
    ),
    Guild(
        guild_id=0, name="Merchants' Guild", skill_id="barter",
        treasury=300000, monthly_dues=150,
        requirements={"barter": 5},
        benefits=["trade_routes", "market_access", "loans"],
        reputation=75.0,
        description="The powerful merchants' guild.",
    ),
    Guild(
        guild_id=0, name="Thieves' Guild", skill_id="stealth",
        treasury=80000, monthly_dues=50,
        requirements={"stealth": 10},
        benefits=["fence_access", "black_market", "safe_houses"],
        reputation=-30.0,
        description="A secret guild of thieves and rogues.",
    ),
    Guild(
        guild_id=0, name="Healers' Circle", skill_id="first_aid",
        treasury=60000, monthly_dues=80,
        requirements={"first_aid": 5},
        benefits=["herb_access", "clinic_access", "training"],
        reputation=85.0,
        description="A guild of healers and herbalists.",
    ),
    Guild(
        guild_id=0, name="Hunters' Lodge", skill_id="hunting",
        treasury=40000, monthly_dues=60,
        requirements={"hunting": 5},
        benefits=["hunting_grounds", "furs_market", "training"],
        reputation=60.0,
        description="A lodge of hunters and trackers.",
    ),
]
