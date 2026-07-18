"""Tests for the new subsystems (reputation, life, animals, kingdoms, etc.)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.reputation.system import (
    ReputationSystem, ReputationType, reputation_level, ReputationLevel,
)
from engine.life.system import LifeSimulator, LifeStage
from engine.animals.system import (
    AnimalLibrary, AnimalSimulator, AnimalType, AnimalPopulation,
)
from engine.kingdoms.system import (
    KingdomLibrary, KingdomSystem, KingdomType, SuccessionLaw,
)
from engine.scripting.interpreter import ScriptEngine, ScriptContext
from engine.audio.system import AudioSystem, AudioLibrary
from engine.performance.pool import ObjectPool, PooledFactory
from engine.performance.profiler import profiler
from engine.performance.cache import LRUCache, TTLCache
from engine.performance.lazy import LazyValue, LazyLoader
from engine.dungeons.system import DungeonGenerator, DungeonType
from engine.structures.system import StructureLibrary, StructureType
from engine.stealth.system import StealthSystem, StealthState
from engine.trade.system import TradeSystem
from engine.auctions.system import AuctionHouse, AuctionState
from engine.companies.system import CompanySystem, CompanyType
from engine.espionage.system import EspionageSystem, MissionType
from engine.mods_loader.system import ModLoader
from engine.themes.system import ThemeLibrary
from engine.keybindings.system import KeyBindings, KeyAction
from engine.accessibility.system import (
    AccessibilitySystem, AccessibilityConfig, ColorBlindnessType,
)
from engine.behaviors.tree import (
    BehaviorTree, SequenceNode, SelectorNode, ActionNode, ConditionNode,
    InverterNode, NodeStatus,
)
from engine.goap.system import GOAPPlanner, GOAPAction, GOAPWorldState
from engine.plugins.installer import PluginInstaller
from engine.plugins.sandbox import PluginSandbox
from engine.plugins.migrations import PluginMigrator
from engine.plugins.validation import PluginValidator
from engine.plugins.docs import PluginDocGenerator


# ---------- Reputation ----------

def test_reputation_basic():
    sys = ReputationSystem()
    assert sys.get(1, ReputationType.GLOBAL) == 0.0
    sys.adjust(1, ReputationType.GLOBAL, 20.0, "heroic deed", current_tick=100)
    assert sys.get(1, ReputationType.GLOBAL) == 20.0
    assert sys.level(1, ReputationType.GLOBAL) == ReputationLevel.FRIENDLY


def test_reputation_decay():
    sys = ReputationSystem()
    sys.adjust(1, ReputationType.GLOBAL, 50.0)
    sys.update(dt_hours=1000.0)  # lots of time
    assert sys.get(1, ReputationType.GLOBAL) < 50.0


def test_reputation_levels():
    assert reputation_level(-80) == ReputationLevel.HATED
    assert reputation_level(-50) == ReputationLevel.HOSTILE
    assert reputation_level(-20) == ReputationLevel.WARY
    assert reputation_level(0) == ReputationLevel.NEUTRAL
    assert reputation_level(20) == ReputationLevel.FRIENDLY
    assert reputation_level(60) == ReputationLevel.HONOURED
    assert reputation_level(90) == ReputationLevel.EXALTED


def test_reputation_serialization():
    sys = ReputationSystem()
    sys.adjust(1, ReputationType.GLOBAL, 30.0)
    sys.adjust(1, ReputationType.CRIMINAL, -50.0, target_id=1)
    data = sys.to_dict()
    restored = ReputationSystem.from_dict(data)
    assert restored.get(1, ReputationType.GLOBAL) == 30.0
    assert restored.get(1, ReputationType.CRIMINAL, target_id=1) == -50.0


# ---------- Life ----------

def test_life_stages():
    assert LifeStage.for_age(2) == LifeStage.INFANT
    assert LifeStage.for_age(10) == LifeStage.CHILD
    assert LifeStage.for_age(20) == LifeStage.YOUNG_ADULT
    assert LifeStage.for_age(40) == LifeStage.ADULT
    assert LifeStage.for_age(70) == LifeStage.ELDER


def test_life_simulator_create_family():
    from engine.core.ecs import World, Entity
    from engine.entities.factory import EntityFactory
    from engine.utils.rng import RNG
    world = World()
    factory = EntityFactory(world, RNG(42))
    founder = factory.create_npc("Founder")
    sim = LifeSimulator(RNG(42))
    family = sim.create_family(founder, "TestFamily", "commoner")
    assert family.family_id == 1
    assert family.surname == "TestFamily"


# ---------- Animals ----------

def test_animal_library():
    species = AnimalLibrary.all()
    assert len(species) >= 15  # we have many defaults


def test_animal_population_reproduction():
    from engine.utils.rng import RNG
    pop = AnimalPopulation(
        species_id="rabbit", region_id=0, location=(10, 10),
        count=10, max_count=100, food_available=1.0,
    )
    rng = RNG(42)
    births = pop.reproduce(1.0, rng)  # 1 month
    assert births > 0
    assert pop.count > 10


def test_animal_evolution():
    from engine.utils.rng import RNG
    pop = AnimalPopulation(
        species_id="wolf", region_id=0, location=(10, 10),
        count=20, food_available=0.3,
    )
    rng = RNG(42)
    pop.evolve(120.0, rng)  # 10 years
    # Endurance should be elevated due to food pressure
    assert pop.traits.get("endurance", 0.5) > 0.5


# ---------- Kingdoms ----------

def test_kingdom_library():
    kingdoms = KingdomLibrary.all()
    assert len(kingdoms) >= 5


def test_kingdom_creation():
    from engine.kingdoms.system import Kingdom
    from engine.utils.rng import RNG
    k = Kingdom(
        id=0, name="Test Kingdom", description="Test",
        color=33, kingdom_type=KingdomType.MONARCHY,
    )
    KingdomLibrary.register(k)
    assert k.id > 0
    assert KingdomLibrary.get(k.id) is k


def test_kingdom_war_and_peace():
    from engine.utils.rng import RNG
    sys = KingdomSystem(RNG(42))
    a = KingdomLibrary.all()[0]
    b = KingdomLibrary.all()[1]
    sys.declare_war(a.id, b.id, current_tick=0.0)
    assert b.id in a.at_war_with
    sys.make_peace(a.id, b.id, current_tick=10.0)
    assert b.id not in a.at_war_with


# ---------- Scripting ----------

def test_script_engine_basic():
    engine = ScriptEngine()
    result = engine.run_source("x = 1 + 2\nresult = x * 2")
    assert result.success
    assert result.return_value == 6


def test_script_engine_forbidden():
    engine = ScriptEngine()
    # Should reject imports of os
    result = engine.run_source("import os")
    assert not result.success


def test_script_engine_safe_funcs():
    engine = ScriptEngine()
    result = engine.run_source("""
import math
result = math.sqrt(16)
""")
    assert result.success
    assert result.return_value == 4.0


def test_script_engine_timeout():
    engine = ScriptEngine()
    ctx = ScriptContext(timeout=0.1)
    result = engine.run_source("while True: pass", ctx)
    assert not result.success
    assert "timed out" in result.error.lower()


# ---------- Audio ----------

def test_audio_library():
    sounds = AudioLibrary.all()
    assert len(sounds) >= 20


def test_audio_cue():
    audio = AudioSystem(silent=True, enable_bell=False)
    audio.cue("sword_hit")
    cues = audio.recent_cues(1)
    assert len(cues) == 1
    assert cues[0].sound_id == "sword_hit"


# ---------- Performance ----------

def test_object_pool():
    factory = PooledFactory(
        create_fn=lambda: {"id": 0, "data": []},
        reset_fn=lambda obj: obj["data"].clear(),
    )
    pool = ObjectPool(factory, initial_size=2, max_size=5)
    obj1 = pool.acquire()
    obj1["data"].append(1)
    pool.release(obj1)
    obj2 = pool.acquire()
    assert obj2["data"] == []  # was reset


def test_lru_cache():
    cache = LRUCache[str, int](capacity=3)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert cache.get("a") == 1
    cache.put("d", 4)  # evicts "b"
    assert cache.get("b") is None
    assert cache.get("d") == 4


def test_ttl_cache():
    import time
    cache = TTLCache[str, int](ttl_seconds=0.1, capacity=3)
    cache.put("a", 1)
    assert cache.get("a") == 1
    time.sleep(0.15)
    assert cache.get("a") is None


def test_lazy_value():
    call_count = [0]
    def factory():
        call_count[0] += 1
        return 42
    lazy = LazyValue(factory)
    assert not lazy.is_computed
    assert lazy.get() == 42
    assert call_count[0] == 1
    # Should be cached
    assert lazy.get() == 42
    assert call_count[0] == 1


def test_profiler():
    with profiler.scope("test_section"):
        sum(range(1000))
    stats = profiler.stats()
    assert "test_section" in stats.get("children", {})


# ---------- Dungeons ----------

def test_dungeon_generation():
    from engine.utils.rng import RNG
    gen = DungeonGenerator(RNG(42))
    dungeon = gen.generate(
        "Test Dungeon", DungeonType.CAVE,
        location=(10, 10), depth=3,
    )
    assert len(dungeon.levels) == 3
    assert dungeon.levels[0].width > 0
    assert dungeon.levels[0].height > 0


def test_dungeon_has_stairs():
    from engine.utils.rng import RNG
    gen = DungeonGenerator(RNG(42))
    dungeon = gen.generate(
        "Test Dungeon", DungeonType.RUINS,
        location=(10, 10), depth=3,
    )
    level = dungeon.levels[0]
    assert level.stairs_down is not None
    # Level 0 may or may not have stairs_up; level 1+ should
    assert dungeon.levels[1].stairs_up is not None


# ---------- Structures ----------

def test_structure_library():
    structures = StructureLibrary.all()
    assert len(structures) >= 30


def test_structure_lookup():
    s = StructureLibrary.get(StructureType.INN)
    assert s is not None
    assert "sleep" in s.services


# ---------- Stealth ----------

def test_stealth_basic():
    from engine.core.ecs import World, Entity
    sys = StealthSystem()
    e = Entity(id=1, generation=0)
    state = sys.get_state(e)
    state.stealth_skill = 5  # Need some skill to enter stealth
    assert state.state == StealthState.VISIBLE
    sys.enter_stealth(e)
    assert state.state == StealthState.HIDDEN


# ---------- Trade ----------

def test_trade_route_creation():
    sys = TradeSystem()
    route = sys.create_route("Test Route", 1, 2, (0, 0), (50, 50))
    assert route.distance_km > 0
    assert route.travel_time_days > 0


def test_caravan_dispatch():
    sys = TradeSystem()
    route = sys.create_route("Test", 1, 2, (0, 0), (50, 50))
    caravan = sys.dispatch_caravan(route.route_id, {"grain": 10}, 100)
    assert caravan is not None
    assert caravan.state.value == 1  # TRAVELLING


# ---------- Auctions ----------

def test_auction_basic():
    house = AuctionHouse()
    auction = house.schedule_auction(
        "Test Item", "A test", seller_id=1,
        item_id=10, item_name="Sword",
        starting_price=100, duration_seconds=3600,
        current_tick=0.0,
    )
    assert auction.state == AuctionState.SCHEDULED
    # Open it
    house.update(current_tick=0.0)
    assert auction.state == AuctionState.OPEN
    # Place bid
    ok, msg = house.place_bid(auction.auction_id, 2, 150, current_tick=10.0)
    assert ok
    assert auction.current_price == 150


# ---------- Companies ----------

def test_companies_library():
    sys = CompanySystem()
    assert len(sys.companies()) > 0
    assert len(sys.guilds()) > 0


def test_employment():
    from engine.utils.rng import RNG
    sys = CompanySystem(RNG(42))
    company = sys.companies()[0]
    employment = sys.employ(company.company_id, entity_id=999,
                            role="worker", salary=100)
    assert employment is not None
    assert employment.salary_copper_per_month == 100


# ---------- Espionage ----------

def test_espionage_recruit_spy():
    sys = EspionageSystem()
    spy = sys.recruit_spy(entity_id=1, name="James Bond")
    assert spy.spy_id == 1
    assert spy.name == "James Bond"


def test_espionage_mission():
    sys = EspionageSystem()
    spy = sys.recruit_spy(entity_id=1, name="Spy", stealth=10, deception=10)
    mission = sys.assign_mission(
        spy.spy_id, MissionType.GATHER_INTEL,
        target_faction_id=2, difficulty=1.0,
        current_tick=0.0,
    )
    assert mission is not None
    # Resolve it
    result = sys.resolve_mission(mission.mission_id, current_tick=100.0)
    assert result.name in ("SUCCESS", "PARTIAL_SUCCESS", "FAILURE",
                            "DISCOVERED", "SPY_CAPTURED", "SPY_KILLED")


# ---------- Mods Loader ----------

def test_mod_loader_discover():
    loader = ModLoader(mods_dir="mods")
    count = loader.discover()
    assert count >= 1  # example_mod.json


# ---------- Themes ----------

def test_themes_library():
    themes = ThemeLibrary.all()
    assert len(themes) >= 5
    dark = ThemeLibrary.get("dark")
    assert dark is not None
    assert dark.is_dark


# ---------- Keybindings ----------

def test_keybindings_default():
    kb = KeyBindings()
    action = kb.action_for("i")
    assert action == KeyAction.OPEN_INVENTORY
    action = kb.action_for("k")
    assert action == KeyAction.MOVE_NORTH


def test_keybindings_rebind():
    kb = KeyBindings()
    kb.rebind(KeyAction.OPEN_INVENTORY, ["I"])
    assert kb.action_for("I") == KeyAction.OPEN_INVENTORY


# ---------- Accessibility ----------

def test_accessibility_colorblindness():
    cfg = AccessibilityConfig()
    cfg.color_blindness = ColorBlindnessType.PROTANOPIA
    sys = AccessibilitySystem(cfg)
    # Red should be remapped
    assert sys.adjust_color(196) != 196


def test_accessibility_screen_reader():
    cfg = AccessibilityConfig()
    cfg.screen_reader.enabled = True
    sys = AccessibilitySystem(cfg)
    text = sys.describe_visual("Health: 50/100")
    assert "[" in text and "]" in text


# ---------- Behavior Trees ----------

def test_behavior_tree_sequence():
    counter = [0]
    def increment(ctx):
        counter[0] += 1
        return NodeStatus.SUCCESS
    tree = BehaviorTree(SequenceNode(children=[
        ActionNode(action_fn=increment),
        ActionNode(action_fn=increment),
        ActionNode(action_fn=increment),
    ]))
    status = tree.tick(None)
    assert status == NodeStatus.SUCCESS
    assert counter[0] == 3


def test_behavior_tree_selector():
    calls = []
    def fail(ctx):
        calls.append("fail")
        return NodeStatus.FAILURE
    def succeed(ctx):
        calls.append("succeed")
        return NodeStatus.SUCCESS
    tree = BehaviorTree(SelectorNode(children=[
        ActionNode(action_fn=fail),
        ActionNode(action_fn=succeed),
        ActionNode(action_fn=fail),
    ]))
    status = tree.tick(None)
    assert status == NodeStatus.SUCCESS
    assert calls == ["fail", "succeed"]


def test_behavior_tree_inverter():
    def always_succeed(ctx):
        return NodeStatus.SUCCESS
    tree = BehaviorTree(InverterNode(child=ActionNode(action_fn=always_succeed)))
    status = tree.tick(None)
    assert status == NodeStatus.FAILURE


# ---------- GOAP ----------

def test_goap_basic():
    planner = GOAPPlanner()
    initial = GOAPWorldState({"has_wood": False, "has_axe": True, "has_planks": False})
    goal = GOAPWorldState({"has_planks": True})
    actions = [
        GOAPAction("chop_wood", cost=1.0,
                   preconditions={"has_axe": True},
                   effects={"has_wood": True}),
        GOAPAction("make_planks", cost=1.0,
                   preconditions={"has_wood": True},
                   effects={"has_planks": True}),
    ]
    plan = planner.plan(initial, goal, actions)
    assert plan is not None
    assert len(plan) == 2
    assert plan[0].name == "chop_wood"
    assert plan[1].name == "make_planks"


def test_goap_no_plan():
    planner = GOAPPlanner()
    initial = GOAPWorldState({"has_wood": False})
    goal = GOAPWorldState({"has_planks": True})
    actions = [
        GOAPAction("make_planks", cost=1.0,
                   preconditions={"has_wood": True},
                   effects={"has_planks": True}),
    ]
    plan = planner.plan(initial, goal, actions)
    assert plan is None


# ---------- Plugin Extensions ----------

def test_plugin_sandbox_validation():
    sandbox = PluginSandbox()
    valid, error = sandbox.validate_source("x = 1 + 2")
    assert valid
    valid, error = sandbox.validate_source("import os")
    assert not valid


def test_plugin_migrator():
    migrator = PluginMigrator()

    @migrator.migration("test_plugin", "0.1.0", "0.2.0",
                        description="Add new field")
    def migrate(data):
        data["new_field"] = "default"
        return data

    data = {"version": "0.1.0", "old_field": 1}
    migrated = migrator.migrate("test_plugin", data, target_version="0.2.0")
    assert migrated["version"] == "0.2.0"
    assert migrated["new_field"] == "default"


def test_plugin_validator():
    from engine.plugins.base import PluginMetadata
    validator = PluginValidator()
    metadata = PluginMetadata(
        name="test_plugin", version="1.0.0",
        description="A test plugin.",
    )
    result = validator.validate_metadata(metadata)
    assert result.is_valid


def test_plugin_validator_invalid():
    from engine.plugins.base import PluginMetadata
    validator = PluginValidator()
    metadata = PluginMetadata(
        name="Test Plugin!", version="invalid",
        description="",
    )
    result = validator.validate_metadata(metadata)
    assert not result.is_valid


def test_plugin_docs_generator():
    from pathlib import Path
    gen = PluginDocGenerator()
    # Generate docs for the fishing plugin
    plugin_path = Path("plugins/fishing/plugin.py")
    if plugin_path.exists():
        doc = gen.generate(plugin_path)
        md = doc.to_markdown()
        assert "fishing" in md.lower()
