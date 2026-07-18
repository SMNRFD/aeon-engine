"""Naval combat system.

Models ship-to-ship combat with:
* Multiple ship types (cog, caravel, galleon, dreadnought)
* Cannons and artillery
* Hull damage, sinking, boarding actions
* Wind and weather effects
* Crew morale
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class ShipType(IntEnum):
    COG = 0           # small merchant
    CARAVEL = 1       # explorer
    GALLEON = 2       # large merchant/warship
    DREADNOUGHT = 3   # massive warship
    GALLEY = 4        # oar-driven
    TRIREME = 5       # ancient warship
    LONGSHIP = 6      # viking
    JUNK = 7          # asian
    SUBMARINE = 8     # modern


# Hull point and cannon capacity by ship type
SHIP_STATS: dict[ShipType, dict[str, Any]] = {
    ShipType.COG: {"hp": 200, "cannons": 4, "crew": 15, "speed": 6, "cargo": 100},
    ShipType.CARAVEL: {"hp": 350, "cannons": 8, "crew": 25, "speed": 8, "cargo": 200},
    ShipType.GALLEON: {"hp": 600, "cannons": 20, "crew": 60, "speed": 7, "cargo": 500},
    ShipType.DREADNOUGHT: {"hp": 1200, "cannons": 50, "crew": 200, "speed": 6, "cargo": 800},
    ShipType.GALLEY: {"hp": 250, "cannons": 6, "crew": 100, "speed": 5, "cargo": 80},
    ShipType.TRIREME: {"hp": 180, "cannons": 0, "crew": 170, "speed": 7, "cargo": 50},
    ShipType.LONGSHIP: {"hp": 220, "cannons": 0, "crew": 60, "speed": 9, "cargo": 60},
    ShipType.JUNK: {"hp": 400, "cannons": 12, "crew": 40, "speed": 6, "cargo": 300},
    ShipType.SUBMARINE: {"hp": 300, "cannons": 8, "crew": 30, "speed": 7, "cargo": 50},
}


@dataclass
class Warship:
    """A warship entity."""

    ship_id: int
    name: str
    ship_type: ShipType
    owner_id: Optional[int] = None
    faction_id: Optional[int] = None
    hp_max: int = 200
    hp_current: int = 200
    sail_hp: int = 100  # separate from hull
    cannon_count: int = 4
    cannon_damage_min: int = 10
    cannon_damage_max: int = 25
    cannon_range: int = 10
    crew_count: int = 15
    crew_morale: float = 75.0  # 0..100
    crew_fatigue: float = 0.0  # 0..100
    speed: float = 6.0
    position: tuple[float, float] = (0.0, 0.0)
    heading: float = 0.0   # degrees
    is_sinking: bool = False
    is_boarded: bool = False
    is_sunk: bool = False
    cargo: list[int] = field(default_factory=list)
    treasure: int = 0
    wind_bonus: float = 1.0
    is_submerged: bool = False  # for submarines
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        stats = SHIP_STATS.get(self.ship_type, {})
        if self.hp_max == 200 and stats:
            self.hp_max = stats.get("hp", 200)
            self.hp_current = self.hp_max
            self.cannon_count = stats.get("cannons", 4)
            self.crew_count = stats.get("crew", 15)
            self.speed = stats.get("speed", 6)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["ship_type"] = int(self.ship_type)
        d["position"] = list(self.position)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Warship":
        d = dict(data)
        d["ship_type"] = ShipType(d.get("ship_type", 0))
        d["position"] = tuple(d.get("position", [0.0, 0.0]))
        return cls(**d)


@dataclass
class NavalCombatResult:
    """Result of a naval engagement."""

    attacker_id: int
    target_id: int
    hit: bool
    damage: int
    part_hit: str = ""  # "hull", "sail", "crew"
    sunk: bool = False
    boarded: bool = False
    message: str = ""


class NavalCombatSystem:
    """Resolves naval combat between ships."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._ships: dict[int, Warship] = {}
        self._next_id: int = 1

    def create_ship(self, name: str, ship_type: ShipType,
                    **kwargs: Any) -> Warship:
        ship = Warship(ship_id=self._next_id, name=name,
                        ship_type=ship_type, **kwargs)
        self._next_id += 1
        self._ships[ship.ship_id] = ship
        return ship

    def get_ship(self, ship_id: int) -> Optional[Warship]:
        return self._ships.get(ship_id)

    def all_ships(self) -> list[Warship]:
        return list(self._ships.values())

    def bombard(self, attacker: Warship, target: Warship,
                cannons_used: Optional[int] = None) -> NavalCombatResult:
        """Fire cannons at a target ship."""
        if attacker.is_sinking or target.is_sunk:
            return NavalCombatResult(
                attacker_id=attacker.ship_id, target_id=target.ship_id,
                hit=False, damage=0, message="Cannot fire — ship incapacitated.",
            )
        # Calculate range
        dist = math.hypot(target.position[0] - attacker.position[0],
                          target.position[1] - attacker.position[1])
        if dist > attacker.cannon_range:
            return NavalCombatResult(
                attacker_id=attacker.ship_id, target_id=target.ship_id,
                hit=False, damage=0,
                message=f"Target out of range ({dist:.0f} > {attacker.cannon_range}).",
            )
        n_cannons = cannons_used or attacker.cannon_count
        # Each cannon has its own hit chance
        hits = 0
        total_damage = 0
        parts_hit: list[str] = []
        for _ in range(n_cannons):
            if self.rng.chance(0.6):  # 60% hit chance per cannon
                hits += 1
                # Random damage
                dmg = self.rng.randint(attacker.cannon_damage_min,
                                        attacker.cannon_damage_max)
                # Determine what was hit
                part = self.rng.weighted_choice(
                    ["hull", "sail", "crew"], [0.6, 0.25, 0.15],
                )
                parts_hit.append(part)
                if part == "hull":
                    target.hp_current = max(0, target.hp_current - dmg)
                elif part == "sail":
                    target.sail_hp = max(0, target.sail_hp - dmg)
                    # Slower with damaged sails
                    target.speed = target.speed * 0.95
                elif part == "crew":
                    casualties = max(1, dmg // 5)
                    target.crew_count = max(0, target.crew_count - casualties)
                    target.crew_morale = max(0, target.crew_morale - 5)
                total_damage += dmg
        # Check if sunk
        sunk = False
        if target.hp_current <= 0:
            target.is_sinking = True
            sunk = True
        # Check if crew surrendered
        if target.crew_morale < 20 and not sunk:
            sunk = True  # effectively out of combat
        msg = (f"{attacker.name} fires {n_cannons} cannons at {target.name}: "
               f"{hits} hits, {total_damage} damage.")
        if sunk:
            target.is_sunk = True
            msg += f" {target.name} is sinking!"
        return NavalCombatResult(
            attacker_id=attacker.ship_id, target_id=target.ship_id,
            hit=hits > 0, damage=total_damage,
            part_hit=", ".join(set(parts_hit)),
            sunk=sunk, message=msg,
        )

    def board(self, attacker: Warship, target: Warship) -> NavalCombatResult:
        """Board an enemy ship."""
        if attacker.crew_count <= 0:
            return NavalCombatResult(
                attacker_id=attacker.ship_id, target_id=target.ship_id,
                hit=False, damage=0, message="No crew to board.",
            )
        if target.is_sunk:
            return NavalCombatResult(
                attacker_id=attacker.ship_id, target_id=target.ship_id,
                hit=False, damage=0, message="Cannot board sinking ship.",
            )
        # Boarding action: both crews fight
        attacker_strength = attacker.crew_count * (1 + attacker.crew_morale / 100)
        target_strength = target.crew_count * (1 + target.crew_morale / 100)
        # Random modifiers
        attacker_strength *= self.rng.uniform(0.8, 1.2)
        target_strength *= self.rng.uniform(0.8, 1.2)
        attacker_wins = attacker_strength > target_strength
        # Casualties
        attacker_casualties = int(attacker.crew_count * 0.2 * (target_strength / max(1, attacker_strength)))
        target_casualties = int(target.crew_count * 0.3 * (attacker_strength / max(1, target_strength)))
        attacker.crew_count = max(0, attacker.crew_count - attacker_casualties)
        target.crew_count = max(0, target.crew_count - target_casualties)
        if attacker_wins:
            target.is_boarded = True
            # Attacker captures ship
            msg = (f"{attacker.name} boards {target.name} — successful! "
                   f"Lost {attacker_casualties} crew, enemy lost {target_casualties}.")
            return NavalCombatResult(
                attacker_id=attacker.ship_id, target_id=target.ship_id,
                hit=True, damage=target_casualties,
                boarded=True, message=msg,
            )
        else:
            msg = (f"{attacker.name} boards {target.name} — repelled! "
                   f"Lost {attacker_casualties} crew.")
            return NavalCombatResult(
                attacker_id=attacker.ship_id, target_id=target.ship_id,
                hit=False, damage=attacker_casualties,
                message=msg,
            )

    def update(self, dt: float) -> None:
        """Update all ships: sinking, morale, fatigue."""
        for ship in self._ships.values():
            if ship.is_sinking:
                ship.hp_current = max(0, ship.hp_current - int(20 * dt))
                if ship.hp_current <= 0:
                    ship.is_sunk = True
            # Crew fatigue regenerates slowly when not in combat
            ship.crew_fatigue = max(0, ship.crew_fatigue - 0.5 * dt)
            # Morale regenerates slowly
            if ship.crew_morale < 75:
                ship.crew_morale = min(75, ship.crew_morale + 0.1 * dt)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ships": {str(sid): s.to_dict() for sid, s in self._ships.items()},
            "next_id": self._next_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NavalCombatSystem":
        sys = cls()
        sys._ships = {
            int(sid): Warship.from_dict(s) for sid, s in data.get("ships", {}).items()
        }
        sys._next_id = data.get("next_id", 1)
        return sys
