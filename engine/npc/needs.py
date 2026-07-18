"""Needs system — hunger, thirst, fatigue, sleep, sanity, morale."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import TYPE_CHECKING

from engine.core.ecs import World
from engine.entities.components import Needs as NeedsComponent

if TYPE_CHECKING:
    from engine.core.clock import GameClock


class NeedType(IntEnum):
    HUNGER = 0
    THIRST = 1
    FATIGUE = 2
    SLEEP = 3
    SANITY = 4
    MORALE = 5
    COMFORT = 6


class NeedSeverity(IntEnum):
    SATISFIED = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return ["Satisfied", "Mild", "Moderate", "Severe", "Critical"][self]


# Rate of change per game-minute (in-game time).
DEFAULT_RATES: dict[NeedType, float] = {
    NeedType.HUNGER: 0.08,    # +0.08 per minute -> 100 in ~21 hours
    NeedType.THIRST: 0.12,    # +0.12 per minute -> 100 in ~14 hours
    NeedType.FATIGUE: 0.04,
    NeedType.SLEEP: 0.06,
    NeedType.SANITY: 0.0,     # only changes from events
    NeedType.MORALE: 0.0,
    NeedType.COMFORT: 0.0,
}


# Effects on stats when needs are critical.
CRITICAL_PENALTIES: dict[NeedType, dict[str, float]] = {
    NeedType.HUNGER: {"strength": -0.5, "endurance": -0.5, "max_hp": -0.2},
    NeedType.THIRST: {"agility": -0.5, "endurance": -0.5, "max_hp": -0.3},
    NeedType.FATIGUE: {"agility": -0.3, "perception": -0.5, "max_stamina": -0.4},
    NeedType.SLEEP: {"intelligence": -0.4, "willpower": -0.4, "max_mana": -0.5},
    NeedType.SANITY: {"willpower": -0.6, "charisma": -0.5},
    NeedType.MORALE: {"charisma": -0.3, "willpower": -0.3},
}


@dataclass
class NeedUpdate:
    need: NeedType
    delta: float
    reason: str = ""


class NeedsSystem:
    """Updates entity needs over time."""

    def __init__(self, rates: dict[NeedType, float] | None = None) -> None:
        self.rates = rates or dict(DEFAULT_RATES)
        # Track partial accumulation per entity.
        self._accumulators: dict[int, dict[NeedType, float]] = {}

    def update(self, world: World, dt_seconds: float, ticks_per_game_minute: int = 10) -> None:
        """Advance needs for all entities with a Needs component."""
        # Convert dt to in-game minutes.
        # Each tick = 1/ticks_per_game_minute of a game minute.
        dt_minutes = (dt_seconds * 20.0) / ticks_per_game_minute  # 20 tps assumed
        for entity, (needs,) in world.view(NeedsComponent):
            self._tick_entity(entity.id, needs, dt_minutes)

    def _tick_entity(self, entity_id: int, needs: NeedsComponent, dt_minutes: float) -> None:
        acc = self._accumulators.setdefault(entity_id, {})
        # Hunger
        acc[NeedType.HUNGER] = acc.get(NeedType.HUNGER, 0.0) + self.rates[NeedType.HUNGER] * dt_minutes
        if acc[NeedType.HUNGER] >= 1.0:
            needs.hunger = min(100.0, needs.hunger + acc[NeedType.HUNGER])
            acc[NeedType.HUNGER] = 0.0
        # Thirst
        acc[NeedType.THIRST] = acc.get(NeedType.THIRST, 0.0) + self.rates[NeedType.THIRST] * dt_minutes
        if acc[NeedType.THIRST] >= 1.0:
            needs.thirst = min(100.0, needs.thirst + acc[NeedType.THIRST])
            acc[NeedType.THIRST] = 0.0
        # Fatigue
        acc[NeedType.FATIGUE] = acc.get(NeedType.FATIGUE, 0.0) + self.rates[NeedType.FATIGUE] * dt_minutes
        if acc[NeedType.FATIGUE] >= 1.0:
            needs.fatigue = min(100.0, needs.fatigue + acc[NeedType.FATIGUE])
            acc[NeedType.FATIGUE] = 0.0
        # Sleep
        acc[NeedType.SLEEP] = acc.get(NeedType.SLEEP, 0.0) + self.rates[NeedType.SLEEP] * dt_minutes
        if acc[NeedType.SLEEP] >= 1.0:
            needs.sleep = min(100.0, needs.sleep + acc[NeedType.SLEEP])
            acc[NeedType.SLEEP] = 0.0
        # Morale drifts toward baseline 75
        if needs.morale > 75:
            needs.morale -= 0.005 * dt_minutes
        elif needs.morale < 75:
            needs.morale += 0.005 * dt_minutes
        # Warmth slowly drifts toward ambient (handled by survival system).
        # Sanity drifts toward 100 slowly when morale > 50.
        if needs.morale > 50 and needs.sanity < 100:
            needs.sanity = min(100.0, needs.sanity + 0.003 * dt_minutes)

    # ---------- queries ----------

    @staticmethod
    def severity(need: NeedType, value: float) -> NeedSeverity:
        """Severity of a need based on its 0..100 value."""
        # For hunger/thirst/fatigue/sleep — higher is worse.
        if need in (NeedType.SANITY, NeedType.MORALE):
            # For these — lower is worse.
            if value > 75:
                return NeedSeverity.SATISFIED
            if value > 50:
                return NeedSeverity.MILD
            if value > 25:
                return NeedSeverity.MODERATE
            if value > 10:
                return NeedSeverity.SEVERE
            return NeedSeverity.CRITICAL
        if value < 10:
            return NeedSeverity.SATISFIED
        if value < 35:
            return NeedSeverity.MILD
        if value < 65:
            return NeedSeverity.MODERATE
        if value < 90:
            return NeedSeverity.SEVERE
        return NeedSeverity.CRITICAL

    @staticmethod
    def active_penalties(needs: NeedsComponent) -> dict[str, float]:
        """Return a merged dict of stat penalties from critical needs."""
        out: dict[str, float] = {}
        mapping = {
            NeedType.HUNGER: needs.hunger,
            NeedType.THIRST: needs.thirst,
            NeedType.FATIGUE: needs.fatigue,
            NeedType.SLEEP: needs.sleep,
            NeedType.SANITY: needs.sanity,
            NeedType.MORALE: needs.morale,
        }
        for need_type, value in mapping.items():
            sev = NeedsSystem.severity(need_type, value)
            if sev.value < NeedSeverity.SEVERE.value:
                continue
            penalty = CRITICAL_PENALTIES.get(need_type, {})
            mult = (sev.value - NeedSeverity.SEVERE.value + 1) / 2.0  # 0.5 .. 1.0
            for stat, val in penalty.items():
                out[stat] = out.get(stat, 0.0) + val * mult
        return out

    # ---------- mutations ----------

    @staticmethod
    def satisfy(need: NeedType, needs: NeedsComponent, amount: float) -> None:
        if need == NeedType.HUNGER:
            needs.hunger = max(0.0, needs.hunger - amount)
        elif need == NeedType.THIRST:
            needs.thirst = max(0.0, needs.thirst - amount)
        elif need == NeedType.FATIGUE:
            needs.fatigue = max(0.0, needs.fatigue - amount)
        elif need == NeedType.SLEEP:
            needs.sleep = max(0.0, needs.sleep - amount)
            needs.fatigue = max(0.0, needs.fatigue - amount * 0.5)
        elif need == NeedType.SANITY:
            needs.sanity = min(100.0, needs.sanity + amount)
        elif need == NeedType.MORALE:
            needs.morale = min(100.0, needs.morale + amount)
        elif need == NeedType.COMFORT:
            needs.comfort = min(100.0, needs.comfort + amount)
