# Aeon Engine

**The world's most advanced, production-grade text-based open-world RPG engine in Python.**

Aeon is a massive, modular, plugin-driven simulation engine inspired by Dwarf Fortress, Cataclysm DDA, Caves of Qud, Rimworld, Starsector, Project Zomboid, Crusader Kings, Mount & Blade, Kenshi, EVE Online, Noita, Minecraft, Terraria, Ultima, and traditional roguelikes.

It is built around an Entity-Component-System core, an event bus, and a plugin manager that supports hot reload, dependency resolution, versioning, and sandboxing.

---

## Quick Start

### Requirements
- Python 3.11+
- No third-party dependencies required for the core engine
- Optional: `pyyaml` for YAML mods, `lupa` for Lua mods

### Run

```bash
# Headless verification (generates world, ticks once, exits)
python main.py --headless --seed 42 --width 60 --height 40

# Full game (terminal UI)
python main.py --seed 42 --width 80 --height 50

# Load a saved game
python main.py --load my_save

# Debug mode (cheat commands enabled)
python main.py --debug
```

### Run Tests

```bash
python -m pytest tests/ -v
```

118 tests cover ECS, events, world generation, combat, items, crafting, skills, magic, dialogue, quests, plugins, reputation, life simulation, animals, kingdoms, scripting, audio, performance, dungeons, structures, stealth, trade, auctions, companies, espionage, mods loader, themes, keybindings, accessibility, behavior trees, GOAP, plugin sandbox/migrations/validation/docs, integration, and performance.

---

## Architecture

The engine is organised into 47 subsystem packages:

```
engine/
├── core/              ECS, EventBus, GameClock, Config, Logging
├── plugins/           Plugin manager, registry, sandbox, installer, validator, docs
├── world/             Terrain, biomes, generator, pathfinding, spatial grid
├── entities/          ECS components, entity factory
├── npc/               AI controllers, needs, memory, schedule, personality
├── items/             Materials, affixes, procedural item generation
├── inventory/         Inventory and equipment slots
├── combat/            Turn-based resolution, damage, status effects
├── skills/            58 skills with XP, decay, training, checks
├── crafting/          Recipes, research, experimentation
├── magic/             8 schools, 12 spells, procedural spell research
├── dialogue/          Trees, persuasion, rumors, memory hooks
├── quests/            Branching, procedural, scripted quests
├── economy/           Markets, trade goods, banks, loans, inflation
├── factions/          Diplomacy, wars, laws, taxes, reputation
├── kingdoms/          Politics, succession, territory, elections
├── reputation/        10-dimension reputation tracking
├── life/              Marriage, family, inheritance, education, jobs
├── animals/           Species, populations, migration, domestication
├── weather/           Seasons, climate, weather events
├── survival/          Disease, exposure, poison, mental health
├── dungeons/          10 dungeon types with 3 generation algorithms
├── structures/        51 structure types (buildings, shops, temples, etc.)
├── stealth/           Sneaking, detection, backstabbing
├── trade/             Trade routes, caravans, ships
├── auctions/          Bidding system with reserve and buyout
├── companies/         Companies, guilds, employment
├── espionage/         Spies, missions, sabotage, assassination
├── behaviors/         Behavior trees (Sequence, Selector, etc.)
├── goap/              Goal-Oriented Action Planning
├── scripting/         Sandboxed Python interpreter
├── audio/             36 sound effects, descriptive cues, terminal bell
├── performance/       Object pool, profiler, LRU/TTL caches, lazy loading
├── commands/          Parser, aliases, macros, permissions, history
├── serialization/     Versioned saves, integrity, autosave, migrations
├── localization/      i18n, pluralization, RTL
├── render/            Double-buffered ANSI terminal renderer
├── ui/                5 screens (main, inventory, character, map, help)
├── themes/            8 colour themes (dark, light, solarized, monokai, etc.)
├── keybindings/       Configurable key mappings (50+ actions)
├── accessibility/     Screen reader, colorblindness, high contrast
├── network/           Client/server protocol (architecture-ready)
├── mods_loader/       JSON, YAML, Lua, Python mod loaders
└── engine.py          Top-level Engine facade
```

See `docs/ARCHITECTURE.md` for the full architecture document.

---

## Core Systems

### ECS (`engine/core/ecs.py`)
- `Entity` — unique 64-bit id with generation
- `Component` — base class for pure-data components
- `World` — central registry with O(1) component operations
- `World.view(*types)` — fast queries
- Tags for boolean classification
- Entity destruction bumps generation to invalidate stale references

### Event Bus (`engine/core/events.py`)
- Priority-ordered handlers (MONITOR, HIGHEST, HIGH, NORMAL, LOW, LOWEST)
- Cancellable events (MONITOR always runs)
- Stop-propagation support
- Sync and async dispatch
- Per-event statistics
- Plugin-scoped unsubscribe

### Plugin System (`engine/plugins/`)
- Discovery via `plugins/<name>/plugin.py`
- Topological dependency resolution with version constraints
- Lifecycle hooks: `on_load`, `on_enable`, `on_disable`, `on_unload`, `on_reload`
- Hot reload
- Installer (from directory, ZIP, or URL)
- Sandboxed execution for untrusted plugins
- Save data migrations
- Metadata and source validation
- Auto-generated documentation

### World Generation (`engine/world/generator.py`)
- Multi-octave value noise (deterministic, no third-party deps)
- Heightmap with island falloff
- Temperature from latitude + altitude + noise
- Moisture from separate noise field
- 13 biomes classified by (elevation, temperature, moisture)
- Rivers traced from peaks downhill to sea
- Settlement placement near water
- Road network via greedy MST + A* pathfinding

### NPC AI (`engine/npc/`)
- **Needs**: 7 needs with severity levels and stat penalties
- **Memory**: per-NPC store with decay, recall reinforcement, knowledge graph
- **Schedule**: occupation-based daily routines
- **Personality**: Big-Five + courage, greed, curiosity
- **Controllers**: WanderAI, AggressiveAI, CivilianAI, PlayerAI

### Items (`engine/items/`)
- 27 materials across 6 categories
- 29 affixes in 5 tiers
- 15 base archetypes
- 6 quality × 7 rarity = millions of unique items
- Properties, enchantments, sockets, durability, history, ownership

### Combat (`engine/combat/`)
- Turn-based resolution
- Hit/crit/block/dodge/parry rolls
- 12 damage types
- 10 status effect presets
- Enchantment on-hit effects

### Skills (`engine/skills/`)
- 58 skills across 6 categories
- XP-based leveling with decay
- Skill checks with crit/botch
- Training with teachers

### Magic (`engine/magic/`)
- 8 schools
- 12 default spells
- Procedural spell research
- Spell targeting: self, ally, enemy, area, point, item

### Crafting (`engine/crafting/`)
- 10 default recipes
- Material requirements, quality rolls, critical success

### Dialogue (`engine/dialogue/`)
- Branching trees with conditions
- Persuasion: persuade, intimidate, deceive, barter
- Rumor spreading via NPC memory

### Quests (`engine/quests/`)
- Branching stages with multiple objectives
- Procedural quest generator

### Economy (`engine/economy/`)
- 22 trade goods
- Regional markets with dynamic supply/demand pricing
- Inflation tracking
- Banks with accounts, loans, interest

### Factions (`engine/factions/`)
- 6 default factions
- 6 diplomatic stances
- Trust system with auto-stance adjustment
- War declarations and war score tracking
- Laws and taxes

### Kingdoms (`engine/kingdoms/`)
- 8 default kingdoms
- 8 kingdom types (monarchy, republic, theocracy, etc.)
- 8 succession laws (primogeniture, election, tanistry, etc.)
- Territory management
- Politicians and elections

### Reputation (`engine/reputation/`)
- 10 reputation dimensions
- Per-entity per-target tracking
- Decay over time
- Gameplay consequences (shop prices, guard reactions, quest availability)

### Life Simulation (`engine/life/`)
- Marriage, childbirth, inheritance
- Family lineages
- Education system
- Job market
- Life stages (infant → ancient)

### Animals (`engine/animals/`)
- 22+ default species
- Population dynamics (reproduction, starvation, evolution)
- Migration patterns
- Domestication with progress tracking
- Livestock management (milk, eggs, wool)

### Survival (`engine/survival/`)
- 8 diseases
- Disease contagiousness
- Exposure damage
- Poisoning

### Weather (`engine/weather/`)
- 14 weather types
- 6 climate types
- Seasonal variation

### Dungeons (`engine/dungeons/`)
- 10 dungeon types
- 3 generation algorithms (room-and-corridor, cellular automata, catacombs)
- Multi-level dungeons with stairs

### Structures (`engine/structures/`)
- 51 structure types
- Placement system with ownership
- Locked structures
- Services (shop, sleep, heal, bank, etc.)

### Stealth (`engine/stealth/`)
- Per-entity stealth state
- Detection meters per watcher
- Lighting, distance, movement, terrain factors
- Backstab bonus

### Trade (`engine/trade/`)
- Trade routes between markets
- Caravans (overland) and ships (maritime)
- Risk events: bandits, storms, piracy, taxes

### Auctions (`engine/auctions/`)
- Open bidding auctions
- Reserve prices and buyout prices
- Anonymous bidding
- Black market auctions

### Companies (`engine/companies/`)
- 6 default companies
- 6 default guilds
- Employment system with contracts and payroll

### Espionage (`engine/espionage/`)
- Spy recruitment and management
- 10 mission types
- Mission resolution with multiple outcomes
- Suspicion and cover quality mechanics

### Scripting (`engine/scripting/`)
- Sandboxed Python interpreter
- AST-based validation
- Timeout enforcement
- Safe builtins (no I/O, no eval, no `__import__`)
- Whitelisted modules (math, random, statistics, datetime)

### Audio (`engine/audio/`)
- 36 default sound effects
- Descriptive audio cues for screen readers
- Terminal bell fallback
- Optional WAV/OGG playback via OS commands
- Volume control per channel

### Performance (`engine/performance/`)
- Object Pool
- Hierarchical Profiler
- LRU Cache
- TTL Cache
- Lazy Value/Loader

### Behaviors & GOAP (`engine/behaviors/`, `engine/goap/`)
- Behavior Trees (Sequence, Selector, Action, Condition, Inverter, Repeater, Parallel, Delay)
- GOAP (Goal-Oriented Action Planning) with A* search

### UI (`engine/ui/`, `engine/render/`, `engine/themes/`, `engine/keybindings/`, `engine/accessibility/`)
- Double-buffered ANSI terminal renderer
- 5 screens (main, inventory, character, world map, help)
- 8 colour themes
- Configurable keybindings (50+ actions)
- Accessibility: screen reader, colorblindness modes, high contrast, reduced motion

### Save System (`engine/serialization/`)
- Versioned saves (currently v1)
- SHA-256 integrity check
- zlib compression
- Autosave rotation
- Migration framework

### Commands (`engine/commands/`)
- 13 default commands
- Aliases and macros
- 5 permission levels
- History and autocomplete

### Localization (`engine/localization/`)
- Locale management with runtime switching
- Plural rules for English, French, Russian, Arabic, CJK
- RTL support

### Network (`engine/network/`)
- Message protocol with 10 message types
- Local transport for tests/single-player
- Threaded client and server
- Architecture-ready for TCP/WebSocket/QUIC

### Mod Support (`engine/mods_loader/`)
- Python mods
- JSON mods
- YAML mods (requires PyYAML)
- Lua mods (requires lupa)
- Directory mods with manifests
- Asset packs

---

## Documentation

- `docs/ARCHITECTURE.md` — High-level architecture
- `docs/PLUGIN_GUIDE.md` — How to develop plugins
- `docs/MODDING_GUIDE.md` — How to create JSON/YAML/Lua mods
- `docs/DEVELOPER_GUIDE.md` — Internal architecture and coding conventions
- `docs/API_REFERENCE.md` — Public API reference

---

## Plugin Development

A plugin is a Python module at `plugins/<name>/plugin.py` that exports a `Plugin` subclass:

```python
from engine.plugins.base import Plugin, PluginMetadata

class MyPlugin(Plugin):
    metadata = PluginMetadata(
        name="my_plugin",
        version="0.1.0",
        description="Does something cool.",
        author="You",
        dependencies=["other_plugin>=1.0"],
        tags=["gameplay"],
        load_order=100,
    )

    def on_load(self, engine):
        # Register skills, items, etc.
        ...

    def on_enable(self, engine):
        # Register commands, subscribe to events
        engine.register_command("mycmd", my_handler,
                                  description="My custom command")

    def on_disable(self, engine):
        # Clean up
        ...
```

See `plugins/fishing/plugin.py` for a complete example.

---

## Mod Formats

JSON, YAML, Lua, and Python mods are supported:

```json
{
  "mod_id": "my_pack",
  "name": "My Pack",
  "version": "0.1.0",
  "content": {
    "items": [...],
    "creatures": [...],
    "spells": [...]
  }
}
```

See `mods/example_mod.json`, `mods/example_mod.yaml`, `mods/example_mod.lua`, and `mods/big_mod/` for examples.

---

## Configuration

Configuration is loaded from `engine.toml` with environment variable overrides:

```toml
[engine]
debug = false
log_level = "INFO"

[world]
world_seed = 48879
world_tiles_x = 256
world_tiles_y = 256

[simulation]
ticks_per_second = 20

[plugins]
hot_reload = true

[save]
save_dir = "saves"
autosave_interval_ticks = 1200

[ui]
theme = "dark"
color_enabled = true
viewport_width = 80
viewport_height = 24

[audio]
play_files = false
enable_bell = true

[accessibility]
color_blindness = 0  # 0=none, 1=protanopia, 2=deuteranopia, 3=tritanopia, 4=achromatopsia
high_contrast = false

[mods]
mods_dir = "mods"
autoload = true
```

Environment overrides: `AEON_DEBUG`, `AEON_LOG_LEVEL`, `AEON_WORLD_SEED`, `AEON_TICKS_PER_SECOND`, `AEON_UI_THEME`, `AEON_SAVE_DIR`.

---

## Default Commands

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `look` (or `l`) | Look around |
| `inventory` (or `i`, `inv`) | Show inventory |
| `status` (or `st`) | Show player status |
| `save [name]` | Save the game |
| `load <name>` | Load a save |
| `time` | Show game time |
| `wait [minutes]` (or `w`) | Wait |
| `weather` | Show weather |
| `plugins` | List plugins |
| `reload <plugin>` | Hot-reload a plugin (admin) |
| `spawn <creature> [count]` | Spawn a creature (debug) |
| `quit` (or `exit`, `q`) | Quit |

---

## Testing

```bash
python -m pytest tests/ -v
```

118 tests across:
- Unit tests (ECS, events, combat, items, etc.)
- Integration tests (engine end-to-end workflows)
- Performance tests (item gen, world gen, pathfinding, ECS queries)
- Plugin tests (lifecycle, dependencies, sandbox, validation)

---

## Design Patterns Used

- **SOLID** — single responsibility per subsystem
- **DRY** — shared utilities
- **Composition over Inheritance** — ECS entities are component bags
- **Dependency Injection** — systems receive dependencies via constructors
- **Event-Driven** — cross-system communication via EventBus
- **Data-Driven** — content defined in code constants (production: JSON/TOML)
- **Repository Pattern** — ItemRegistry, PluginRegistry, CommandRegistry
- **Factory Pattern** — EntityFactory, ItemGenerator, QuestGenerator
- **Strategy Pattern** — AI controllers, damage calculators
- **Observer Pattern** — component listeners, event subscribers
- **State Pattern** — game phase, weather state, NPC AI state
- **Command Pattern** — command system
- **Builder Pattern** — world generator pipeline
- **Behavior Trees** — composable AI
- **GOAP** — goal-oriented action planning

---

## Statistics

- ~16,000 lines of production Python code
- 47 subsystem packages
- 118 passing tests
- 22 terrain types, 15 biomes
- 27 materials, 29 affixes, 15 item archetypes
- 58 skills, 12 spells, 8 magic schools
- 10 crafting recipes, 8 diseases, 14 weather types
- 8 kingdoms, 6 factions, 22 trade goods
- 22+ animal species, 8 default dialogue trees
- 51 structure types, 10 dungeon types
- 36 sound effects, 8 themes, 50+ keybinding actions
- 13 default commands, 3 default quests
- Sample plugin (fishing), 4 sample mods (JSON, YAML, Lua, directory)

---

## License

MIT
