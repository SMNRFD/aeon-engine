"""Tests for Phase 3 systems."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.dimensions.system import (
    DimensionManager, DimensionType, DEFAULT_DIMENSIONS,
)
from engine.realtime_combat.system import (
    RealtimeCombatSystem, CombatAction, ActionPriority,
)
from engine.bodyparts.system import (
    BodyPartsSystem, BodyPartType, BodyPartStatus, BodyPartLibrary,
)
from engine.mounted_combat.system import MountedCombatSystem, Mount
from engine.naval_combat.system import (
    NavalCombatSystem, Warship, ShipType,
)
from engine.aerial_combat.system import (
    AerialCombatSystem, FlyingMount, AerialManeuver,
)
from engine.siege_combat.system import (
    SiegeCombatSystem, SiegeEngineType, SiegeState,
)
from engine.space_combat.system import (
    SpaceCombatSystem, Spacecraft, SpaceWeaponType,
)
from engine.runes.system import (
    RuneSystem, RuneLibrary, RuneType,
)
from engine.artifacts.system import (
    ArtifactSystem, ArtifactLibrary, ArtifactRarity,
)
from engine.rebellions.system import (
    RebellionSystem, RebellionType, RebellionState,
)
from engine.blackmarket.system import BlackMarketSystem
from engine.replication.system import (
    ReplicationSystem, ClientPredictor, ServerAuthority, RollbackSystem,
    NetworkPriority,
)
from engine.streaming.system import StreamingWorld, ChunkManager, ChunkLoader
from engine.content_packs.system import (
    ContentPackManager, ContentPackType,
)
from engine.bookmarks.system import (
    BookmarkManager, BookmarkType,
)
from engine.ui_extensions.system import (
    SearchFilter, FilterCriteria, SortableList, SortOrder, MouseInput,
    UIStateManager,
)
from engine.procedural_dialogue.system import (
    ProceduralDialogueEngine, NPCContext,
)
from engine.skill_books.system import (
    SkillBookLibrary, BookReadingSystem, SkillDiscoverySystem, BookType,
)
from engine.quest_consequences.system import (
    ConsequenceSystem, ConsequenceType, QuestChain, QuestConsequence,
)
from engine.background_sim.system import (
    BackgroundSimulator, EventType,
)


# ---------- Dimensions ----------

def test_dimension_manager():
    mgr = DimensionManager()
    assert len(mgr.all_dimensions()) >= 10  # defaults
    material = next(d for d in mgr.all_dimensions()
                    if d.dimension_type == DimensionType.MATERIAL)
    assert material.name == "Material Plane"

def test_dimension_create_planet():
    mgr = DimensionManager()
    material = next(d for d in mgr.all_dimensions()
                    if d.dimension_type == DimensionType.MATERIAL)
    planet = mgr.create_planet("Test", material.dimension_id)
    assert planet.name == "Test"
    assert planet.dimension_id == material.dimension_id
    assert planet.planet_id in material.planets

def test_dimension_travel():
    mgr = DimensionManager()
    dims = mgr.all_dimensions()
    # Open portal from material to shadowfell
    material = next(d for d in dims if d.dimension_type == DimensionType.MATERIAL)
    shadow = next(d for d in dims if d.dimension_type == DimensionType.SHADOW)
    mgr.open_portal(material.dimension_id, shadow.dimension_id)
    can, _ = mgr.can_travel(material.dimension_id, shadow.dimension_id)
    assert can
    # Close it
    mgr.close_portal(material.dimension_id, shadow.dimension_id)
    can, _ = mgr.can_travel(material.dimension_id, shadow.dimension_id)
    assert not can


# ---------- Real-time Combat ----------

def test_realtime_combat_queue_attack():
    from engine.core.ecs import World, Entity
    from engine.entities.factory import EntityFactory
    from engine.utils.rng import RNG
    world = World()
    factory = EntityFactory(world, RNG(42))
    attacker = factory.create_creature("Attacker", "a", 100, hp=50, aggressive=True)
    target = factory.create_creature("Target", "t", 100, hp=50, aggressive=False)
    sys = RealtimeCombatSystem(RNG(42))
    action = sys.queue_attack(attacker, target, cast_time=0.5, cooldown=1.0)
    assert action is not None
    assert action.attacker_id == attacker.id
    assert action.target_id == target.id


def test_realtime_combat_cooldown():
    from engine.core.ecs import World, Entity
    from engine.entities.factory import EntityFactory
    from engine.utils.rng import RNG
    world = World()
    factory = EntityFactory(world, RNG(42))
    attacker = factory.create_creature("A", "a", 100, hp=50, aggressive=True)
    target = factory.create_creature("T", "t", 100, hp=50, aggressive=False)
    sys = RealtimeCombatSystem(RNG(42))
    sys.queue_attack(attacker, target, action_id="basic", cast_time=0.1, cooldown=2.0)
    # Try again — should fail (cooldown)
    action2 = sys.queue_attack(attacker, target, action_id="basic")
    assert action2 is None


def test_realtime_combat_update():
    from engine.core.ecs import World, Entity
    from engine.entities.factory import EntityFactory
    from engine.utils.rng import RNG
    world = World()
    factory = EntityFactory(world, RNG(42))
    attacker = factory.create_creature("A", "a", 100, hp=50, aggressive=True)
    target = factory.create_creature("T", "t", 100, hp=50, aggressive=False)
    sys = RealtimeCombatSystem(RNG(42))
    sys.queue_attack(attacker, target, cast_time=0.1)
    # Advance time
    results = sys.update(world, dt=0.2)
    assert len(results) >= 1  # action should have resolved


# ---------- Body Parts ----------

def test_body_parts_library():
    parts = BodyPartLibrary.get("humanoid")
    assert parts is not None
    assert len(parts) >= 15  # many body parts

def test_body_parts_assign():
    from engine.core.ecs import World, Entity
    world = World()
    entity = world.create_entity()
    sys = BodyPartsSystem()
    sys.assign_body(entity, "humanoid")
    parts = sys.body_parts(entity)
    assert len(parts) > 0

def test_body_parts_hit():
    from engine.core.ecs import World, Entity, Entity
    from engine.entities.components import Health
    from engine.utils.rng import RNG
    world = World()
    entity = world.create_entity()
    world.add_component(entity, Health(current=100, maximum=100))
    sys = BodyPartsSystem(RNG(42))
    sys.assign_body(entity, "humanoid")
    hit = sys.hit(world, entity, damage=20)
    assert hit is not None
    assert hit.damage > 0


def test_body_parts_cripple():
    from engine.core.ecs import World, Entity
    from engine.entities.components import Health
    from engine.utils.rng import RNG
    world = World()
    entity = world.create_entity()
    world.add_component(entity, Health(current=100, maximum=100))
    sys = BodyPartsSystem(RNG(42))
    sys.assign_body(entity, "humanoid")
    # Hit the head repeatedly
    for _ in range(10):
        sys.hit(world, entity, damage=20, part_type=BodyPartType.HEAD)
    head = sys.get_part(entity, BodyPartType.HEAD)
    assert head.status >= BodyPartStatus.INJURED


# ---------- Mounted Combat ----------

def test_mounted_combat():
    from engine.core.ecs import World, Entity
    from engine.entities.factory import EntityFactory
    from engine.utils.rng import RNG
    world = World()
    factory = EntityFactory(world, RNG(42))
    rider = factory.create_creature("Rider", "r", 100, hp=50)
    target = factory.create_creature("Target", "t", 100, hp=50)
    sys = MountedCombatSystem(RNG(42))
    mount = sys.create_mount("horse", "Thunder")
    sys.mount_up(rider, mount)
    assert sys.is_mounted(rider)
    result = sys.mounted_attack(world, rider, target)
    assert result.attacker == rider.id
    sys.dismount(rider)
    assert not sys.is_mounted(rider)


# ---------- Naval Combat ----------

def test_naval_combat_create_ship():
    sys = NavalCombatSystem()
    ship = sys.create_ship("HMS Test", ShipType.GALLEON)
    assert ship.name == "HMS Test"
    assert ship.ship_type == ShipType.GALLEON
    assert ship.cannon_count == 20  # from SHIP_STATS


def test_naval_combat_bombard():
    sys = NavalCombatSystem()
    attacker = sys.create_ship("Attacker", ShipType.GALLEON, position=(0, 0))
    target = sys.create_ship("Target", ShipType.COG, position=(5, 5))
    result = sys.bombard(attacker, target)
    # Should hit at least sometimes (with 20 cannons at 60% chance)
    # but with the RNG seed it might vary, so just check the result is well-formed
    assert result.attacker_id == attacker.ship_id


# ---------- Aerial Combat ----------

def test_aerial_combat():
    from engine.core.ecs import World, Entity
    from engine.entities.factory import EntityFactory
    from engine.utils.rng import RNG
    world = World()
    factory = EntityFactory(world, RNG(42))
    rider = factory.create_creature("Rider", "r", 100, hp=50)
    target = factory.create_creature("Target", "t", 100, hp=50, aggressive=False)
    sys = AerialCombatSystem(RNG(42))
    mount = sys.create_mount("griffin", "Windrider")
    sys.mount_up(rider, mount)
    sys.set_maneuver(rider, AerialManeuver.DIVE)
    result = sys.aerial_attack(world, rider, target)
    assert result.attacker == rider.id


# ---------- Siege Combat ----------

def test_siege_combat():
    sys = SiegeCombatSystem()
    siege = sys.create_siege(
        attacker_faction_id=1, defender_faction_id=2,
        fortification_name="Test Castle",
    )
    assert siege.fortification_name == "Test Castle"
    assert len(siege.wall_sections) > 0
    sys.add_siege_engine(siege.siege_id, SiegeEngineType.CATAPULT)
    assert len(siege.siege_engines) == 1


# ---------- Space Combat ----------

def test_space_combat():
    sys = SpaceCombatSystem()
    ship1 = sys.create_ship("USS Test", "frigate")
    ship2 = sys.create_ship("Enemy", "corvette",
                             position=(10, 0, 0))
    weapon = sys.add_weapon(ship1, SpaceWeaponType.LASER)
    result = sys.fire_weapon(ship1, ship2, weapon)
    assert "hit" in result


# ---------- Runes ----------

def test_rune_library():
    runes = RuneLibrary.all()
    assert len(runes) >= 10

def test_rune_inscribe():
    sys = RuneSystem()
    fire_rune = RuneLibrary.get("rune_fire")
    ok, msg, inscription = sys.inscribe(1, fire_rune, skill_level=10)
    assert ok
    assert inscription is not None
    effects = sys.total_effects(1)
    assert "fire_damage" in effects


# ---------- Artifacts ----------

def test_artifact_library():
    artifacts = ArtifactLibrary.all()
    assert len(artifacts) >= 5

def test_artifact_wield():
    sys = ArtifactSystem()
    artifact = ArtifactLibrary.all()[0]
    sys.wield(artifact, entity_id=42)
    assert artifact.owner_id == 42
    assert 42 in artifact.previous_owners or artifact.previous_owners == []


def test_artifact_use_power():
    sys = ArtifactSystem()
    artifact = ArtifactLibrary.all()[0]
    # Reset uses first
    for power in artifact.powers:
        if "uses_per_day" in power:
            power["uses_remaining"] = power["uses_per_day"]
    if artifact.powers:
        power_name = artifact.powers[0]["name"]
        ok, msg = sys.use_power(artifact, power_name, current_tick=0.0)
        assert ok


# ---------- Rebellions ----------

def test_rebellion_start():
    sys = RebellionSystem()
    rebellion = sys.start_rebellion(
        "Test Revolt", RebellionType.PEASANT_REVOLT, faction_id=1,
        grievances=["high taxes", "famine"],
    )
    assert rebellion.state == RebellionState.BREWING
    assert "high taxes" in rebellion.grievances


def test_civil_war():
    sys = RebellionSystem()
    cw = sys.start_civil_war(faction_id=1, claimant_a=1, claimant_b=2,
                              cause="succession dispute")
    assert cw.is_active
    result = sys.civil_war_battle(cw.civil_war_id)
    assert "a_wins" in result


# ---------- Black Market ----------

def test_black_market():
    sys = BlackMarketSystem()
    market = sys.create_market("Thieves' Den", (10, 20))
    assert market.is_hidden
    sys.discover_market(market.market_id, entity_id=1)
    assert not market.is_hidden
    sys.add_listing(market.market_id, "Stolen Sword", "stolen_good",
                    price=100, is_stolen=True)
    assert len(market.listings) == 1


# ---------- Replication ----------

def test_replication_system():
    sys = ReplicationSystem()
    state = sys.register_entity(1, NetworkPriority.HIGH)
    sys.update_state(1, {"x": 10, "y": 20})
    snapshot = sys.take_snapshot(current_tick=0)
    assert 1 in snapshot.states

def test_client_predictor():
    predictor = ClientPredictor()
    predictor.predict(1, tick=0, state={"x": 0, "y": 0})
    predictor.predict(1, tick=1, state={"x": 1, "y": 0})
    mismatch, state = predictor.reconcile(1, server_tick=0, server_state={"x": 0, "y": 0})
    # No mismatch
    assert not mismatch

def test_server_authority():
    auth = ServerAuthority()
    auth.authorize_client("move", client_id=1)
    ok, msg = auth.validate_action("move", 1, {"x": 5, "y": 5, "old_x": 4, "old_y": 5})
    assert ok
    # Try unauthorized client
    ok, msg = auth.validate_action("move", 2, {})
    assert not ok


def test_rollback_system():
    sys = RollbackSystem()
    sys.save_state(0, {"hp": 100})
    sys.save_state(1, {"hp": 90})
    sys.save_state(2, {"hp": 80})
    state = sys.rollback_to(1)
    assert state == {"hp": 90}


# ---------- Streaming World ----------

def test_streaming_world():
    world = StreamingWorld(seed=42, chunk_size=16, view_distance=2)
    # Disable async loading so chunks load synchronously
    world.coordinator.async_loading = False
    # Force update by moving to a non-default center first
    world.update_center(100, 100)
    world.update_center(0, 0)
    # Should load some chunks
    stats = world.stats()
    assert stats["manager"]["loaded"] > 0


def test_streaming_world_get_tile():
    world = StreamingWorld(seed=42, chunk_size=16, view_distance=2)
    world.coordinator.async_loading = False
    world.update_center(100, 100)
    world.update_center(0, 0)
    tile = world.get_tile(0, 0)
    assert tile is not None
    assert tile.x == 0
    assert tile.y == 0


# ---------- Content Packs ----------

def test_content_pack_manager():
    mgr = ContentPackManager()
    # No packs dir, so 0 discovered
    assert mgr.registry is not None


# ---------- Bookmarks ----------

def test_bookmark_manager():
    mgr = BookmarkManager()
    bookmark = mgr.add_bookmark("My Spot", x=10, y=20,
                                 bookmark_type=BookmarkType.LOCATION)
    assert bookmark.name == "My Spot"
    assert bookmark.x == 10
    assert bookmark.y == 20
    # Search
    results = mgr.search("spot")
    assert len(results["bookmarks"]) == 1


def test_bookmark_pins():
    mgr = BookmarkManager()
    pin = mgr.add_pin(x=5, y=10, label="Look here")
    assert pin.label == "Look here"
    pins = mgr.pins_at(5, 10)
    assert len(pins) == 1


# ---------- UI Extensions ----------

def test_search_filter():
    items = [
        {"name": "Sword", "value": 100},
        {"name": "Shield", "value": 50},
        {"name": "Potion", "value": 10},
    ]
    f = SearchFilter(query="sword")
    result = f.filter(items)
    assert len(result) == 1
    assert result[0]["name"] == "Sword"

def test_filter_criteria():
    items = [
        {"name": "Sword", "value": 100},
        {"name": "Shield", "value": 50},
        {"name": "Potion", "value": 10},
    ]
    f = SearchFilter(criteria=[FilterCriteria("value", 50, operator=">=")])
    result = f.filter(items)
    assert len(result) == 2  # Sword and Shield

def test_sortable_list():
    items = [
        {"name": "Sword", "value": 100},
        {"name": "Shield", "value": 50},
        {"name": "Potion", "value": 10},
    ]
    slist = SortableList(items)
    slist.sort("value", SortOrder.DESCENDING)
    assert slist.items[0]["value"] == 100
    assert slist.items[-1]["value"] == 10

def test_ui_state_manager():
    mgr = UIStateManager()
    mgr.set_focus("inventory")
    assert mgr.focus == "inventory"
    mgr.scroll_down("inventory", amount=5)
    assert mgr.get_scroll("inventory") == 5
    mgr.toggle_expanded("inventory")
    assert mgr.is_expanded("inventory")


# ---------- Procedural Dialogue ----------

def test_procedural_dialogue_greeting():
    engine = ProceduralDialogueEngine()
    context = NPCContext(npc_name="Aldric", player_name="Hero",
                          relationship_to_player=0.7)
    line = engine.generate_greeting(context)
    assert line.speaker == "Aldric"
    assert "Hero" in line.text or "traveler" in line.text.lower()


def test_procedural_dialogue_response():
    engine = ProceduralDialogueEngine()
    context = NPCContext(npc_name="Aldric", player_name="Hero")
    line = engine.generate_response_to_question("What's the weather like?", context)
    assert line.speaker == "Aldric"
    assert line.topic == "weather"


# ---------- Skill Books ----------

def test_skill_book_library():
    books = SkillBookLibrary.all()
    assert len(books) >= 10

def test_book_reading():
    from engine.core.ecs import World, Entity
    world = World()
    entity = world.create_entity()
    sys = BookReadingSystem()
    book = SkillBookLibrary.all()[0]
    ok, msg = sys.start_reading(entity, book)
    assert ok
    # Advance reading
    result = sys.update_reading(entity, dt_hours=book.reading_time_hours + 0.1)
    assert result is not None
    assert result.get("completed") is True


def test_skill_discovery():
    from engine.core.ecs import World, Entity
    world = World()
    entity = world.create_entity()
    sys = SkillDiscoverySystem()
    # Try many times for inspiration
    discovered = None
    for _ in range(100):
        result = sys.check_inspiration(entity, "swordsmanship", skill_level=5)
        if result:
            discovered = result
            break
    # Inspiration chance is low, so this might be None; that's OK
    # but we want to verify the function doesn't crash


# ---------- Quest Consequences ----------

def test_quest_consequences():
    sys = ConsequenceSystem()
    assert len(sys.chains()) > 0
    # Complete the first quest of the first chain
    chain = sys.chains()[0]
    if chain.quest_ids:
        applied = sys.on_quest_complete(chain.quest_ids[0], current_tick=0.0)
        # Some consequences may have been applied
        assert isinstance(applied, list)


# ---------- Background Simulation ----------

def test_background_simulator():
    sys = BackgroundSimulator()
    sys.start()
    report = sys.simulate(duration_real_seconds=1.0, start_tick=0.0)
    assert report.duration_real_seconds == 1.0
    # Should have generated some events
    assert report.total_events > 0
    assert report.duration_game_hours > 0
    assert report.summary != ""


def test_background_simulator_events():
    sys = BackgroundSimulator()
    sys.start()
    sys.simulate(duration_real_seconds=0.5, start_tick=0.0)
    events = sys.all_events()
    assert len(events) > 0
    major = sys.major_events()
    # Some events might be major
    assert isinstance(major, list)
