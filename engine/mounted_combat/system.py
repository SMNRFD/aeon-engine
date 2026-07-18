"""Mounted combat system.

Mounted combat grants:
* Height advantage (vs. infantry)
* Speed bonus to attacks
* Charge bonus (moving + attacking)
* Risk of being unseated

Mounts have their own HP, stats, and can be targeted separately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Health, Stats, Position
from engine.combat.system import CombatSystem, AttackResult
from engine.utils.rng import RNG


@dataclass
class Mount:
    """A mount entity."""

    mount_id: int
    species_id: str
    name: str
    rider_id: Optional[int] = None
    hp_max: int = 100
    hp_current: int = 100
    stamina_max: int = 100
    stamina_current: int = 100
    speed: float = 1.5       # movement multiplier
    charge_bonus: float = 1.5  # damage multiplier when charging
    height_advantage: float = 1.2  # attack bonus vs. infantry
    dismount_difficulty: int = 10  # difficulty to unseat the rider
    is_trained_for_combat: bool = True
    is_flying: bool = False
    armor: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "Mount":
        return cls(**data)


class MountedCombatSystem:
    """Resolves mounted combat actions."""

    def __init__(self, rng: Optional[RNG] = None,
                 base_combat: Optional[CombatSystem] = None) -> None:
        self.rng = rng or RNG()
        self.base_combat = base_combat or CombatSystem(rng)
        self._mounts: dict[int, Mount] = {}
        self._rider_to_mount: dict[int, int] = {}

    # ---------- mount management ----------

    def create_mount(self, species_id: str, name: str, **kwargs: Any) -> Mount:
        mount = Mount(mount_id=len(self._mounts) + 1,
                       species_id=species_id, name=name, **kwargs)
        self._mounts[mount.mount_id] = mount
        return mount

    def mount_up(self, rider: Entity, mount: Mount) -> bool:
        """A rider mounts a mount."""
        if mount.rider_id is not None:
            return False
        mount.rider_id = rider.id
        self._rider_to_mount[rider.id] = mount.mount_id
        return True

    def dismount(self, rider: Entity) -> Optional[Mount]:
        """A rider dismounts."""
        mount_id = self._rider_to_mount.pop(rider.id, None)
        if mount_id is None:
            return None
        mount = self._mounts.get(mount_id)
        if mount:
            mount.rider_id = None
        return mount

    def get_mount(self, rider: Entity) -> Optional[Mount]:
        mount_id = self._rider_to_mount.get(rider.id)
        if mount_id is None:
            return None
        return self._mounts.get(mount_id)

    def is_mounted(self, rider: Entity) -> bool:
        return rider.id in self._rider_to_mount

    # ---------- combat ----------

    def mounted_attack(self, world: World, attacker: Entity, target: Entity,
                       is_charging: bool = False) -> AttackResult:
        """Resolve a mounted attack."""
        mount = self.get_mount(attacker)
        if mount is None:
            return self.base_combat.attack(world, attacker, target)
        # Compute damage bonus
        damage_bonus = 1.0
        # Height advantage vs. unmounted target
        target_mount = self.get_mount(target)
        if target_mount is None:
            damage_bonus *= mount.height_advantage
        # Charge bonus
        if is_charging and mount.stamina_current > 20:
            damage_bonus *= mount.charge_bonus
            mount.stamina_current = max(0, mount.stamina_current - 20)
        # Apply bonus via temporary stats boost
        attacker_stats = world.get_component(attacker, Stats)
        original_strength = attacker_stats.strength if attacker_stats else 10
        if attacker_stats:
            # Boost strength temporarily
            boosted = int(attacker_stats.strength * damage_bonus)
            attacker_stats.strength = boosted
        result = self.base_combat.attack(world, attacker, target)
        # Restore original stats
        if attacker_stats:
            attacker_stats.strength = original_strength
        # Update message
        if is_charging:
            result.message = f"Charging attack! {result.message}"
        return result

    def unseat_attempt(self, attacker: Entity, target: Entity) -> tuple[bool, str]:
        """Attempt to knock a rider off their mount."""
        target_mount = self.get_mount(target)
        if target_mount is None:
            return False, "Target is not mounted."
        attacker_stats = None  # would look up
        difficulty = target_mount.dismount_difficulty
        roll = self.rng.randint(1, 100)
        if roll > difficulty:
            self.dismount(target)
            return True, f"Unseated rider {target.id}!"
        return False, f"Failed to unseat {target.id}."

    def damage_mount(self, mount: Mount, damage: int) -> bool:
        """Damage a mount. Returns True if mount died."""
        mount.hp_current = max(0, mount.hp_current - damage)
        if mount.hp_current <= 0:
            # Force-dismount the rider
            if mount.rider_id is not None:
                rider = Entity(id=mount.rider_id, generation=0)
                self.dismount(rider)
            return True
        return False

    def update(self, world: World, dt: float) -> None:
        """Regenerate mount stamina."""
        for mount in self._mounts.values():
            mount.stamina_current = min(
                mount.stamina_max,
                mount.stamina_current + 0.5 * dt,
            )

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "mounts": {str(mid): m.to_dict() for mid, m in self._mounts.items()},
            "rider_to_mount": {str(r): m for r, m in self._rider_to_mount.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MountedCombatSystem":
        sys = cls()
        sys._mounts = {
            int(mid): Mount.from_dict(m) for mid, m in data.get("mounts", {}).items()
        }
        sys._rider_to_mount = {
            int(r): m for r, m in data.get("rider_to_mount", {}).items()
        }
        return sys
