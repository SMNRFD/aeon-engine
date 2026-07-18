"""Combat variants — mounted, naval, aerial, siege, space."""

from engine.mounted_combat.system import MountedCombatSystem, Mount
from engine.naval_combat.system import (
    NavalCombatSystem, Warship, ShipType, NavalCombatResult,
)
from engine.aerial_combat.system import (
    AerialCombatSystem, FlyingMount, AerialManeuver,
)
from engine.siege_combat.system import (
    SiegeCombatSystem, SiegeEngine, SiegeEngineType, SiegeState,
)
from engine.space_combat.system import (
    SpaceCombatSystem, Spacecraft, SpaceWeapon, SpaceWeaponType,
)
