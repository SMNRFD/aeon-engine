"""Aeon Engine — top-level engine class wiring all subsystems together."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from engine.core.clock import GameClock, Season
from engine.core.config import EngineConfig, get_config
from engine.core.ecs import Entity, World
from engine.core.events import EventBus, Event
from engine.core.logging import configure_logging, get_logger
from engine.commands.system import (
    CommandRegistry, CommandProcessor, CommandContext, CommandResult,
    DEFAULT_COMMANDS, Permission,
)
from engine.combat.system import CombatSystem
from engine.combat.effects import StatusEffectSystem
from engine.crafting.system import CraftingSystem, RecipeLibrary
from engine.dialogue.system import DialogueEngine, DialogueLibrary
from engine.entities.factory import EntityFactory
from engine.economy.market import EconomySystem, TradeGoodLibrary
from engine.factions.system import FactionLibrary, FactionSystem
from engine.inventory.inventory import Inventory
from engine.items.generator import ItemGenerator, ItemGenerationParams
from engine.items.item import Item
from engine.items.registry import ItemRegistry
from engine.localization.i18n import I18n
from engine.magic.research import SpellResearcher
from engine.magic.spells import SpellCaster, SpellLibrary, Mana
from engine.npc.ai import AIRegistry, AIContext, default_registry, PlayerAI
from engine.npc.memory import NPCMemory
from engine.npc.needs import NeedsSystem
from engine.plugins.manager import PluginManager
from engine.quests.system import QuestGenerator, QuestLibrary, QuestTracker
from engine.render.terminal import Color, TerminalRenderer
from engine.serialization.save import SaveData, SaveManager
from engine.skills.system import SkillsSystem, SkillLibrary
from engine.survival.system import SurvivalSystem, DiseaseLibrary
from engine.ui.screens import (
    CharacterScreen, HelpScreen, InventoryScreen, MainScreen, MapScreen,
    MessageLog, ScreenManager,
)
from engine.utils.rng import RNG
from engine.weather.system import WeatherSystem
from engine.world.generator import WorldGenParams, WorldGenerator
from engine.world.map import WorldMap
from engine.world.pathfinding import AStarPathfinder
from engine.world.spatial import SpatialGrid


log = get_logger("engine")


class Engine:
    """The top-level engine facade."""

    def __init__(self, config: Optional[EngineConfig] = None,
                 headless: bool = False) -> None:
        self.config = config or get_config()
        import logging as _logging
        level_value = (self.config.log_level.upper() if isinstance(self.config.log_level, str)
                       else self.config.log_level)
        if isinstance(level_value, str):
            level_value = getattr(_logging, level_value, _logging.INFO)
        configure_logging(
            level=level_value,
            log_file=Path(self.config.log_file) if self.config.log_file else None,
        )
        log.info("Initialising %s v%s", self.config.engine_name, self.config.version)

        self.headless = headless
        self.rng = RNG(self.config.world.world_seed)
        self.event_bus = EventBus()
        self.world = World()
        self.clock = GameClock(
            ticks_per_second=self.config.simulation.ticks_per_second,
            ticks_per_game_minute=self.config.simulation.ticks_per_game_minute,
            minutes_per_hour=self.config.simulation.minutes_per_game_hour,
            hours_per_day=self.config.simulation.hours_per_day,
            days_per_season=self.config.simulation.days_per_season,
            seasons_per_year=self.config.simulation.seasons_per_year,
        )

        # Subsystem managers
        self.items = ItemRegistry()
        self.item_generator = ItemGenerator(self.rng)
        self.inventories: dict[int, Inventory] = {}
        self.factory = EntityFactory(self.world, self.rng)

        # Combat
        self.status_system = StatusEffectSystem()
        self.combat = CombatSystem(self.rng, self.status_system, self.items)

        # Skills
        self.skills = SkillsSystem()

        # Crafting
        self.crafting = CraftingSystem(self.item_generator, self.rng)

        # Magic
        self.spell_caster = SpellCaster(self.status_system, self.rng)
        self.spell_researcher = SpellResearcher(self.rng)

        # Dialogue
        self.dialogue = DialogueEngine(self.skills, self.rng)

        # Quests
        self.quest_generator = QuestGenerator(self.rng)
        self.quest_trackers: dict[int, QuestTracker] = {}

        # Factions
        self.factions = FactionSystem(self.rng)

        # Economy
        self.economy = EconomySystem(self.rng)

        # Weather & Survival
        self.weather = WeatherSystem(self.rng)
        self.survival = SurvivalSystem(self.rng)

        # Needs
        self.needs_system = NeedsSystem()

        # AI
        self.ai_registry = default_registry()

        # World
        self.world_map: Optional[WorldMap] = None
        self.pathfinder: Optional[AStarPathfinder] = None
        self.spatial = SpatialGrid(cell_size=8)

        # Player
        self.player: Optional[Entity] = None

        # Localization
        self.i18n = I18n()

        # Commands
        self.commands = CommandRegistry()
        for cmd in DEFAULT_COMMANDS:
            self.commands.register(cmd)
        self.command_processor = CommandProcessor(self.commands)

        # Save
        self.save_manager = SaveManager(
            save_dir=self.config.save.save_dir,
            compression=self.config.save.compression,
            integrity_check=self.config.save.integrity_check,
        )

        # Plugins
        self.plugins = PluginManager(self, self.config.plugins.plugin_dirs)

        # UI
        if not headless:
            self.renderer = TerminalRenderer(
                width=self.config.ui.viewport_width,
                height=self.config.ui.viewport_height,
                use_color=self.config.ui.color_enabled,
            )
            self.message_log = MessageLog(max_size=self.config.ui.message_log_size)
            self.screens = ScreenManager(self.renderer, self.i18n)
            self._register_screens()
        else:
            self.renderer = None
            self.message_log = MessageLog(max_size=200)
            self.screens = None

        self.current_input: str = ""
        self.cheat_mode: bool = self.config.debug
        self._running = False
        # When True, the player is dead and the simulation pauses for the
        # player until respawn_player() or new_game() is called.
        self.player_dead: bool = False
        self._last_tick_time: float = 0.0
        self._last_autosave_tick: int = 0

        # ----- Bannerlord-style travel / follow / auto-attack state -----
        # When True, the engine auto-attacks adjacent hostiles at the end of
        # each tick (after the AI has acted). Toggled via cmd_autoattack.
        self.auto_attack_enabled: bool = False
        # Pending travel path (list of (x, y) tiles). When non-empty, each
        # tick consumes the next tile and walks the player there, while the
        # world keeps simulating around them — exactly like Mount & Blade's
        # overland travel.
        self._travel_path: list[tuple[int, int]] = []
        # When non-None, the engine walks the player toward this entity's
        # position each tick (catch-up / pursuit). Cleared when the entity
        # dies or the player catches up.
        self._follow_target_id: Optional[int] = None
        # When non-None, the engine has detected a hostile encounter and the
        # REPL should show the encounter panel next tick. Set by move_player
        # on a hostile bump; cleared by the REPL after the player chooses.
        self.pending_encounter_id: Optional[int] = None
        # Settlements placed at world-gen (list of (x, y, name)). Used by
        # the holy-map renderer and the structure layer.
        self.settlements: list[tuple[int, int, str]] = []
        # Placed structures (instances on the map). Keyed by placement_id.
        self.structure_placements: dict[int, Any] = {}
        self._next_placement_id: int = 1

        log.info("Engine initialised")

    # ---------- world setup ----------

    def generate_world(self, params: Optional[WorldGenParams] = None) -> None:
        params = params or WorldGenParams(
            seed=self.config.world.world_seed,
            width=self.config.world.world_tiles_x // 2,
            height=self.config.world.world_tiles_y // 2,
            sea_level=self.config.world.sea_level,
            mountain_level=self.config.world.mountain_level,
            temperature_noise_scale=self.config.world.temperature_noise_scale,
            moisture_noise_scale=self.config.world.moisture_noise_scale,
            enable_rivers=self.config.world.enable_rivers,
            enable_roads=self.config.world.enable_roads,
        )
        generator = WorldGenerator(params)
        self.world_map = generator.generate()
        self.pathfinder = AStarPathfinder(self.world_map)
        # Generate a few settlements with NPCs
        self._populate_world()
        log.info("World generated: %dx%d", self.world_map.width, self.world_map.height)

    def _populate_world(self) -> None:
        """Spawn NPCs, creatures, villages, castles and kingdom territories."""
        if self.world_map is None:
            return
        from engine.world.terrain import TerrainType
        # Find walkable tiles for spawning
        walkable = [t for t in self.world_map.iter_tiles()
                    if t.is_walkable and t.terrain_type != TerrainType.ROAD]
        self.rng.shuffle(walkable)
        density = self.config.world.initial_npc_density
        npc_count = int(len(walkable) * density)
        # Cap NPC count for performance in this build
        npc_count = min(npc_count, 60)
        for i in range(npc_count):
            tile = walkable[i]
            name = self._random_name()
            npc = self.factory.create_npc(
                name=name, x=tile.x, y=tile.y,
                faction_id=self.rng.randint(1, 5) if self.rng.chance(0.6) else None,
            )
            # Add a basic inventory
            self.inventories[npc.id] = Inventory(capacity=15, max_weight=30.0)
            self.spatial.insert(npc, tile.x, tile.y)
        # Spawn some creatures — fewer, more balanced
        creature_types = [
            ("Wolf", "w", Color.GRAY, 25, 8, 12, True),
            ("Deer", "d", Color.BROWN, 18, 4, 14, False),
            ("Rat", "r", Color.DARK_GRAY, 6, 2, 14, True),
            ("Goblin", "g", Color.GREEN, 20, 7, 10, True),
            ("Bandit", "b", Color.RED, 35, 10, 10, True),
        ]
        # Scale creature count with world size
        creature_count = min(20, max(5, (self.world_map.width * self.world_map.height) // 200))
        for _ in range(creature_count):
            tile = self.rng.choice(walkable)
            name, glyph, color, hp, strn, agi, hostile = self.rng.choice(creature_types)
            creature = self.factory.create_creature(
                name=name, glyph=glyph, color=color,
                x=tile.x, y=tile.y, hp=hp, strength=strn, agility=agi,
                aggressive=hostile,
            )
            # FIX: insert the actual creature entity (was: world.create_entity())
            self.spatial.insert(creature, tile.x, tile.y)
        log.info("Populated world with %d NPCs and ~%d creatures", npc_count, creature_count)
        # ----- Place villages, castles, kingdom capitals -----
        # These are derived from the road tiles the generator placed, since
        # the generator discards the explicit settlement list. We re-discover
        # them by scanning for ROAD tiles that form small clusters.
        self._place_settlements_and_kingdoms()

    def _place_settlements_and_kingdoms(self) -> None:
        """Discover settlement clusters from ROAD tiles and place structures,
        kingdom territories, and map markers on them.

        This populates:
          * ``self.settlements`` — list of (x, y, name)
          * ``self.structure_placements`` — placed StructurePlacement instances
          * ``self.kingdoms`` (KingdomSystem) — territories + capitals
          * ``self.bookmarks`` (BookmarkManager) — map markers
        """
        if self.world_map is None:
            return
        from engine.world.terrain import TerrainType
        from engine.structures.system import (
            StructurePlacement, StructureType, StructureLibrary,
        )
        from engine.kingdoms.system import KingdomLibrary
        from engine.bookmarks.system import BookmarkManager
        # ----- 1. Discover settlement clusters from ROAD tiles -----
        road_tiles = [t for t in self.world_map.iter_tiles()
                      if t.terrain_type == TerrainType.ROAD]
        if not road_tiles:
            return
        # Cluster road tiles by connectivity (flood-fill). Each cluster is a
        # settlement. Cap at 12 to keep things sane.
        clusters: list[list[tuple[int, int]]] = []
        visited: set[tuple[int, int]] = set()
        road_set = {(t.x, t.y) for t in road_tiles}
        for t in road_tiles:
            if (t.x, t.y) in visited:
                continue
            # BFS
            stack = [(t.x, t.y)]
            cluster: list[tuple[int, int]] = []
            while stack:
                cx, cy = stack.pop()
                if (cx, cy) in visited:
                    continue
                visited.add((cx, cy))
                cluster.append((cx, cy))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue
                        if (cx + dx, cy + dy) in road_set and (cx + dx, cy + dy) not in visited:
                            stack.append((cx + dx, cy + dy))
            if len(cluster) >= 3:  # ignore tiny road fragments
                clusters.append(cluster)
            if len(clusters) >= 12:
                break
        # ----- 2. For each cluster, pick a center and name it -----
        settlement_names = [
            "Brackton", "Oakhaven", "Rivermouth", "Stonebridge", "Goldhollow",
            "Ravensford", "Whitewater", "Ironforge", "Frosthollow", "Sunpeak",
            "Mistwood", "Elderbrook", "Thornwall", "Brightmeadow", "Darkhollow",
        ]
        self.settlements = []
        for i, cluster in enumerate(clusters):
            # Pick a center: the tile closest to the cluster's centroid.
            cx = sum(p[0] for p in cluster) // len(cluster)
            cy = sum(p[1] for p in cluster) // len(cluster)
            # Find the actual road tile nearest to the centroid.
            best = min(cluster, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
            name = settlement_names[i % len(settlement_names)]
            self.settlements.append((best[0], best[1], name))
        # ----- 3. Place structures (castle + houses + inn + temple) -----
        # Reset placement state in case this is a new_game() re-population.
        self.structure_placements = {}
        self._next_placement_id = 1
        for sx, sy, name in self.settlements:
            # Castle / keep at the settlement center (mark the tile).
            self._place_structure(StructureType.CASTLE, f"{name} Castle", sx, sy)
            # Surround with 2-4 houses, an inn, and a temple on adjacent walkable tiles.
            surround_types = [
                (StructureType.HOUSE, "House"),
                (StructureType.HOUSE, "House"),
                (StructureType.INN, f"{name} Inn"),
                (StructureType.TEMPLE, f"{name} Temple"),
                (StructureType.SHOP, f"{name} Shop"),
                (StructureType.MARKET, f"{name} Market"),
            ]
            placed_count = 0
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if dx == 0 and dy == 0:
                        continue
                    if placed_count >= len(surround_types):
                        break
                    nx, ny = sx + dx, sy + dy
                    tile = self.world_map.get_tile(nx, ny)
                    if tile is None or not tile.is_walkable:
                        continue
                    if tile.terrain_type == TerrainType.ROAD:
                        continue
                    stype, sname = surround_types[placed_count]
                    self._place_structure(stype, sname, nx, ny)
                    placed_count += 1
        # ----- 4. Assign settlements to kingdoms -----
        # Make sure the kingdom system has been initialised (it's lazy on the
        # REPL side; we use a fresh KingdomSystem here just for territory
        # creation, since KingdomLibrary is the global registry).
        from engine.kingdoms.system import KingdomSystem
        ks = KingdomSystem(self.rng)
        kingdoms = KingdomLibrary.all()
        if not kingdoms:
            return
        # Each settlement becomes a territory; first settlement of each
        # kingdom becomes its capital. We assign in round-robin so each
        # kingdom gets at least one territory.
        for i, (sx, sy, sname) in enumerate(self.settlements):
            kingdom = kingdoms[i % len(kingdoms)]
            territory = ks.create_territory(
                name=sname, location=(sx, sy),
                size=self.rng.randint(50, 300),
                population=self.rng.randint(100, 5000),
                has_capital=(kingdom.capital_territory_id is None),
            )
            kingdom.territories.append(territory.territory_id)
            if kingdom.capital_territory_id is None:
                kingdom.capital_territory_id = territory.territory_id
                kingdom.population += territory.population
                kingdom.military_strength += self.rng.randint(50, 500)
        # Stash the KingdomSystem instance on the engine so the REPL's lazy
        # `kingdoms` property picks it up (it constructs a new one otherwise;
        # we'll also expose territories via the engine directly).
        self._kingdom_system = ks
        # ----- 5. Register map markers for the holy map -----
        # Use the BookmarkManager (also lazy on the REPL). We create one
        # here and stash it so the REPL's `bookmarks` property picks it up.
        bm = BookmarkManager()
        for sx, sy, sname in self.settlements:
            # Mark the settlement as a "city" marker.
            bm.add_marker(
                name=sname, x=sx, y=sy,
                marker_type="city",
                description=f"The settlement of {sname}.",
                icon="⌂", color=215,
                is_visible=True, requires_discovery=False,
            )
            # Also mark the castle.
            bm.add_marker(
                name=f"{sname} Castle", x=sx, y=sy,
                marker_type="castle",
                description=f"The castle of {sname}.",
                icon="⚰", color=220,
                is_visible=True, requires_discovery=False,
            )
        self._bookmarks_mgr = bm

    def _place_structure(self, structure_type, name: str, x: int, y: int) -> Any:
        """Place a structure on the map and register it."""
        from engine.structures.system import StructurePlacement, StructureLibrary
        arch = StructureLibrary.get(structure_type)
        placement = StructurePlacement(
            placement_id=self._next_placement_id,
            structure_type=structure_type,
            name=name,
            x=x, y=y,
            description=arch.description if arch else "",
        )
        self._next_placement_id += 1
        self.structure_placements[placement.placement_id] = placement
        # Pin to the tile so the renderer can show it.
        tile = self.world_map.get_tile(x, y) if self.world_map else None
        if tile is not None:
            tile.structure_id = placement.placement_id
        return placement

    def _random_name(self) -> str:
        first = self.rng.choice([
            "Aldric", "Brenna", "Cedric", "Daera", "Elgin", "Faye", "Garret",
            "Helena", "Ivor", "Jana", "Kael", "Lyra", "Magnus", "Nira",
            "Orin", "Petra", "Quinn", "Rhea", "Soren", "Tara", "Ulric",
            "Vera", "Wren", "Xara", "Yorin", "Zara",
        ])
        last = self.rng.choice([
            "of the Vale", "the Smith", "Ironhand", "Greycastle", "Blackwood",
            "Stormwind", "Thornfield", "Ravenhill", "Oakheart", "Brightblade",
            "the Younger", "the Elder", "of Aldor", "the Healer",
        ])
        return f"{first} {last}"

    # ---------- player ----------

    def create_player(self, name: str = "Hero") -> Entity:
        self.player = self.factory.create_player(name)
        if self.world_map is not None:
            pos = self.world.get_component(self.player, type(self.player).__class__) if False else None
            from engine.entities.components import Position
            pos = self.world.get_component(self.player, Position)
            if pos:
                pos.x = self.world_map.spawn_point.x
                pos.y = self.world_map.spawn_point.y
            self.spatial.insert(self.player, self.world_map.spawn_point.x,
                                self.world_map.spawn_point.y)
        # Give player an inventory and starter items
        inv = Inventory(capacity=30, max_weight=60.0)
        self.inventories[self.player.id] = inv
        # Starter weapon: iron dagger
        params = ItemGenerationParams(archetype="dagger", material_id="iron")
        weapon = self.item_generator.generate(params, self.items.next_id())
        self.items.register(weapon)
        inv.add(weapon)
        # Equip it — dual-write to BOTH Combat.weapon_id (for combat code)
        # AND Inventory._equipment (for inventory display). This is the
        # fix for the "equipped items not shown in inventory" bug.
        from engine.inventory.inventory import EquipmentSlot
        comp = self.world.get_component(self.player, type(self.player).__class__) if False else None
        from engine.entities.components import Combat as CombatComp
        combat_comp = self.world.get_component(self.player, CombatComp)
        if combat_comp:
            combat_comp.weapon_id = weapon.id
        # Remove from backpack and put in the MAIN_HAND equipment slot.
        inv.remove(weapon.id, 1)
        inv._equipment[EquipmentSlot.MAIN_HAND] = weapon.id
        # Starter consumables
        for archetype in ("health_potion", "health_potion", "bread", "water_flask", "torch"):
            p = ItemGenerationParams(archetype=archetype)
            it = self.item_generator.generate(p, self.items.next_id())
            self.items.register(it)
            inv.add(it)
        # Mana component
        self.world.add_component(self.player, Mana(current=50, maximum=50, regeneration=0.5))
        # Initial explored area around spawn
        self._update_visibility()
        # Quest tracker
        self.quest_trackers[self.player.id] = QuestTracker()
        log.info("Player created: %s", name)
        return self.player

    # ---------- visibility ----------

    def _update_visibility(self) -> None:
        if self.world_map is None or self.player is None:
            return
        from engine.entities.components import Position
        pos = self.world.get_component(self.player, Position)
        if pos is None:
            return
        radius = 8
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > radius * radius:
                    continue
                tile = self.world_map.get_tile(pos.x + dx, pos.y + dy)
                if tile:
                    tile.is_visible = True
                    tile.is_explored = True

    def reset_visibility(self) -> None:
        if self.world_map is None:
            return
        for tile in self.world_map.iter_tiles():
            tile.is_visible = False
        self._update_visibility()

    # ---------- game loop ----------

    def start(self) -> None:
        """Start the engine. If not headless, runs the main loop."""
        if self.config.plugins.autoload_enabled:
            try:
                success, failure = self.plugins.load_all()
                if success:
                    self.plugins.enable_all()
                log.info("Plugins loaded: %d success, %d failed", success, failure)
            except Exception as exc:  # noqa: BLE001
                log.error("Plugin loading failed: %s", exc)
        self._running = True
        self._last_tick_time = time.perf_counter()
        if not self.headless:
            self._run_main_loop()
        else:
            log.info("Engine started in headless mode")

    def shutdown(self) -> None:
        log.info("Shutting down engine")
        self._running = False
        if self.plugins:
            try:
                self.plugins.disable_all()
            except Exception:  # noqa: BLE001
                pass
        if self.renderer:
            self.renderer.shutdown()

    def _run_main_loop(self) -> None:
        """Main game loop."""
        assert self.renderer is not None
        assert self.screens is not None
        self.screens.set("main")
        # Initial render
        self.screens.render(self)
        while self._running:
            # 1. Read input (blocking)
            line = self.renderer.get_input()
            if line is None:
                self.shutdown()
                break
            # 2. Process command
            ctx = CommandContext(
                world=self.world, player=self.player,
                raw_input=line, engine=self,
                caller_id=self.player.id if self.player else None,
                permission=Permission.OWNER if self.cheat_mode else Permission.PLAYER,
            )
            result = self.command_processor.execute(line, ctx)
            if result.output:
                self.message_log.add(result.output, Color.WHITE)
            elif result.error:
                self.message_log.add(result.error, Color.RED)
            # 3. Advance simulation
            self.tick_simulation()
            # 4. Autosave?
            if (self.clock.time.tick - self._last_autosave_tick
                    >= self.config.save.autosave_interval_ticks):
                try:
                    self.save_game("autosave")
                    self._last_autosave_tick = self.clock.time.tick
                except Exception as exc:  # noqa: BLE001
                    log.error("Autosave failed: %s", exc)
            # 5. Re-render
            self.screens.render(self)

    def tick_simulation(self, dt: Optional[float] = None) -> None:
        """Advance one simulation tick."""
        if dt is None:
            dt = 1.0 / self.clock.tps
        # Don't tick the world if the player is dead — the game-over panel
        # is showing and we want a clean pause until the player chooses.
        if getattr(self, "player_dead", False):
            return
        # Advance game time
        self.clock.tick(dt)
        # Update needs
        self.needs_system.update(self.world, dt, self.clock.ticks_per_game_minute)
        # Update status effects
        self.status_system.update(self.world, dt)
        # Update weather
        season = Season(self.clock.time.season)
        self.weather.update(dt, season)
        # Update survival
        self.survival.update(self.world, dt, self.weather.current)
        # Update economy
        self.economy.update(dt)
        # Update factions
        self.factions.update(dt)
        # Update skill decay
        self.skills.decay(self.world, dt)
        # Update AI for all entities with AI component
        self._update_ai()
        # ----- Bannerlord-style travel / follow -----
        # Walk the player one tile along the pending path, or one step toward
        # the follow target. The world has just been updated above (AI moved,
        # needs decayed, etc.), so this matches Bannerlord's "world keeps
        # simulating while you travel" feel.
        self._advance_travel()
        # ----- Auto-attack -----
        # If enabled, the player auto-attacks adjacent hostiles. This runs
        # AFTER the AI so the player can retaliate even when the player's
        # typing speed is slower than the AI's tick rate.
        if self.auto_attack_enabled:
            self._auto_attack_hostiles()
        # NPC daily schedules — drive NPCs toward routine locations
        # based on time of day (work, home, tavern, etc.).
        self._update_schedules()
        # NPC memory consolidation — let NPCs slowly forget trivial
        # memories and reinforce important ones.
        self._update_memories(dt)
        # World system update
        self.world.update(dt)
        # Check for player death (HP at zero) — must happen last so all
        # damage sources for this tick are applied first.
        self._check_player_death()

    def _check_player_death(self) -> None:
        """Handle the player reaching 0 HP.

        Sets the ``player_dead`` flag so the REPL can show a game-over
        panel. The simulation pauses for the player (other entities keep
        simulating) until the REPL calls ``respawn_player()`` or
        ``new_game()``.

        This is the canonical death detector — it runs LAST in every tick
        so all damage sources for this tick are applied first. The AI
        combat path does NOT destroy the player entity (see ``_handle_death``
        which special-cases the player); it only reduces HP, so this method
        is guaranteed to see the lethal HP value.
        """
        if self.player is None:
            return
        # Defensive: if the player entity was destroyed (legacy code path
        # or a buggy plugin), reconstruct a minimal dead-state so the
        # game-over panel still appears.
        if not self.world.is_alive(self.player):
            if not getattr(self, "player_dead", False):
                self.player_dead = True
                self.message_log.add("You have been slain! Game over.", Color.RED)
                self.message_log.add("  Press R to respawn, N for a new game, Q to quit.",
                                     Color.YELLOW)
            return
        from engine.entities.components import Health as HealthComp, Identity
        health = self.world.get_component(self.player, HealthComp)
        if health is None:
            return
        if health.current > 0:
            return
        if getattr(self, "player_dead", False):
            return  # already dead — don't re-trigger
        # Mark the player as dead.
        self.player_dead = True
        identity = self.world.get_component(self.player, Identity)
        name = identity.display_name if identity else "Hero"
        self.message_log.add(f"{name} has been slain! Game over.", Color.RED)
        self.message_log.add("  Press R to respawn, N for a new game, Q to quit.",
                             Color.YELLOW)

    def respawn_player(self) -> None:
        """Respawn the dead player at the spawn point with full HP.

        Called by the REPL when the player presses R on the game-over
        screen, or types ``respawn``. Applies a wealth penalty (lose half
        of carried wealth) and resets needs, mana, and ALL status effects,
        but keeps the same world and character.

        This is safe to call repeatedly — every field is re-reset each
        call, so the second death (and the third, and so on) recovers
        correctly. The key fix vs. the original implementation is that
        status effects are cleared (a player who died of poison no longer
        re-dies on the next tick) and mana is restored.
        """
        if self.player is None or self.world_map is None:
            return
        from engine.entities.components import (
            Health as HealthComp, Needs as NeedsComp, Position as PosComp,
            Wealth, Identity, Combat as CombatComp,
        )
        from engine.magic.spells import Mana
        # If the player entity was destroyed (legacy path), rebuild it.
        if not self.world.is_alive(self.player):
            log.warning("Player entity was destroyed — rebuilding on respawn.")
            old_name = "Hero"
            self.player = self.factory.create_player(old_name)
            # Re-add to inventories mapping (factory doesn't do this).
            if self.player.id not in self.inventories:
                self.inventories[self.player.id] = Inventory(capacity=30, max_weight=60.0)
            # Re-add Mana (factory doesn't).
            self.world.add_component(self.player, Mana(current=50, maximum=50, regeneration=0.5))
        health = self.world.get_component(self.player, HealthComp)
        if health:
            health.current = health.maximum
            health.regeneration = max(health.regeneration, 1.0)
        needs = self.world.get_component(self.player, NeedsComp)
        if needs:
            needs.hunger = 0.0
            needs.thirst = 0.0
            needs.fatigue = 50.0
            needs.sleep = 50.0
            needs.warmth = 37.0
            needs.morale = 75.0
            needs.comfort = 50.0
            needs.sanity = 100.0
        # Reset mana to full.
        mana = self.world.get_component(self.player, Mana)
        if mana:
            mana.current = mana.maximum
        else:
            # Add a Mana component if the player didn't have one.
            self.world.add_component(self.player, Mana(current=50, maximum=50, regeneration=0.5))
        # Clear ALL status effects (poison, disease, bleed, etc.) so the
        # player doesn't instantly re-die from a lingering DoT.
        combat_comp = self.world.get_component(self.player, CombatComp)
        if combat_comp:
            combat_comp.status_effects.clear()
            combat_comp.in_combat = False
            combat_comp.cooldown = 0.0
        pos = self.world.get_component(self.player, PosComp)
        if pos:
            pos.x = self.world_map.spawn_point.x
            pos.y = self.world_map.spawn_point.y
            self.spatial.update(self.player, pos.x, pos.y)
        wealth = self.world.get_component(self.player, Wealth)
        if wealth:
            wealth.copper = wealth.copper // 2
            wealth.silver = wealth.silver // 2
            wealth.gold = wealth.gold // 2
        # Cancel any in-progress travel / follow.
        self._travel_path = []
        self._follow_target_id = None
        self.pending_encounter_id = None
        self._update_visibility()
        self.player_dead = False
        identity = self.world.get_component(self.player, Identity)
        name = identity.display_name if identity else "Hero"
        self.message_log.add(f"{name} awakens at the spawn point, weakened.", Color.GREEN)
        self.message_log.add("  (Lost half of carried wealth.)", Color.YELLOW)

    def new_game(self, name: str = "Hero") -> None:
        """Start a brand new game — regenerate the world and player.

        Called by the REPL when the player presses N on the game-over
        screen. Discards the current world and generates a fresh one.
        """
        # Reset the world and all derived state.
        self.world = World()
        # Re-wire the entity factory to use the new world.
        self.factory = EntityFactory(self.world, self.rng)
        # Clear the spatial grid.
        from engine.world.spatial import SpatialGrid
        self.spatial = SpatialGrid(cell_size=8)
        # Clear inventories, items, and quest trackers.
        self.inventories = {}
        self.items = ItemRegistry()
        self.item_generator = ItemGenerator(self.rng)
        self.quest_trackers = {}
        self.player = None
        self.player_dead = False
        # Clear Bannerlord-style state.
        self.auto_attack_enabled = False
        self._travel_path = []
        self._follow_target_id = None
        self.pending_encounter_id = None
        self.settlements = []
        self.structure_placements = {}
        self._next_placement_id = 1
        # Clear the message log.
        if self.message_log:
            self.message_log.messages.clear()
        # Generate a fresh world with a new seed.
        from engine.world.generator import WorldGenParams
        params = WorldGenParams(
            seed=self.rng.randint(1, 999999),
            width=self.config.world.world_tiles_x // 2,
            height=self.config.world.world_tiles_y // 2,
        )
        self.generate_world(params)
        self.create_player(name)
        self.message_log.add("A new world awaits...", Color.CYAN)

    def _update_schedules(self) -> None:
        """Drive NPCs toward their daily routine locations.

        This integrates the (previously unused) engine.npc.schedule
        module: each NPC with an AI component picks a destination based
        on the current phase of day (dawn/day/dusk/night) and slowly
        wanders toward it.
        """
        if self.world_map is None:
            return
        from engine.entities.components import AI as AIComp, Position as PosComp
        from engine.core.clock import PhaseOfDay
        try:
            phase = self.clock.time.phase_of_day()
        except Exception:  # noqa: BLE001
            return
        # Pick a target offset based on phase of day.
        # Dawn  -> gather near (0, +5)  — "morning market"
        # Day   -> scatter (±8, ±8)     — "working"
        # Dusk  -> gather near (0, -5)  — "tavern"
        # Night -> cluster near (0, 0)  — "home/sleep"
        phase_targets = {
            PhaseOfDay.DAWN:  (0, 5),
            PhaseOfDay.DAY:   (None, None),   # scatter
            PhaseOfDay.DUSK:  (0, -5),
            PhaseOfDay.NIGHT: (0, 0),
        }
        tx, ty = phase_targets.get(phase, (0, 0))
        for entity, (ai, pos) in self.world.view(AIComp, PosComp):
            if ai.controller == "player":
                continue
            # Only civilian NPCs follow schedules; creatures and
            # aggressive mobs keep wandering.
            if ai.controller not in ("civilian", "wander"):
                continue
            # 30% chance per tick to step toward target — keeps movement
            # organic without flooding the message log.
            if not self.rng.chance(0.3):
                continue
            if tx is None:
                # Scatter: pick a random nearby offset.
                ndx = self.rng.randint(-2, 2)
                ndy = self.rng.randint(-2, 2)
            else:
                dx = tx - pos.x
                dy = ty - pos.y
                if abs(dx) <= 1 and abs(dy) <= 1:
                    continue
                ndx = (1 if dx > 0 else -1 if dx < 0 else 0)
                ndy = (1 if dy > 0 else -1 if dy < 0 else 0)
            new_x, new_y = pos.x + ndx, pos.y + ndy
            tile = self.world_map.get_tile(new_x, new_y)
            if tile is None or not tile.is_walkable:
                continue
            # Don't step onto another entity — use a spatial query for speed.
            occupants = self.spatial.query_cell(new_x, new_y)
            if any(o.id != entity.id for o in occupants):
                continue
            self.spatial.update(entity, new_x, new_y)
            pos.x = new_x
            pos.y = new_y

    def _update_memories(self, dt: float) -> None:
        """Slowly decay trivial NPC memories so the memory store doesn't
        grow without bound. This integrates the (previously unused)
        engine.npc.memory module into the main tick loop.
        """
        from engine.entities.components import Memory as MemoryComp
        for entity, (mem,) in self.world.view(MemoryComp):
            # Drop the oldest trivial memories when the list grows past 50.
            if len(mem.memories) <= 50:
                continue
            # Keep only the most recent 30 entries.
            mem.memories = mem.memories[-30:]

    def _update_ai(self) -> None:
        """Tick AI for all NPCs and creatures.

        Uses the spatial grid for nearby-entity queries (O(nearby) instead
        of O(all entities)) so AI scales to large populations. Also skips
        pacified creatures (those with ``Memory.knowledge["pacified_by_player"]``
        set by the ``give`` command) — they will not target the player.
        """
        from engine.entities.components import (
            AI as AIComp, Position as PosComp, Identity, Memory as MemoryComp,
        )
        for entity, (ai, pos) in self.world.view(AIComp, PosComp):
            if ai.controller == "player":
                continue
            controller = self.ai_registry.get(ai.controller)
            if controller is None:
                continue
            # Use the spatial grid to find nearby entities (radius 12).
            # This is O(nearby) instead of O(all entities).
            nearby: list[tuple[Entity, float]] = []
            for other, dist in self.spatial.query_radius(pos.x, pos.y, 12):
                if other.id == entity.id:
                    continue
                nearby.append((other, dist))
            ctx = AIContext(
                world=self.world, entity=entity, rng=self.rng,
                current_tick=self.clock.time.tick,
                current_hour=self.clock.time.hour,
                current_minute=self.clock.time.minute,
                nearby_entities=nearby,
            )
            try:
                action = controller.decide(ctx)
                # Pacified check: if this entity has been pacified by the
                # player (via the `give` command), suppress any attack
                # action targeting the player.
                if action and action.type == "attack" and action.target_entity is not None:
                    mem = self.world.get_component(entity, MemoryComp)
                    if mem and mem.knowledge.get("pacified_by_player"):
                        # Convert to a wait action — the entity will not
                        # attack the player even if the AI controller
                        # suggested it.
                        from engine.npc.ai import AIAction
                        action = AIAction(type="wait")
                self._execute_ai_action(entity, action)
            except Exception:  # noqa: BLE001
                log.exception("AI controller %s raised on entity %d",
                              ai.controller, entity.id)

    def _execute_ai_action(self, entity: Entity, action: Any) -> None:
        """Execute a chosen AI action."""
        from engine.entities.components import Position, Health
        if action.type == "wait":
            return
        if action.type == "move":
            if action.target_position is None:
                return
            pos = self.world.get_component(entity, Position)
            if pos is None:
                return
            tx, ty = action.target_position
            # Check world bounds and walkability
            if self.world_map is None:
                return
            tile = self.world_map.get_tile(tx, ty)
            if tile is None or not tile.is_walkable:
                # Try adjacent tiles
                return
            # Check if another entity occupies the tile — spatial query.
            occupants = self.spatial.query_cell(tx, ty)
            if any(o.id != entity.id for o in occupants):
                return
            self.spatial.update(entity, tx, ty)
            pos.x = tx
            pos.y = ty
            return
        if action.type == "attack":
            if action.target_entity is None:
                return
            target = Entity(id=action.target_entity, generation=0)
            # Find the actual entity by id
            for ent, (p,) in self.world.view(Position):
                if ent.id == action.target_entity:
                    target = ent
                    break
            else:
                return
            weapon = None
            from engine.entities.components import Combat as CombatComp
            combat_comp = self.world.get_component(entity, CombatComp)
            if combat_comp and combat_comp.weapon_id is not None:
                weapon = self.items.get(combat_comp.weapon_id)
            result = self.combat.attack(self.world, entity, target, weapon)
            if result.message:
                self.message_log.add(result.message, Color.YELLOW if result.hit else Color.GRAY)
            # If player was involved, ensure visibility
            if (self.player and (entity.id == self.player.id
                                 or target.id == self.player.id)):
                pass  # already visible
            # Handle death
            if result.killed:
                self._handle_death(target, entity)
            return
        if action.type == "use_item":
            # Very simplified — just reduce a need
            from engine.entities.components import Needs as NeedsComp
            needs = self.world.get_component(entity, NeedsComp)
            if needs is None:
                return
            need = action.data.get("need")
            if need == "food":
                needs.hunger = max(0, needs.hunger - 30)
            elif need == "water":
                needs.thirst = max(0, needs.thirst - 30)
            elif need == "sleep":
                needs.sleep = max(0, needs.sleep - 50)
                needs.fatigue = max(0, needs.fatigue - 30)
            return
        if action.type == "talk":
            # No-op for now
            return
        if action.type == "work":
            # Gain a small amount of gold
            from engine.entities.components import Wealth
            wealth = self.world.get_component(entity, Wealth)
            if wealth:
                wealth.copper += 1
            return

    def _handle_death(self, victim: Entity, killer: Entity) -> None:
        """Handle an entity death.

        IMPORTANT: when the victim is the player, we do NOT destroy the
        player entity. We only drop the player's HP to 0, drop inventory,
        and let ``_check_player_death`` (called at the end of every tick)
        flip the ``player_dead`` flag and trigger the game-over panel.
        This is the fix for the "game over cycle" bug where the player
        was destroyed and ``respawn_player`` couldn't recover.
        """
        from engine.entities.components import Identity, Wealth, Health as HealthComp
        # ----- Special case: the player is the victim -----
        if self.player is not None and victim.id == self.player.id:
            # Drop HP to 0 so _check_player_death triggers.
            health = self.world.get_component(victim, HealthComp)
            if health:
                health.current = 0
            killer_id_name = "unknown"
            killer_id_comp = self.world.get_component(killer, Identity)
            if killer_id_comp:
                killer_id_name = killer_id_comp.display_name
            identity = self.world.get_component(victim, Identity)
            name = identity.display_name if identity else "Hero"
            self.message_log.add(
                f"{name} was struck down by {killer_id_name}!", Color.RED)
            # Award XP to the killer (so the AI that killed the player
            # still benefits — this also matches the original behaviour).
            from engine.entities.components import Skills as SkillsComp
            killer_skills = self.world.get_component(killer, SkillsComp)
            if killer_skills is None:
                killer_skills = SkillsComp()
                self.world.add_component(killer, killer_skills)
            self.skills.add_xp(killer, "swordsmanship", 30, self.world)
            # DO NOT destroy the player entity, DO NOT remove from spatial.
            # The canonical death path (_check_player_death) takes it from
            # here. Return without touching the player further.
            return
        # ----- Standard death (NPC or creature) -----
        identity = self.world.get_component(victim, Identity)
        name = identity.display_name if identity else f"entity#{victim.id}"
        killer_id_name = "unknown"
        killer_id_comp = self.world.get_component(killer, Identity)
        if killer_id_comp:
            killer_id_name = killer_id_comp.display_name
        self.message_log.add(f"{name} was killed by {killer_id_name}.", Color.RED)
        # Drop inventory
        inv = self.inventories.get(victim.id)
        if inv and self.world_map:
            from engine.entities.components import Position
            pos = self.world.get_component(victim, Position)
            if pos:
                # Just mark items as dropped on the ground
                for slot_idx, item, count in list(inv.iter_items(self.items)):
                    dropped = self.factory.create_item_entity(item.id, pos.x, pos.y)
        # Update spatial grid
        self.spatial.remove(victim)
        # Destroy entity
        self.world.destroy_entity(victim)
        # Award XP if killer has skills
        from engine.entities.components import Skills as SkillsComp
        killer_skills = self.world.get_component(killer, SkillsComp)
        if killer_skills is None:
            killer_skills = SkillsComp()
            self.world.add_component(killer, killer_skills)
        # Use a default combat skill for XP
        self.skills.add_xp(killer, "swordsmanship", 30, self.world)

    # ---------- player actions ----------

    def move_player(self, dx: int, dy: int) -> bool:
        """Move the player by (dx, dy). Returns True if the move succeeded.

        If the destination tile has a hostile entity, an encounter is
        triggered: ``pending_encounter_id`` is set so the REPL can show
        the Mount-&-Blade-style encounter panel next tick. (Auto-attack
        still fires from ``_auto_attack_hostiles`` if enabled.)
        """
        if self.player is None or self.world_map is None:
            return False
        from engine.entities.components import Position, Identity, Combat as CombatComp
        pos = self.world.get_component(self.player, Position)
        if pos is None:
            return False
        new_x, new_y = pos.x + dx, pos.y + dy
        tile = self.world_map.get_tile(new_x, new_y)
        if tile is None or not tile.is_walkable:
            return False
        # Check for entity at destination — spatial query (fast).
        occupants = self.spatial.query_cell(new_x, new_y)
        for ent in occupants:
            if ent.id == self.player.id:
                continue
            # Pacified entities don't block / attack — they're friendly.
            from engine.entities.components import Memory as MemoryComp
            mem = self.world.get_component(ent, MemoryComp)
            if mem and mem.knowledge.get("pacified_by_player"):
                # Walk past them — they're a friend now.
                identity = self.world.get_component(ent, Identity)
                name = identity.display_name if identity else f"entity#{ent.id}"
                self.message_log.add(f"You brush past {name}, your ally.", Color.GREEN)
                continue
            if self.world.has_tag(ent, "hostile"):
                # Trigger the encounter panel — the player picks what to do.
                self.pending_encounter_id = ent.id
                identity = self.world.get_component(ent, Identity)
                name = identity.display_name if identity else f"entity#{ent.id}"
                self.message_log.add(f"You bump into {name}! (encounter)", Color.RED)
                # If auto-attack is enabled, the engine will hit them this tick.
                return False
            else:
                identity = self.world.get_component(ent, Identity)
                name = identity.display_name if identity else f"entity#{ent.id}"
                self.message_log.add(f"{name} is in the way.", Color.GRAY)
                return False
        # Move
        self.spatial.update(self.player, new_x, new_y)
        pos.x = new_x
        pos.y = new_y
        # Trigger random encounters
        if tile.encounter_rate > 0 and self.rng.chance(tile.encounter_rate):
            self._trigger_encounter(tile)
        # Update visibility
        self._update_visibility()
        # Advance the clock one tick worth of movement time
        self.clock.advance_ticks(int(self.clock.ticks_per_game_minute * 0.1))
        return True

    def _trigger_encounter(self, tile: Any) -> None:
        """Spawn a hostile creature on encounter."""
        from engine.entities.components import Position
        if self.player is None:
            return
        pos = self.world.get_component(self.player, Position)
        if pos is None:
            return
        creature = self.rng.choice([
            ("Wolf", "w", Color.GRAY, 25, 8, 12),
            ("Goblin", "g", Color.GREEN, 20, 7, 10),
            ("Bandit", "b", Color.RED, 35, 10, 10),
            ("Rat", "r", Color.DARK_GRAY, 6, 2, 14),
            ("Skeleton", "s", Color.WHITE, 22, 8, 8),
        ])
        name, glyph, color, hp, strn, agi = creature
        # Spawn near the player.
        sx = pos.x + self.rng.randint(-3, 3)
        sy = pos.y + self.rng.randint(-3, 3)
        e = self.factory.create_creature(
            name=name, glyph=glyph, color=color,
            x=sx, y=sy,
            hp=hp, strength=strn, agility=agi, aggressive=True,
        )
        # FIX: insert the creature into the spatial grid so the player can
        # actually see and target it.
        self.spatial.insert(e, sx, sy)
        self.message_log.add(f"A {name} appears!", Color.RED)
        # If the creature spawned adjacent to the player, trigger the
        # encounter panel so the player can choose how to react.
        if max(abs(sx - pos.x), abs(sy - pos.y)) <= 1:
            self.pending_encounter_id = e.id

    # ---------- Bannerlord-style travel / follow / auto-attack ----------

    def _auto_attack_hostiles(self) -> None:
        """Auto-attack any adjacent hostile entity.

        Called from ``tick_simulation`` when ``auto_attack_enabled`` is True.
        Mirrors the bump-attack logic in ``move_player`` but runs every
        tick so the player can keep up with faster NPCs. Skips pacified
        entities (those with ``Memory.knowledge["pacified_by_player"]``).
        """
        if self.player is None:
            return
        from engine.entities.components import (
            Position, Combat as CombatComp, Memory as MemoryComp,
        )
        pos = self.world.get_component(self.player, Position)
        if pos is None:
            return
        combat_comp = self.world.get_component(self.player, CombatComp)
        weapon = None
        if combat_comp and combat_comp.weapon_id is not None:
            weapon = self.items.get(combat_comp.weapon_id)
        # Find adjacent hostiles via spatial query (radius 1.5 = 8-neighbourhood).
        for ent, dist in self.spatial.query_radius(pos.x, pos.y, 1.5):
            if ent.id == self.player.id:
                continue
            if dist > 1.5:
                continue
            if not self.world.has_tag(ent, "hostile"):
                continue
            # Skip pacified entities.
            mem = self.world.get_component(ent, MemoryComp)
            if mem and mem.knowledge.get("pacified_by_player"):
                continue
            # Skip if the entity is already dead.
            health = self.world.get_component(ent, type(ent).__class__) if False else None
            from engine.entities.components import Health
            health = self.world.get_component(ent, Health)
            if health is None or health.current <= 0:
                continue
            result = self.combat.attack(self.world, self.player, ent, weapon)
            if result.message:
                self.message_log.add(result.message, Color.YELLOW if result.hit else Color.GRAY)
            if result.killed:
                self._handle_death(ent, self.player)
            # Only attack one hostile per tick — keeps combat turn-based
            # and readable.
            return

    def _advance_travel(self) -> None:
        """Walk the player one tile along the pending travel path, or one
        step toward the follow target.

        Called every tick from ``tick_simulation``. This is the engine
        of the Mount-&-Blade-style overland travel: the player moves
        automatically while the world (AI, needs, weather, economy)
        keeps updating around them.
        """
        if self.player is None:
            return
        from engine.entities.components import Position
        pos = self.world.get_component(self.player, Position)
        if pos is None:
            return
        # ----- Follow target takes precedence -----
        if self._follow_target_id is not None:
            target = None
            from engine.core.ecs import Entity as _E
            for ent, (tp,) in self.world.view(Position):
                if ent.id == self._follow_target_id:
                    target = ent
                    break
            if target is None:
                # Target died or was removed — stop following.
                self._follow_target_id = None
                self.message_log.add("You lose sight of your follow target.",
                                     Color.GRAY)
                return
            tp = self.world.get_component(target, Position)
            if tp is None:
                self._follow_target_id = None
                return
            dx = tp.x - pos.x
            dy = tp.y - pos.y
            dist = max(abs(dx), abs(dy))
            if dist <= 1:
                # Caught up — stop following.
                from engine.entities.components import Identity
                identity = self.world.get_component(target, Identity)
                name = identity.display_name if identity else f"entity#{target.id}"
                self.message_log.add(f"You catch up to {name}.", Color.GREEN)
                self._follow_target_id = None
                return
            # Step toward the target (Chebyshev normalization).
            step_x = (1 if dx > 0 else -1 if dx < 0 else 0)
            step_y = (1 if dy > 0 else -1 if dy < 0 else 0)
            self.move_player(step_x, step_y)
            return
        # ----- Pending travel path -----
        if not self._travel_path:
            return
        next_tile = self._travel_path[0]
        nx, ny = next_tile
        dx = nx - pos.x
        dy = ny - pos.y
        if dx == 0 and dy == 0:
            # Reached this tile — pop and continue.
            self._travel_path.pop(0)
            if not self._travel_path:
                self.message_log.add("You have arrived at your destination.",
                                     Color.GREEN)
            return
        step_x = (1 if dx > 0 else -1 if dx < 0 else 0)
        step_y = (1 if dy > 0 else -1 if dy < 0 else 0)
        # If the move fails (e.g. an encounter triggered), abort the path
        # so the player can react — they can re-issue `travel` after.
        if not self.move_player(step_x, step_y):
            if self.pending_encounter_id is not None:
                # Encounter — pause travel.
                self.message_log.add("Travel paused — encounter!", Color.YELLOW)
                self._travel_path = []
            else:
                # Blocked — try to re-path around the obstacle.
                self._travel_path.pop(0)
                if not self._travel_path:
                    self.message_log.add("Travel aborted — path blocked.",
                                         Color.YELLOW)

    def teleport_player(self, x: int, y: int) -> bool:
        """Teleport the player to (x, y) instantly.

        Used by the holy map's "travel here" function for fast travel.
        Validates the destination is in-bounds and walkable.
        """
        if self.player is None or self.world_map is None:
            return False
        from engine.entities.components import Position
        tile = self.world_map.get_tile(x, y)
        if tile is None or not tile.is_walkable:
            return False
        pos = self.world.get_component(self.player, Position)
        if pos is None:
            return False
        pos.x = x
        pos.y = y
        self.spatial.update(self.player, x, y)
        # Cancel any in-progress travel / follow.
        self._travel_path = []
        self._follow_target_id = None
        self._update_visibility()
        self.message_log.add(f"You materialize at ({x}, {y}).", Color.CYAN)
        return True

    def travel_to(self, x: int, y: int) -> bool:
        """Begin walking the player to (x, y) along an A* path.

        The path is computed once and stored in ``_travel_path``. Each
        subsequent tick, ``_advance_travel`` walks the player one tile
        along the path while the world keeps simulating around them.
        Returns True if a path was found.
        """
        if self.player is None or self.world_map is None or self.pathfinder is None:
            return False
        from engine.entities.components import Position
        pos = self.world.get_component(self.player, Position)
        if pos is None:
            return False
        # Validate destination.
        tile = self.world_map.get_tile(x, y)
        if tile is None or not tile.is_walkable:
            self.message_log.add("Cannot travel there — terrain is impassable.",
                                 Color.RED)
            return False
        path = self.pathfinder.find_path((pos.x, pos.y), (x, y), max_iterations=20000)
        if not path or len(path) < 2:
            self.message_log.add("No path to that destination.", Color.RED)
            return False
        # Drop the first tile (it's the player's current position).
        self._travel_path = path[1:]
        # Cancel any follow.
        self._follow_target_id = None
        self.message_log.add(
            f"Travelling to ({x}, {y}) — {len(self._travel_path)} steps.",
            Color.CYAN)
        return True

    def follow_entity(self, entity_id: int) -> bool:
        """Begin following the entity with the given id.

        Each tick, ``_advance_travel`` walks the player one step toward
        the target's current position. Cleared when the player catches
        up or the target dies.
        """
        if self.player is None:
            return False
        # Verify the entity exists.
        from engine.entities.components import Position, Identity
        target = None
        for ent, (tp,) in self.world.view(Position):
            if ent.id == entity_id:
                target = ent
                break
        if target is None:
            self.message_log.add("No such entity to follow.", Color.RED)
            return False
        self._follow_target_id = entity_id
        # Cancel any pending travel path.
        self._travel_path = []
        identity = self.world.get_component(target, Identity)
        name = identity.display_name if identity else f"entity#{entity_id}"
        self.message_log.add(f"You begin following {name}.", Color.CYAN)
        return True

    def cancel_travel(self) -> None:
        """Cancel any in-progress travel or follow."""
        was_travelling = bool(self._travel_path) or self._follow_target_id is not None
        self._travel_path = []
        self._follow_target_id = None
        if was_travelling:
            self.message_log.add("Travel cancelled.", Color.YELLOW)

    def befriend_entity(self, entity: Entity) -> bool:
        """Mark an entity as pacified — it will never attack the player again.

        Called by the ``give`` command when the player gives an item the
        entity likes. Sets ``Memory.knowledge["pacified_by_player"]``,
        removes the ``"hostile"`` tag, and switches the AI controller
        to ``"wander"`` so the entity stops hunting the player.
        """
        from engine.entities.components import (
            Memory as MemoryComp, AI as AIComp, Identity,
        )
        # Tag removal — neutralises bump-attack, auto-attack, and the
        # _find_adjacent_hostile helper.
        self.world.untag(entity, "hostile")
        # Memory flag — neutralises the AI controllers' attack logic.
        mem = self.world.get_component(entity, MemoryComp)
        if mem is None:
            mem = MemoryComp()
            self.world.add_component(entity, mem)
        mem.knowledge["pacified_by_player"] = 1.0
        # Switch AI controller to wander so the entity stops hunting.
        ai = self.world.get_component(entity, AIComp)
        if ai:
            ai.controller = "wander"
            ai.target_id = None
            ai.state = "idle"
        identity = self.world.get_component(entity, Identity)
        name = identity.display_name if identity else f"entity#{entity.id}"
        self.message_log.add(f"{name} is now friendly toward you!", Color.GREEN)
        return True

    # ---------- save/load ----------

    def save_game(self, name: str) -> None:
        """Save the current game state."""
        from engine.entities.components import Identity, Position
        character_name = ""
        if self.player is not None:
            identity = self.world.get_component(self.player, Identity)
            character_name = identity.display_name if identity else ""
        data = SaveData(
            game_time=self.clock.time.to_dict(),
            world=self.world_map.to_dict() if self.world_map else {},
            entities=self._serialize_entities(),
            items=self.items.to_dict(),
            inventories={eid: inv.to_dict() for eid, inv in self.inventories.items()},
            factions={f.id: f.to_dict() for f in FactionLibrary.all()},
            markets={mid: {"name": m.name, "wealth": m.wealth}
                     for mid, m in self.economy.markets.items()},
            quests={qt: tr.to_dict() for qt, tr in self.quest_trackers.items()},
            weather={"type": self.weather.current.type.value,
                      "temperature": self.weather.current.temperature,
                      "humidity": self.weather.current.humidity},
            meta={"player_id": self.player.id if self.player else None},
        )
        self.save_manager.save(name, data,
                               character_name=character_name,
                               game_time_display=self.clock.time.display())

    def _serialize_entities(self) -> dict:
        """Serialize all entities and their components."""
        from engine.entities.components import (
            Identity, Position, Health, Stats, Needs, AI, Combat, Race,
            Personality, Relationships, Wealth, Memory, Skills, Player, Tag, Faction,
        )
        out: dict = {}
        for entity_id, components in self.world._components.items():
            ent_data: dict = {"components": {}}
            for comp_type, comp in components.items():
                cls_name = comp_type.__name__
                try:
                    if hasattr(comp, "__dataclass_fields__"):
                        ent_data["components"][cls_name] = {
                            f.name: getattr(comp, f.name)
                            for f in comp.__dataclass_fields__.values()
                        }
                except Exception:  # noqa: BLE001
                    continue
            out[str(entity_id)] = ent_data
        return out

    def load_game(self, name: str) -> None:
        """Load a saved game."""
        data = self.save_manager.load(name)
        # Restore clock
        from engine.core.clock import GameTime
        self.clock.time = GameTime.from_dict(data.game_time)
        # Restore world map
        if data.world:
            self.world_map = WorldMap.from_dict(data.world)
            self.pathfinder = AStarPathfinder(self.world_map)
        # Restore items
        self.items.load_from_dict(data.items)
        # Restore inventories
        self.inventories = {
            int(eid): Inventory.from_dict(idata)
            for eid, idata in data.inventories.items()
        }
        # Restore player
        if data.meta.get("player_id"):
            for ent in list(self.world._components.keys()):
                from engine.core.ecs import Entity as E
                if ent.id == data.meta["player_id"]:
                    self.player = ent
                    break
        self.message_log.add(f"Loaded game: {name}", Color.GREEN)
        log.info("Loaded save: %s", name)

    # ---------- UI ----------

    def _register_screens(self) -> None:
        assert self.screens is not None
        main = MainScreen(self.renderer, self.i18n)
        self.screens.register_screen(main)
        self.screens.register_screen(InventoryScreen(self.renderer, self.i18n))
        self.screens.register_screen(CharacterScreen(self.renderer, self.i18n))
        self.screens.register_screen(MapScreen(self.renderer, self.i18n))
        self.screens.register_screen(HelpScreen(self.renderer, self.i18n))

    # ---------- convenience ----------

    def message(self, text: str, color: int = Color.WHITE) -> None:
        self.message_log.add(text, color)

    def register_command(self, name: str, handler: Any, **kwargs: Any) -> None:
        from engine.commands.system import Command
        cmd = Command(name=name, handler=handler, **kwargs)
        self.commands.register(cmd)
