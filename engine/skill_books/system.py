"""Skill books — read to learn skills, discover new ones.

Books provide XP to specific skills when read:
* Skill Books — grant XP in a specific skill
* Spell Tomes — teach a specific spell
* Recipe Books — unlock crafting recipes
* Technique Manuals — teach combat techniques
* Bestiaries — reveal creature weaknesses
* Maps — reveal locations

Books have:
* Required skill level to understand
* Reading time (in-game hours)
* XP granted on completion
* One-time use (consumed or memorized)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.utils.rng import RNG


class BookType(IntEnum):
    SKILL_BOOK = 0       # grants XP to a skill
    SPELL_TOME = 1       # teaches a spell
    RECIPE_BOOK = 2      # unlocks recipes
    TECHNIQUE_MANUAL = 3 # combat technique
    BESTIARY = 4         # creature info
    MAP = 5              # reveals locations
    LORE = 6             # story/background
    ENCYCLOPEDIA = 7     # general knowledge


@dataclass
class SkillBook:
    """A book definition."""

    book_id: str
    title: str
    author: str = "Unknown"
    book_type: BookType = BookType.SKILL_BOOK
    description: str = ""
    skill_id: str = ""
    skill_xp_grant: int = 100
    required_skill_level: int = 0  # to understand the book
    reading_time_hours: float = 4.0
    is_consumable: bool = True  # consumed after reading
    is_repeatable: bool = False  # can be read multiple times
    spell_taught: Optional[str] = None  # for spell tomes
    recipe_taught: Optional[str] = None  # for recipe books
    pages: int = 100
    language: str = "common"
    rarity: float = 0.3  # 0=common, 1=very rare
    value_copper: int = 50
    color: int = 215
    glyph: str = "≡"
    content_preview: str = ""  # first few lines
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["book_type"] = int(self.book_type)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SkillBook":
        d = dict(data)
        d["book_type"] = BookType(d.get("book_type", 0))
        return cls(**d)


class SkillBookLibrary:
    """Registry of all books."""

    _books: ClassVar[dict[str, SkillBook]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, book: SkillBook) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._books[book.book_id] = book

    @classmethod
    def get(cls, book_id: str) -> Optional[SkillBook]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._books.get(book_id)

    @classmethod
    def all(cls) -> list[SkillBook]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._books.values())

    @classmethod
    def by_skill(cls, skill_id: str) -> list[SkillBook]:
        return [b for b in cls.all() if b.skill_id == skill_id]

    @classmethod
    def by_type(cls, book_type: BookType) -> list[SkillBook]:
        return [b for b in cls.all() if b.book_type == book_type]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for b in DEFAULT_BOOKS:
            cls._books[b.book_id] = b
        cls._defaults_loaded = True


class BookReadingSystem:
    """Manages reading books and applying their effects."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        # entity_id -> set of book_ids already read
        self._read_books: dict[int, set[str]] = {}
        # entity_id -> currently reading (book_id, progress_hours)
        self._currently_reading: dict[int, tuple[str, float]] = {}

    def start_reading(self, entity: Entity, book: SkillBook) -> tuple[bool, str]:
        """An entity starts reading a book."""
        # Check if already read
        if book.book_id in self._read_books.get(entity.id, set()):
            if not book.is_repeatable:
                return False, "You've already read this book."
        # Check skill requirement
        # (Would look up entity's skill level here)
        self._currently_reading[entity.id] = (book.book_id, 0.0)
        return True, f"You begin reading '{book.title}'."

    def update_reading(self, entity: Entity, dt_hours: float) -> Optional[dict[str, Any]]:
        """Advance reading progress. Returns completion info if finished."""
        if entity.id not in self._currently_reading:
            return None
        book_id, progress = self._currently_reading[entity.id]
        book = SkillBookLibrary.get(book_id)
        if book is None:
            del self._currently_reading[entity.id]
            return None
        progress += dt_hours
        if progress >= book.reading_time_hours:
            # Finished!
            del self._currently_reading[entity.id]
            self._read_books.setdefault(entity.id, set()).add(book_id)
            return self._apply_book_effects(entity, book)
        self._currently_reading[entity.id] = (book_id, progress)
        return {
            "book_id": book_id,
            "progress": progress / book.reading_time_hours,
            "remaining_hours": book.reading_time_hours - progress,
        }

    def _apply_book_effects(self, entity: Entity, book: SkillBook) -> dict[str, Any]:
        """Apply the effects of finishing a book."""
        result: dict[str, Any] = {
            "book_id": book.book_id,
            "title": book.title,
            "completed": True,
        }
        if book.book_type == BookType.SKILL_BOOK and book.skill_id:
            result["skill_id"] = book.skill_id
            result["xp_granted"] = book.skill_xp_grant
            # In production, would call engine.skills.add_xp(...)
        elif book.book_type == BookType.SPELL_TOME and book.spell_taught:
            result["spell_learned"] = book.spell_taught
        elif book.book_type == BookType.RECIPE_BOOK and book.recipe_taught:
            result["recipe_learned"] = book.recipe_taught
        elif book.book_type == BookType.BESTIARY:
            result["bestiary_unlocked"] = True
        elif book.book_type == BookType.MAP:
            result["locations_revealed"] = True
        return result

    def get_progress(self, entity: Entity) -> Optional[dict[str, Any]]:
        if entity.id not in self._currently_reading:
            return None
        book_id, progress = self._currently_reading[entity.id]
        book = SkillBookLibrary.get(book_id)
        if book is None:
            return None
        return {
            "book_id": book_id,
            "title": book.title,
            "progress": progress / book.reading_time_hours,
            "remaining_hours": book.reading_time_hours - progress,
        }

    def has_read(self, entity: Entity, book_id: str) -> bool:
        return book_id in self._read_books.get(entity.id, set())

    def books_read(self, entity: Entity) -> set[str]:
        return set(self._read_books.get(entity.id, set()))


class SkillDiscoverySystem:
    """Manages procedural skill discovery.

Characters can discover new skills through:
* Random inspiration (low chance per skill use)
* Reaching milestones in related skills
* Combining two skills at high levels
* Studying under a master
* Reading ancient texts
* Achieving specific feats
"""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._discoveries: dict[int, list[dict[str, Any]]] = {}  # entity_id -> discoveries
        self._inspiration_chance = 0.001  # per skill use
        self._milestone_levels = [10, 25, 50, 75, 100]
        # Skill combinations that yield new skills
        self._combinations: list[tuple[str, str, str]] = [
            ("smithing", "enchanting", "rune_carving"),
            ("alchemy", "evocation", "potion_mastery"),
            ("stealth", "archery", "sniper"),
            ("swordsmanship", "dodge", "fencing"),
            ("unarmed", "acrobatics", "martial_arts"),
            ("cooking", "alchemy", "gourmet"),
            ("engineering", "magic", "artificing"),
            ("necromancy", "enchantment", "soul_magic"),
        ]

    def check_inspiration(self, entity: Entity, skill_id: str,
                          skill_level: int) -> Optional[str]:
        """Check if entity gets inspired to learn a new skill."""
        if not self.rng.chance(self._inspiration_chance):
            return None
        # Inspiration can reveal a related skill
        discovered = self._discover_related_skill(skill_id, skill_level)
        if discovered:
            self._record_discovery(entity, "inspiration", skill_id, discovered)
            return discovered
        return None

    def check_milestone(self, entity: Entity, skill_id: str,
                         new_level: int) -> Optional[str]:
        """Check if reaching a milestone level unlocks a new skill."""
        if new_level not in self._milestone_levels:
            return None
        # Higher milestones unlock rarer skills
        if new_level == 10:
            discovered = self._discover_basic_skill(skill_id)
        elif new_level == 25:
            discovered = self._discover_advanced_skill(skill_id)
        elif new_level == 50:
            discovered = self._discover_master_skill(skill_id)
        elif new_level == 75:
            discovered = self._discover_legendary_skill(skill_id)
        else:  # 100
            discovered = self._discover_mythic_skill(skill_id)
        if discovered:
            self._record_discovery(entity, "milestone", skill_id, discovered,
                                    milestone=new_level)
            return discovered
        return None

    def check_combination(self, entity: Entity, skill_a: str, level_a: int,
                          skill_b: str, level_b: int) -> Optional[str]:
        """Check if combining two high-level skills unlocks a new skill."""
        if level_a < 25 or level_b < 25:
            return None
        for sa, sb, result in self._combinations:
            if (sa == skill_a and sb == skill_b) or (sa == skill_b and sb == skill_a):
                self._record_discovery(entity, "combination",
                                        f"{skill_a}+{skill_b}", result)
                return result
        return None

    def _discover_related_skill(self, skill_id: str, level: int) -> Optional[str]:
        """Discover a skill related to the one being used."""
        related: dict[str, list[str]] = {
            "swordsmanship": ["parry", "dodge", "tactics"],
            "archery": ["fletching", "tracking", "stealth"],
            "smithing": ["mining", "enchanting", "engineering"],
            "alchemy": ["foraging", "medicine", "cooking"],
            "evocation": ["mana_control", "abjuration", "divination"],
            "stealth": ["trapping", "deception", "archery"],
        }
        options = related.get(skill_id, [])
        if not options:
            return None
        return self.rng.choice(options)

    def _discover_basic_skill(self, skill_id: str) -> Optional[str]:
        basic_unlocks: dict[str, str] = {
            "swordsmanship": "parry",
            "archery": "fletching",
            "smithing": "mining",
            "alchemy": "foraging",
        }
        return basic_unlocks.get(skill_id)

    def _discover_advanced_skill(self, skill_id: str) -> Optional[str]:
        advanced_unlocks: dict[str, str] = {
            "swordsmanship": "tactics",
            "archery": "tracking",
            "smithing": "engineering",
            "alchemy": "medicine",
            "evocation": "mana_control",
        }
        return advanced_unlocks.get(skill_id)

    def _discover_master_skill(self, skill_id: str) -> Optional[str]:
        master_unlocks: dict[str, str] = {
            "swordsmanship": "weapon_master",
            "archery": "sniper",
            "smithing": "artificing",
            "alchemy": "transmutation_mastery",
        }
        return master_unlocks.get(skill_id)

    def _discover_legendary_skill(self, skill_id: str) -> Optional[str]:
        legendary_unlocks: dict[str, str] = {
            "swordsmanship": "blade_saint",
            "archery": "eagle_eye",
            "smithing": "legendary_smithing",
        }
        return legendary_unlocks.get(skill_id)

    def _discover_mythic_skill(self, skill_id: str) -> Optional[str]:
        mythic_unlocks: dict[str, str] = {
            "swordsmanship": "swordsmanship_transcendence",
            "evocation": "archmage_evocation",
            "necromancy": "lichdom",
        }
        return mythic_unlocks.get(skill_id)

    def _record_discovery(self, entity: Entity, discovery_type: str,
                           source: str, discovered: str,
                           milestone: Optional[int] = None) -> None:
        record = {
            "type": discovery_type,
            "source": source,
            "discovered": discovered,
            "milestone": milestone,
        }
        self._discoveries.setdefault(entity.id, []).append(record)

    def discoveries_of(self, entity: Entity) -> list[dict[str, Any]]:
        return list(self._discoveries.get(entity.id, []))


# ---------- Default books ----------

DEFAULT_BOOKS: list[SkillBook] = [
    SkillBook("book_swordsmanship_basic", "The Way of the Blade",
              "Sir Aldric the Elder", BookType.SKILL_BOOK,
              "A foundational text on swordsmanship.",
              skill_id="swordsmanship", skill_xp_grant=100,
              required_skill_level=0, reading_time_hours=4.0,
              value_copper=100, color=130, glyph="≡",
              tags=["combat", "beginner"]),
    SkillBook("book_swordsmanship_advanced", "Master of Blades",
              "Master Kael", BookType.SKILL_BOOK,
              "Advanced techniques for the seasoned swordsman.",
              skill_id="swordsmanship", skill_xp_grant=300,
              required_skill_level=20, reading_time_hours=8.0,
              value_copper=500, rarity=0.5, color=215, glyph="≡",
              tags=["combat", "advanced"]),
    SkillBook("tome_fireball", "Tome of Fireball",
              "Archmage Velindra", BookType.SPELL_TOME,
              "Teaches the fireball spell.",
              skill_id="evocation", skill_xp_grant=50,
              required_skill_level=5, reading_time_hours=2.0,
              spell_taught="fireball",
              value_copper=1000, rarity=0.6, color=196, glyph="†",
              tags=["magic", "spell"]),
    SkillBook("tome_lightning_bolt", "Tome of Lightning Bolt",
              "Archmage Velindra", BookType.SPELL_TOME,
              "Teaches the lightning bolt spell.",
              skill_id="evocation", skill_xp_grant=50,
              required_skill_level=10, reading_time_hours=2.0,
              spell_taught="lightning_bolt",
              value_copper=1500, rarity=0.7, color=165, glyph="†",
              tags=["magic", "spell"]),
    SkillBook("book_smithing_basic", "The Smith's Companion",
              "Master Smith Dorin", BookType.SKILL_BOOK,
              "A guide to basic smithing techniques.",
              skill_id="smithing", skill_xp_grant=100,
              required_skill_level=0, reading_time_hours=4.0,
              value_copper=150, color=130, glyph="≡",
              tags=["craft", "beginner"]),
    SkillBook("book_alchemy_basic", "Herbalist's Primer",
              "Old Mother Marsh", BookType.SKILL_BOOK,
              "An introduction to alchemy and potion-making.",
              skill_id="alchemy", skill_xp_grant=100,
              required_skill_level=0, reading_time_hours=4.0,
              value_copper=120, color=41, glyph="≡",
              tags=["magic", "beginner"]),
    SkillBook("bestiary_common", "Bestiary of Common Beasts",
              "Scholar Penwick", BookType.BESTIARY,
              "A catalog of common creatures and their weaknesses.",
              skill_id="nature", skill_xp_grant=50,
              required_skill_level=0, reading_time_hours=6.0,
              value_copper=200, color=114, glyph="≡",
              tags=["knowledge"]),
    SkillBook("book_stealth_arts", "The Shadow's Art",
              "Unknown", BookType.SKILL_BOOK,
              "Techniques of stealth and subterfuge.",
              skill_id="stealth", skill_xp_grant=150,
              required_skill_level=5, reading_time_hours=5.0,
              value_copper=300, rarity=0.4, color=90, glyph="≡",
              tags=["rogue", "intermediate"]),
    SkillBook("book_history_aldor", "History of the Aldor Kingdom",
              "Court Historian Bramwell", BookType.LORE,
              "A comprehensive history of the kingdom.",
              skill_id="history", skill_xp_grant=100,
              required_skill_level=0, reading_time_hours=10.0,
              value_copper=80, color=130, glyph="≡",
              tags=["knowledge", "lore"]),
    SkillBook("recipe_smithing_advanced", "Advanced Smithing Recipes",
              "Master Smith Dorin", BookType.RECIPE_BOOK,
              "Unlock advanced smithing recipes.",
              skill_id="smithing", skill_xp_grant=50,
              required_skill_level=15, reading_time_hours=3.0,
              recipe_taught="steel_longsword",
              value_copper=400, rarity=0.5, color=215, glyph="≡",
              tags=["craft", "recipe"]),
    SkillBook("map_ancient_ruins", "Map to the Ancient Ruins",
              "Explorer's Guild", BookType.MAP,
              "Reveals the location of ancient ruins.",
              skill_id="navigation", skill_xp_grant=50,
              required_skill_level=0, reading_time_hours=1.0,
              value_copper=500, rarity=0.6, color=75, glyph=" mapa",
              tags=["exploration"]),
    SkillBook("book_arcana_advanced", "Principles of Arcane Theory",
              "Archmage Velindra", BookType.SKILL_BOOK,
              "Deep theory of magical principles.",
              skill_id="arcana", skill_xp_grant=200,
              required_skill_level=10, reading_time_hours=8.0,
              value_copper=400, rarity=0.5, color=165, glyph="≡",
              tags=["magic", "knowledge"]),
    SkillBook("tome_heal", "Tome of Healing",
              "High Priest Aldous", BookType.SPELL_TOME,
              "Teaches the heal spell.",
              skill_id="abjuration", skill_xp_grant=50,
              required_skill_level=3, reading_time_hours=2.0,
              spell_taught="heal",
              value_copper=800, rarity=0.5, color=41, glyph="†",
              tags=["magic", "spell", "healing"]),
    SkillBook("book_cooking_arts", "The Culinary Arts",
              "Chef Marcello", BookType.SKILL_BOOK,
              "A guide to fine cooking.",
              skill_id="cooking", skill_xp_grant=100,
              required_skill_level=0, reading_time_hours=3.0,
              value_copper=80, color=215, glyph="≡",
              tags=["craft", "beginner"]),
    SkillBook("book_engineering_basic", "Principles of Engineering",
              "Engineer Thelma", BookType.SKILL_BOOK,
              "Foundations of mechanical engineering.",
              skill_id="engineering", skill_xp_grant=100,
              required_skill_level=0, reading_time_hours=6.0,
              value_copper=200, color=244, glyph="≡",
              tags=["craft", "knowledge"]),
]
