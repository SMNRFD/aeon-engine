"""Content pack system — asset, sound, localization, AI, UI, kingdom, economy packs.

A content pack is a bundle of related content:
* Asset Pack — textures, sprites, models (for future graphical modes)
* Sound Pack — sound effects and music
* Localization Pack — translation strings
* AI Pack — AI behavior scripts and parameters
* UI Pack — UI themes, layouts, fonts
* Kingdom Pack — predefined kingdoms and politicians
* Economy Pack — trade goods, market configs, companies
* Biome Pack — biome definitions
* Magic Pack — spells, schools, runes
* Weapon Pack — weapon archetypes and affixes
* Monster Pack — creature definitions
* Item Pack — item archetypes and materials
* Skill Pack — skill definitions
* Story Pack — quests and dialogue trees
* NPC Pack — predefined NPCs
* Quest Pack — quest definitions

Each pack has metadata and can depend on other packs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntFlag
from pathlib import Path
from typing import Any, ClassVar, Optional

from engine.core.logging import get_logger


log = get_logger("content_packs")


class ContentPackType(IntFlag):
    ASSET = 1 << 0
    SOUND = 1 << 1
    LOCALIZATION = 1 << 2
    AI = 1 << 3
    UI = 1 << 4
    KINGDOM = 1 << 5
    ECONOMY = 1 << 6
    BIOME = 1 << 7
    MAGIC = 1 << 8
    WEAPON = 1 << 9
    MONSTER = 1 << 10
    ITEM = 1 << 11
    SKILL = 1 << 12
    STORY = 1 << 13
    NPC = 1 << 14
    QUEST = 1 << 15
    FACTION = 1 << 16
    RECIPE = 1 << 17
    DUNGEON = 1 << 18
    STRUCTURE = 1 << 19
    DISEASE = 1 << 20
    ANIMAL = 1 << 21
    SPELL = 1 << 22
    RUNE = 1 << 23
    ARTIFACT = 1 << 24


@dataclass
class ContentPack:
    """A content pack definition."""

    pack_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = "MIT"
    pack_types: ContentPackType = ContentPackType(0)
    dependencies: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    path: Optional[Path] = None
    is_loaded: bool = False
    load_error: Optional[str] = None
    content: dict[str, Any] = field(default_factory=dict)
    # content is keyed by content type:
    # "items" -> list of item defs
    # "creatures" -> list of creature defs
    # "spells" -> list of spell defs
    # "skills" -> list of skill defs
    # etc.

    @property
    def pack_type_names(self) -> list[str]:
        names = []
        for t in ContentPackType:
            if self.pack_types & t:
                names.append(t.name.lower())
        return names

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id, "name": self.name,
            "version": self.version, "description": self.description,
            "author": self.author, "license": self.license,
            "pack_types": int(self.pack_types),
            "dependencies": list(self.dependencies),
            "conflicts": list(self.conflicts),
            "tags": list(self.tags),
            "path": str(self.path) if self.path else None,
            "is_loaded": self.is_loaded,
            "load_error": self.load_error,
        }


class ContentPackRegistry:
    """Registry of all known content packs."""

    def __init__(self) -> None:
        self._packs: dict[str, ContentPack] = {}

    def register(self, pack: ContentPack) -> None:
        self._packs[pack.pack_id] = pack

    def unregister(self, pack_id: str) -> Optional[ContentPack]:
        return self._packs.pop(pack_id, None)

    def get(self, pack_id: str) -> Optional[ContentPack]:
        return self._packs.get(pack_id)

    def all(self) -> list[ContentPack]:
        return list(self._packs.values())

    def loaded(self) -> list[ContentPack]:
        return [p for p in self._packs.values() if p.is_loaded]

    def by_type(self, pack_type: ContentPackType) -> list[ContentPack]:
        return [p for p in self._packs.values() if p.pack_types & pack_type]

    def __len__(self) -> int:
        return len(self._packs)

    def __contains__(self, pack_id: str) -> bool:
        return pack_id in self._packs


class ContentPackManager:
    """Discovers, loads, and applies content packs."""

    def __init__(self, packs_dir: str = "content_packs") -> None:
        self.packs_dir = Path(packs_dir)
        self.registry = ContentPackRegistry()
        self._applied_count: int = 0

    def discover(self) -> int:
        """Discover content packs in the packs directory."""
        if not self.packs_dir.exists():
            return 0
        count = 0
        for entry in sorted(self.packs_dir.iterdir()):
            if entry.is_file() and entry.suffix in (".json", ".yaml", ".yml", ".toml"):
                if self._load_manifest(entry):
                    count += 1
            elif entry.is_dir() and (entry / "pack.toml").exists():
                if self._load_manifest(entry / "pack.toml"):
                    count += 1
            elif entry.is_dir() and (entry / "pack.json").exists():
                if self._load_manifest(entry / "pack.json"):
                    count += 1
        return count

    def _load_manifest(self, path: Path) -> bool:
        try:
            if path.suffix == ".toml":
                import tomllib
                with path.open("rb") as f:
                    data = tomllib.load(f)
            elif path.suffix == ".yaml" or path.suffix == ".yml":
                try:
                    import yaml
                    data = yaml.safe_load(path.read_text(encoding="utf-8"))
                except ImportError:
                    log.warning("YAML support requires PyYAML")
                    return False
            else:
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
            pack = ContentPack(
                pack_id=data.get("pack_id", path.stem),
                name=data.get("name", path.stem),
                version=str(data.get("version", "0.0.1")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                license=data.get("license", "MIT"),
                pack_types=ContentPackType(
                    sum(ContentPackType[t.upper()] for t in data.get("pack_types", []))
                ) if data.get("pack_types") else ContentPackType(0),
                dependencies=list(data.get("dependencies", [])),
                conflicts=list(data.get("conflicts", [])),
                tags=list(data.get("tags", [])),
                path=path.parent if path.is_file() else path,
                content=data.get("content", {}),
            )
            self.registry.register(pack)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load content pack %s: %s", path, exc)
            return False

    def apply_all(self, engine: Any) -> dict[str, int]:
        """Apply all loaded content packs to the engine."""
        counts: dict[str, int] = {}
        for pack in self.registry.all():
            if not pack.content:
                continue
            for content_type, items in pack.content.items():
                if not isinstance(items, list):
                    continue
                for item_data in items:
                    self._apply_item(engine, content_type, item_data)
                    counts[content_type] = counts.get(content_type, 0) + 1
            pack.is_loaded = True
            self._applied_count += 1
        return counts

    def _apply_item(self, engine: Any, content_type: str, data: dict) -> None:
        """Apply a single content item."""
        try:
            if content_type == "items":
                from engine.items.generator import ARCHETYPES, BaseItemArchetype
                archetype_id = data.get("archetype") or data.get("id")
                if archetype_id and archetype_id not in ARCHETYPES:
                    ARCHETYPES[archetype_id] = BaseItemArchetype(
                        base_type=archetype_id,
                        name=data.get("name", archetype_id),
                        category=data.get("category", "misc"),
                        weight_kg=data.get("weight", 1.0),
                        volume_l=data.get("volume", 1.0),
                        base_value=data.get("value", 10),
                        durability=data.get("durability", 100),
                        icon=data.get("icon", "?"),
                        color=data.get("color", 244),
                    )
            elif content_type == "creatures":
                from engine.animals.system import AnimalLibrary, AnimalSpecies, AnimalType
                species_id = data.get("id")
                if species_id and not AnimalLibrary.get(species_id):
                    AnimalLibrary.register(AnimalSpecies(
                        id=species_id,
                        name=data.get("name", species_id),
                        animal_type=AnimalType[data.get("animal_type", "PREDATOR").upper()],
                        base_hp=data.get("hp", 20),
                        base_strength=data.get("strength", 8),
                        base_agility=data.get("agility", 10),
                        glyph=data.get("glyph", "a"),
                        color=data.get("color", 244),
                        description=data.get("description", ""),
                    ))
            elif content_type == "spells":
                from engine.magic.spells import Spell, SpellLibrary, SpellTarget
                spell_id = data.get("id")
                if spell_id and not SpellLibrary.get(spell_id):
                    SpellLibrary.register(Spell(
                        id=spell_id, name=data.get("name", spell_id),
                        school_id=data.get("school", "evocation"),
                        description=data.get("description", ""),
                        mana_cost=data.get("mana_cost", 20),
                        target=SpellTarget(data.get("target", "enemy")),
                    ))
            elif content_type == "skills":
                from engine.skills.system import Skill, SkillLibrary
                skill_id = data.get("id")
                if skill_id and not SkillLibrary.get(skill_id):
                    SkillLibrary.register(Skill(
                        id=skill_id, name=data.get("name", skill_id),
                        description=data.get("description", ""),
                        category=data.get("category", "knowledge"),
                        governing_attribute=data.get("governing_attribute", "intelligence"),
                    ))
            elif content_type == "recipes":
                from engine.crafting.system import Recipe, RecipeLibrary
                recipe_id = data.get("id")
                if recipe_id and not RecipeLibrary.get(recipe_id):
                    RecipeLibrary.register(Recipe(
                        id=recipe_id, name=data.get("name", recipe_id),
                        skill_id=data.get("skill", "smithing"),
                        skill_level_required=data.get("level_required", 1),
                        result_archetype=data.get("result_archetype", ""),
                        materials=data.get("materials", {}),
                    ))
            elif content_type == "themes":
                from engine.themes.system import Theme, ThemeLibrary
                theme_name = data.get("name")
                if theme_name and not ThemeLibrary.get(theme_name):
                    ThemeLibrary.register(Theme(
                        name=theme_name,
                        description=data.get("description", ""),
                        colors=data.get("colors", {}),
                        is_dark=data.get("is_dark", True),
                    ))
            elif content_type == "sounds":
                from engine.audio.system import SoundEffect, AudioLibrary
                sound_id = data.get("id")
                if sound_id and not AudioLibrary.get(sound_id):
                    AudioLibrary.register(SoundEffect(
                        id=sound_id,
                        name=data.get("name", sound_id),
                        description=data.get("description", ""),
                        onomatopoeia=data.get("onomatopoeia", ""),
                        category=data.get("category", "sfx"),
                    ))
            elif content_type == "localization":
                from engine.localization.i18n import I18n
                locale = data.get("locale", "en_US")
                strings = data.get("strings", {})
                I18n().add_strings(locale, strings)
            elif content_type == "diseases":
                from engine.survival.system import Disease, DiseaseLibrary
                disease_id = data.get("id")
                if disease_id and not DiseaseLibrary.get(disease_id):
                    DiseaseLibrary.register(Disease(
                        id=disease_id,
                        name=data.get("name", disease_id),
                        description=data.get("description", ""),
                        base_duration=data.get("duration", 86400),
                        severity=data.get("severity", 3.0),
                        damage_per_tick=data.get("damage_per_tick", 0.1),
                    ))
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not apply %s item: %s", content_type, exc)

    def applied_count(self) -> int:
        return self._applied_count
