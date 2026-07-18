"""Quest engine — branching, procedural, scripted quests."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, ClassVar, Optional

from engine.core.ecs import Entity
from engine.utils.rng import RNG


class QuestState(Enum):
    INACTIVE = "inactive"
    AVAILABLE = "available"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


@dataclass
class QuestObjective:
    """A single objective within a quest."""

    id: str
    description: str
    kind: str  # "kill", "fetch", "talk", "explore", "escort", "defend", "custom"
    target: Optional[str] = None   # entity type / item id / npc id
    count: int = 1
    current: int = 0
    optional: bool = False
    next_objectives: list[str] = field(default_factory=list)
    on_complete: Optional[Callable[[Entity, "Quest"], None]] = None


@dataclass
class QuestStage:
    """A stage in a branching quest."""

    id: str
    description: str
    objectives: list[QuestObjective] = field(default_factory=list)
    reward_xp: int = 0
    reward_gold: int = 0
    reward_items: dict[str, int] = field(default_factory=dict)
    next_stages: list[str] = field(default_factory=list)
    requires_all_objectives: bool = True


@dataclass
class Quest:
    """A complete quest definition."""

    id: int
    name: str
    description: str
    giver: Optional[str] = None  # npc archetype or specific id
    faction: Optional[str] = None
    min_level: int = 1
    repeatable: bool = False
    time_limit: Optional[float] = None  # in-game seconds
    stages: dict[str, QuestStage] = field(default_factory=dict)
    start_stage: str = "start"
    tags: list[str] = field(default_factory=list)
    # Branching
    choices: dict[str, list[str]] = field(default_factory=dict)
    prerequisite_quest_ids: list[int] = field(default_factory=list)


class QuestLibrary:
    """Registry of quest definitions."""

    _quests: ClassVar[dict[int, Quest]] = {}
    _next_id: ClassVar[int] = 1
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, quest: Quest) -> Quest:
        if not cls._defaults_loaded:
            cls._init_defaults()
        if quest.id == 0:
            quest.id = cls._next_id
            cls._next_id += 1
        else:
            cls._next_id = max(cls._next_id, quest.id + 1)
        cls._quests[quest.id] = quest
        return quest

    @classmethod
    def get(cls, quest_id: int) -> Optional[Quest]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._quests.get(quest_id)

    @classmethod
    def all(cls) -> list[Quest]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._quests.values())

    @classmethod
    def by_tag(cls, tag: str) -> list[Quest]:
        return [q for q in cls.all() if tag in q.tags]

    @classmethod
    def available_for(cls, level: int, completed: list[int]) -> list[Quest]:
        out: list[Quest] = []
        for q in cls.all():
            if q.id in completed:
                if not q.repeatable:
                    continue
            if q.min_level > level:
                continue
            if any(pre not in completed for pre in q.prerequisite_quest_ids):
                continue
            out.append(q)
        return out

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        cls._defaults_loaded = True  # set first to avoid recursion via register()
        for q in DEFAULT_QUESTS:
            if q.id == 0:
                q.id = cls._next_id
                cls._next_id += 1
            else:
                cls._next_id = max(cls._next_id, q.id + 1)
            cls._quests[q.id] = q


@dataclass
class QuestTracker:
    """Per-entity quest progress tracker."""

    active: dict[int, str] = field(default_factory=dict)  # quest_id -> current_stage_id
    completed: list[int] = field(default_factory=list)
    failed: list[int] = field(default_factory=list)
    abandoned: list[int] = field(default_factory=list)
    objectives_progress: dict[tuple[int, str, str], int] = field(default_factory=dict)
    started_at: dict[int, float] = field(default_factory=dict)

    def start(self, quest: Quest, current_tick: float) -> None:
        if quest.id in self.active or quest.id in self.completed:
            return
        self.active[quest.id] = quest.start_stage
        self.started_at[quest.id] = current_tick

    def advance_objective(self, quest_id: int, stage_id: str, obj_id: str,
                          amount: int = 1) -> None:
        key = (quest_id, stage_id, obj_id)
        self.objectives_progress[key] = self.objectives_progress.get(key, 0) + amount

    def objective_progress(self, quest_id: int, stage_id: str, obj_id: str) -> int:
        return self.objectives_progress.get((quest_id, stage_id, obj_id), 0)

    def complete_quest(self, quest_id: int) -> None:
        self.active.pop(quest_id, None)
        if quest_id not in self.completed:
            self.completed.append(quest_id)

    def fail_quest(self, quest_id: int) -> None:
        self.active.pop(quest_id, None)
        if quest_id not in self.failed:
            self.failed.append(quest_id)

    def abandon_quest(self, quest_id: int) -> None:
        self.active.pop(quest_id, None)
        if quest_id not in self.abandoned:
            self.abandoned.append(quest_id)

    def is_stage_complete(self, quest: Quest, stage_id: str) -> bool:
        stage = quest.stages.get(stage_id)
        if stage is None:
            return False
        completed_objs = 0
        required = 0
        for obj in stage.objectives:
            if obj.optional:
                continue
            required += 1
            prog = self.objective_progress(quest.id, stage_id, obj.id)
            if prog >= obj.count:
                completed_objs += 1
        if stage.requires_all_objectives:
            return completed_objs == required
        return completed_objs >= 1

    def to_dict(self) -> dict:
        return {
            "active": dict(self.active),
            "completed": list(self.completed),
            "failed": list(self.failed),
            "abandoned": list(self.abandoned),
            "objectives_progress": {f"{q}:{s}:{o}": v
                                    for (q, s, o), v in self.objectives_progress.items()},
            "started_at": dict(self.started_at),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "QuestTracker":
        t = cls()
        t.active = {int(k): v for k, v in data.get("active", {}).items()}
        t.completed = list(data.get("completed", []))
        t.failed = list(data.get("failed", []))
        t.abandoned = list(data.get("abandoned", []))
        for key_str, val in data.get("objectives_progress", {}).items():
            q, s, o = key_str.split(":")
            t.objectives_progress[(int(q), s, o)] = val
        t.started_at = {int(k): v for k, v in data.get("started_at", {}).items()}
        return t


# ---------- Default quests ----------

DEFAULT_QUESTS: list[Quest] = [
    Quest(
        id=0,  # auto-assigned
        name="Rats in the Cellar",
        description="The innkeeper has a rat problem in the cellar. Clear them out.",
        giver="innkeeper",
        min_level=1,
        tags=["tutorial", "combat"],
        stages={
            "start": QuestStage(
                id="start",
                description="Kill 5 rats in the inn cellar.",
                objectives=[
                    QuestObjective(id="kill_rats", description="Kill cellar rats",
                                   kind="kill", target="rat", count=5),
                ],
                reward_xp=50, reward_gold=20,
                reward_items={"health_potion": 1},
                next_stages=["done"],
            ),
            "done": QuestStage(
                id="done",
                description="Return to the innkeeper for your reward.",
                objectives=[
                    QuestObjective(id="return", description="Return to innkeeper",
                                   kind="talk", target="innkeeper", count=1),
                ],
                reward_xp=20,
            ),
        },
    ),
    Quest(
        id=0,
        name="Bandit Trouble",
        description="Bandits have been raiding the caravans. Hunt them down.",
        giver="merchant",
        min_level=5,
        tags=["combat", "faction"],
        stages={
            "start": QuestStage(
                id="start",
                description="Find the bandit camp in the southern woods.",
                objectives=[
                    QuestObjective(id="find_camp", description="Find the bandit camp",
                                   kind="explore", target="bandit_camp", count=1),
                ],
                next_stages=["assault"],
            ),
            "assault": QuestStage(
                id="assault",
                description="Defeat the bandit leader.",
                objectives=[
                    QuestObjective(id="kill_leader", description="Kill the bandit leader",
                                   kind="kill", target="bandit_leader", count=1),
                    QuestObjective(id="kill_bandits", description="Kill bandits",
                                   kind="kill", target="bandit", count=5,
                                   optional=True),
                ],
                reward_xp=200, reward_gold=150,
                reward_items={"steel_longsword": 1},
                next_stages=["report"],
            ),
            "report": QuestStage(
                id="report",
                description="Return to the merchant for your reward.",
                objectives=[
                    QuestObjective(id="return", description="Return to merchant",
                                   kind="talk", target="merchant", count=1),
                ],
                reward_xp=50, reward_gold=100,
            ),
        },
    ),
    Quest(
        id=0,
        name="The Lost Heirloom",
        description="An old woman lost her heirloom necklace in the forest.",
        giver="elder_woman",
        min_level=2,
        tags=["fetch", "social"],
        stages={
            "start": QuestStage(
                id="start",
                description="Find the necklace in the forest.",
                objectives=[
                    QuestObjective(id="find_necklace", description="Find the necklace",
                                   kind="fetch", target="silver_necklace", count=1),
                ],
                next_stages=["return"],
            ),
            "return": QuestStage(
                id="return",
                description="Return the necklace to the old woman.",
                objectives=[
                    QuestObjective(id="return", description="Return the necklace",
                                   kind="talk", target="elder_woman", count=1),
                ],
                reward_xp=80, reward_gold=50,
                reward_items={"amulet": 1},
            ),
        },
    ),
]


# ---------- Procedural quest generation ----------

class QuestGenerator:
    """Generates simple procedural fetch/kill quests."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()

    def generate(self, level: int, archetype: Optional[str] = None) -> Quest:
        archetype = archetype or self.rng.choice(["fetch", "kill", "explore"])
        giver = self.rng.choice(["merchant", "innkeeper", "guard", "villager",
                                 "noble", "priest"])
        target_mob = self.rng.choice(["wolf", "bandit", "goblin", "skeleton",
                                      "rat", "ogre"])
        target_item = self.rng.choice(["silver_ring", "ancient_tome",
                                       "herb_bundle", "gemstone"])
        target_place = self.rng.choice(["abandoned_mine", "old_ruins",
                                        "deep_forest", "cave_system"])
        if archetype == "fetch":
            q = Quest(
                id=0,
                name=f"Fetch the {target_item.replace('_', ' ').title()}",
                description=f"Retrieve a {target_item} from the {target_place}.",
                giver=giver, min_level=level,
                stages={
                    "start": QuestStage(
                        id="start",
                        description=f"Find the {target_item}.",
                        objectives=[QuestObjective(
                            id="find", description=f"Find the {target_item}",
                            kind="fetch", target=target_item, count=1,
                        )],
                        next_stages=["return"],
                        reward_xp=50 + level * 20,
                        reward_gold=30 + level * 10,
                    ),
                    "return": QuestStage(
                        id="return",
                        description="Return to the quest giver.",
                        objectives=[QuestObjective(
                            id="return", description="Return",
                            kind="talk", target=giver, count=1,
                        )],
                        reward_xp=20 + level * 5,
                    ),
                },
            )
        elif archetype == "kill":
            count = self.rng.randint(3, 8)
            q = Quest(
                id=0,
                name=f"{target_mob.title()} Hunt",
                description=f"Kill {count} {target_mob}s threatening the area.",
                giver=giver, min_level=level,
                stages={
                    "start": QuestStage(
                        id="start",
                        description=f"Kill {count} {target_mob}s.",
                        objectives=[QuestObjective(
                            id="kill", description=f"Kill {target_mob}s",
                            kind="kill", target=target_mob, count=count,
                        )],
                        next_stages=["report"],
                        reward_xp=80 + level * 30,
                        reward_gold=50 + level * 15,
                    ),
                    "report": QuestStage(
                        id="report",
                        description="Report your success.",
                        objectives=[QuestObjective(
                            id="return", description="Return",
                            kind="talk", target=giver, count=1,
                        )],
                        reward_xp=30,
                    ),
                },
            )
        else:
            q = Quest(
                id=0,
                name=f"Expedition: {target_place.replace('_', ' ').title()}",
                description=f"Explore the {target_place} and report back.",
                giver=giver, min_level=level,
                stages={
                    "start": QuestStage(
                        id="start",
                        description=f"Reach the {target_place}.",
                        objectives=[QuestObjective(
                            id="explore", description=f"Explore {target_place}",
                            kind="explore", target=target_place, count=1,
                        )],
                        next_stages=["report"],
                        reward_xp=100 + level * 25,
                        reward_gold=40 + level * 12,
                    ),
                    "report": QuestStage(
                        id="report",
                        description="Report your findings.",
                        objectives=[QuestObjective(
                            id="return", description="Return",
                            kind="talk", target=giver, count=1,
                        )],
                        reward_xp=40,
                    ),
                },
            )
        return QuestLibrary.register(q)
