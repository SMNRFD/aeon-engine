"""Daily schedules — NPC routines based on time of day."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from engine.core.clock import PhaseOfDay
from engine.utils.rng import RNG


class TimeOfDay(IntEnum):
    EARLY_MORNING = 0   # 4-7
    MORNING = 1         # 7-10
    MIDDAY = 2          # 10-14
    AFTERNOON = 3       # 14-18
    EVENING = 4         # 18-22
    NIGHT = 5           # 22-4


@dataclass
class ScheduleEntry:
    """A scheduled activity."""

    activity: str       # "sleep", "eat", "work", "wander", "shop", "pray", "drink"
    start_hour: int     # 0..23
    end_hour: int       # 0..23 (wrap if end < start)
    location_tag: str = "home"  # location kind to travel to
    priority: int = 5
    flexibility: float = 0.5  # 0=strict, 1=very flexible

    def covers(self, hour: int) -> bool:
        if self.start_hour <= self.end_hour:
            return self.start_hour <= hour < self.end_hour
        # wraps midnight
        return hour >= self.start_hour or hour < self.end_hour


@dataclass
class Schedule:
    """A full daily schedule."""

    entries: list[ScheduleEntry] = field(default_factory=list)

    def activity_at(self, hour: int) -> Optional[ScheduleEntry]:
        candidates = [e for e in self.entries if e.covers(hour)]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e.priority)

    def add(self, entry: ScheduleEntry) -> None:
        self.entries.append(entry)

    def to_dict(self) -> dict:
        return {
            "entries": [
                {"activity": e.activity, "start_hour": e.start_hour,
                 "end_hour": e.end_hour, "location_tag": e.location_tag,
                 "priority": e.priority, "flexibility": e.flexibility}
                for e in self.entries
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Schedule":
        s = cls()
        for e in data.get("entries", []):
            s.add(ScheduleEntry(
                activity=e["activity"], start_hour=e["start_hour"],
                end_hour=e["end_hour"], location_tag=e.get("location_tag", "home"),
                priority=e.get("priority", 5), flexibility=e.get("flexibility", 0.5),
            ))
        return s


def generate_default_schedule(rng: Optional[RNG] = None,
                              occupation: str = "commoner") -> Schedule:
    """Generate a believable daily schedule for an NPC."""
    rng = rng or RNG()
    sched = Schedule()
    wake_hour = rng.randint(5, 7)
    breakfast = wake_hour + 1
    work_start = breakfast + 1
    lunch = 12
    work_end = 17 + rng.randint(-1, 2)
    dinner = work_end + 1
    sleep = 21 + rng.randint(-1, 2)

    sched.add(ScheduleEntry("wake", wake_hour, wake_hour + 1, "home", 8, 0.3))
    sched.add(ScheduleEntry("eat", breakfast, breakfast + 1, "home", 7, 0.5))
    sched.add(ScheduleEntry("work", work_start, lunch, "workplace", 6, 0.4))
    sched.add(ScheduleEntry("eat", lunch, lunch + 1, "tavern", 6, 0.5))
    sched.add(ScheduleEntry("work", lunch + 1, work_end, "workplace", 6, 0.4))
    sched.add(ScheduleEntry("eat", dinner, dinner + 1, "home", 7, 0.5))
    if rng.chance(0.4):
        sched.add(ScheduleEntry("drink", dinner + 1, dinner + 3, "tavern", 4, 0.7))
    else:
        sched.add(ScheduleEntry("wander", dinner + 1, sleep, "town", 3, 0.8))
    sched.add(ScheduleEntry("sleep", sleep, wake_hour, "home", 9, 0.2))
    return sched


# Occupation-flavoured schedules
OCCUPATION_WORKPLACES: dict[str, str] = {
    "commoner": "fields", "merchant": "market", "guard": "barracks",
    "smith": "smithy", "tavern_keeper": "tavern", "priest": "temple",
    "scholar": "library", "hunter": "woods", "fisher": "docks",
    "farmer": "fields", "noble": "manor", "soldier": "barracks",
    "thief": "alleys", "mage": "tower", "healer": "clinic",
}


def schedule_for_occupation(occupation: str, rng: Optional[RNG] = None) -> Schedule:
    rng = rng or RNG()
    sched = generate_default_schedule(rng, occupation)
    workplace = OCCUPATION_WORKPLACES.get(occupation, "workplace")
    for entry in sched.entries:
        if entry.activity == "work":
            entry.location_tag = workplace
    return sched
