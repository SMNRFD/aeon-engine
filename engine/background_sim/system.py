"""Background simulation — the world progresses while the player is absent.

When the player is offline, the simulation continues:
* NPCs continue their routines, marry, have children, die
* Wars are fought and resolved
* Economies fluctuate
* Weather changes
* Plagues spread
* Caravans travel
* Building construction completes
* Kingdoms rise and fall

The background simulator runs at a reduced rate (e.g., 1 simulation
hour per real second) to advance the world quickly without overwhelming
the system.

On player return, a summary report of major events is generated.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.logging import get_logger
from engine.utils.rng import RNG


log = get_logger("background_sim")


class EventType(IntEnum):
    NPC_BIRTH = 0
    NPC_DEATH = 1
    NPC_MARRIAGE = 2
    NPC_DIVORCE = 3
    NPC_MIGRATION = 4
    BATTLE = 5
    WAR_DECLARED = 6
    WAR_ENDED = 7
    TREATY_SIGNED = 8
    PLAGUE_OUTBREAK = 9
    FAMINE = 10
    DROUGHT = 11
    FLOOD = 12
    EARTHQUAKE = 13
    STORM = 14
    CARAVAN_ARRIVED = 15
    CARAVAN_LOST = 16
    BUILDING_CONSTRUCTED = 17
    BUILDING_DESTROYED = 18
    DUNGEON_DISCOVERED = 19
    DUNGEON_CLEARED = 20
    FACTION_FOUNDED = 21
    FACTION_DESTROYED = 22
    NEW_QUEST_AVAILABLE = 23
    PRICE_CHANGE = 24
    ELECTION_HELD = 25
    RULER_CORONATED = 26
    RULER_DIED = 27
    REBELLION_STARTED = 28
    REBELLION_ENDED = 29
    MIGRATION = 30
    DISCOVERY = 31
    PORTAL_OPENED = 32
    PORTAL_CLOSED = 33
    DRAGON_SIGHTING = 34
    MIRACLE = 35
    OMEN = 36


@dataclass
class BackgroundEvent:
    """A single world event."""

    event_id: int
    event_type: EventType
    timestamp: float  # in-game tick
    description: str = ""
    location: Optional[tuple[int, int]] = None
    involved_entities: list[int] = field(default_factory=list)
    involved_factions: list[int] = field(default_factory=list)
    severity: int = 1  # 1=minor, 5=major, 10=world-changing
    is_major: bool = False  # shown in summary
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["event_type"] = int(self.event_type)
        if self.location:
            d["location"] = list(self.location)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "BackgroundEvent":
        d = dict(data)
        d["event_type"] = EventType(d.get("event_type", 0))
        if d.get("location"):
            d["location"] = tuple(d["location"])
        return cls(**d)


@dataclass
class SimulationReport:
    """A summary of events that occurred during a simulation period."""

    start_tick: float
    end_tick: float
    duration_real_seconds: float
    duration_game_hours: float
    total_events: int = 0
    major_events: list[BackgroundEvent] = field(default_factory=list)
    notable_deaths: list[int] = field(default_factory=list)
    wars_started: int = 0
    wars_ended: int = 0
    battles_fought: int = 0
    births: int = 0
    deaths: int = 0
    marriages: int = 0
    buildings_constructed: int = 0
    new_quests: int = 0
    price_changes: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["major_events"] = [e.to_dict() for e in self.major_events]
        return d


class BackgroundSimulator:
    """Runs background simulation while player is absent."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._events: list[BackgroundEvent] = []
        self._next_event_id: int = 1
        self._is_running: bool = False
        self._sim_speed: float = 3600.0  # 1 hour per real second
        self._last_tick: float = 0.0

    def start(self) -> None:
        self._is_running = True
        log.info("Background simulation started")

    def stop(self) -> None:
        self._is_running = False
        log.info("Background simulation stopped")

    @property
    def is_running(self) -> bool:
        return self._is_running

    def set_speed(self, hours_per_second: float) -> None:
        """Set simulation speed in game-hours per real second."""
        self._sim_speed = max(0.1, min(86400.0, hours_per_second))

    def simulate(self, duration_real_seconds: float,
                 start_tick: float = 0.0) -> SimulationReport:
        """Simulate for a duration. Returns a report of events."""
        if not self._is_running:
            self.start()
        start_time = time.time()
        game_hours = duration_real_seconds * self._sim_speed
        end_tick = start_tick + game_hours * 3600  # convert hours to seconds
        self._last_tick = start_tick
        events_generated: list[BackgroundEvent] = []
        # Generate events at random intervals
        while self._last_tick < end_tick:
            # Advance time by a random amount
            step_hours = self.rng.uniform(0.5, 6.0)
            self._last_tick += step_hours * 3600
            # Generate 0-3 events per step
            n_events = self.rng.randint(0, 3)
            for _ in range(n_events):
                event = self._generate_event(self._last_tick)
                if event:
                    events_generated.append(event)
                    self._events.append(event)
        # Build report
        report = self._build_report(start_tick, end_tick,
                                     duration_real_seconds, game_hours,
                                     events_generated)
        log.info("Simulated %.1f game hours, generated %d events",
                  game_hours, len(events_generated))
        return report

    def _generate_event(self, tick: float) -> Optional[BackgroundEvent]:
        """Generate a random world event."""
        event_type = self.rng.choice(list(EventType))
        severity = self.rng.randint(1, 10)
        is_major = severity >= 7
        description = self._describe_event(event_type, severity)
        event = BackgroundEvent(
            event_id=self._next_event_id,
            event_type=event_type,
            timestamp=tick,
            description=description,
            severity=severity,
            is_major=is_major,
        )
        self._next_event_id += 1
        return event

    def _describe_event(self, event_type: EventType, severity: int) -> str:
        """Generate a description for an event."""
        descriptions: dict[EventType, list[str]] = {
            EventType.NPC_BIRTH: ["A child is born.", "A new baby enters the world."],
            EventType.NPC_DEATH: ["An old man passes away peacefully.",
                                   "A beloved citizen has died."],
            EventType.NPC_MARRIAGE: ["Two young lovers are married in a small ceremony."],
            EventType.BATTLE: ["A skirmish was fought on the borders.",
                                "A major battle saw heavy casualties."],
            EventType.WAR_DECLARED: ["War has been declared!",
                                      "The drums of war sound again."],
            EventType.WAR_ENDED: ["A peace treaty is signed.",
                                   "The long war is finally over."],
            EventType.PLAGUE_OUTBREAK: ["A plague has broken out!",
                                         "Disease spreads through the city."],
            EventType.FAMINE: ["Crops fail and famine looms.",
                                "The harvest was poor this year."],
            EventType.STORM: ["A great storm batters the coast.",
                               "Thunder and lightning rage overhead."],
            EventType.CARAVAN_ARRIVED: ["A merchant caravan arrives with goods."],
            EventType.CARAVAN_LOST: ["A caravan was lost to bandits."],
            EventType.BUILDING_CONSTRUCTED: ["A new building is completed.",
                                              "Construction finishes on the temple."],
            EventType.DUNGEON_DISCOVERED: ["An adventurer discovers a new dungeon."],
            EventType.FACTION_FOUNDED: ["A new faction has been founded."],
            EventType.REBELLION_STARTED: ["Rebels rise up against their rulers!"],
            EventType.PRICE_CHANGE: ["Market prices have shifted."],
            EventType.RULER_DIED: ["The ruler has died!",
                                    "The king is dead. Long live the king."],
            EventType.DRAGON_SIGHTING: ["A dragon was sighted in the mountains!"],
            EventType.MIRACLE: ["A miracle has occurred!",
                                 "The gods have shown their favor."],
            EventType.OMEN: ["A dark omen was seen in the sky."],
        }
        opts = descriptions.get(event_type, ["Something happened."])
        return self.rng.choice(opts)

    def _build_report(self, start_tick: float, end_tick: float,
                       duration_real: float, duration_game: float,
                       events: list[BackgroundEvent]) -> SimulationReport:
        major = [e for e in events if e.is_major]
        report = SimulationReport(
            start_tick=start_tick, end_tick=end_tick,
            duration_real_seconds=duration_real,
            duration_game_hours=duration_game,
            total_events=len(events),
            major_events=major,
            wars_started=sum(1 for e in events if e.event_type == EventType.WAR_DECLARED),
            wars_ended=sum(1 for e in events if e.event_type == EventType.WAR_ENDED),
            battles_fought=sum(1 for e in events if e.event_type == EventType.BATTLE),
            births=sum(1 for e in events if e.event_type == EventType.NPC_BIRTH),
            deaths=sum(1 for e in events if e.event_type == EventType.NPC_DEATH),
            marriages=sum(1 for e in events if e.event_type == EventType.NPC_MARRIAGE),
            buildings_constructed=sum(1 for e in events if e.event_type == EventType.BUILDING_CONSTRUCTED),
            new_quests=sum(1 for e in events if e.event_type == EventType.NEW_QUEST_AVAILABLE),
            price_changes=sum(1 for e in events if e.event_type == EventType.PRICE_CHANGE),
        )
        # Generate summary text
        lines = [
            f"During your absence ({duration_game:.0f} game hours):",
            f"  {report.total_events} events occurred",
            f"  {report.births} births, {report.deaths} deaths, {report.marriages} marriages",
            f"  {report.wars_started} wars started, {report.wars_ended} ended",
            f"  {report.battles_fought} battles were fought",
            f"  {report.buildings_constructed} buildings were constructed",
        ]
        if major:
            lines.append("  Major events:")
            for event in major[:5]:  # top 5
                lines.append(f"    - {event.description}")
        report.summary = "\n".join(lines)
        return report

    def all_events(self) -> list[BackgroundEvent]:
        return list(self._events)

    def major_events(self) -> list[BackgroundEvent]:
        return [e for e in self._events if e.is_major]

    def events_since(self, tick: float) -> list[BackgroundEvent]:
        return [e for e in self._events if e.timestamp >= tick]

    def to_dict(self) -> dict[str, Any]:
        return {
            "events": [e.to_dict() for e in self._events],
            "next_event_id": self._next_event_id,
            "sim_speed": self._sim_speed,
            "last_tick": self._last_tick,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackgroundSimulator":
        sys = cls()
        sys._events = [BackgroundEvent.from_dict(e) for e in data.get("events", [])]
        sys._next_event_id = data.get("next_event_id", 1)
        sys._sim_speed = data.get("sim_speed", 3600.0)
        sys._last_tick = data.get("last_tick", 0.0)
        return sys
