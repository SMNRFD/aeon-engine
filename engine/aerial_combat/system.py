"""Aerial combat system.

Models combat between flying entities:
* Flying mounts (griffins, wyverns, dragons)
* Airships
* Spellcasters in flight
* Anti-air defenses

Features altitude, maneuvers (dive, climb, banking), and weather effects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Health, Position
from engine.combat.system import CombatSystem, AttackResult
from engine.combat.damage import Damage, DamageType
from engine.utils.rng import RNG


class AerialManeuver(IntEnum):
    LEVEL_FLIGHT = 0
    DIVE = 1        # descending rapidly, gains speed
    CLIMB = 2       # ascending, loses speed
    BANK_LEFT = 3
    BANK_RIGHT = 4
    ROLL = 5        # evasive roll
    LOOP = 6        # vertical loop
    HOVER = 7
    GROUNDED = 8


@dataclass
class FlyingMount:
    """A flying mount."""

    mount_id: int
    species_id: str
    name: str
    rider_id: Optional[int] = None
    hp_max: int = 100
    hp_current: int = 100
    stamina_max: int = 100
    stamina_current: int = 100
    base_speed: float = 20.0       # km/h
    altitude: float = 100.0        # metres
    max_altitude: float = 1000.0
    min_altitude: float = 0.0
    maneuver: AerialManeuver = AerialManeuver.LEVEL_FLIGHT
    wing_damage: float = 0.0       # 0..1, reduces speed and lift
    can_breathe_fire: bool = False
    fire_damage: int = 30
    fire_range: int = 20
    size: str = "large"            # small, medium, large, huge
    tags: list[str] = field(default_factory=list)

    @property
    def current_speed(self) -> float:
        """Speed modified by maneuver and wing damage."""
        speed = self.base_speed
        if self.maneuver == AerialManeuver.DIVE:
            speed *= 2.0
        elif self.maneuver == AerialManeuver.CLIMB:
            speed *= 0.5
        elif self.maneuver == AerialManeuver.HOVER:
            speed = 0.0
        speed *= (1.0 - self.wing_damage * 0.5)
        return speed

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["maneuver"] = int(self.maneuver)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "FlyingMount":
        d = dict(data)
        d["maneuver"] = AerialManeuver(d.get("maneuver", 0))
        return cls(**d)


class AerialCombatSystem:
    """Resolves aerial combat."""

    def __init__(self, rng: Optional[RNG] = None,
                 base_combat: Optional[CombatSystem] = None) -> None:
        self.rng = rng or RNG()
        self.base_combat = base_combat or CombatSystem(rng)
        self._mounts: dict[int, FlyingMount] = {}
        self._rider_to_mount: dict[int, int] = {}

    def create_mount(self, species_id: str, name: str,
                     **kwargs: Any) -> FlyingMount:
        mount = FlyingMount(mount_id=len(self._mounts) + 1,
                             species_id=species_id, name=name, **kwargs)
        self._mounts[mount.mount_id] = mount
        return mount

    def mount_up(self, rider: Entity, mount: FlyingMount) -> bool:
        if mount.rider_id is not None:
            return False
        mount.rider_id = rider.id
        self._rider_to_mount[rider.id] = mount.mount_id
        return True

    def dismount(self, rider: Entity) -> Optional[FlyingMount]:
        mount_id = self._rider_to_mount.pop(rider.id, None)
        if mount_id is None:
            return None
        mount = self._mounts.get(mount_id)
        if mount:
            mount.rider_id = None
        return mount

    def get_mount(self, rider: Entity) -> Optional[FlyingMount]:
        mount_id = self._rider_to_mount.get(rider.id)
        if mount_id is None:
            return None
        return self._mounts.get(mount_id)

    def set_maneuver(self, rider: Entity, maneuver: AerialManeuver) -> bool:
        mount = self.get_mount(rider)
        if mount is None:
            return False
        mount.maneuver = maneuver
        return True

    def change_altitude(self, rider: Entity, delta: float) -> float:
        """Change altitude by delta metres. Returns new altitude."""
        mount = self.get_mount(rider)
        if mount is None:
            return 0.0
        mount.altitude = max(mount.min_altitude,
                              min(mount.max_altitude, mount.altitude + delta))
        # Climbing costs stamina
        if delta > 0:
            mount.stamina_current = max(0, mount.stamina_current - delta * 0.1)
        return mount.altitude

    def aerial_attack(self, world: World, attacker: Entity,
                      target: Entity) -> AttackResult:
        """Resolve an aerial attack."""
        attacker_mount = self.get_mount(attacker)
        target_mount = self.get_mount(target)
        # Compute bonuses
        damage_bonus = 1.0
        if attacker_mount:
            # Diving grants bonus
            if attacker_mount.maneuver == AerialManeuver.DIVE:
                damage_bonus *= 1.5
            # Altitude advantage
            if target_mount:
                if attacker_mount.altitude > target_mount.altitude:
                    damage_bonus *= 1.2
            else:
                # Ground target — air advantage
                damage_bonus *= 1.3
        # Apply bonus
        attacker_stats = None
        from engine.entities.components import Stats
        attacker_stats_comp = world.get_component(attacker, Stats)
        if attacker_stats_comp:
            original_strength = attacker_stats_comp.strength
            attacker_stats_comp.strength = int(original_strength * damage_bonus)
        result = self.base_combat.attack(world, attacker, target)
        # Restore
        if attacker_stats_comp:
            attacker_stats_comp.strength = original_strength
        # Special: dragon breath
        if attacker_mount and attacker_mount.can_breathe_fire:
            if self.rng.chance(0.4):
                target_health = world.get_component(target, Health)
                if target_health:
                    fire_dmg = attacker_mount.fire_damage
                    target_health.current = max(0, target_health.current - fire_dmg)
                    result.damage += fire_dmg
                    result.message += f" Dragon breath deals {fire_dmg} fire damage!"
        return result

    def air_to_ground(self, world: World, attacker: Entity,
                      ground_target: Entity) -> AttackResult:
        """Aerial attack on a ground target."""
        return self.aerial_attack(world, attacker, ground_target)

    def ground_to_air(self, world: World, ground_attacker: Entity,
                      flying_target: Entity) -> AttackResult:
        """Ground attack on a flying target."""
        target_mount = self.get_mount(flying_target)
        # Penalty for shooting upward
        attacker_stats = None
        from engine.entities.components import Stats
        attacker_stats_comp = world.get_component(ground_attacker, Stats)
        if attacker_stats_comp:
            original_agility = attacker_stats_comp.agility
            attacker_stats_comp.agility = int(original_agility * 0.7)  # -30%
        result = self.base_combat.attack(world, ground_attacker, flying_target)
        if attacker_stats_comp:
            attacker_stats_comp.agility = original_agility
        # If hit, damage the mount too
        if result.hit and target_mount:
            target_mount.hp_current = max(0, target_mount.hp_current - int(result.damage * 0.5))
            # Possible wing damage
            if self.rng.chance(0.3):
                target_mount.wing_damage = min(1.0, target_mount.wing_damage + 0.1)
                result.message += " Wing damaged!"
        return result

    def update(self, dt: float) -> None:
        """Update all flying mounts."""
        for mount in self._mounts.values():
            # Stamina regen when not in active maneuvers
            if mount.maneuver in (AerialManeuver.LEVEL_FLIGHT, AerialManeuver.HOVER):
                mount.stamina_current = min(
                    mount.stamina_max,
                    mount.stamina_current + 0.5 * dt,
                )
            # Diving loses altitude
            if mount.maneuver == AerialManeuver.DIVE:
                mount.altitude = max(mount.min_altitude, mount.altitude - 50 * dt)
            # Climbing requires stamina
            if mount.maneuver == AerialManeuver.CLIMB:
                if mount.stamina_current <= 0:
                    mount.maneuver = AerialManeuver.LEVEL_FLIGHT
                else:
                    mount.altitude = min(mount.max_altitude, mount.altitude + 20 * dt)
            # Wing-damaged mounts lose altitude
            if mount.wing_damage > 0.5:
                mount.altitude = max(mount.min_altitude, mount.altitude - 5 * dt)
            # Crashed?
            if mount.altitude <= 0 and mount.maneuver != AerialManeuver.GROUNDED:
                mount.maneuver = AerialManeuver.GROUNDED
                # Force-dismount rider
                if mount.rider_id is not None:
                    rider = Entity(id=mount.rider_id, generation=0)
                    self.dismount(rider)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mounts": {str(mid): m.to_dict() for mid, m in self._mounts.items()},
            "rider_to_mount": {str(r): m for r, m in self._rider_to_mount.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AerialCombatSystem":
        sys = cls()
        sys._mounts = {
            int(mid): FlyingMount.from_dict(m)
            for mid, m in data.get("mounts", {}).items()
        }
        sys._rider_to_mount = {
            int(r): m for r, m in data.get("rider_to_mount", {}).items()
        }
        return sys
