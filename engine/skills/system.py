"""Skill catalog, XP, decay, training, and skill checks."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Skills as SkillsComponent, SkillLevel
from engine.utils.rng import RNG


@dataclass
class Skill:
    """A skill definition."""

    id: str
    name: str
    description: str
    category: str          # combat, magic, craft, social, survival, knowledge
    governing_attribute: str  # strength, agility, intelligence, etc.
    difficulty: float = 1.0   # higher = harder to advance
    base_xp: int = 100        # XP to reach level 1
    max_level: int = 100
    decay_rate: float = 0.0001  # XP lost per tick when not used
    tags: list[str] = field(default_factory=list)


@dataclass
class SkillCheckResult:
    success: bool
    roll: float
    difficulty: float
    margin: float
    critical: bool = False
    botch: bool = False


class SkillLibrary:
    """Registry of skill definitions."""

    _skills: ClassVar[dict[str, Skill]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, skill: Skill) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._skills[skill.id] = skill

    @classmethod
    def get(cls, skill_id: str) -> Optional[Skill]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._skills.get(skill_id)

    @classmethod
    def all(cls) -> list[Skill]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._skills.values())

    @classmethod
    def by_category(cls, category: str) -> list[Skill]:
        return [s for s in cls.all() if s.category == category]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for s in DEFAULT_SKILLS:
            cls._skills[s.id] = s
        cls._defaults_loaded = True


def xp_for_level(level: int, base: int = 100, difficulty: float = 1.0) -> int:
    return int(base * (level ** 1.5) * difficulty)


class SkillsSystem:
    """Manages skill progression."""

    def __init__(self) -> None:
        self._last_used: dict[tuple[int, str], float] = {}

    def get_level(self, entity: Entity, skill_id: str) -> int:
        comp = self._get_comp(entity)
        if comp is None:
            return 0
        sl = comp.skills.get(skill_id)
        return sl.level if sl else 0

    def add_xp(self, entity: Entity, skill_id: str, xp: float, world: World) -> int:
        comp = self._get_comp(entity)
        if comp is None:
            comp = SkillsComponent()
            world.add_component(entity, comp)
        sl = comp.skills.get(skill_id)
        if sl is None:
            sl = SkillLevel(level=0, xp=0.0)
            comp.skills[skill_id] = sl
        sl.xp += xp
        skill = SkillLibrary.get(skill_id)
        if skill is None:
            return sl.level
        leveled = 0
        while sl.level < skill.max_level:
            needed = xp_for_level(sl.level + 1, skill.base_xp, skill.difficulty)
            if sl.xp >= needed:
                sl.xp -= needed
                sl.level += 1
                leveled += 1
            else:
                break
        return sl.level

    def check(self, entity: Entity, skill_id: str, difficulty: float,
              rng: Optional[RNG] = None) -> SkillCheckResult:
        rng = rng or RNG()
        level = self.get_level(entity, skill_id)
        roll = rng.uniform(0, 100) + level
        margin = roll - difficulty
        crit = roll > 95
        botch = roll < 5
        return SkillCheckResult(
            success=margin >= 0 or crit,
            roll=roll, difficulty=difficulty, margin=margin,
            critical=crit, botch=botch,
        )

    def decay(self, world: World, dt: float) -> None:
        for entity, (comp,) in world.view(SkillsComponent):
            for skill_id, sl in comp.skills.items():
                if sl.level <= 0:
                    continue
                skill = SkillLibrary.get(skill_id)
                if skill is None:
                    continue
                sl.xp -= skill.decay_rate * dt
                if sl.xp < -xp_for_level(sl.level, skill.base_xp, skill.difficulty) * 0.5:
                    sl.level = max(0, sl.level - 1)
                    sl.xp = 0.0

    def train(self, entity: Entity, skill_id: str, teacher_level: int,
              hours: float, world: World) -> int:
        xp_gain = teacher_level * hours * 10
        return self.add_xp(entity, skill_id, xp_gain, world)

    def _get_comp(self, entity: Entity) -> Optional[SkillsComponent]:
        return None


DEFAULT_SKILLS: list[Skill] = [
    # Combat
    Skill("swordsmanship", "Swordsmanship", "Sword and blade weapons.",
          "combat", "agility", 1.0, 100, 100),
    Skill("archery", "Archery", "Bows and crossbows.", "combat", "agility", 1.1, 120, 100),
    Skill("polearms", "Polearms", "Spears, halberds, pikes.", "combat", "strength", 1.0, 100, 100),
    Skill("maces", "Maces & Hammers", "Crushing weapons.", "combat", "strength", 1.0, 100, 100),
    Skill("axes", "Axes", "Axes and cleavers.", "combat", "strength", 1.0, 100, 100),
    Skill("unarmed", "Unarmed", "Brawling and grappling.", "combat", "agility", 0.9, 80, 100),
    Skill("dodge", "Dodge", "Avoiding blows.", "combat", "agility", 1.0, 100, 100),
    Skill("block", "Block", "Blocking with shields.", "combat", "endurance", 1.0, 100, 100),
    Skill("parry", "Parry", "Deflecting attacks.", "combat", "agility", 1.1, 110, 100),
    Skill("tactics", "Tactics", "Battlefield command.", "combat", "intelligence", 1.2, 150, 100),
    Skill("throwing", "Throwing", "Throwing weapons and objects.", "combat", "agility", 1.0, 100, 100),

    # Magic
    Skill("evocation", "Evocation", "Energy and elemental magic.", "magic", "intelligence", 1.3, 150, 100),
    Skill("conjuration", "Conjuration", "Summoning creatures and objects.", "magic", "intelligence", 1.3, 150, 100),
    Skill("enchantment", "Enchantment", "Mind-affecting magic.", "magic", "willpower", 1.3, 150, 100),
    Skill("necromancy", "Necromancy", "Death and undead magic.", "magic", "willpower", 1.5, 200, 100),
    Skill("abjuration", "Abjuration", "Protective and warding magic.", "magic", "willpower", 1.2, 130, 100),
    Skill("transmutation", "Transmutation", "Changing matter.", "magic", "intelligence", 1.3, 150, 100),
    Skill("divination", "Divination", "Knowing and seeing.", "magic", "intelligence", 1.2, 130, 100),
    Skill("rune_carving", "Rune Carving", "Engraving magical runes.", "magic", "intelligence", 1.4, 180, 100),
    Skill("alchemy", "Alchemy", "Potion-brewing and reagents.", "magic", "intelligence", 1.2, 120, 100),
    Skill("mana_control", "Mana Control", "Efficient spellcasting.", "magic", "willpower", 1.2, 140, 100),

    # Crafting
    Skill("smithing", "Smithing", "Forging metal items.", "craft", "strength", 1.2, 130, 100),
    Skill("tailoring", "Tailoring", "Sewing cloth and leather.", "craft", "agility", 1.1, 120, 100),
    Skill("woodworking", "Woodworking", "Carving wood.", "craft", "agility", 1.1, 110, 100),
    Skill("masonry", "Masonry", "Working stone.", "craft", "strength", 1.2, 130, 100),
    Skill("jewelcraft", "Jewelcrafting", "Cutting gems and fine metals.", "craft", "agility", 1.3, 150, 100),
    Skill("enchanting", "Enchanting", "Imbuing items with magic.", "craft", "intelligence", 1.5, 200, 100),
    Skill("engineering", "Engineering", "Machines and mechanisms.", "craft", "intelligence", 1.3, 160, 100),
    Skill("cooking", "Cooking", "Preparing food.", "craft", "intelligence", 0.9, 80, 100),
    Skill("brewing", "Brewing", "Brewing beer, ale, and mead.", "craft", "intelligence", 1.0, 100, 100),
    Skill("fletching", "Fletching", "Making bows and arrows.", "craft", "agility", 1.1, 110, 100),

    # Social
    Skill("persuasion", "Persuasion", "Convincing others.", "social", "charisma", 1.1, 110, 100),
    Skill("intimidation", "Intimidation", "Threatening others.", "social", "strength", 1.0, 100, 100),
    Skill("deception", "Deception", "Lying and subterfuge.", "social", "charisma", 1.2, 120, 100),
    Skill("barter", "Barter", "Trading and haggling.", "social", "charisma", 1.0, 100, 100),
    Skill("leadership", "Leadership", "Commanding followers.", "social", "charisma", 1.3, 150, 100),
    Skill("performance", "Performance", "Music and acting.", "social", "charisma", 1.1, 110, 100),
    Skill("etiquette", "Etiquette", "Noble manners.", "social", "charisma", 1.1, 110, 100),

    # Survival
    Skill("foraging", "Foraging", "Finding wild food.", "survival", "perception", 1.0, 100, 100),
    Skill("hunting", "Hunting", "Tracking and killing game.", "survival", "perception", 1.1, 110, 100),
    Skill("tracking", "Tracking", "Following trails.", "survival", "perception", 1.1, 110, 100),
    Skill("fishing", "Fishing", "Catching fish.", "survival", "perception", 0.9, 80, 100),
    Skill("trapping", "Trapping", "Setting snares and traps.", "survival", "agility", 1.0, 100, 100),
    Skill("survival", "Survival", "General outdoors craft.", "survival", "endurance", 1.0, 100, 100),
    Skill("stealth", "Stealth", "Moving silently and unseen.", "survival", "agility", 1.1, 120, 100),
    Skill("fire_making", "Fire Making", "Starting and tending fires.", "survival", "perception", 0.8, 70, 100),
    Skill("navigation", "Navigation", "Finding your way.", "survival", "intelligence", 1.0, 100, 100),
    Skill("first_aid", "First Aid", "Field medicine.", "survival", "intelligence", 1.1, 110, 100),

    # Knowledge
    Skill("history", "History", "Knowledge of the past.", "knowledge", "intelligence", 1.0, 100, 100),
    Skill("religion", "Religion", "Gods and rituals.", "knowledge", "intelligence", 1.0, 100, 100),
    Skill("arcana", "Arcana", "Magical theory.", "knowledge", "intelligence", 1.2, 130, 100),
    Skill("nature", "Nature", "Plants, animals, and ecosystems.", "knowledge", "intelligence", 1.0, 100, 100),
    Skill("engineering_lore", "Engineering Lore", "Mechanical knowledge.", "knowledge", "intelligence", 1.1, 120, 100),
    Skill("law", "Law", "Legal systems.", "knowledge", "intelligence", 1.2, 130, 100),
    Skill("medicine", "Medicine", "Healing and anatomy.", "knowledge", "intelligence", 1.3, 150, 100),
    Skill("languages", "Languages", "Foreign tongues.", "knowledge", "intelligence", 1.1, 120, 100),
    Skill("appraisal", "Appraisal", "Valuing items.", "knowledge", "intelligence", 1.0, 100, 100),
    Skill("research", "Research", "Library and archives use.", "knowledge", "intelligence", 1.0, 100, 100),
]
