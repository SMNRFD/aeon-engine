# Aeon Engine — Developer Guide

This guide covers internal architecture, coding conventions, and how to extend the engine.

## Project Structure

```
aeon-engine/
├── engine/                  # Engine source
│   ├── core/                # ECS, EventBus, GameClock, Config, Logging
│   ├── plugins/             # Plugin manager, sandbox, installer, validator
│   ├── world/               # World generation, terrain, biomes, pathfinding
│   ├── entities/            # ECS components, entity factory
│   ├── npc/                 # AI, needs, memory, schedule, personality
│   ├── items/               # Materials, affixes, item generation
│   ├── inventory/           # Inventory and equipment
│   ├── combat/              # Combat resolution, damage, status effects
│   ├── skills/              # Skill catalog and progression
│   ├── crafting/            # Recipes and crafting
│   ├── magic/               # Spells, schools, research
│   ├── dialogue/            # Dialogue trees and persuasion
│   ├── quests/              # Quest system and generator
│   ├── economy/             # Markets, trade goods, banks
│   ├── factions/            # Diplomacy, wars, laws
│   ├── kingdoms/            # Politics, succession, territory
│   ├── reputation/          # Multi-dimensional reputation
│   ├── life/                # Marriage, family, inheritance
│   ├── animals/             # Species, populations, domestication
│   ├── weather/             # Weather simulation
│   ├── survival/            # Disease, exposure, poison
│   ├── dungeons/            # Dungeon generation
│   ├── structures/          # Buildings and placeable features
│   ├── stealth/             # Sneaking and detection
│   ├── trade/               # Trade routes, caravans, ships
│   ├── auctions/            # Bidding system
│   ├── companies/           # Companies, guilds, employment
│   ├── espionage/           # Spies, missions, sabotage
│   ├── behaviors/           # Behavior trees
│   ├── goap/                # Goal-Oriented Action Planning
│   ├── scripting/           # Sandboxed Python interpreter
│   ├── audio/               # Sound effects and cues
│   ├── performance/         # Object pool, profiler, caches
│   ├── commands/            # Command parser and registry
│   ├── serialization/       # Save system
│   ├── localization/        # i18n
│   ├── render/              # Terminal renderer
│   ├── ui/                  # Screens and panels
│   ├── themes/              # Colour themes
│   ├── keybindings/         # Key mappings
│   ├── accessibility/       # Screen reader, colorblindness
│   ├── network/             # Client/server protocol
│   ├── mods_loader/         # JSON/YAML/Lua mod loaders
│   └── engine.py            # Top-level Engine facade
├── plugins/                 # Plugin directory
│   └── fishing/             # Sample plugin
├── mods/                    # Mod directory
│   └── example_mod.json     # Sample mod
├── tests/                   # Test suite
├── docs/                    # Documentation
├── main.py                  # Entry point
├── engine.toml              # Configuration
├── pyproject.toml           # Python project config
└── README.md                # Project overview
```

## Coding Conventions

### Python Version
- Target Python 3.11+
- Use `from __future__ import annotations` for forward references
- Use modern typing: `list[str]` not `List[str]`, `dict[str, int]` not `Dict[str, int]`

### File Organization
- One primary class per file (small helpers OK)
- Files < 500 lines preferred
- Use `__init__.py` to re-export public API

### Naming
- Modules: `snake_case`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

### Type Hints
- All public functions must have type hints
- Use `Optional[T]` not `T | None` for compatibility
- Use `dict[str, Any]` for JSON-like data

### Documentation
- Module-level docstring at top of every file
- Class docstring for every class
- Function docstring for public functions
- Use Google-style docstrings

### Error Handling
- Use specific exceptions, not bare `Exception`
- Log errors with `get_logger(__name__)`
- Don't catch exceptions silently — at minimum log them

## Adding a New Subsystem

To add a new subsystem (e.g., `mining`):

1. Create `engine/mining/__init__.py` with re-exports
2. Create `engine/mining/system.py` with the main classes
3. Add the subsystem to `engine/engine.py`:
   ```python
   from engine.mining.system import MiningSystem
   # In Engine.__init__:
   self.mining = MiningSystem(self.rng)
   ```
4. Wire it into the simulation loop in `tick_simulation`
5. Add serialization to `save_game` and `load_game`
6. Write tests in `tests/test_mining.py`
7. Document in `docs/ARCHITECTURE.md`

## ECS Component Pattern

Components are pure data:

```python
from engine.core.ecs import Component
from dataclasses import dataclass

@dataclass
class MiningSite(Component):
    """A mining site component."""
    resource_type: str = "iron"
    remaining: int = 1000
    difficulty: float = 1.0
```

Systems operate on components:

```python
class MiningSystem:
    def update(self, world: World, dt: float) -> None:
        for entity, (site,) in world.view(MiningSite):
            site.remaining = max(0, site.remaining - int(dt * 10))
```

## Event Pattern

Define events as dataclasses inheriting from `Event`:

```python
from engine.core.events import Event

class OreDepletedEvent(Event):
    def __init__(self, site_id: int):
        super().__init__()
        self.site_id = site_id
```

Subscribe and dispatch:

```python
bus.subscribe(OreDepletedEvent, handler, priority=Priority.NORMAL)
bus.dispatch(OreDepletedEvent(site_id=42))
```

## Registry Pattern

Use class-level dicts with lazy default loading:

```python
class ResourceLibrary:
    _resources: ClassVar[dict[str, Resource]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, resource: Resource) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._resources[resource.id] = resource

    @classmethod
    def get(cls, resource_id: str) -> Optional[Resource]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._resources.get(resource_id)

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for r in DEFAULT_RESOURCES:
            cls._resources[r.id] = r
        cls._defaults_loaded = True
```

## Serialization Pattern

Every serializable class should have `to_dict` and `from_dict`:

```python
@dataclass
class MyData:
    field1: int
    field2: str

    def to_dict(self) -> dict:
        return {"field1": self.field1, "field2": self.field2}

    @classmethod
    def from_dict(cls, data: dict) -> "MyData":
        return cls(field1=data["field1"], field2=data["field2"])
```

## Testing

### Test Structure
- Unit tests: `tests/test_<module>.py`
- Integration tests: `tests/test_integration.py`
- Performance tests: `tests/test_performance.py`

### Test Naming
- Test functions: `test_<behavior>`
- Use descriptive names: `test_player_takes_damage_when_attacked`

### Fixtures
- Use pytest fixtures for shared setup
- Common fixtures: `engine`, `world`, `player`

```python
@pytest.fixture
def engine():
    config = EngineConfig()
    config.ui.color_enabled = False
    return Engine(config, headless=True)
```

### Running Tests
```bash
# All tests
python -m pytest tests/

# Verbose
python -m pytest tests/ -v

# Specific test
python -m pytest tests/test_combat.py::test_attack_resolves

# With coverage
python -m pytest tests/ --cov=engine
```

## Performance Considerations

### ECS Queries
- `World.view(*comp_types)` picks the rarest component type as the lead
- For very large worlds, consider archetypes (grouping entities by component signature)

### Caching
- Use `LRUCache` for repeated computations
- Use `TTLCache` for data that expires
- Use `LazyValue` for one-time expensive computations

### Object Pooling
- Use `ObjectPool` for frequently created/destroyed objects (e.g., damage instances, pathfinding nodes)

### Profiling
```python
from engine.performance.profiler import profiler

with profiler.scope("my_expensive_operation"):
    # ... code ...
```

Print a report:
```python
print(profiler.print_report())
```

## Save Compatibility

### Schema Versioning
- The save format has a `format_version` field
- Migrations are registered with the `@migration` decorator
- Always bump the version when adding breaking changes

```python
from engine.serialization.save import migration

@migration(1)
def migrate_v1_to_v2(data: dict) -> dict:
    data["new_field"] = "default"
    data["format_version"] = 2
    return data
```

### Plugin Save Data
Plugins should version their own save data:

```python
from engine.plugins.migrations import PluginMigrator

migrator = PluginMigrator()

@migrator.migration("my_plugin", "0.1.0", "0.2.0")
def migrate(data):
    data["new_field"] = "default"
    return data
```

## Adding Commands

```python
from engine.commands.system import Command, CommandContext, CommandResult

def _cmd_mine(ctx: CommandContext) -> CommandResult:
    if ctx.player is None:
        return CommandResult(success=False, error="No player.")
    # ... mining logic ...
    return CommandResult(success=True, output="You mine 5 iron ore.")

# In Engine.__init__ or plugin on_enable:
self.commands.register(Command(
    name="mine", handler=_cmd_mine,
    description="Mine for ore.",
    usage="mine",
    aliases=["m"],
))
```

## Adding UI Screens

```python
from engine.ui.screens import Screen

class MiningScreen(Screen):
    name = "mining"

    def render(self, engine):
        r = self.renderer
        r.clear()
        r.draw_box(0, 0, r.width, r.height, title="Mining")
        # ... render mining UI ...
        r.render()

# Register:
self.screens.register_screen(MiningScreen(self.renderer, self.i18n))
```

## Debugging

### Logging
```python
from engine.core.logging import get_logger
log = get_logger("my_module")
log.info("Something happened: %s", value)
log.debug("Detailed info: %s", detail)
log.warning("Unexpected: %s", issue)
log.error("Failed: %s", error)
```

### Debug Mode
Run with `--debug` to enable:
- Debug log level
- Cheat commands (`spawn`)
- Visibility of all map tiles
- Owner-level permissions

### Profiler
```python
from engine.performance.profiler import profiler
profiler.enable()
# ... run game ...
print(profiler.print_report())
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new features
4. Ensure all tests pass: `python -m pytest tests/`
5. Update documentation
6. Submit a pull request

### Commit Messages
Use conventional commits:
- `feat: add mining system`
- `fix: resolve pathfinding bug in caves`
- `docs: update plugin guide`
- `test: add dungeon generation tests`
- `refactor: extract damage calculation`
