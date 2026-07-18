"""Entity factory — creates common entity archetypes."""

from __future__ import annotations

from typing import Optional

from engine.core.ecs import Entity, World
from engine.entities.components import (
    AI, Combat, Faction, Health, Identity, Inventory, Memory, Needs,
    Personality, Player, Position, Race, Relationships, Stats, Wealth,
)
from engine.utils.rng import RNG


class EntityFactory:
    """Builds common entity archetypes and attaches the right components."""

    def __init__(self, world: World, rng: Optional[RNG] = None) -> None:
        self.world = world
        self.rng = rng or RNG()

    # ---------- archetypes ----------

    def create_player(self, name: str = "Hero") -> Entity:
        e = self.world.create_entity()
        self.world.add_component(e, Identity(name=name, glyph="@", color=255))
        self.world.add_component(e, Position(x=0, y=0))
        self.world.add_component(e, Health(current=120, maximum=120, regeneration=0.5))
        self.world.add_component(e, Stats(strength=14, agility=14, endurance=12,
                                          intelligence=12, willpower=12,
                                          charisma=12, perception=14, luck=10))
        self.world.add_component(e, Needs())
        self.world.add_component(e, AI(controller="player", state="idle"))
        self.world.add_component(e, Combat())
        self.world.add_component(e, Race(race_id="human", age=22, max_age=85))
        self.world.add_component(e, Personality(courage=0.5, curiosity=0.4))
        self.world.add_component(e, Relationships())
        self.world.add_component(e, Wealth(gold=20, silver=50, copper=0))
        self.world.add_component(e, Memory())
        self.world.add_component(e, Player())
        self.world.tag(e, "player")
        self.world.tag(e, "humanoid")
        return e

    def create_npc(self, name: str, race_id: str = "human", x: int = 0, y: int = 0,
                   faction_id: Optional[int] = None) -> Entity:
        e = self.world.create_entity()
        glyph = self.rng.choice("abcdefgilmnoprstuvw")
        color = self.rng.randint(120, 250)
        self.world.add_component(e, Identity(name=name, glyph=glyph, color=color))
        self.world.add_component(e, Position(x=x, y=y))
        self.world.add_component(e, Health(current=80, maximum=80))
        # Random-ish stats centred on 10.
        stats_kwargs = {
            attr: max(3, self.rng.randint(7, 14))
            for attr in ("strength", "agility", "endurance", "intelligence",
                         "willpower", "charisma", "perception", "luck")
        }
        self.world.add_component(e, Stats(**stats_kwargs))
        self.world.add_component(e, Needs())
        self.world.add_component(e, AI(controller="civilian", state="idle"))
        self.world.add_component(e, Combat())
        self.world.add_component(e, Race(race_id=race_id, age=self.rng.randint(18, 70),
                                         max_age=85))
        personality = Personality(
            openness=self.rng.uniform(-0.8, 0.8),
            conscientiousness=self.rng.uniform(-0.8, 0.8),
            extraversion=self.rng.uniform(-0.8, 0.8),
            agreeableness=self.rng.uniform(-0.8, 0.8),
            neuroticism=self.rng.uniform(-0.8, 0.8),
            courage=self.rng.uniform(-0.5, 0.8),
            greed=self.rng.uniform(-0.5, 0.6),
            curiosity=self.rng.uniform(-0.5, 0.8),
        )
        self.world.add_component(e, personality)
        self.world.add_component(e, Relationships())
        self.world.add_component(e, Wealth(gold=self.rng.randint(0, 50),
                                           silver=self.rng.randint(0, 200),
                                           copper=self.rng.randint(0, 500)))
        self.world.add_component(e, Memory())
        if faction_id is not None:
            self.world.add_component(e, Faction(faction_id=faction_id,
                                                rank=self.rng.randint(0, 3),
                                                reputation=self.rng.randint(-10, 30)))
        self.world.tag(e, "humanoid")
        self.world.tag(e, "npc")
        return e

    def create_creature(self, name: str, glyph: str, color: int,
                        x: int = 0, y: int = 0, *,
                        hp: int = 30, strength: int = 8, agility: int = 10,
                        aggressive: bool = False, race_id: str = "beast") -> Entity:
        e = self.world.create_entity()
        self.world.add_component(e, Identity(name=name, glyph=glyph, color=color,
                                             description=f"A wild {name.lower()}."))
        self.world.add_component(e, Position(x=x, y=y))
        self.world.add_component(e, Health(current=hp, maximum=hp))
        self.world.add_component(e, Stats(strength=strength, agility=agility,
                                          endurance=hp // 4 + 5,
                                          perception=12, luck=5))
        self.world.add_component(e, Needs(hunger=self.rng.uniform(20, 60),
                                          thirst=self.rng.uniform(20, 60)))
        self.world.add_component(e, AI(controller="aggressive" if aggressive else "wander",
                                       state="idle"))
        self.world.add_component(e, Combat())
        self.world.add_component(e, Race(race_id=race_id, size="medium",
                                         age=self.rng.randint(1, 10), max_age=15))
        if aggressive:
            self.world.tag(e, "hostile")
        self.world.tag(e, "creature")
        return e

    def create_item_entity(self, item_id: int, x: int, y: int) -> Entity:
        """A dropped item entity — links to the ItemRegistry via item_id."""
        from engine.entities.components import Tag
        e = self.world.create_entity()
        self.world.add_component(e, Position(x=x, y=y))
        self.world.add_component(e, Tag(tags=[f"item:{item_id}", "ground"]))
        self.world.tag(e, "item")
        return e
