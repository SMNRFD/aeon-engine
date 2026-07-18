"""Quest consequences and chain quests.

When a player completes or fails a quest, the world reacts:
* Faction reputation changes
* NPC relationships shift
* New quests become available
* Areas may become accessible or inaccessible
* NPCs may move, die, or change roles
* Prices may change
* New merchants may appear
* Wars may start or end

Chain quests are sequences of quests where each one unlocks the next,
and the outcomes of earlier quests affect later ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class ConsequenceType(IntEnum):
    FACTION_REPUTATION = 0
    NPC_RELATIONSHIP = 1
    UNLOCK_QUEST = 2
    LOCK_QUEST = 3
    UNLOCK_AREA = 4
    LOCK_AREA = 5
    SPAWN_NPC = 6
    DESPAWN_NPC = 7
    CHANGE_PRICE = 8
    START_WAR = 9
    END_WAR = 10
    ALLIANCE_FORMED = 11
    ALLIANCE_BROKEN = 12
    NPC_MOVE = 13
    NPC_DEATH = 14
    NPC_ROLE_CHANGE = 15
    WORLD_EVENT = 16
    PLAYER_REWARD = 17
    PLAYER_PENALTY = 18
    WEATHER_CHANGE = 19
    TIME_ADVANCE = 20
    DUNGEON_REVEAL = 21
    STRUCTURE_SPAWN = 22


@dataclass
class QuestConsequence:
    """A consequence of completing or failing a quest."""

    consequence_id: int
    consequence_type: ConsequenceType
    description: str = ""
    # Parameters depend on type
    target_faction_id: Optional[int] = None
    target_npc_id: Optional[int] = None
    target_quest_id: Optional[int] = None
    target_area: Optional[tuple[int, int]] = None
    reputation_delta: float = 0.0
    relationship_delta: float = 0.0
    price_multiplier: float = 1.0
    reward_gold: int = 0
    reward_xp: int = 0
    reward_item_id: Optional[int] = None
    world_event_id: Optional[str] = None
    is_applied: bool = False
    applies_on: str = "complete"  # "complete" or "fail"
    delay_ticks: float = 0.0  # delayed consequence

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["consequence_type"] = int(self.consequence_type)
        if self.target_area:
            d["target_area"] = list(self.target_area)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QuestConsequence":
        d = dict(data)
        d["consequence_type"] = ConsequenceType(d.get("consequence_type", 0))
        if d.get("target_area"):
            d["target_area"] = tuple(d["target_area"])
        return cls(**d)


@dataclass
class QuestChain:
    """A chain of related quests."""

    chain_id: int
    name: str
    description: str = ""
    quest_ids: list[int] = field(default_factory=list)  # in order
    current_quest_index: int = 0
    consequences: list[QuestConsequence] = field(default_factory=list)
    # Branches: if a quest fails, the chain may diverge
    branches: dict[int, list[int]] = field(default_factory=list)
    # quest_id -> list of alternative quest_ids on failure
    is_complete: bool = False
    is_failed: bool = False
    started_tick: float = 0.0
    completed_tick: Optional[float] = None
    rewards: dict[str, Any] = field(default_factory=dict)

    def current_quest_id(self) -> Optional[int]:
        if self.current_quest_index >= len(self.quest_ids):
            return None
        return self.quest_ids[self.current_quest_index]

    def advance(self) -> Optional[int]:
        """Advance to the next quest. Returns the new quest_id or None if done."""
        self.current_quest_index += 1
        if self.current_quest_index >= len(self.quest_ids):
            self.is_complete = True
            return None
        return self.current_quest_id()

    def fail_current(self) -> list[int]:
        """Fail the current quest, returning alternative quest IDs if any."""
        current = self.current_quest_id()
        if current is None:
            return []
        alternatives = self.branches.get(current, [])
        if not alternatives:
            self.is_failed = True
        return alternatives

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["consequences"] = [c.to_dict() for c in self.consequences]
        d["branches"] = {str(k): v for k, v in self.branches.items()}
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "QuestChain":
        d = dict(data)
        d["consequences"] = [QuestConsequence.from_dict(c) for c in d.get("consequences", [])]
        d["branches"] = {int(k): v for k, v in d.get("branches", {}).items()}
        return cls(**d)


class ConsequenceSystem:
    """Manages quest consequences and chains."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._chains: dict[int, QuestChain] = {}
        self._pending_consequences: list[tuple[float, QuestConsequence]] = []
        self._applied_consequences: list[QuestConsequence] = []
        self._next_chain_id: int = 1
        self._next_consequence_id: int = 1
        self._init_default_chains()

    def _init_default_chains(self) -> None:
        for chain in DEFAULT_CHAINS:
            chain.chain_id = self._next_chain_id
            self._next_chain_id += 1
            self._chains[chain.chain_id] = chain

    def create_chain(self, name: str, quest_ids: list[int],
                     **kwargs: Any) -> QuestChain:
        chain = QuestChain(
            chain_id=self._next_chain_id,
            name=name, quest_ids=list(quest_ids),
            **kwargs,
        )
        self._next_chain_id += 1
        self._chains[chain.chain_id] = chain
        return chain

    def add_consequence(self, chain_id: int, consequence: QuestConsequence) -> None:
        chain = self._chains.get(chain_id)
        if chain is None:
            return
        consequence.consequence_id = self._next_consequence_id
        self._next_consequence_id += 1
        chain.consequences.append(consequence)

    def on_quest_complete(self, quest_id: int,
                          current_tick: float = 0.0) -> list[QuestConsequence]:
        """Called when a quest is completed. Returns applied consequences."""
        applied: list[QuestConsequence] = []
        for chain in self._chains.values():
            if chain.current_quest_id() == quest_id:
                # Apply consequences that fire on completion
                for consequence in chain.consequences:
                    if consequence.applies_on == "complete" and not consequence.is_applied:
                        if consequence.delay_ticks > 0:
                            self._pending_consequences.append(
                                (current_tick + consequence.delay_ticks, consequence)
                            )
                        else:
                            consequence.is_applied = True
                            self._applied_consequences.append(consequence)
                            applied.append(consequence)
                # Advance the chain
                chain.advance()
                if chain.is_complete:
                    chain.completed_tick = current_tick
        return applied

    def on_quest_fail(self, quest_id: int,
                       current_tick: float = 0.0) -> list[QuestConsequence]:
        """Called when a quest fails."""
        applied: list[QuestConsequence] = []
        for chain in self._chains.values():
            if chain.current_quest_id() == quest_id:
                for consequence in chain.consequences:
                    if consequence.applies_on == "fail" and not consequence.is_applied:
                        consequence.is_applied = True
                        self._applied_consequences.append(consequence)
                        applied.append(consequence)
                chain.fail_current()
        return applied

    def update(self, current_tick: float) -> list[QuestConsequence]:
        """Process pending delayed consequences."""
        triggered: list[QuestConsequence] = []
        remaining: list[tuple[float, QuestConsequence]] = []
        for trigger_tick, consequence in self._pending_consequences:
            if current_tick >= trigger_tick:
                consequence.is_applied = True
                self._applied_consequences.append(consequence)
                triggered.append(consequence)
            else:
                remaining.append((trigger_tick, consequence))
        self._pending_consequences = remaining
        return triggered

    def chains(self) -> list[QuestChain]:
        return list(self._chains.values())

    def active_chains(self) -> list[QuestChain]:
        return [c for c in self._chains.values()
                if not c.is_complete and not c.is_failed]

    def applied_consequences(self) -> list[QuestConsequence]:
        return list(self._applied_consequences)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chains": {str(cid): c.to_dict() for cid, c in self._chains.items()},
            "pending_consequences": [
                {"trigger_tick": t, "consequence": c.to_dict()}
                for t, c in self._pending_consequences
            ],
            "applied_consequences": [c.to_dict() for c in self._applied_consequences],
            "next_chain_id": self._next_chain_id,
            "next_consequence_id": self._next_consequence_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConsequenceSystem":
        sys = cls()
        sys._chains = {
            int(cid): QuestChain.from_dict(c)
            for cid, c in data.get("chains", {}).items()
        }
        sys._pending_consequences = [
            (entry["trigger_tick"], QuestConsequence.from_dict(entry["consequence"]))
            for entry in data.get("pending_consequences", [])
        ]
        sys._applied_consequences = [
            QuestConsequence.from_dict(c)
            for c in data.get("applied_consequences", [])
        ]
        sys._next_chain_id = data.get("next_chain_id", 1)
        sys._next_consequence_id = data.get("next_consequence_id", 1)
        return sys


# ---------- Default quest chains ----------

DEFAULT_CHAINS: list[QuestChain] = [
    QuestChain(
        chain_id=0,
        name="The Bandit Threat",
        description="A multi-stage quest to deal with bandit raids.",
        quest_ids=[1, 2, 3],  # would be real quest IDs
        consequences=[
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.FACTION_REPUTATION,
                description="Merchants' Guild approves of your actions.",
                target_faction_id=6,  # Free Merchants' Guild
                reputation_delta=10.0,
                applies_on="complete",
            ),
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.UNLOCK_QUEST,
                description="The mayor has a special task for you.",
                target_quest_id=4,
                applies_on="complete",
            ),
        ],
        rewards={"gold": 500, "xp": 1000},
    ),
    QuestChain(
        chain_id=0,
        name="The Lost Heirloom",
        description="Recover a family heirloom and uncover a family secret.",
        quest_ids=[10, 11, 12],
        consequences=[
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.NPC_RELATIONSHIP,
                description="The old woman is grateful.",
                target_npc_id=5,
                relationship_delta=0.5,
                applies_on="complete",
            ),
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.NPC_DEATH,
                description="The old woman passes away peacefully.",
                target_npc_id=5,
                applies_on="complete",
                delay_ticks=86400,  # 1 day later
            ),
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.UNLOCK_QUEST,
                description="The old woman's will mentions a hidden treasure.",
                target_quest_id=13,
                applies_on="complete",
                delay_ticks=86400,
            ),
        ],
    ),
    QuestChain(
        chain_id=0,
        name="The Necromancer's Plot",
        description="Uncover and stop a necromancer's plot to raise an undead army.",
        quest_ids=[20, 21, 22, 23],
        consequences=[
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.FACTION_REPUTATION,
                description="The Order of the Silver Flame rewards you.",
                target_faction_id=4,
                reputation_delta=25.0,
                applies_on="complete",
            ),
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.LOCK_AREA,
                description="The necromancer's tower collapses.",
                target_area=(50, 30),
                applies_on="complete",
            ),
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.PLAYER_REWARD,
                description="You receive a powerful artifact.",
                reward_gold=1000,
                reward_xp=5000,
                reward_item_id=999,  # would be a real item
                applies_on="complete",
            ),
            QuestConsequence(
                consequence_id=0,
                consequence_type=ConsequenceType.START_WAR,
                description="The necromancer's death triggers a war with the undead.",
                target_faction_id=4,
                applies_on="complete",
                delay_ticks=86400 * 7,  # 1 week later
            ),
        ],
    ),
]
