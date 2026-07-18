"""Stealth system — sneaking, detection, hiding, backstabbing.

Tracks per-entity stealth state and resolves detection checks based on:
* Lighting (ambient + torches)
* Distance
* Movement speed (still vs walking vs running)
* Terrain (open, foliage, shadow)
* Camouflage / armour stealth penalties
* Skills (stealth, perception)
* Status effects (invisible, hasted, etc.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Stats, Position
from engine.utils.rng import RNG


class StealthState(IntEnum):
    VISIBLE = 0
    HIDDEN = 1
    DETECTED = 2
    SPOTTED = 3  # was hidden, now detected this tick
    INVISIBLE = 4


class DetectionResult(IntEnum):
    UNDETECTED = 0
    PARTIAL = 1   # heard but not seen
    DETECTED = 2  # fully spotted
    CRITICAL = 3  # detected with extra awareness


@dataclass
class StealthComponent:
    """Per-entity stealth state. Stored in the world as needed."""

    state: StealthState = StealthState.VISIBLE
    stealth_skill: int = 0
    noise_level: float = 1.0      # multiplier on noise emitted
    visibility: float = 1.0       # multiplier on visibility
    last_known_position: Optional[tuple[int, int]] = None
    detection_meter: dict[int, float] = field(default_factory=dict)  # watcher_id -> 0..100
    in_shadows: bool = False
    camouflaged: bool = False
    invisible: bool = False


class StealthSystem:
    """Resolves stealth and detection."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._state: dict[int, StealthComponent] = {}

    def get_state(self, entity: Entity) -> StealthComponent:
        if entity.id not in self._state:
            self._state[entity.id] = StealthComponent()
        return self._state[entity.id]

    def set_stealth_skill(self, entity: Entity, level: int) -> None:
        self.get_state(entity).stealth_skill = level

    def enter_stealth(self, entity: Entity) -> bool:
        """Try to enter stealth mode."""
        state = self.get_state(entity)
        if state.invisible:
            state.state = StealthState.INVISIBLE
            return True
        # Roll skill check
        skill = state.stealth_skill
        if skill < 1:
            return False
        state.state = StealthState.HIDDEN
        return True

    def exit_stealth(self, entity: Entity) -> None:
        state = self.get_state(entity)
        state.state = StealthState.VISIBLE

    def set_invisible(self, entity: Entity, duration: float) -> None:
        state = self.get_state(entity)
        state.invisible = True
        state.state = StealthState.INVISIBLE
        # In a real system we'd track duration and revert.

    # ---------- detection ----------

    def detect(self, watcher: Entity, target: Entity,
               ambient_light: float = 0.5,
               distance: Optional[float] = None) -> DetectionResult:
        """Check if watcher detects target."""
        target_state = self.get_state(target)
        if target_state.state == StealthState.VISIBLE:
            return DetectionResult.DETECTED
        if target_state.invisible:
            return DetectionResult.UNDETECTED
        # Compute distance if not provided
        if distance is None:
            w_pos = self._get_position(watcher)
            t_pos = self._get_position(target)
            if w_pos is None or t_pos is None:
                return DetectionResult.DETECTED
            distance = math.hypot(t_pos.x - w_pos.x, t_pos.y - w_pos.y)
        # Detection factors
        watcher_stats = self._get_stats(watcher)
        target_stats = self._get_stats(target)
        perception = watcher_stats.perception if watcher_stats else 10
        stealth_skill = target_state.stealth_skill
        agility = target_stats.agility if target_stats else 10
        # Visibility score (higher = easier to see)
        visibility = target_state.visibility
        if target_state.in_shadows:
            visibility *= 0.5
        if target_state.camouflaged:
            visibility *= 0.7
        # Distance penalty
        distance_mod = max(0.1, 1.0 - distance / 20.0)
        # Lighting
        light_mod = ambient_light
        # Compute detection chance
        detection_chance = (
            50
            + perception * 1.5
            - stealth_skill * 2
            - agility * 0.5
            + visibility * 30
            + light_mod * 30
            + distance_mod * 40
            - (10 if target_state.in_shadows else 0)
        )
        detection_chance = max(5, min(95, detection_chance))
        # Watcher's detection meter rises
        meter = target_state.detection_meter.get(watcher.id, 0.0)
        meter += detection_chance * 0.05
        meter = min(100.0, meter)
        target_state.detection_meter[watcher.id] = meter
        # Result
        if meter >= 100:
            target_state.state = StealthState.SPOTTED
            return DetectionResult.CRITICAL
        if meter >= 70:
            return DetectionResult.DETECTED
        if meter >= 40:
            return DetectionResult.PARTIAL
        return DetectionResult.UNDETECTED

    def make_noise(self, entity: Entity, noise_amount: float,
                   radius: int = 10) -> None:
        """Entity makes noise; nearby watchers' detection meters rise."""
        state = self.get_state(entity)
        state.noise_level = max(0.1, state.noise_level + noise_amount)
        # Decay over time would happen in update()

    def backstab_bonus(self, attacker: Entity, target: Entity) -> float:
        """Returns damage multiplier for a backstab (1.0 = no bonus)."""
        attacker_state = self.get_state(attacker)
        target_state = self.get_state(target)
        if target_state.state not in (StealthState.HIDDEN, StealthState.INVISIBLE):
            return 1.0
        if attacker_state.state != StealthState.HIDDEN:
            return 1.0
        # Hidden attacker striking a target that hasn't detected them
        return 2.0 + attacker_state.stealth_skill * 0.05

    def update(self, world: World, dt: float) -> None:
        """Decay detection meters over time."""
        for entity_id, state in self._state.items():
            for watcher_id in list(state.detection_meter.keys()):
                state.detection_meter[watcher_id] = max(0.0,
                    state.detection_meter[watcher_id] - 5.0 * dt)
                if state.detection_meter[watcher_id] <= 0:
                    del state.detection_meter[watcher_id]
            # Decay noise level
            state.noise_level = max(1.0, state.noise_level - 0.5 * dt)
            # If spotted, return to visible after a delay
            if state.state == StealthState.SPOTTED:
                if not state.detection_meter:
                    state.state = StealthState.VISIBLE

    # ---------- helpers ----------

    def _get_position(self, entity: Entity) -> Optional[Position]:
        # We need a world reference; in practice this is passed in.
        # For simplicity, return None here and let callers pass distance.
        return None

    def _get_stats(self, entity: Entity) -> Optional[Stats]:
        return None

    # ---------- serialization ----------

    def to_dict(self) -> dict:
        return {
            "states": {
                str(eid): {
                    "state": int(s.state),
                    "stealth_skill": s.stealth_skill,
                    "noise_level": s.noise_level,
                    "visibility": s.visibility,
                    "last_known_position": s.last_known_position,
                    "detection_meter": {str(k): v for k, v in s.detection_meter.items()},
                    "in_shadows": s.in_shadows,
                    "camouflaged": s.camouflaged,
                    "invisible": s.invisible,
                }
                for eid, s in self._state.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StealthSystem":
        sys = cls()
        for eid_str, sdata in data.get("states", {}).items():
            eid = int(eid_str)
            comp = StealthComponent(
                state=StealthState(sdata.get("state", 0)),
                stealth_skill=sdata.get("stealth_skill", 0),
                noise_level=sdata.get("noise_level", 1.0),
                visibility=sdata.get("visibility", 1.0),
                last_known_position=tuple(sdata["last_known_position"])
                    if sdata.get("last_known_position") else None,
                detection_meter={int(k): v for k, v in sdata.get("detection_meter", {}).items()},
                in_shadows=sdata.get("in_shadows", False),
                camouflaged=sdata.get("camouflaged", False),
                invisible=sdata.get("invisible", False),
            )
            sys._state[eid] = comp
        return sys
