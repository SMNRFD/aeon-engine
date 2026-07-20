# Aeon Engine

**The world's most advanced, production-grade text-based open-world RPG engine in Python.**

Aeon is a massive, modular, plugin-driven simulation engine inspired by Dwarf Fortress, Cataclysm DDA, Caves of Qud, Rimworld, Starsector, Project Zomboid, Crusader Kings, Mount & Blade, Kenshi, EVE Online, Noita, Minecraft, Terraria, Ultima, and traditional roguelikes.

It is built around an Entity-Component-System core, an event bus, and a plugin manager that supports hot reload, dependency resolution, versioning, sandboxing, installer, migrations, validation, and documentation generation.

---

## Quick Start

### Requirements
- Python 3.11+
- No third-party dependencies required for the core engine
- Optional: `pyyaml` for YAML mods, `lupa` for Lua mods

### Run

```bash
# Headless verification (generates world, ticks once, exits)
python engine/repl/repl.py --headless --seed 42 --width 60 --height 40

# Full game (terminal UI)
python engine/repl/repl.py --seed 42 --width 80 --height 50

# Load a saved game
python engine/repl/repl.py --load my_save

# Debug mode (cheat commands enabled)
python engine/repl/repl.py --debug
```

### Run Tests

```bash
python -m pytest tests/ -v
```

**172 tests** cover ECS, events, world generation, combat, items, crafting, skills, magic, dialogue, quests, plugins, reputation, life simulation, animals, kingdoms, scripting, audio, performance, dungeons, structures, stealth, trade, auctions, companies, espionage, mods loader, themes, keybindings, accessibility, behavior trees, GOAP, plugin sandbox/migrations/validation/docs, dimensions, real-time combat, body parts, mounted/naval/aerial/siege/space combat, runes, artifacts, rebellions, black markets, replication/prediction/rollback/authority, streaming world, content packs, bookmarks, UI extensions, procedural dialogue, skill books, quest consequences, background simulation, async NPC simulation, plugin networking hooks, integration, and performance.

---

## Architecture

The engine is organised into **70+ subsystem packages**:

```
engine/
├── core/              ECS, EventBus, GameClock, Config, Logging
├── plugins/           Plugin manager, registry, sandbox, installer, validator, docs, migrations, networking hooks
├── world/             Terrain, biomes, generator, pathfinding, spatial grid
├── dimensions/        Multi-dimensional world: 12 dimensions, planets, galaxies
├── streaming/         Chunk-based streaming world
├── entities/          ECS components, entity factory
├── npc/               AI controllers, needs, memory, schedule, personality, async simulator
├── items/             Materials, affixes, procedural item generation
├── inventory/         Inventory and equipment slots
├── combat/            Turn-based resolution, damage, status effects
├── realtime_combat/   Real-time combat with cooldowns
├── bodyparts/         Hit locations, body part damage
├── mounted_combat/    Mounted combat (horses, griffins)
├── naval_combat/      Ship-to-ship combat
├── aerial_combat/     Flying mount combat
├── siege_combat/      Siege engines, walls, assaults
├── space_combat/      Starship combat
├── skills/            58 skills with XP, decay, training, checks
├── crafting/          Recipes, research, experimentation
├── magic/             8 schools, 12 spells, procedural spell research
├── runes/             17 rune types for item inscription
├── artifacts/         7 unique artifacts with sentience and curses
├── dialogue/          Trees, persuasion, rumors, memory hooks
├── procedural_dialogue/  Template-based dialogue generation
├── quests/            Branching, procedural, scripted quests
├── quest_consequences/   Quest chains with delayed consequences
├── economy/           Markets, trade goods, banks, loans, inflation
├── factions/          Diplomacy, wars, laws, taxes, reputation
├── kingdoms/          Politics, succession, territory, elections
├── reputation/        10-dimension reputation tracking
├── life/              Marriage, family, inheritance, education, jobs
├── animals/           Species, populations, migration, domestication
├── rebellions/        Rebellions, civil wars, succession crises
├── blackmarket/       Black markets, fencing, assassination contracts
├── weather/           Seasons, climate, weather events
├── survival/          Disease, exposure, poison, mental health
├── dungeons/          10 dungeon types with 3 generation algorithms
├── structures/        51 structure types
├── stealth/           Sneaking, detection, backstabbing
├── trade/             Trade routes, caravans, ships
├── auctions/          Bidding system with reserve and buyout
├── companies/         Companies, guilds, employment
├── espionage/         Spies, missions, sabotage, assassination
├── behaviors/         Behavior trees
├── goap/              Goal-Oriented Action Planning
├── scripting/         Sandboxed Python interpreter
├── audio/             36 sound effects, descriptive cues, terminal bell
├── performance/       Object pool, profiler, LRU/TTL caches, lazy loading
├── commands/          Parser, aliases, macros, permissions, history
├── serialization/     Versioned saves, integrity, autosave, migrations
├── localization/      i18n, pluralization, RTL
├── render/            Double-buffered ANSI terminal renderer
├── ui/                5 screens (main, inventory, character, map, help)
├── ui_extensions/     Search, filtering, sortable lists, mouse support
├── themes/            8 colour themes
├── keybindings/       Configurable key mappings (50+ actions)
├── accessibility/     Screen reader, colorblindness, high contrast
├── bookmarks/         Map bookmarks, pins, markers
├── network/           Client/server protocol
├── replication/       Replication, prediction, rollback, authority
├── content_packs/     25 content pack types
├── mods_loader/       JSON, YAML, Lua, Python mod loaders
├── background_sim/    Persistent world simulation
├── skill_books/       Skill books, discovery, procedural progression
└── engine.py          Top-level Engine facade
```

See `docs/ARCHITECTURE.md` and `docs/DIAGRAMS.md` for the full architecture documents with Mermaid diagrams.

---

## Documentation

- `docs/ARCHITECTURE.md` — High-level architecture
- `docs/DIAGRAMS.md` — Mermaid architecture diagrams (12 diagrams)
- `docs/PLUGIN_GUIDE.md` — How to develop plugins
- `docs/MODDING_GUIDE.md` — How to create JSON/YAML/Lua mods
- `docs/DEVELOPER_GUIDE.md` — Internal architecture and coding conventions
- `docs/API_REFERENCE.md` — Public API reference

---

## Statistics

- ~25,000 lines of production Python code
- 70+ subsystem packages
- 172 passing tests
- 6 documentation files
- 22 terrain types, 15 biomes
- 27 materials, 29 affixes, 15 item archetypes
- 58 skills, 12 spells, 8 magic schools, 17 runes, 7 artifacts
- 10 crafting recipes, 8 diseases, 14 weather types, 6 climates
- 8 kingdoms, 6 factions, 22 trade goods
- 22+ animal species, 14 skill books
- 51 structure types, 10 dungeon types
- 12 dimensions, 5 planets, 3 galaxies
- 36 sound effects, 8 themes, 50+ keybinding actions
- 13 default commands, 3 default quests
- 7 combat variants (turn-based, real-time, mounted, naval, aerial, siege, space)
- Sample plugin (fishing), 4 sample mods (JSON, YAML, Lua, directory)

---

## License

MIT

---

## AI Agent

z.ai GLM 5.2