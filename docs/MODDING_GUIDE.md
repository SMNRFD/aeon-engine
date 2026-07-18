# Aeon Engine — Modding Guide

This guide covers how to create content mods for the Aeon Engine using JSON, YAML, or Lua.

## Mod Formats

Aeon supports four mod formats:

| Format | Extension | Use Case |
|--------|-----------|----------|
| JSON | `.json` | Declarative content (items, creatures, spells) |
| YAML | `.yaml`/`.yml` | Human-readable declarative content |
| Lua | `.lua` | Scripted mods (requires `lupa` package) |
| Python | `.py` | Full programmatic mods |
| Directory | (folder) | Multi-file mods with manifest |

## JSON Mods

A JSON mod is a single file in `mods/` with this structure:

```json
{
  "mod_id": "my_content_pack",
  "name": "My Content Pack",
  "version": "0.1.0",
  "description": "Adds new items, creatures, and spells.",
  "author": "Your Name",
  "dependencies": [],
  "conflicts": [],
  "tags": ["item_pack", "monster_pack"],
  "content": {
    "items": [...],
    "creatures": [...],
    "spells": [...],
    "skills": [...],
    "recipes": [...]
  }
}
```

### Items

```json
{
  "archetype": "longsword",
  "name": "Sunsteel Blade",
  "material": "steel",
  "quality": "excellent",
  "rarity": "rare",
  "enchantments": [
    {"type": "fire_damage", "magnitude": 2.5}
  ],
  "history": ["Forged in the heart of the sun."]
}
```

Supported `archetype` values: `dagger`, `shortsword`, `longsword`, `greatsword`, `mace`, `warhammer`, `axe`, `battleaxe`, `spear`, `bow`, `crossbow`, `staff`, `wand`, `leather_armor`, `chainmail`, `plate_armor`, `helmet`, `shield`, `boots`, `cloak`, `ring`, `amulet`, `health_potion`, `mana_potion`, `bread`, `water_flask`, `gold_coin`, `torch`.

Supported `material` values: `copper`, `bronze`, `iron`, `steel`, `silver`, `gold`, `mithril`, `adamant`, `orichalcum`, `oak`, `pine`, `yew`, `ebony`, `ironwood`, `leather`, `boiled_leather`, `silk`, `linen`, `wool`, `granite`, `obsidian`, `flint`, `marble`, `bone`, `dragonbone`, `glass`, `crystal`, `organic`.

Supported `quality` values: `broken`, `worn`, `average`, `fine`, `excellent`, `pristine`.

Supported `rarity` values: `junk`, `common`, `uncommon`, `rare`, `epic`, `legendary`, `mythic`.

### Creatures

```json
{
  "id": "forest_troll",
  "name": "Forest Troll",
  "glyph": "T",
  "color": 71,
  "hp": 80,
  "strength": 14,
  "agility": 6,
  "aggressive": true,
  "tags": ["hostile", "regenerating"]
}
```

### Spells

```json
{
  "id": "icelance",
  "name": "Ice Lance",
  "school": "evocation",
  "mana_cost": 18,
  "cast_time": 1.2,
  "target": "enemy",
  "effects": [
    {"kind": "damage", "magnitude": 32.0, "damage_type": "cold"}
  ],
  "tags": ["cold"]
}
```

### Skills

```json
{
  "id": "runecrafting",
  "name": "Runecrafting",
  "category": "magic",
  "governing_attribute": "intelligence",
  "difficulty": 1.4,
  "base_xp": 180,
  "description": "Engraving magical runes onto items."
}
```

### Recipes

```json
{
  "id": "steel_dagger",
  "name": "Steel Dagger",
  "skill": "smithing",
  "level_required": 10,
  "result_archetype": "dagger",
  "result_material": "steel",
  "materials": {"steel": 1}
}
```

## YAML Mods

YAML mods use the same structure as JSON but with YAML syntax:

```yaml
mod_id: my_yaml_mod
name: My YAML Mod
version: 0.1.0
description: A YAML-based content mod.
content:
  items:
    - archetype: longsword
      name: Moonlight Blade
      material: mithril
      quality: excellent
      rarity: epic
      enchantments:
        - type: cold_damage
          magnitude: 5.0
```

YAML requires the `pyyaml` package: `pip install pyyaml`.

## Lua Mods

Lua mods allow scripted content with sandboxed execution:

```lua
-- mods/my_lua_mod.lua
local items = {}

function items.register()
    return {
        id = "lua_sword",
        name = "Lua-Forged Blade",
        archetype = "longsword",
        material = "steel",
        quality = "fine"
    }
end

return items
```

Lua requires the `lupa` package: `pip install lupa`.

## Python Mods

Python mods are full modules that can do anything a plugin can:

```python
# mods/my_python_mod.py
MOD_INFO = {
    "mod_id": "my_python_mod",
    "name": "My Python Mod",
    "version": "1.0.0",
    "description": "A Python-based mod.",
    "tags": ["gameplay"],
}

def on_load(engine):
    """Called when the mod is loaded."""
    from engine.skills.system import Skill, SkillLibrary
    SkillLibrary.register(Skill(
        id="custom_skill",
        name="Custom Skill",
        description="A skill added by a Python mod.",
        category="knowledge",
        governing_attribute="intelligence",
    ))
```

## Directory Mods

Multi-file mods use a directory with a `mod.toml` or `mod.json` manifest:

```
mods/my_big_mod/
├── mod.toml
├── items/
│   ├── weapons.json
│   └── armor.json
├── creatures/
│   └── monsters.json
├── scripts/
│   └── custom_logic.py
└── locale/
    ├── en_US.json
    └── fr_FR.json
```

`mod.toml`:

```toml
mod_id = "my_big_mod"
name = "My Big Mod"
version = "1.0.0"
description = "A large multi-file mod."
author = "Your Name"
dependencies = []
conflicts = []
tags = ["content_pack"]

[content]
items = []
creatures = []
```

## Asset Packs

Asset packs contain only data, no code. They're loaded like other mods but typically contain:
- Item definitions
- Creature definitions
- Localization strings
- Tile/texture references (for future graphical modes)

## Mod Discovery

Mods are auto-discovered in the `mods/` directory. To load them:

```python
from engine.mods_loader.system import ModLoader

loader = ModLoader(mods_dir="mods")
loader.discover()
loader.apply_mods(engine)
```

## Mod Conflicts

If two mods define the same item/creature/spell, the last-loaded one wins. Use the `conflicts` field to declare incompatibilities:

```json
{
  "mod_id": "my_mod",
  "conflicts": ["other_mod"]
}
```

## Mod Dependencies

Mods can depend on other mods:

```json
{
  "mod_id": "expansion_pack",
  "dependencies": ["base_pack>=1.0"]
}
```

## Distribution

Distribute mods as ZIP files containing the mod directory:

```
my_mod.zip
└── my_mod/
    ├── mod.json
    └── content/
```

Users unzip into their `mods/` directory.

## Complete Example

See `mods/example_mod.json` for a complete JSON mod that adds items, creatures, skills, and spells.
