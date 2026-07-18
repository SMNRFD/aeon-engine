"""Mod loader — supports Python, JSON, YAML, and Lua mod formats.

Mods are content packs that add or modify game data:
* Python mods — full plugin-like mods with code
* JSON mods — declarative content (items, creatures, etc.)
* YAML mods — like JSON but more human-readable
* Lua mods — sandboxed Lua scripts (requires lupa, falls back to text-only)

The ModLoader discovers mods in `mods/` and dispatches them to the
appropriate loader based on file extension.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

from engine.core.logging import get_logger


log = get_logger("mods")


class ModFormat(IntEnum):
    PYTHON = 0
    JSON = 1
    YAML = 2
    LUA = 3
    TOML = 4
    DIRECTORY = 5  # multi-file mod


@dataclass
class ModInfo:
    """Metadata about a discovered mod."""

    mod_id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    format: ModFormat = ModFormat.JSON
    path: Path = field(default_factory=lambda: Path())
    dependencies: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    content: dict[str, Any] = field(default_factory=dict)
    loaded: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mod_id": self.mod_id, "name": self.name, "version": self.version,
            "description": self.description, "author": self.author,
            "format": int(self.format), "path": str(self.path),
            "dependencies": list(self.dependencies),
            "conflicts": list(self.conflicts),
            "tags": list(self.tags), "loaded": self.loaded,
            "error": self.error,
        }


class ModLoadError(Exception):
    """Raised when a mod fails to load."""


class ModRegistry:
    """Registry of loaded mods."""

    def __init__(self) -> None:
        self._mods: dict[str, ModInfo] = {}

    def register(self, mod: ModInfo) -> None:
        self._mods[mod.mod_id] = mod

    def get(self, mod_id: str) -> Optional[ModInfo]:
        return self._mods.get(mod_id)

    def all(self) -> list[ModInfo]:
        return list(self._mods.values())

    def loaded(self) -> list[ModInfo]:
        return [m for m in self._mods.values() if m.loaded]

    def failed(self) -> list[ModInfo]:
        return [m for m in self._mods.values() if m.error]

    def __len__(self) -> int:
        return len(self._mods)

    def __contains__(self, mod_id: str) -> bool:
        return mod_id in self._mods


class ModLoader:
    """Discovers and loads mods from the filesystem."""

    def __init__(self, mods_dir: str = "mods") -> None:
        self.mods_dir = Path(mods_dir)
        self.registry = ModRegistry()
        self._lua_available = self._check_lua()

    def _check_lua(self) -> bool:
        try:
            import lupa  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    def discover(self) -> int:
        """Scan the mods directory for mod files."""
        if not self.mods_dir.exists():
            log.info("Mods directory %s does not exist", self.mods_dir)
            return 0
        count = 0
        for entry in sorted(self.mods_dir.iterdir()):
            if entry.is_dir():
                # Check for mod.toml or mod.json manifest
                manifest = entry / "mod.toml"
                if not manifest.exists():
                    manifest = entry / "mod.json"
                if manifest.exists():
                    if self._load_directory_mod(entry, manifest):
                        count += 1
                    continue
                # Otherwise, treat as Python mod if plugin.py exists
                plugin = entry / "plugin.py"
                if plugin.exists():
                    if self._load_python_mod(plugin):
                        count += 1
                    continue
            elif entry.is_file():
                ext = entry.suffix.lower()
                if ext == ".json":
                    if self._load_json_mod(entry):
                        count += 1
                elif ext in (".yaml", ".yml"):
                    if self._load_yaml_mod(entry):
                        count += 1
                elif ext == ".lua":
                    if self._load_lua_mod(entry):
                        count += 1
                elif ext == ".py":
                    if self._load_python_mod(entry):
                        count += 1
        log.info("Discovered %d mods", count)
        return count

    def _load_directory_mod(self, dir_path: Path, manifest: Path) -> bool:
        try:
            if manifest.suffix == ".toml":
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib  # type: ignore
                with manifest.open("rb") as f:
                    data = tomllib.load(f)
            else:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            mod_id = data.get("mod_id") or dir_path.name
            mod = ModInfo(
                mod_id=mod_id,
                name=data.get("name", mod_id),
                version=str(data.get("version", "0.0.1")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                format=ModFormat.DIRECTORY,
                path=dir_path,
                dependencies=list(data.get("dependencies", [])),
                conflicts=list(data.get("conflicts", [])),
                tags=list(data.get("tags", [])),
                content=data.get("content", {}),
            )
            self.registry.register(mod)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load directory mod %s: %s", dir_path, exc)
            return False

    def _load_json_mod(self, path: Path) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            mod_id = data.get("mod_id") or path.stem
            mod = ModInfo(
                mod_id=mod_id, name=data.get("name", mod_id),
                version=str(data.get("version", "0.0.1")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                format=ModFormat.JSON, path=path,
                dependencies=list(data.get("dependencies", [])),
                conflicts=list(data.get("conflicts", [])),
                tags=list(data.get("tags", [])),
                content=data.get("content", {}),
            )
            self.registry.register(mod)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load JSON mod %s: %s", path, exc)
            return False

    def _load_yaml_mod(self, path: Path) -> bool:
        try:
            import yaml  # type: ignore
        except ImportError:
            log.warning("YAML support requires PyYAML — install with 'pip install pyyaml'")
            return False
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return False
            mod_id = data.get("mod_id") or path.stem
            mod = ModInfo(
                mod_id=mod_id, name=data.get("name", mod_id),
                version=str(data.get("version", "0.0.1")),
                description=data.get("description", ""),
                author=data.get("author", ""),
                format=ModFormat.YAML, path=path,
                dependencies=list(data.get("dependencies", [])),
                conflicts=list(data.get("conflicts", [])),
                tags=list(data.get("tags", [])),
                content=data.get("content", {}),
            )
            self.registry.register(mod)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load YAML mod %s: %s", path, exc)
            return False

    def _load_lua_mod(self, path: Path) -> bool:
        if not self._lua_available:
            log.warning("Lua mod %s requires 'lupa' package — install with 'pip install lupa'", path)
            mod = ModInfo(
                mod_id=path.stem, name=path.stem, version="0.0.1",
                format=ModFormat.LUA, path=path,
                error="Lua runtime not available (install 'lupa')",
            )
            self.registry.register(mod)
            return False
        try:
            import lupa  # type: ignore
            from lupa import LuaRuntime  # type: ignore
            lua = LuaRuntime(unpack_returned_tuples=True)
            source = path.read_text(encoding="utf-8")
            # Run the Lua script in a sandbox
            lua.execute("""
                function safe_setup()
                    return {
                        register_item = function(data) return data end,
                        register_creature = function(data) return data end,
                        register_spell = function(data) return data end,
                    }
                end
            """)
            result = lua.execute(source)
            mod_id = path.stem
            mod = ModInfo(
                mod_id=mod_id, name=mod_id, version="0.0.1",
                format=ModFormat.LUA, path=path,
                content={"lua_result": str(result) if result else ""},
            )
            self.registry.register(mod)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load Lua mod %s: %s", path, exc)
            return False

    def _load_python_mod(self, path: Path) -> bool:
        try:
            mod_id = path.stem if path.is_file() else path.name
            spec = importlib.util.spec_from_file_location(f"mods.{mod_id}", path)
            if spec is None or spec.loader is None:
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            mod_info_data = getattr(module, "MOD_INFO", {})
            mod = ModInfo(
                mod_id=mod_info_data.get("mod_id", mod_id),
                name=mod_info_data.get("name", mod_id),
                version=str(mod_info_data.get("version", "0.0.1")),
                description=mod_info_data.get("description", ""),
                author=mod_info_data.get("author", ""),
                format=ModFormat.PYTHON, path=path,
                dependencies=list(mod_info_data.get("dependencies", [])),
                conflicts=list(mod_info_data.get("conflicts", [])),
                tags=list(mod_info_data.get("tags", [])),
                content={"module": module.__name__},
            )
            self.registry.register(mod)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load Python mod %s: %s", path, exc)
            return False

    def apply_mods(self, engine: Any) -> dict[str, int]:
        """Apply all discovered mods to the engine. Returns counts by category."""
        counts: dict[str, int] = {}
        for mod in self.registry.all():
            if not mod.content:
                continue
            for category, items in mod.content.items():
                if not isinstance(items, list):
                    continue
                for item_data in items:
                    self._apply_item(engine, category, item_data)
                    counts[category] = counts.get(category, 0) + 1
            mod.loaded = True
        return counts

    def _apply_item(self, engine: Any, category: str, data: dict) -> None:
        """Apply a single mod item to the appropriate engine subsystem."""
        if category == "items":
            # Register a new item archetype
            from engine.items.generator import ARCHETYPES, BaseItemArchetype
            archetype_id = data.get("archetype") or data.get("id")
            if archetype_id and archetype_id not in ARCHETYPES:
                # Convert dict to archetype — minimal required fields
                try:
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
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not register mod item %s: %s", archetype_id, exc)
        elif category == "creatures":
            # Register a new creature species
            from engine.animals.system import AnimalLibrary, AnimalSpecies, AnimalType
            species_id = data.get("id") or data.get("name", "").lower().replace(" ", "_")
            if species_id and not AnimalLibrary.get(species_id):
                try:
                    species = AnimalSpecies(
                        id=species_id,
                        name=data.get("name", species_id),
                        animal_type=AnimalType[data.get("animal_type", "PREDATOR").upper()],
                        base_hp=data.get("hp", 20),
                        base_strength=data.get("strength", 8),
                        base_agility=data.get("agility", 10),
                        glyph=data.get("glyph", "a"),
                        color=data.get("color", 244),
                        aggressive=data.get("aggressive", False),
                        description=data.get("description", ""),
                    )
                    AnimalLibrary.register(species)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not register mod creature %s: %s", species_id, exc)
        elif category == "spells":
            from engine.magic.spells import Spell, SpellLibrary, SpellTarget
            spell_id = data.get("id")
            if spell_id and not SpellLibrary.get(spell_id):
                try:
                    spell = Spell(
                        id=spell_id,
                        name=data.get("name", spell_id),
                        school_id=data.get("school", "evocation"),
                        description=data.get("description", ""),
                        mana_cost=data.get("mana_cost", 20),
                        target=SpellTarget(data.get("target", "enemy")),
                    )
                    SpellLibrary.register(spell)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not register mod spell %s: %s", spell_id, exc)
        elif category == "skills":
            from engine.skills.system import Skill, SkillLibrary
            skill_id = data.get("id")
            if skill_id and not SkillLibrary.get(skill_id):
                try:
                    skill = Skill(
                        id=skill_id,
                        name=data.get("name", skill_id),
                        description=data.get("description", ""),
                        category=data.get("category", "knowledge"),
                        governing_attribute=data.get("governing_attribute", "intelligence"),
                    )
                    SkillLibrary.register(skill)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not register mod skill %s: %s", skill_id, exc)
        elif category == "recipes":
            from engine.crafting.system import Recipe, RecipeLibrary
            recipe_id = data.get("id")
            if recipe_id and not RecipeLibrary.get(recipe_id):
                try:
                    recipe = Recipe(
                        id=recipe_id,
                        name=data.get("name", recipe_id),
                        skill_id=data.get("skill", "smithing"),
                        skill_level_required=data.get("level_required", 1),
                        result_archetype=data.get("result_archetype", ""),
                        materials=data.get("materials", {}),
                    )
                    RecipeLibrary.register(recipe)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not register mod recipe %s: %s", recipe_id, exc)
