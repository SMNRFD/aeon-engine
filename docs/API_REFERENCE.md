# Aeon Engine — API Reference

This document lists the public API for each subsystem.

## Core

### `engine.core.ecs`

#### `Entity(id: int, generation: int = 0)`
- `id: int` — unique entity id
- `generation: int` — bumped on destruction

#### `Component`
Base class for all components. Subclass to define a component type.

#### `World`
- `create_entity() -> Entity`
- `destroy_entity(entity: Entity) -> None`
- `is_alive(entity: Entity) -> bool`
- `add_component(entity: Entity, component: Component) -> Component`
- `remove_component(entity: Entity, comp_type: Type[T]) -> Optional[T]`
- `get_component(entity: Entity, comp_type: Type[T]) -> Optional[T]`
- `has_component(entity: Entity, comp_type: Type[Component]) -> bool`
- `get_components(entity: Entity) -> dict[Type[Component], Component]`
- `entities_with(comp_type: Type[Component]) -> set[Entity]`
- `view(*comp_types: Type[Component]) -> Iterator[tuple[Entity, tuple[Component, ...]]]`
- `tag(entity: Entity, tag: str) -> None`
- `untag(entity: Entity, tag: str) -> None`
- `has_tag(entity: Entity, tag: str) -> bool`
- `entities_with_tag(tag: str) -> set[Entity]`
- `add_system(system: System) -> None`
- `update(dt: float) -> None`
- `on_component_change(comp_type: Type[Component], callback: Callable) -> None`

### `engine.core.events`

#### `Event`
- `cancelled: bool`
- `propagation_stopped: bool`
- `timestamp: float`
- `source: Optional[str]`
- `cancel() -> None`
- `stop_propagation() -> None`

#### `Priority(IntEnum)`
- `MONITOR = 0` — always runs, cannot cancel
- `HIGHEST = 10`
- `HIGH = 25`
- `NORMAL = 50`
- `LOW = 75`
- `LOWEST = 100`

#### `EventBus`
- `subscribe(event_type: Type[E], handler: HandlerFn, priority: Priority = NORMAL, plugin: Optional[str] = None) -> None`
- `unsubscribe(event_type: Type[E], handler: HandlerFn) -> None`
- `unsubscribe_plugin(plugin_name: str) -> int`
- `dispatch(event: Event) -> bool`
- `async dispatch_async(event: Event) -> bool`
- `stats() -> dict[str, dict[str, Any]]`
- `clear() -> None`

### `engine.core.clock`

#### `GameClock(ticks_per_second=20, ticks_per_game_minute=10, ...)`
- `tick(dt: Optional[float] = None) -> None`
- `advance_ticks(ticks: int) -> None`
- `pause() -> None`
- `resume() -> None`
- `toggle_pause() -> bool`
- `set_time_scale(scale: float) -> None`
- `time: GameTime`

#### `GameTime`
- `tick: int`
- `minute: int`
- `hour: int`
- `day: int`
- `season: int`
- `year: int`
- `phase_of_day() -> PhaseOfDay`
- `season_name() -> str`
- `display() -> str`
- `to_dict() -> dict`
- `from_dict(data: dict) -> GameTime`

### `engine.core.config`

#### `EngineConfig`
Top-level configuration dataclass with nested:
- `WorldConfig` — `world_seed`, `world_tiles_x`, `world_tiles_y`, etc.
- `SimulationConfig` — `ticks_per_second`, `ticks_per_game_minute`, etc.
- `PluginConfig` — `plugin_dirs`, `hot_reload`, `sandbox_enabled`
- `SaveConfig` — `save_dir`, `autosave_interval_ticks`, `compression`
- `UIConfig` — `theme`, `color_enabled`, `viewport_width`, `viewport_height`

- `load_config(path: Optional[Path] = None) -> EngineConfig`
- `get_config() -> EngineConfig`
- `set_config(cfg: EngineConfig) -> None`

### `engine.core.logging`

- `configure_logging(level: int = INFO, log_file: Optional[Path] = None, ...) -> None`
- `get_logger(name: str = "engine") -> logging.Logger`

## Engine

### `engine.engine.Engine`

```python
Engine(config: Optional[EngineConfig] = None, headless: bool = False)
```

#### Properties
- `config: EngineConfig`
- `event_bus: EventBus`
- `world: World`
- `clock: GameClock`
- `items: ItemRegistry`
- `combat: CombatSystem`
- `skills: SkillsSystem`
- `crafting: CraftingSystem`
- `spell_caster: SpellCaster`
- `dialogue: DialogueEngine`
- `quest_generator: QuestGenerator`
- `factions: FactionSystem`
- `economy: EconomySystem`
- `weather: WeatherSystem`
- `survival: SurvivalSystem`
- `needs_system: NeedsSystem`
- `ai_registry: AIRegistry`
- `save_manager: SaveManager`
- `plugins: PluginManager`
- `commands: CommandRegistry`
- `command_processor: CommandProcessor`
- `world_map: Optional[WorldMap]`
- `pathfinder: Optional[AStarPathfinder]`
- `player: Optional[Entity]`
- `i18n: I18n`
- `message_log: MessageLog`

#### Methods
- `generate_world(params: Optional[WorldGenParams] = None) -> None`
- `create_player(name: str = "Hero") -> Entity`
- `start() -> None`
- `shutdown() -> None`
- `tick_simulation(dt: Optional[float] = None) -> None`
- `move_player(dx: int, dy: int) -> bool`
- `save_game(name: str) -> None`
- `load_game(name: str) -> None`
- `register_command(name: str, handler: Any, **kwargs: Any) -> None`
- `message(text: str, color: int = WHITE) -> None`

## Items

### `engine.items.item.Item`

#### Class Methods
- `from_dict(data: dict) -> Item`

#### Instance Properties
- `id: int`
- `base_type: str`
- `name: str`
- `material_id: str`
- `quality: ItemQuality`
- `rarity: ItemRarity`
- `level: int`
- `weight: float`
- `value: int`
- `durability: int`
- `durability_max: int`
- `properties: dict[str, ItemProperty]`
- `prefixes: list[Affix]`
- `suffixes: list[Affix]`
- `enchantments: list[dict]`
- `display_name: str` (computed)
- `is_broken: bool`
- `total_weight: float`
- `total_value: int`

#### Methods
- `damage(amount: int) -> None`
- `repair(amount: Optional[int] = None) -> None`
- `add_owner(entity_id: int) -> None`
- `append_history(entry: str) -> None`
- `property_value(key: str, default: float = 0.0) -> float`
- `add_property(key: str, value: float, mode: str = "add") -> None`
- `to_dict() -> dict`

### `engine.items.generator.ItemGenerator`

```python
ItemGenerator(rng: Optional[RNG] = None)
```

- `generate(params: ItemGenerationParams, item_id: int) -> Item`

### `engine.items.registry.ItemRegistry`

- `register(item: Item) -> Item`
- `get(item_id: int) -> Optional[Item]`
- `remove(item_id: int) -> Optional[Item]`
- `all() -> list[Item]`
- `next_id() -> int`
- `to_dict() -> dict`
- `load_from_dict(data: dict) -> None`

### `engine.items.materials.MaterialLibrary`

- `register(material: Material) -> None`
- `get(material_id: str) -> Optional[Material]`
- `all() -> list[Material]`
- `by_category(category: str) -> list[Material]`

### `engine.items.affixes.AffixLibrary`

- `register(affix: Affix) -> None`
- `get(affix_id: str) -> Optional[Affix]`
- `all() -> list[Affix]`
- `prefixes() -> list[Affix]`
- `suffixes() -> list[Affix]`
- `prefixes_for(category: str) -> list[Affix]`
- `suffixes_for(category: str) -> list[Affix]`

## Combat

### `engine.combat.system.CombatSystem`

```python
CombatSystem(rng: Optional[RNG] = None,
             status_system: Optional[StatusEffectSystem] = None,
             item_registry=None)
```

- `attack(world: World, attacker: Entity, target: Entity, weapon_item=None) -> AttackResult`
- `resolve_combat(world: World, attacker: Entity, target: Entity, max_rounds: int = 20) -> CombatResult`

### `engine.combat.damage.DamageCalculator`

- `compute(damage: Damage, target_stats: Optional[Stats], target_armor: float = 0.0, target_resistances: Optional[dict[DamageType, float]] = None, target_vulnerabilities: Optional[dict[DamageType, float]] = None) -> float` (static)

### `engine.combat.effects.StatusEffectSystem`

- `apply(world: World, entity: Entity, effect_name: str, duration: Optional[float] = None, magnitude: Optional[float] = None, source: Optional[int] = None) -> Optional[StatusEffectInstance]`
- `remove(world: World, entity: Entity, effect_name: str) -> bool`
- `update(world: World, dt: float) -> None`
- `active_stat_modifiers(world: World, entity: Entity) -> dict[str, float]`
- `is_controlled(world: World, entity: Entity) -> bool`

## World

### `engine.world.generator.WorldGenerator`

```python
WorldGenerator(params: WorldGenParams)
```

- `generate() -> WorldMap`

### `engine.world.pathfinding.AStarPathfinder`

```python
AStarPathfinder(world: WorldMap)
```

- `find_path(start: tuple[int, int], goal: tuple[int, int], max_iterations: int = 50000, allow_diagonal: bool = True, allow_road_penalty: bool = True) -> Optional[list[tuple[int, int]]]`
- `path_length(path: list[tuple[int, int]]) -> float`

### `engine.world.spatial.SpatialGrid`

```python
SpatialGrid(cell_size: int = 16)
```

- `insert(entity: T, x: float, y: float) -> None`
- `remove(entity: T) -> None`
- `update(entity: T, x: float, y: float) -> None`
- `query_radius(x: float, y: float, radius: float) -> list[tuple[T, float]]`
- `query_cell(x: float, y: float) -> set[T]`
- `query_box(x1: float, y1: float, x2: float, y2: float) -> list[T]`
- `nearest(x: float, y: float, k: int = 1) -> list[tuple[T, float]]`

## NPC AI

### `engine.npc.ai.AIRegistry`

- `register(controller: AIController) -> None`
- `get(name: str) -> Optional[AIController]`
- `all() -> list[AIController]`

### Controllers
- `WanderAI` — wandering creatures
- `AggressiveAI` — hostile creatures that hunt
- `CivilianAI` — schedule-driven NPCs
- `PlayerAI` — player (no-op, awaiting input)

## Plugins

### `engine.plugins.manager.PluginManager`

```python
PluginManager(engine: Any, plugin_dirs: Optional[list[str]] = None)
```

- `discover() -> int`
- `load_all() -> tuple[int, int]`
- `enable(name: str) -> None`
- `disable(name: str) -> None`
- `unload(name: str) -> None`
- `reload(name: str) -> None`
- `enable_all() -> None`
- `disable_all() -> None`
- `status() -> list[dict[str, Any]]`

### `engine.plugins.base.Plugin`

Subclass and override:
- `on_load(engine) -> None`
- `on_enable(engine) -> None`
- `on_disable(engine) -> None`
- `on_unload(engine) -> None`
- `on_reload(engine) -> None`

### `engine.plugins.base.PluginMetadata`

```python
PluginMetadata(
    name: str,
    version: str,
    description: str = "",
    author: str = "",
    license: str = "MIT",
    dependencies: list[str] = [],
    conflicts: list[str] = [],
    permissions: list[str] = [],
    api_version: str = "0.1",
    tags: list[str] = [],
    load_order: int = 1000,
)
```

## Save System

### `engine.serialization.save.SaveManager`

```python
SaveManager(save_dir: str = "saves",
            compression: str = "zlib",
            integrity_check: bool = True)
```

- `save(name: str, data: SaveData, **kwargs) -> Path`
- `load(name: str) -> SaveData`
- `delete(name: str) -> bool`
- `exists(name: str) -> bool`
- `list_slots() -> list[SaveSlot]`
- `autosave(data: SaveData, max_autosaves: int = 5, **kwargs) -> Path`

## Commands

### `engine.commands.system.CommandRegistry`

- `register(command: Command) -> None`
- `unregister(name: str) -> None`
- `get(name: str) -> Optional[Command]`
- `all() -> list[Command]`
- `names() -> list[str]`
- `add_macro(name: str, expansion: str) -> None`
- `add_history(raw: str) -> None`
- `autocomplete(partial: str) -> list[str]`

### `engine.commands.system.CommandProcessor`

- `execute(raw_input: str, ctx: CommandContext) -> CommandResult`

## Localization

### `engine.localization.i18n.I18n`

```python
I18n(locale: str = "en_US")
```

- `set_locale(code: str) -> None`
- `add_strings(locale: str, strings: dict[str, str]) -> None`
- `t(key: str, **kwargs) -> str` — translate
- `tn(key: str, n: int, **kwargs) -> str` — translate with plural
- `rtl: bool` — right-to-left?
- `available_locales() -> list[str]`

## Performance

### `engine.performance.pool.ObjectPool`

```python
ObjectPool(factory: PooledFactory[T],
           initial_size: int = 0,
           max_size: int = 100,
           block: bool = True,
           timeout: float = 1.0)
```

- `acquire() -> T | None`
- `release(obj: T) -> None`
- `stats() -> dict[str, int]`
- `clear() -> None`

### `engine.performance.profiler.Profiler`

- `scope(name: str) -> ContextManager[ProfileScope]`
- `enable() -> None`
- `disable() -> None`
- `reset() -> None`
- `stats() -> dict[str, Any]`
- `top_slowest(n: int = 10) -> list[tuple[str, float, int]]`
- `print_report(n: int = 20) -> str`

### `engine.performance.cache.LRUCache`

```python
LRUCache(capacity: int = 128)
```

- `get(key: K, default: Any = None) -> Any`
- `put(key: K, value: V) -> None`
- `remove(key: K) -> None`
- `clear() -> None`
- `stats() -> dict[str, int]`

### `engine.performance.cache.TTLCache`

```python
TTLCache(ttl_seconds: float = 60.0, capacity: int = 256)
```

- `get(key: K, default: Any = None) -> Any`
- `put(key: K, value: V, ttl: Optional[float] = None) -> None`
- `cleanup_expired() -> int`
- `stats() -> dict[str, Any]`

## Scripting

### `engine.scripting.interpreter.ScriptEngine`

- `register_script(name: str, source: str) -> None`
- `get_script(name: str) -> Optional[str]`
- `run(name: str, context: Optional[ScriptContext] = None) -> ScriptResult`
- `run_source(source: str, context: Optional[ScriptContext] = None) -> ScriptResult`
- `call(name: str, function_name: str, args: tuple = (), kwargs: Optional[dict] = None, context: Optional[ScriptContext] = None) -> ScriptResult`
- `list_scripts() -> list[str]`

### `engine.scripting.interpreter.ScriptContext`

```python
ScriptContext(
    engine: Any = None,
    entity: Any = None,
    world: Any = None,
    event_bus: Any = None,
    rng: Any = None,
    variables: dict[str, Any] = {},
    timeout: float = 5.0,
    max_operations: int = 1_000_000,
)
```
