"""Hit locations — body parts damage system.

Each entity has a set of body parts. Attacks can target specific parts,
with different effects:
* Head — critical hits, instant KO chance
* Torso — large target, standard damage
* Arms — disarming chance
* Legs — movement reduction
* Wings — grounded flight
* Tail — balance loss

Body parts have their own HP, can be injured, crippled, or severed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Health, Stats, Position
from engine.utils.rng import RNG


class BodyPartType(IntEnum):
    HEAD = 0
    NECK = 1
    TORSO = 2
    ABDOMEN = 3
    ARM_LEFT = 4
    ARM_RIGHT = 5
    HAND_LEFT = 6
    HAND_RIGHT = 7
    LEG_LEFT = 8
    LEG_RIGHT = 9
    FOOT_LEFT = 10
    FOOT_RIGHT = 11
    WING_LEFT = 12
    WING_RIGHT = 13
    TAIL = 14
    EYE_LEFT = 15
    EYE_RIGHT = 16
    EAR_LEFT = 17
    EAR_RIGHT = 18
    HEART = 19
    BRAIN = 20
    SPINE = 21
    VITAL_ORGAN = 22  # generic


class BodyPartStatus(IntEnum):
    HEALTHY = 0
    INJURED = 1     # reduced function
    CRIPPLED = 2    # severely damaged
    SEVERED = 3     # lost entirely
    INFECTED = 4


@dataclass
class BodyPart:
    """A single body part."""

    part_type: BodyPartType
    name: str
    hp_max: int = 100
    hp_current: int = 100
    status: BodyPartStatus = BodyPartStatus.HEALTHY
    hit_weight: float = 1.0   # relative chance of being hit
    armor_id: Optional[int] = None  # worn armor on this part
    critical_multiplier: float = 2.0
    cripple_threshold: float = 0.25  # hp fraction below which part is crippled
    severable: bool = False
    effects_when_hit: dict[str, float] = field(default_factory=dict)
    # Effects fired when this part is hit:
    #   "disarm" - chance to drop weapon (hands)
    #   "knockout" - chance to KO (head)
    #   "immobilize" - chance to stop movement (legs)
    #   "blind" - chance to blind (eyes)
    #   "deafen" - chance to deafen (ears)
    #   "bleed" - chance to cause bleeding

    @property
    def hp_fraction(self) -> float:
        return self.hp_current / max(1, self.hp_max)

    @property
    def is_crippled(self) -> bool:
        return self.status >= BodyPartStatus.CRIPPLED

    @property
    def is_severed(self) -> bool:
        return self.status == BodyPartStatus.SEVERED

    def damage(self, amount: int) -> None:
        self.hp_current = max(0, self.hp_current - amount)
        if self.hp_current == 0 and self.severable:
            self.status = BodyPartStatus.SEVERED
        elif self.hp_fraction <= self.cripple_threshold:
            self.status = BodyPartStatus.CRIPPLED
        elif self.hp_fraction < 0.5:
            self.status = BodyPartStatus.INJURED

    def heal(self, amount: int) -> None:
        self.hp_current = min(self.hp_max, self.hp_current + amount)
        if self.status == BodyPartStatus.INJURED and self.hp_fraction >= 0.5:
            self.status = BodyPartStatus.HEALTHY
        elif self.status == BodyPartStatus.CRIPPLED and self.hp_fraction >= self.cripple_threshold + 0.1:
            self.status = BodyPartStatus.INJURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "part_type": int(self.part_type),
            "name": self.name,
            "hp_max": self.hp_max,
            "hp_current": self.hp_current,
            "status": int(self.status),
            "hit_weight": self.hit_weight,
            "armor_id": self.armor_id,
            "critical_multiplier": self.critical_multiplier,
            "cripple_threshold": self.cripple_threshold,
            "severable": self.severable,
            "effects_when_hit": dict(self.effects_when_hit),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BodyPart":
        return cls(
            part_type=BodyPartType(data["part_type"]),
            name=data["name"],
            hp_max=data.get("hp_max", 100),
            hp_current=data.get("hp_current", 100),
            status=BodyPartStatus(data.get("status", 0)),
            hit_weight=data.get("hit_weight", 1.0),
            armor_id=data.get("armor_id"),
            critical_multiplier=data.get("critical_multiplier", 2.0),
            cripple_threshold=data.get("cripple_threshold", 0.25),
            severable=data.get("severable", False),
            effects_when_hit=dict(data.get("effects_when_hit", {})),
        )


@dataclass
class BodyPartHit:
    """Result of a hit to a body part."""

    part: BodyPartType
    damage: int
    is_critical: bool
    status_changed: bool = False
    severed: bool = False
    effects_applied: list[str] = field(default_factory=list)
    message: str = ""


class BodyPartLibrary:
    """Registry of body part templates for different species."""

    _templates: ClassVar[dict[str, list[BodyPart]]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, species: str, parts: list[BodyPart]) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._templates[species] = parts

    @classmethod
    def get(cls, species: str) -> Optional[list[BodyPart]]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._templates.get(species)

    @classmethod
    def all_species(cls) -> list[str]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return sorted(cls._templates.keys())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for species, parts in [
            ("humanoid", HUMANOID_BODY),
            ("quadruped", QUADRUPED_BODY),
            ("avian", AVIAN_BODY),
            ("serpentine", SERPENTINE_BODY),
        ]:
            cls._templates[species] = [BodyPart(**p.__dict__) for p in parts]
        cls._defaults_loaded = True


class BodyPartsSystem:
    """Manages per-entity body parts."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        # entity_id -> list of body parts
        self._body_parts: dict[int, list[BodyPart]] = {}

    def assign_body(self, entity: Entity, species: str = "humanoid") -> None:
        """Assign a body part set to an entity based on its species."""
        parts_template = BodyPartLibrary.get(species)
        if parts_template is None:
            parts_template = BodyPartLibrary.get("humanoid")
        if parts_template is None:
            return
        # Deep-copy the template
        self._body_parts[entity.id] = [
            BodyPart(
                part_type=p.part_type, name=p.name,
                hp_max=p.hp_max, hp_current=p.hp_max,
                hit_weight=p.hit_weight,
                critical_multiplier=p.critical_multiplier,
                cripple_threshold=p.cripple_threshold,
                severable=p.severable,
                effects_when_hit=dict(p.effects_when_hit),
            )
            for p in parts_template
        ]

    def body_parts(self, entity: Entity) -> list[BodyPart]:
        return self._body_parts.get(entity.id, [])

    def get_part(self, entity: Entity, part_type: BodyPartType) -> Optional[BodyPart]:
        for p in self._body_parts.get(entity.id, []):
            if p.part_type == part_type:
                return p
        return None

    def roll_hit_location(self, entity: Entity) -> Optional[BodyPart]:
        """Randomly select a body part to be hit, weighted by hit_weight."""
        parts = self._body_parts.get(entity.id, [])
        if not parts:
            return None
        # Skip severed parts
        available = [p for p in parts if not p.is_severed]
        if not available:
            return None
        weights = [p.hit_weight for p in available]
        return self.rng.weighted_choice(available, weights)

    def hit(self, world: World, target: Entity, damage: int,
            part_type: Optional[BodyPartType] = None,
            is_critical: bool = False) -> Optional[BodyPartHit]:
        """Apply damage to a specific or random body part."""
        if part_type is None:
            part = self.roll_hit_location(target)
        else:
            part = self.get_part(target, part_type)
        if part is None:
            return None
        # Apply critical multiplier
        actual_damage = damage
        if is_critical:
            actual_damage = int(damage * part.critical_multiplier)
        # Reduce by armor on this part
        if part.armor_id is not None:
            # In a real system we'd look up the armor item
            actual_damage = max(1, int(actual_damage * 0.7))
        # Apply damage
        old_status = part.status
        part.damage(actual_damage)
        status_changed = part.status != old_status
        severed = part.status == BodyPartStatus.SEVERED
        # Apply effects
        effects_applied: list[str] = []
        for effect, chance in part.effects_when_hit.items():
            if self.rng.chance(chance):
                effects_applied.append(effect)
        # Reduce overall HP
        target_health = world.get_component(target, Health)
        if target_health:
            target_health.current = max(0, target_health.current - actual_damage)
        # Build message
        msg = f"Hit {part.name} for {actual_damage} damage"
        if is_critical:
            msg += " (CRITICAL!)"
        if severed:
            msg += f" — {part.name} severed!"
        elif status_changed and part.is_crippled:
            msg += f" — {part.name} crippled!"
        return BodyPartHit(
            part=part.part_type, damage=actual_damage,
            is_critical=is_critical, status_changed=status_changed,
            severed=severed, effects_applied=effects_applied,
            message=msg,
        )

    def heal_part(self, entity: Entity, part_type: BodyPartType,
                  amount: int) -> None:
        part = self.get_part(entity, part_type)
        if part and not part.is_severed:
            part.heal(amount)

    def heal_all(self, entity: Entity, amount: int) -> None:
        for part in self._body_parts.get(entity.id, []):
            if not part.is_severed:
                part.heal(amount)

    def is_crippled(self, entity: Entity, part_type: BodyPartType) -> bool:
        part = self.get_part(entity, part_type)
        return part.is_crippled if part else False

    def is_severed(self, entity: Entity, part_type: BodyPartType) -> bool:
        part = self.get_part(entity, part_type)
        return part.is_severed if part else False

    def can_see(self, entity: Entity) -> bool:
        """Entity can see if at least one eye is functional."""
        left = self.get_part(entity, BodyPartType.EYE_LEFT)
        right = self.get_part(entity, BodyPartType.EYE_RIGHT)
        left_ok = left is None or not left.is_severed
        right_ok = right is None or not right.is_severed
        return left_ok or right_ok

    def can_walk(self, entity: Entity) -> bool:
        """Entity can walk if at least one leg is functional."""
        left = self.get_part(entity, BodyPartType.LEG_LEFT)
        right = self.get_part(entity, BodyPartType.LEG_RIGHT)
        if left is None and right is None:
            return True  # legless entities (e.g., snakes) can always move
        left_ok = left is None or not left.is_crippled
        right_ok = right is None or not right.is_crippled
        return left_ok or right_ok

    def can_fly(self, entity: Entity) -> bool:
        """Entity can fly if both wings are functional."""
        left = self.get_part(entity, BodyPartType.WING_LEFT)
        right = self.get_part(entity, BodyPartType.WING_RIGHT)
        if left is None and right is None:
            return False  # no wings
        left_ok = left is None or not left.is_crippled
        right_ok = right is None or not right.is_crippled
        return left_ok and right_ok

    def can_attack(self, entity: Entity) -> bool:
        """Entity can attack if at least one arm/hand is functional."""
        arm_left = self.get_part(entity, BodyPartType.ARM_LEFT)
        arm_right = self.get_part(entity, BodyPartType.ARM_RIGHT)
        hand_left = self.get_part(entity, BodyPartType.HAND_LEFT)
        hand_right = self.get_part(entity, BodyPartType.HAND_RIGHT)
        # Check if at least one arm and matching hand is functional
        for arm, hand in [(arm_left, hand_left), (arm_right, hand_right)]:
            if arm is None:
                continue
            if not arm.is_crippled and (hand is None or not hand.is_crippled):
                return True
        return False

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "body_parts": {
                str(eid): [p.to_dict() for p in parts]
                for eid, parts in self._body_parts.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BodyPartsSystem":
        sys = cls()
        for eid_str, parts_data in data.get("body_parts", {}).items():
            sys._body_parts[int(eid_str)] = [
                BodyPart.from_dict(p) for p in parts_data
            ]
        return sys


# ---------- Default body templates ----------

HUMANOID_BODY: list[BodyPart] = [
    BodyPart(BodyPartType.HEAD, "Head", 40, 40, hit_weight=0.5,
             critical_multiplier=3.0, severable=True,
             effects_when_hit={"knockout": 0.15, "bleed": 0.4}),
    BodyPart(BodyPartType.NECK, "Neck", 30, 30, hit_weight=0.3,
             critical_multiplier=2.5, severable=True,
             effects_when_hit={"bleed": 0.6, "knockout": 0.1}),
    BodyPart(BodyPartType.TORSO, "Torso", 200, 200, hit_weight=3.0,
             critical_multiplier=1.5,
             effects_when_hit={"bleed": 0.3}),
    BodyPart(BodyPartType.ABDOMEN, "Abdomen", 150, 150, hit_weight=2.0,
             critical_multiplier=1.8,
             effects_when_hit={"bleed": 0.4, "infection": 0.1}),
    BodyPart(BodyPartType.ARM_LEFT, "Left Arm", 80, 80, hit_weight=1.5,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"disarm": 0.2, "bleed": 0.3}),
    BodyPart(BodyPartType.ARM_RIGHT, "Right Arm", 80, 80, hit_weight=1.5,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"disarm": 0.3, "bleed": 0.3}),
    BodyPart(BodyPartType.HAND_LEFT, "Left Hand", 30, 30, hit_weight=0.8,
             critical_multiplier=1.3, severable=True,
             effects_when_hit={"disarm": 0.5}),
    BodyPart(BodyPartType.HAND_RIGHT, "Right Hand", 30, 30, hit_weight=0.8,
             critical_multiplier=1.3, severable=True,
             effects_when_hit={"disarm": 0.6}),
    BodyPart(BodyPartType.LEG_LEFT, "Left Leg", 100, 100, hit_weight=1.5,
             critical_multiplier=1.4, severable=True,
             effects_when_hit={"immobilize": 0.15, "bleed": 0.3}),
    BodyPart(BodyPartType.LEG_RIGHT, "Right Leg", 100, 100, hit_weight=1.5,
             critical_multiplier=1.4, severable=True,
             effects_when_hit={"immobilize": 0.15, "bleed": 0.3}),
    BodyPart(BodyPartType.FOOT_LEFT, "Left Foot", 25, 25, hit_weight=0.5,
             critical_multiplier=1.2, severable=True,
             effects_when_hit={"immobilize": 0.1}),
    BodyPart(BodyPartType.FOOT_RIGHT, "Right Foot", 25, 25, hit_weight=0.5,
             critical_multiplier=1.2, severable=True,
             effects_when_hit={"immobilize": 0.1}),
    BodyPart(BodyPartType.EYE_LEFT, "Left Eye", 5, 5, hit_weight=0.1,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.8}),
    BodyPart(BodyPartType.EYE_RIGHT, "Right Eye", 5, 5, hit_weight=0.1,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.8}),
    BodyPart(BodyPartType.EAR_LEFT, "Left Ear", 10, 10, hit_weight=0.15,
             critical_multiplier=2.0, severable=True,
             effects_when_hit={"deafen": 0.7}),
    BodyPart(BodyPartType.EAR_RIGHT, "Right Ear", 10, 10, hit_weight=0.15,
             critical_multiplier=2.0, severable=True,
             effects_when_hit={"deafen": 0.7}),
    BodyPart(BodyPartType.HEART, "Heart", 60, 60, hit_weight=0.05,
             critical_multiplier=10.0,
             effects_when_hit={"bleed": 1.0, "knockout": 0.5}),
    BodyPart(BodyPartType.BRAIN, "Brain", 50, 50, hit_weight=0.05,
             critical_multiplier=15.0,
             effects_when_hit={"knockout": 0.9}),
    BodyPart(BodyPartType.SPINE, "Spine", 80, 80, hit_weight=0.2,
             critical_multiplier=4.0,
             effects_when_hit={"paralyze": 0.4, "immobilize": 0.3}),
]

QUADRUPED_BODY: list[BodyPart] = [
    BodyPart(BodyPartType.HEAD, "Head", 50, 50, hit_weight=0.8,
             critical_multiplier=3.0, severable=True,
             effects_when_hit={"knockout": 0.2, "bleed": 0.4}),
    BodyPart(BodyPartType.NECK, "Neck", 40, 40, hit_weight=0.5,
             critical_multiplier=2.5, severable=True,
             effects_when_hit={"bleed": 0.7}),
    BodyPart(BodyPartType.TORSO, "Torso", 250, 250, hit_weight=3.5,
             critical_multiplier=1.5,
             effects_when_hit={"bleed": 0.3}),
    BodyPart(BodyPartType.ABDOMEN, "Abdomen", 180, 180, hit_weight=2.5,
             critical_multiplier=1.8,
             effects_when_hit={"bleed": 0.4}),
    BodyPart(BodyPartType.LEG_LEFT, "Front Left Leg", 80, 80, hit_weight=1.0,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"immobilize": 0.2}),
    BodyPart(BodyPartType.LEG_RIGHT, "Front Right Leg", 80, 80, hit_weight=1.0,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"immobilize": 0.2}),
    BodyPart(BodyPartType.FOOT_LEFT, "Hind Left Leg", 80, 80, hit_weight=1.0,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"immobilize": 0.2}),
    BodyPart(BodyPartType.FOOT_RIGHT, "Hind Right Leg", 80, 80, hit_weight=1.0,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"immobilize": 0.2}),
    BodyPart(BodyPartType.TAIL, "Tail", 30, 30, hit_weight=0.5,
             critical_multiplier=1.3, severable=True),
    BodyPart(BodyPartType.EYE_LEFT, "Left Eye", 8, 8, hit_weight=0.15,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.8}),
    BodyPart(BodyPartType.EYE_RIGHT, "Right Eye", 8, 8, hit_weight=0.15,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.8}),
]

AVIAN_BODY: list[BodyPart] = [
    BodyPart(BodyPartType.HEAD, "Head", 25, 25, hit_weight=0.7,
             critical_multiplier=3.0, severable=True,
             effects_when_hit={"knockout": 0.3}),
    BodyPart(BodyPartType.NECK, "Neck", 15, 15, hit_weight=0.5,
             critical_multiplier=2.5, severable=True),
    BodyPart(BodyPartType.TORSO, "Torso", 80, 80, hit_weight=3.0,
             critical_multiplier=1.5),
    BodyPart(BodyPartType.WING_LEFT, "Left Wing", 40, 40, hit_weight=1.2,
             critical_multiplier=2.0, severable=True,
             effects_when_hit={"ground": 0.5}),
    BodyPart(BodyPartType.WING_RIGHT, "Right Wing", 40, 40, hit_weight=1.2,
             critical_multiplier=2.0, severable=True,
             effects_when_hit={"ground": 0.5}),
    BodyPart(BodyPartType.LEG_LEFT, "Left Leg", 20, 20, hit_weight=0.6,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"immobilize": 0.3}),
    BodyPart(BodyPartType.LEG_RIGHT, "Right Leg", 20, 20, hit_weight=0.6,
             critical_multiplier=1.5, severable=True,
             effects_when_hit={"immobilize": 0.3}),
    BodyPart(BodyPartType.TAIL, "Tail", 15, 15, hit_weight=0.4,
             critical_multiplier=1.3, severable=True,
             effects_when_hit={"ground": 0.3}),
    BodyPart(BodyPartType.EYE_LEFT, "Left Eye", 4, 4, hit_weight=0.1,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.9}),
    BodyPart(BodyPartType.EYE_RIGHT, "Right Eye", 4, 4, hit_weight=0.1,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.9}),
]

SERPENTINE_BODY: list[BodyPart] = [
    BodyPart(BodyPartType.HEAD, "Head", 35, 35, hit_weight=0.8,
             critical_multiplier=3.0, severable=True,
             effects_when_hit={"knockout": 0.25, "venom": 0.4}),
    BodyPart(BodyPartType.NECK, "Neck", 25, 25, hit_weight=0.6,
             critical_multiplier=2.5, severable=True),
    BodyPart(BodyPartType.TORSO, "Upper Body", 100, 100, hit_weight=2.5,
             critical_multiplier=1.5),
    BodyPart(BodyPartType.ABDOMEN, "Mid Body", 100, 100, hit_weight=2.5,
             critical_multiplier=1.5),
    BodyPart(BodyPartType.TAIL, "Tail", 80, 80, hit_weight=2.0,
             critical_multiplier=1.3, severable=True),
    BodyPart(BodyPartType.EYE_LEFT, "Left Eye", 4, 4, hit_weight=0.15,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.8}),
    BodyPart(BodyPartType.EYE_RIGHT, "Right Eye", 4, 4, hit_weight=0.15,
             critical_multiplier=5.0, severable=True,
             effects_when_hit={"blind": 0.8}),
]
