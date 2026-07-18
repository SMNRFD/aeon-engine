"""Space combat system.

Models combat between spacecraft:
* Energy weapons (lasers, plasma, particle beams)
* Kinetic weapons (railguns, missiles, torpedoes)
* Defenses (shields, point defense, armor)
* Fighters and carriers
* FTL tactics (warp strafing, micro-jumps)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class SpaceWeaponType(IntEnum):
    LASER = 0           # short-range energy
    PLASMA = 1          # medium-range energy
    PARTICLE_BEAM = 2   # long-range energy
    RAILGUN = 3         # kinetic, long-range
    MISSILE = 4         # guided, very long range
    TORPEDO = 5         # heavy, slow
    POINT_DEFENSE = 6   # anti-missile/fighter


SPACE_WEAPON_STATS: dict[SpaceWeaponType, dict[str, Any]] = {
    SpaceWeaponType.LASER: {
        "damage": 20, "range": 50, "fire_rate": 2.0,
        "shield_mult": 1.5, "armor_mult": 0.5,
        "energy_cost": 5, "can_target_fighters": True,
    },
    SpaceWeaponType.PLASMA: {
        "damage": 50, "range": 100, "fire_rate": 0.5,
        "shield_mult": 1.0, "armor_mult": 1.5,
        "energy_cost": 20, "can_target_fighters": False,
    },
    SpaceWeaponType.PARTICLE_BEAM: {
        "damage": 80, "range": 200, "fire_rate": 0.3,
        "shield_mult": 2.0, "armor_mult": 0.8,
        "energy_cost": 40, "can_target_fighters": False,
    },
    SpaceWeaponType.RAILGUN: {
        "damage": 100, "range": 150, "fire_rate": 0.4,
        "shield_mult": 0.5, "armor_mult": 2.0,
        "energy_cost": 10, "ammo_per_shot": 1, "can_target_fighters": False,
    },
    SpaceWeaponType.MISSILE: {
        "damage": 150, "range": 300, "fire_rate": 0.2,
        "shield_mult": 1.0, "armor_mult": 1.0,
        "energy_cost": 5, "ammo_per_shot": 1, "can_target_fighters": False,
    },
    SpaceWeaponType.TORPEDO: {
        "damage": 300, "range": 200, "fire_rate": 0.1,
        "shield_mult": 0.8, "armor_mult": 2.5,
        "energy_cost": 10, "ammo_per_shot": 1, "can_target_fighters": False,
    },
    SpaceWeaponType.POINT_DEFENSE: {
        "damage": 5, "range": 20, "fire_rate": 5.0,
        "shield_mult": 1.0, "armor_mult": 1.0,
        "energy_cost": 1, "can_target_fighters": True,
    },
}


@dataclass
class SpaceWeapon:
    """A weapon mounted on a spacecraft."""

    weapon_id: int
    weapon_type: SpaceWeaponType
    name: str
    ammo: int = 999  # energy weapons have effectively infinite ammo
    ammo_max: int = 999
    is_operational: bool = True
    target_id: Optional[int] = None

    @property
    def damage(self) -> int:
        return SPACE_WEAPON_STATS.get(self.weapon_type, {}).get("damage", 0)

    @property
    def range(self) -> int:
        return SPACE_WEAPON_STATS.get(self.weapon_type, {}).get("range", 0)

    @property
    def fire_rate(self) -> float:
        return SPACE_WEAPON_STATS.get(self.weapon_type, {}).get("fire_rate", 0)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["weapon_type"] = int(self.weapon_type)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SpaceWeapon":
        d = dict(data)
        d["weapon_type"] = SpaceWeaponType(d.get("weapon_type", 0))
        return cls(**d)


@dataclass
class Spacecraft:
    """A starship."""

    ship_id: int
    name: str
    ship_class: str = "frigate"  # fighter, corvette, frigate, destroyer, cruiser, battleship, carrier, dreadnought
    owner_id: Optional[int] = None
    faction_id: Optional[int] = None
    hull_hp_max: int = 500
    hull_hp_current: int = 500
    shield_hp_max: int = 500
    shield_hp_current: int = 500
    shield_regen_rate: float = 10.0  # per second
    armor: int = 50  # flat damage reduction
    energy_max: int = 1000
    energy_current: int = 1000
    energy_regen_rate: float = 50.0
    speed: float = 100.0  # km/s
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)  # 3D position
    heading: tuple[float, float, float] = (1.0, 0.0, 0.0)
    weapons: list[int] = field(default_factory=list)  # weapon_ids
    fighter_count: int = 0  # for carriers
    is_destroyed: bool = False
    is_disabled: bool = False  # engines offline
    crew_count: int = 50
    crew_morale: float = 75.0
    cargo: dict[str, int] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["position"] = list(self.position)
        d["heading"] = list(self.heading)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Spacecraft":
        d = dict(data)
        d["position"] = tuple(d.get("position", [0, 0, 0]))
        d["heading"] = tuple(d.get("heading", [1, 0, 0]))
        return cls(**d)


class SpaceCombatSystem:
    """Manages space combat."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._ships: dict[int, Spacecraft] = {}
        self._weapons: dict[int, SpaceWeapon] = {}
        self._next_ship_id: int = 1
        self._next_weapon_id: int = 1

    def create_ship(self, name: str, ship_class: str = "frigate",
                    **kwargs: Any) -> Spacecraft:
        ship = Spacecraft(
            ship_id=self._next_ship_id,
            name=name, ship_class=ship_class,
            **kwargs,
        )
        self._next_ship_id += 1
        self._ships[ship.ship_id] = ship
        return ship

    def add_weapon(self, ship: Spacecraft, weapon_type: SpaceWeaponType,
                   name: str = "") -> SpaceWeapon:
        weapon = SpaceWeapon(
            weapon_id=self._next_weapon_id,
            weapon_type=weapon_type,
            name=name or f"{weapon_type.name.title()} #{self._next_weapon_id}",
        )
        self._next_weapon_id += 1
        self._weapons[weapon.weapon_id] = weapon
        ship.weapons.append(weapon.weapon_id)
        return weapon

    def fire_weapon(self, attacker: Spacecraft, target: Spacecraft,
                    weapon: SpaceWeapon) -> dict[str, Any]:
        """Fire a weapon at a target."""
        if not weapon.is_operational:
            return {"hit": False, "reason": "Weapon offline"}
        if attacker.is_destroyed or target.is_destroyed:
            return {"hit": False, "reason": "Ship destroyed"}
        # Check range
        dist = math.sqrt(sum(
            (a - b) ** 2 for a, b in zip(attacker.position, target.position)
        ))
        if dist > weapon.range:
            return {"hit": False, "reason": f"Out of range ({dist:.0f} > {weapon.range})"}
        # Check energy
        stats = SPACE_WEAPON_STATS.get(weapon.weapon_type, {})
        energy_cost = stats.get("energy_cost", 5)
        if attacker.energy_current < energy_cost:
            return {"hit": False, "reason": "Insufficient energy"}
        # Check ammo
        if weapon.ammo <= 0:
            return {"hit": False, "reason": "Out of ammo"}
        attacker.energy_current -= energy_cost
        weapon.ammo -= 1
        # Hit chance
        hit_chance = 0.7 - (dist / weapon.range) * 0.3  # further = harder
        if not self.rng.chance(hit_chance):
            return {"hit": False, "reason": "Miss"}
        # Apply damage
        base_damage = weapon.damage
        shield_mult = stats.get("shield_mult", 1.0)
        armor_mult = stats.get("armor_mult", 1.0)
        # Damage shields first
        shield_damage = int(base_damage * shield_mult)
        hull_damage = 0
        if target.shield_hp_current > 0:
            if shield_damage >= target.shield_hp_current:
                # Shields down — leftover goes to hull
                leftover = shield_damage - target.shield_hp_current
                target.shield_hp_current = 0
                hull_damage = int(leftover * armor_mult - target.armor)
            else:
                target.shield_hp_current -= shield_damage
        else:
            hull_damage = int(base_damage * armor_mult - target.armor)
        hull_damage = max(1, hull_damage)
        target.hull_hp_current = max(0, target.hull_hp_current - hull_damage)
        # Check destruction
        destroyed = target.hull_hp_current <= 0
        if destroyed:
            target.is_destroyed = True
        return {
            "hit": True,
            "shield_damage": shield_damage,
            "hull_damage": hull_damage,
            "destroyed": destroyed,
            "weapon": weapon.name,
            "target": target.name,
        }

    def launch_fighters(self, carrier: Spacecraft, target: Spacecraft) -> dict[str, Any]:
        """Launch fighters from a carrier against a target."""
        if carrier.fighter_count <= 0:
            return {"launched": 0, "reason": "No fighters"}
        launched = min(carrier.fighter_count, 10)
        carrier.fighter_count -= launched
        # Each fighter does small damage
        total_damage = 0
        for _ in range(launched):
            if self.rng.chance(0.6):  # 60% hit
                dmg = self.rng.randint(5, 15)
                if target.shield_hp_current > 0:
                    target.shield_hp_current = max(0, target.shield_hp_current - dmg)
                else:
                    target.hull_hp_current = max(0, target.hull_hp_current - dmg)
                total_damage += dmg
        return {
            "launched": launched,
            "total_damage": total_damage,
            "target_destroyed": target.hull_hp_current <= 0,
        }

    def update(self, dt: float) -> None:
        """Regenerate shields and energy."""
        for ship in self._ships.values():
            if ship.is_destroyed:
                continue
            ship.shield_hp_current = min(
                ship.shield_hp_max,
                ship.shield_hp_current + ship.shield_regen_rate * dt,
            )
            ship.energy_current = min(
                ship.energy_max,
                ship.energy_current + ship.energy_regen_rate * dt,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ships": {str(sid): s.to_dict() for sid, s in self._ships.items()},
            "weapons": {str(wid): w.to_dict() for wid, w in self._weapons.items()},
            "next_ship_id": self._next_ship_id,
            "next_weapon_id": self._next_weapon_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SpaceCombatSystem":
        sys = cls()
        sys._ships = {
            int(sid): Spacecraft.from_dict(s)
            for sid, s in data.get("ships", {}).items()
        }
        sys._weapons = {
            int(wid): SpaceWeapon.from_dict(w)
            for wid, w in data.get("weapons", {}).items()
        }
        sys._next_ship_id = data.get("next_ship_id", 1)
        sys._next_weapon_id = data.get("next_weapon_id", 1)
        return sys
