# Aeon Engine — Architecture Documentation

This document describes the high-level architecture of the Aeon Engine, a production-grade text-based open-world RPG engine in Python.

## Overview

Aeon is built around an Entity-Component-System (ECS) core, with a central event bus for cross-system communication and a plugin manager for extensibility. Every subsystem is isolated in its own package, communicating only through well-defined interfaces.

## Subsystem Map

```
                     ┌──────────────────────────┐
                     │       Engine (facade)     │
                     └────────────┬─────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
   ┌────▼─────┐            ┌──────▼──────┐           ┌──────▼─────┐
   │   Core   │            │   Plugins   │           │   World    │
   │  ECS     │            │  Manager    │           │  Generator │
   │  Events  │            │  Registry   │           │  Pathfind  │
   │  Clock   │            │  Sandbox    │           │  Spatial   │
   │  Config  │            │  Installer  │           │  Terrain   │
   │  Logging │            │  Validator  │           │  Biomes    │
   └────┬─────┘            └─────────────┘           └────────────┘
        │
   ┌────┴─────────────────────────────────────────────────────┐
   │                                                          │
┌──▼──────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────▼────┐
│Entities │  │  Items  │  │  NPC    │  │ Combat  │  │  Magic    │
│Components│ │Materials│  │  AI     │  │ Damage  │  │  Spells   │
│Factory  │  │ Affixes │  │ Memory  │  │ Effects │  │  Research │
└─────────┘  │Generator│  │Schedule │  └─────────┘  └───────────┘
             └─────────┘  │Personality│
                          └─────────┘
```

## Core (`engine/core/`)

### ECS (`ecs.py`)
- `Entity` — unique 64-bit id with generation
- `Component` — base class for pure-data components
- `World` — central registry with O(1) component operations
- `World.view(*comp_types)` — fast queries
- Tags for boolean classification
- Entity destruction bumps generation to invalidate stale references

### Event Bus (`events.py`)
- Priority-ordered handlers (MONITOR, HIGHEST, HIGH, NORMAL, LOW, LOWEST)
- Cancellable events (MONITOR always runs)
- Stop-propagation support
- Sync and async dispatch
- Per-event statistics
- Plugin-scoped unsubscribe

### Game Clock (`clock.py`)
- Tick-based time advancement
- In-world date/time (year, season, day, hour, minute)
- Day/night phases
- Pause/resume and time scaling

## World (`engine/world/`)
- **Terrain** — 22 terrain types with display glyphs, movement costs, walkability
- **Biomes** — 15 biomes classified by (elevation, temperature, moisture)
- **Generator** — multi-octave value noise (deterministic, no third-party deps), island falloff, rivers, settlements, roads
- **Pathfinding** — terrain-aware A* with diagonal movement
- **Spatial Grid** — uniform-grid hash for fast neighbour queries

## Plugins (`engine/plugins/`)
- **Discovery** — scans `plugins/` for `plugin.py` modules
- **Dependency Resolution** — topological sort with version constraints
- **Lifecycle** — `on_load`, `on_enable`, `on_disable`, `on_unload`, `on_reload`
- **Hot Reload** — `manager.reload(name)`
- **Installer** — install from directory, ZIP, or URL
- **Sandbox** — restricted execution environment for untrusted plugins
- **Migrations** — versioned save data migration
- **Validation** — metadata and source code validation
- **Documentation Generator** — auto-generate Markdown/JSON docs

## NPC AI (`engine/npc/`)
- **Needs** — 7 needs (hunger, thirst, fatigue, sleep, sanity, morale, comfort)
- **Memory** — short and long-term recall with decay
- **Schedule** — occupation-based daily routines
- **Personality** — Big-Five + courage, greed, curiosity
- **Controllers** — WanderAI, AggressiveAI, CivilianAI, PlayerAI

## Items (`engine/items/`)
- 27 materials across 6 categories
- 29 affixes (prefixes + suffixes) in 5 tiers
- 15 base archetypes
- 6 quality × 7 rarity = millions of unique items
- Properties, enchantments, sockets, durability, history, ownership

## Combat (`engine/combat/`)
- Turn-based resolution
- Hit/crit/block/dodge/parry rolls
- 12 damage types
- 10 status effect presets
- Enchantment on-hit effects

## Skills (`engine/skills/`)
- 58 skills across 6 categories (combat, magic, craft, social, survival, knowledge)
- XP-based leveling with decay
- Skill checks with crit/botch
- Training with teachers

## Magic (`engine/magic/`)
- 8 schools of magic
- 12 default spells
- Procedural spell research
- Spell targeting: self, ally, enemy, area, point, item
- Mana component with regeneration

## Crafting (`engine/crafting/`)
- 10 default recipes
- Material requirements, quality rolls, critical success
- Skill-gated crafting

## Dialogue (`engine/dialogue/`)
- Branching trees with conditions
- Persuasion attempts (persuade, intimidate, deceive, barter)
- Rumor spreading via NPC memory
- 3 default trees (commoner, merchant, guard)

## Quests (`engine/quests/`)
- Branching stages with multiple objectives
- Objective types: kill, fetch, talk, explore, escort, defend, custom
- Prerequisites, repeatable, time-limited
- Procedural quest generator

## Economy (`engine/economy/`)
- 22 trade goods
- Regional markets with dynamic supply/demand pricing
- Inflation tracking
- Banks with accounts, loans, interest

## Factions (`engine/factions/`)
- 6 default factions
- 6 diplomatic stances (war, hostile, neutral, friendly, allied, vassal)
- Trust system with auto-stance adjustment
- War declarations and war score tracking
- Laws and taxes

## Kingdoms (`engine/kingdoms/`)
- 8 default kingdoms
- 8 kingdom types (monarchy, republic, theocracy, oligarchy, tribal, empire, city-state, confederation)
- 8 succession laws (primogeniture, ultimogeniture, seniority, election, tanistry, matrilineal, partible, meritocratic)
- Territory management
- Politicians and elections
- Ruler succession on death

## Reputation (`engine/reputation/`)
- 10 reputation dimensions (global, regional, faction, NPC, criminal, heroic, political, religious, economic, military)
- Per-entity per-target tracking
- Decay over time
- Gameplay consequences (shop prices, guard reactions, quest availability)

## Life Simulation (`engine/life/`)
- Marriage, childbirth, inheritance
- Family lineages
- Education system
- Job market with postings and applications
- Life stages (infant → ancient)
- Life event tracking

## Animals (`engine/animals/`)
- 22+ default species (predators, herbivores, birds, reptiles, fish, insects, magical)
- Population dynamics (reproduction, starvation, evolution)
- Migration patterns
- Domestication with progress tracking
- Livestock management (milk, eggs, wool)

## Survival (`engine/survival/`)
- 8 diseases (cold, flu, dysentery, tetanus, plague, red death, frostbite, heatstroke)
- Disease contagiousness with radius
- Exposure damage from extreme body temperatures
- Poisoning with magnitude decay

## Weather (`engine/weather/`)
- 14 weather types
- 6 climate types
- Seasonal temperature variation
- Wind, humidity, visibility, pressure tracking

## Trade (`engine/trade/`)
- Trade routes between markets
- Caravans (overland) and ships (maritime)
- Risk events: bandits, storms, piracy, taxes
- Cargo management

## Auctions (`engine/auctions/`)
- Open bidding auctions
- Reserve prices and buyout prices
- Anonymous bidding
- Black market auctions

## Companies (`engine/companies/`)
- 6 default companies (merchant, mining, forestry, banking, shipping, mercenary)
- 6 default guilds (smiths, mages, merchants, thieves, healers, hunters)
- Employment system with contracts and payroll
- Monthly financial updates

## Espionage (`engine/espionage/`)
- Spy recruitment and management
- 10 mission types (gather intel, sabotage, assassinate, incite rebellion, steal tech, frame, spread rumor, infiltrate, extract, counterintelligence)
- Mission resolution with success/partial/failure/discovered/captured/killed outcomes
- Suspicion and cover quality mechanics

## Dungeons (`engine/dungeons/`)
- 10 dungeon types (cave, ruins, catacombs, vault, mine, temple, tomb, lair, stronghold, abyss)
- 3 generation algorithms (room-and-corridor, cellular automata, catacombs)
- Multi-level dungeons with stairs
- Boss rooms and treasure rooms

## Structures (`engine/structures/`)
- 51 structure types (houses, shops, inns, temples, fortresses, castles, etc.)
- Placement system with ownership
- Locked structures with lock difficulty
- Services (shop, sleep, heal, bank, etc.)

## Stealth (`engine/stealth/`)
- Per-entity stealth state (visible, hidden, detected, spotted, invisible)
- Detection meters per watcher
- Lighting, distance, movement, terrain factors
- Backstab bonus for hidden attackers

## Scripting (`engine/scripting/`)
- Sandboxed Python interpreter
- AST-based validation (forbidden nodes, names, attributes)
- Timeout enforcement
- Safe builtins (no I/O, no eval, no __import__)
- Whitelisted modules (math, random, statistics, datetime)

## Audio (`engine/audio/`)
- 36 default sound effects (combat, UI, environment, creatures, items, music)
- Descriptive audio cues for screen readers
- Terminal bell fallback
- Optional WAV/OGG playback via OS commands
- Volume control per channel

## Performance (`engine/performance/`)
- **Object Pool** — reuse expensive-to-create objects
- **Profiler** — hierarchical scoped timing
- **LRU Cache** — thread-safe LRU with hit/miss stats
- **TTL Cache** — time-based expiry
- **Lazy Value/Loader** — defer expensive computation

## Behaviors & GOAP (`engine/behaviors/`, `engine/goap/`)
- **Behavior Trees** — Sequence, Selector, Action, Condition, Inverter, Repeater, Parallel, Delay nodes
- **GOAP** — Goal-Oriented Action Planning with A* search over state space

## UI (`engine/ui/`, `engine/render/`, `engine/themes/`, `engine/keybindings/`, `engine/accessibility/`)
- **Renderer** — double-buffered ANSI terminal renderer
- **Screens** — main, inventory, character, world map, help
- **Themes** — 8 default themes (dark, light, solarized_dark, monokai, dracula, nord, gruvbox, high_contrast)
- **Keybindings** — configurable key mappings with 50+ actions
- **Accessibility** — screen reader support, colorblindness modes, high contrast, reduced motion

## Save System (`engine/serialization/`)
- Versioned saves (currently v1)
- SHA-256 integrity check
- zlib compression
- Autosave rotation
- Migration framework for forward compatibility

## Commands (`engine/commands/`)
- 13 default commands
- Aliases and macros
- 5 permission levels (player, moderator, admin, owner, debug)
- History tracking
- Autocomplete

## Localization (`engine/localization/`)
- Locale management with runtime switching
- Plural rules for English, French, Russian, Arabic, CJK
- RTL support (Arabic, Hebrew, Farsi, Urdu)
- JSON-based locale files

## Network (`engine/network/`)
- Message protocol with 10 message types
- Local transport for tests/single-player
- Threaded client and server implementations
- Architecture-ready for TCP/WebSocket/QUIC transports

## Mod Support (`engine/mods_loader/`)
- **Python mods** — full plugin-like mods
- **JSON mods** — declarative content (items, creatures, spells, skills, recipes)
- **YAML mods** — human-readable format (requires PyYAML)
- **Lua mods** — sandboxed Lua scripts (requires lupa)
- **Asset packs** — content packs with manifests

## Design Patterns Used

- **SOLID** — each subsystem has a single responsibility
- **DRY** — shared utilities in `engine/utils/`
- **Composition over Inheritance** — ECS entities are component bags
- **Dependency Injection** — systems receive dependencies via constructors
- **Event-Driven** — cross-system communication via EventBus
- **Data-Driven** — content defined in code constants (production: JSON/TOML)
- **Repository Pattern** — ItemRegistry, PluginRegistry, CommandRegistry
- **Factory Pattern** — EntityFactory, ItemGenerator, QuestGenerator
- **Strategy Pattern** — AI controllers, damage calculators
- **Observer Pattern** — component change listeners, event subscribers
- **State Pattern** — game phase, weather state, NPC AI state
- **Command Pattern** — command system with undo support
- **Builder Pattern** — world generator pipeline
- **Behavior Trees** — composable AI decision-making
- **GOAP** — goal-oriented action planning
