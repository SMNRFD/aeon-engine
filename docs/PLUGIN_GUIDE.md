# Aeon Engine — Plugin Development Guide

This guide covers how to develop, package, and distribute plugins for the Aeon Engine.

## Quick Start

A plugin is a Python module at `plugins/<name>/plugin.py` that exports a `Plugin` subclass.

### Minimal Plugin

```python
# plugins/my_plugin/plugin.py
from engine.plugins.base import Plugin, PluginMetadata

class MyPlugin(Plugin):
    metadata = PluginMetadata(
        name="my_plugin",
        version="0.1.0",
        description="My awesome plugin.",
        author="Your Name",
        license="MIT",
        tags=["gameplay"],
        load_order=100,
    )

    def on_load(self, engine):
        self.logger.info("My plugin is loading!")

    def on_enable(self, engine):
        self.logger.info("My plugin is enabled!")

    def on_disable(self, engine):
        self.logger.info("My plugin is disabled.")
```

## Lifecycle Hooks

Plugins override these lifecycle hooks:

| Hook | When Called |
|------|-------------|
| `on_load(engine)` | Once after the module is imported |
| `on_enable(engine)` | When the plugin is enabled |
| `on_disable(engine)` | When the plugin is disabled |
| `on_unload(engine)` | When the module is being unloaded |
| `on_reload(engine)` | On hot reload (after `on_disable`, before `on_enable`) |

## Metadata Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | str | Plugin identifier (lowercase, snake_case) |
| `version` | str | Semantic version (e.g., "1.0.0") |
| `description` | str | Human-readable description |
| `author` | str | Author name |
| `license` | str | License identifier |
| `dependencies` | list[str] | Required plugins with version constraints |
| `conflicts` | list[str] | Incompatible plugins |
| `permissions` | list[str] | Required permissions |
| `api_version` | str | Engine API version |
| `tags` | list[str] | Categorisation tags |
| `load_order` | int | Lower loads first (default 1000) |

### Dependency Version Constraints

Dependencies use the format `plugin_name<operator><version>`:

- `core>=1.0` — at least version 1.0
- `core==2.0.0` — exactly version 2.0.0
- `core!=1.5.0` — any version except 1.5.0
- `core>1.0` — greater than 1.0
- `core<2.0` — less than 2.0

## Registering Commands

```python
from engine.commands.system import Command, CommandContext, CommandResult, Permission

def _cmd_greet(ctx: CommandContext) -> CommandResult:
    name = ctx.args[0] if ctx.args else "world"
    return CommandResult(success=True, output=f"Hello, {name}!")

class MyPlugin(Plugin):
    # ...
    def on_enable(self, engine):
        engine.register_command(
            "greet", _cmd_greet,
            description="Greet someone.",
            usage="greet [name]",
            aliases=["hi"],
            permission=Permission.PLAYER,
            plugin=self.metadata.name,
        )
```

## Subscribing to Events

```python
from engine.core.events import Event, EventBus, Priority

class MyEvent(Event):
    def __init__(self, message: str):
        super().__init__()
        self.message = message

def _on_my_event(event: MyEvent):
    print(f"Got event: {event.message}")

class MyPlugin(Plugin):
    # ...
    def on_enable(self, engine):
        engine.event_bus.subscribe(
            MyEvent, _on_my_event,
            priority=Priority.NORMAL,
            plugin=self.metadata.name,
        )
```

## Registering Skills, Items, Spells

```python
from engine.skills.system import Skill, SkillLibrary
from engine.items.generator import ARCHETYPES, BaseItemArchetype
from engine.magic.spells import Spell, SpellLibrary

class MyPlugin(Plugin):
    def on_load(self, engine):
        # Add a new skill
        SkillLibrary.register(Skill(
            id="dragon_taming",
            name="Dragon Taming",
            description="Tame and ride dragons.",
            category="survival",
            governing_attribute="charisma",
            difficulty=2.0,
        ))

        # Add a new item archetype
        ARCHETYPES["dragon_scale_armor"] = BaseItemArchetype(
            base_type="dragon_scale_armor",
            name="dragon scale armour",
            category="armor",
            weight_kg=8.0, volume_l=4.0,
            base_value=2000, durability=200,
            icon="]", color=22,
            default_material="dragonbone",
            allowed_material_categories=("bone", "metal"),
            base_properties={"armor": 15.0, "fire_resist": 0.5},
        )
```

## Plugin Assets

Plugin assets (data files, configs, localization) live alongside `plugin.py`:

```
plugins/my_plugin/
├── plugin.py
├── config.toml          # plugin configuration
├── items.json           # item definitions
├── locale/
│   ├── en_US.json
│   └── fr_FR.json
└── README.md
```

Load them in `on_load`:

```python
import json
from pathlib import Path

class MyPlugin(Plugin):
    def on_load(self, engine):
        plugin_dir = Path(__file__).parent
        config_path = plugin_dir / "config.toml"
        if config_path.exists():
            import tomllib
            with config_path.open("rb") as f:
                self.config = tomllib.load(f)
```

## Hot Reload

Plugins can be hot-reloaded at runtime:

```python
engine.plugins.reload("my_plugin")
```

This calls `on_disable`, reloads the module, then calls `on_reload` and `on_enable`.

## Sandboxing

Untrusted plugins can be run in a sandbox:

```python
from engine.plugins.sandbox import PluginSandbox

sandbox = PluginSandbox(max_cpu_seconds=5.0)
result = sandbox.execute_with_timeout(source, "my_plugin", api={...})
```

The sandbox:
- Validates source for forbidden patterns (imports, function calls)
- Restricts file access to the plugin's data directory
- Enforces CPU time limits
- Audits sensitive API calls

## Plugin Validation

Validate plugins before distribution:

```python
from engine.plugins.validation import PluginValidator

validator = PluginValidator()
result = validator.validate_metadata(metadata)
if not result.is_valid:
    print(result)
```

## Plugin Documentation Generation

Auto-generate docs for your plugin:

```python
from engine.plugins.docs import PluginDocGenerator

gen = PluginDocGenerator()
doc = gen.generate(Path("plugins/my_plugin/plugin.py"), metadata)
gen.save_markdown(doc, Path("docs/my_plugin.md"))
gen.save_json(doc, Path("docs/my_plugin.json"))
```

## Save Data Migrations

When your plugin's save format changes, register migrations:

```python
from engine.plugins.migrations import PluginMigrator

migrator = PluginMigrator()

@migrator.migration("my_plugin", "0.1.0", "0.2.0",
                    description="Add new field")
def migrate_v1_to_v2(data):
    data["new_field"] = "default"
    return data

# On load:
data = migrator.migrate("my_plugin", loaded_data, target_version="0.2.0")
```

## Distribution

Package your plugin as a ZIP:

```
my_plugin.zip
└── my_plugin/
    ├── plugin.py
    ├── config.toml
    └── README.md
```

Install via the installer:

```python
from engine.plugins.installer import PluginInstaller

installer = PluginInstaller(engine.plugins)
installer.install_from_zip(Path("my_plugin.zip"))
# or from a URL:
installer.install_from_url("https://example.com/my_plugin.zip",
                            expected_hash="abc123...")
```

## Complete Example

See `plugins/fishing/plugin.py` for a complete plugin that:
- Registers a new skill (fishing)
- Registers a new command (fish)
- Subscribes to a custom event (FishingEvent)
- Generates items procedurally
- Awards XP for successful fishing
