"""Game clock — manages ticks, in-world time, and calendar progression."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from engine.core.logging import get_logger


log = get_logger("clock")


class Season(IntEnum):
    SPRING = 0
    SUMMER = 1
    AUTUMN = 2
    WINTER = 3

    @property
    def display_name(self) -> str:
        return self.name.title()


class PhaseOfDay(IntEnum):
    DAWN = 0
    DAY = 1
    DUSK = 2
    NIGHT = 3

    @property
    def display_name(self) -> str:
        return self.name.title()


@dataclass
class GameTime:
    """In-world date and time.

    Fields:
        tick:      Total ticks since the world began.
        minute:    In-world minute of day [0, minutes_per_hour).
        hour:      In-world hour of day [0, hours_per_day).
        day:       In-world day since start of game.
        season:    Current season index.
        year:      In-world year.

    The full day cycle is determined by the engine's `SimulationConfig`.
    """

    tick: int = 0
    minute: int = 6
    hour: int = 8
    day: int = 0
    season: int = 0
    year: int = 1

    def phase_of_day(self) -> PhaseOfDay:
        if 5 <= self.hour < 8:
            return PhaseOfDay.DAWN
        if 8 <= self.hour < 18:
            return PhaseOfDay.DAY
        if 18 <= self.hour < 21:
            return PhaseOfDay.DUSK
        return PhaseOfDay.NIGHT

    def season_name(self) -> str:
        return Season(self.season % 4).display_name

    def display(self) -> str:
        return (
            f"Year {self.year}, {self.season_name()}, "
            f"Day {self.day % 30 + 1}, {self.hour:02d}:{self.minute:02d}"
        )

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "minute": self.minute,
            "hour": self.hour,
            "day": self.day,
            "season": self.season,
            "year": self.year,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameTime":
        return cls(**data)


class GameClock:
    """Advances game-time based on real-time ticks.

    The clock runs at a configurable ticks-per-second rate, with each tick
    advancing in-world minutes by `ticks_per_game_minute` configured in the
    simulation config.
    """

    def __init__(
        self,
        ticks_per_second: int = 20,
        ticks_per_game_minute: int = 10,
        minutes_per_hour: int = 60,
        hours_per_day: int = 24,
        days_per_season: int = 30,
        seasons_per_year: int = 4,
    ) -> None:
        self.tps = ticks_per_second
        self.ticks_per_game_minute = max(1, ticks_per_game_minute)
        self.minutes_per_hour = minutes_per_hour
        self.hours_per_day = hours_per_day
        self.days_per_season = days_per_season
        self.seasons_per_year = seasons_per_year
        self.time = GameTime()
        self._tick_accumulator = 0
        self._real_start = time.perf_counter()
        self._paused = False
        self._time_scale = 1.0

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def toggle_pause(self) -> bool:
        self._paused = not self._paused
        return self._paused

    @property
    def paused(self) -> bool:
        return self._paused

    def set_time_scale(self, scale: float) -> None:
        self._time_scale = max(0.0, scale)

    def tick(self, dt: Optional[float] = None) -> None:
        """Advance the clock by one simulation tick (or by `dt` seconds)."""
        if self._paused:
            return
        if dt is None:
            dt = 1.0 / self.tps
        # Effective tick increments — we treat each `tick()` call as
        # one logical tick; if dt is supplied we accumulate fractional ticks.
        self._tick_accumulator += dt * self.tps * self._time_scale
        ticks = int(self._tick_accumulator)
        self._tick_accumulator -= ticks
        for _ in range(ticks):
            self._advance_one_tick()

    def advance_ticks(self, ticks: int) -> None:
        """Advance by an exact number of ticks, ignoring time scale."""
        if self._paused:
            return
        for _ in range(ticks):
            self._advance_one_tick()

    def _advance_one_tick(self) -> None:
        self.time.tick += 1
        if self.time.tick % self.ticks_per_game_minute == 0:
            self.time.minute += 1
            if self.time.minute >= self.minutes_per_hour:
                self.time.minute = 0
                self.time.hour += 1
                if self.time.hour >= self.hours_per_day:
                    self.time.hour = 0
                    self.time.day += 1
                    season_len = self.days_per_season
                    if self.time.day % season_len == 0:
                        self.time.season = (self.time.season + 1) % self.seasons_per_year
                        if self.time.season == 0:
                            self.time.year += 1

    def elapsed_real_seconds(self) -> float:
        return time.perf_counter() - self._real_start


__all__ = ["GameClock", "GameTime", "Season", "PhaseOfDay"]
