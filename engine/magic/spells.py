"""Spell definitions and casting logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, Optional

from engine.core.ecs import Component, Entity, World
from engine.entities.components import Health, Stats, Combat as CombatComponent
from engine.combat.damage import Damage, DamageType
from engine.combat.effects import StatusEffectSystem
from engine.utils.rng import RNG


# Mana component (declared here so we don't pollute entities.components).
from dataclasses import dataclass as _dc


@_dc
class Mana(Component):
    current: float = 50.0
    maximum: float = 50.0
    regeneration: float = 0.5


class SpellTarget(Enum):
    SELF = "self"
    ALLY = "ally"
    ENEMY = "enemy"
    AREA = "area"
    POINT = "point"
    ITEM = "item"


@dataclass
class SpellEffect:
    """A single effect of a spell."""

    kind: str  # "damage", "heal", "buff", "debuff", "summon", "teleport", "ward"
    magnitude: float = 0.0
    duration: float = 0.0
    damage_type: Optional[DamageType] = None
    area_radius: float = 0.0
    target_filter: Optional[str] = None
    status_effect: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Spell:
    """A spell definition."""

    id: str
    name: str
    school_id: str
    description: str
    mana_cost: int
    cast_time: float = 1.0       # seconds
    cooldown: float = 0.0
    target: SpellTarget = SpellTarget.ENEMY
    range_: float = 30.0
    level: int = 1
    skill_id: str = ""
    effects: list[SpellEffect] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    verbal: bool = True
    somatic: bool = True
    material: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "school_id": self.school_id,
            "description": self.description, "mana_cost": self.mana_cost,
            "cast_time": self.cast_time, "cooldown": self.cooldown,
            "target": self.target.value, "range_": self.range_,
            "level": self.level, "skill_id": self.skill_id,
            "effects": [
                {"kind": e.kind, "magnitude": e.magnitude, "duration": e.duration,
                 "damage_type": e.damage_type.value if e.damage_type else None,
                 "area_radius": e.area_radius, "status_effect": e.status_effect,
                 "data": e.data}
                for e in self.effects
            ],
            "tags": self.tags,
        }


@dataclass
class SpellCastResult:
    success: bool
    message: str
    mana_spent: int = 0
    damage_dealt: float = 0.0
    healing_done: float = 0.0
    status_effects_applied: list[str] = field(default_factory=list)
    targets_affected: list[int] = field(default_factory=list)


class SpellLibrary:
    """Registry of spells."""

    _spells: ClassVar[dict[str, Spell]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, spell: Spell) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._spells[spell.id] = spell

    @classmethod
    def get(cls, spell_id: str) -> Spell | None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._spells.get(spell_id)

    @classmethod
    def all(cls) -> list[Spell]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._spells.values())

    @classmethod
    def by_school(cls, school_id: str) -> list[Spell]:
        return [s for s in cls.all() if s.school_id == school_id]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for s in DEFAULT_SPELLS:
            cls._spells[s.id] = s
        cls._defaults_loaded = True


class SpellCaster:
    """Resolves spell casting."""

    def __init__(self, status_system: Optional[StatusEffectSystem] = None,
                 rng: Optional[RNG] = None) -> None:
        self.status = status_system or StatusEffectSystem()
        self.rng = rng or RNG()

    def cast(self, world: World, caster: Entity, spell: Spell,
             target: Optional[Entity] = None) -> SpellCastResult:
        # Check mana
        mana = world.get_component(caster, Mana)
        if mana is None or mana.current < spell.mana_cost:
            return SpellCastResult(success=False,
                                    message="Not enough mana.",
                                    mana_spent=0)
        # Consume mana
        mana.current -= spell.mana_cost

        # Apply effects
        damage_total = 0.0
        heal_total = 0.0
        statuses_applied: list[str] = []
        targets_affected: list[int] = []

        # Determine targets
        targets: list[Entity] = []
        if spell.target == SpellTarget.SELF:
            targets = [caster]
        elif spell.target in (SpellTarget.ENEMY, SpellTarget.ALLY, SpellTarget.ITEM):
            if target is None:
                return SpellCastResult(success=False,
                                        message="Spell requires a target.",
                                        mana_spent=spell.mana_cost)
            targets = [target]
        elif spell.target == SpellTarget.AREA:
            # Find all entities near target
            pos_c = world.get_component(caster, None.__class__) if False else None
            from engine.entities.components import Position
            caster_pos = world.get_component(caster, Position)
            target_pos = world.get_component(target, Position) if target else caster_pos
            if target_pos is None:
                return SpellCastResult(success=False,
                                        message="No position to centre the area.",
                                        mana_spent=spell.mana_cost)
            radius = max(e.area_radius for e in spell.effects) if spell.effects else 5.0
            from engine.entities.components import Position
            for ent, (p,) in world.view(Position):
                if (p.x - target_pos.x) ** 2 + (p.y - target_pos.y) ** 2 <= radius * radius:
                    targets.append(ent)

        for tgt in targets:
            tgt_health = world.get_component(tgt, Health)
            for effect in spell.effects:
                if effect.kind == "damage" and tgt_health:
                    dmg = Damage(
                        amount=effect.magnitude,
                        type=effect.damage_type or DamageType.TRUE,
                        source=f"spell:{spell.id}",
                    )
                    from engine.combat.damage import DamageCalculator
                    final = DamageCalculator.compute(dmg, world.get_component(tgt, Stats))
                    if not tgt_health.invulnerable:
                        tgt_health.current = max(0, int(tgt_health.current - final))
                    damage_total += final
                elif effect.kind == "heal" and tgt_health:
                    tgt_health.current = min(tgt_health.maximum,
                                             int(tgt_health.current + effect.magnitude))
                    heal_total += effect.magnitude
                elif effect.kind in ("buff", "debuff") and effect.status_effect:
                    self.status.apply(world, tgt, effect.status_effect,
                                      duration=effect.duration,
                                      magnitude=effect.magnitude,
                                      source=caster.id)
                    statuses_applied.append(effect.status_effect)
            targets_affected.append(tgt.id)

        return SpellCastResult(
            success=True,
            message=f"{caster.id} casts {spell.name}!",
            mana_spent=spell.mana_cost,
            damage_dealt=damage_total,
            healing_done=heal_total,
            status_effects_applied=statuses_applied,
            targets_affected=targets_affected,
        )


# Default spells
DEFAULT_SPELLS: list[Spell] = [
    Spell("fireball", "Fireball", "evocation",
          "Hurls a ball of fire that explodes on impact.",
          30, 1.5, 3.0, SpellTarget.AREA, 30.0, 5, "evocation",
          [SpellEffect("damage", 35.0, 0.0, DamageType.FIRE, area_radius=4.0)],
          tags=["fire", "destructive"], material="sulphur"),
    Spell("magic_missile", "Magic Missile", "evocation",
          "Homing bolts of force that never miss.", 10, 0.5, 0.0,
          SpellTarget.ENEMY, 40.0, 1, "evocation",
          [SpellEffect("damage", 15.0, 0.0, DamageType.TRUE)],
          tags=["force"]),
    Spell("frost_nova", "Frost Nova", "evocation",
          "A burst of ice that freezes nearby enemies.", 25, 1.0, 5.0,
          SpellTarget.AREA, 5.0, 5, "evocation",
          [SpellEffect("damage", 20.0, 0.0, DamageType.COLD, area_radius=5.0),
           SpellEffect("debuff", 0.0, 3.0, status_effect="frozen", area_radius=5.0)],
          tags=["cold", "control"]),
    Spell("heal", "Heal Wounds", "abjuration",
          "Restores health to a single ally.", 20, 2.0, 1.0,
          SpellTarget.ALLY, 5.0, 1, "abjuration",
          [SpellEffect("heal", 30.0, 0.0)],
          tags=["healing"]),
    Spell("mass_heal", "Mass Heal", "abjuration",
          "Heals all nearby allies.", 80, 4.0, 10.0,
          SpellTarget.AREA, 15.0, 30, "abjuration",
          [SpellEffect("heal", 50.0, 0.0, area_radius=15.0)],
          tags=["healing"]),
    Spell("lightning_bolt", "Lightning Bolt", "evocation",
          "A bolt of pure electricity.", 35, 1.0, 2.0,
          SpellTarget.ENEMY, 50.0, 10, "evocation",
          [SpellEffect("damage", 45.0, 0.0, DamageType.LIGHTNING)],
          tags=["lightning", "destructive"]),
    Spell("summon_familiar", "Summon Familiar", "conjuration",
          "Summons a small spirit companion.", 50, 5.0, 60.0,
          SpellTarget.SELF, 0.0, 15, "conjuration",
          [SpellEffect("summon", 0.0, 600.0, data={"creature": "familiar"})],
          tags=["summoning"]),
    Spell("fear", "Cause Fear", "enchantment",
          "Causes terror in the target.", 25, 2.0, 8.0,
          SpellTarget.ENEMY, 20.0, 10, "enchantment",
          [SpellEffect("debuff", 0.0, 8.0, status_effect="fear")],
          tags=["mental", "control"]),
    Spell("raise_dead", "Raise Dead", "necromancy",
          "Animates a corpse as a zombie servant.", 60, 5.0, 30.0,
          SpellTarget.ITEM, 5.0, 25, "necromancy",
          [SpellEffect("summon", 0.0, 1200.0, data={"creature": "zombie"})],
          tags=["forbidden", "death"], material="corpse"),
    Spell("shield", "Arcane Shield", "abjuration",
          "Covers the caster in protective energy.", 15, 1.0, 8.0,
          SpellTarget.SELF, 0.0, 3, "abjuration",
          [SpellEffect("buff", 5.0, 60.0, status_effect="blessed")],
          tags=["protective"]),
    Spell("teleport", "Blink", "transmutation",
          "Instantly transports the caster a short distance.", 20, 0.5, 3.0,
          SpellTarget.SELF, 0.0, 10, "transmutation",
          [SpellEffect("teleport", 0.0, 0.0, data={"range": 15})],
          tags=["movement"]),
    Spell("clairvoyance", "Clairvoyance", "divination",
          "Reveals nearby entities and items.", 30, 3.0, 10.0,
          SpellTarget.SELF, 0.0, 8, "divination",
          [SpellEffect("buff", 0.0, 30.0, status_effect="blessed")],
          tags=["knowledge"]),
]
