"""Dialogue engine — trees with conditions, persuasion, and memory hooks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Personality, Relationships, Stats
from engine.npc.memory import NPCMemory
from engine.npc.personality import PersonalitySystem
from engine.skills.system import SkillsSystem
from engine.utils.rng import RNG


@dataclass
class DialogueChoice:
    """A player response option."""

    text: str
    next_node: Optional[str] = None
    condition: Optional[Callable[["DialogueContext"], bool]] = None
    effects: list[Callable[["DialogueContext"], None]] = field(default_factory=list)
    requires_skill: Optional[tuple[str, int]] = None  # (skill_id, min_level)
    persuasion: Optional["PersuasionAttempt"] = None
    ends_conversation: bool = False
    enables_quest: Optional[int] = None  # quest_id


@dataclass
class PersuasionAttempt:
    """A skill-checking persuasion attempt."""

    kind: str  # "persuade", "intimidate", "deceive", "barter"
    difficulty: float
    success_node: Optional[str] = None
    failure_node: Optional[str] = None


@dataclass
class DialogueNode:
    """A single node in a dialogue tree."""

    id: str
    speaker_text: str
    choices: list[DialogueChoice] = field(default_factory=list)
    on_enter: Optional[Callable[["DialogueContext"], None]] = None
    gives_quest: Optional[int] = None
    gives_item: Optional[str] = None
    rumor: Optional[str] = None
    is_exit: bool = False


class DialogueTree:
    """A complete dialogue tree."""

    def __init__(self, tree_id: str, root_id: str,
                 nodes: dict[str, DialogueNode]) -> None:
        self.tree_id = tree_id
        self.root_id = root_id
        self.nodes = nodes

    def root(self) -> DialogueNode:
        return self.nodes[self.root_id]

    def get(self, node_id: str) -> Optional[DialogueNode]:
        return self.nodes.get(node_id)


@dataclass
class DialogueContext:
    """State of an ongoing dialogue."""

    world: World
    player: Entity
    npc: Entity
    npc_memory: NPCMemory
    rng: RNG
    current_node_id: str = ""
    visited_nodes: set[str] = field(default_factory=set)
    history: list[str] = field(default_factory=list)
    quest_log: Optional[Any] = None
    extra: dict[str, Any] = field(default_factory=dict)


class DialogueLibrary:
    """Registry of dialogue trees."""

    _trees: ClassVar[dict[str, DialogueTree]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, tree: DialogueTree) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._trees[tree.tree_id] = tree

    @classmethod
    def get(cls, tree_id: str) -> Optional[DialogueTree]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._trees.get(tree_id)

    @classmethod
    def all(cls) -> list[DialogueTree]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._trees.values())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for tree in DEFAULT_DIALOGUES:
            cls._trees[tree.tree_id] = tree
        cls._defaults_loaded = True


class DialogueEngine:
    """Runs dialogue interactions."""

    def __init__(self, skills: Optional[SkillsSystem] = None,
                 rng: Optional[RNG] = None) -> None:
        self.skills = skills or SkillsSystem()
        self.rng = rng or RNG()

    def start(self, world: World, player: Entity, npc: Entity,
              tree: DialogueTree, npc_memory: Optional[NPCMemory] = None) -> DialogueContext:
        ctx = DialogueContext(
            world=world, player=player, npc=npc,
            npc_memory=npc_memory or NPCMemory(), rng=self.rng,
            current_node_id=tree.root_id,
        )
        self._enter_node(ctx, tree, tree.root())
        return ctx

    def choose(self, ctx: DialogueContext, tree: DialogueTree,
               choice_index: int) -> Optional[DialogueNode]:
        node = tree.get(ctx.current_node_id)
        if node is None or choice_index >= len(node.choices):
            return None
        choice = node.choices[choice_index]
        if choice.condition and not choice.condition(ctx):
            return None
        if choice.requires_skill:
            skill_id, min_lvl = choice.requires_skill
            if self.skills.get_level(ctx.player, skill_id) < min_lvl:
                return None
        # Apply effects
        for effect in choice.effects:
            effect(ctx)
        # Persuasion check
        if choice.persuasion:
            success = self._roll_persuasion(ctx, choice.persuasion)
            next_id = choice.persuasion.success_node if success else choice.persuasion.failure_node
        else:
            next_id = choice.next_node
        if choice.ends_conversation or next_id is None:
            return None
        next_node = tree.get(next_id)
        if next_node is None:
            return None
        self._enter_node(ctx, tree, next_node)
        return next_node

    def _enter_node(self, ctx: DialogueContext, tree: DialogueTree,
                    node: DialogueNode) -> None:
        ctx.current_node_id = node.id
        ctx.visited_nodes.add(node.id)
        ctx.history.append(node.speaker_text)
        if node.on_enter:
            node.on_enter(ctx)
        if node.rumor:
            ctx.npc_memory.add_rumor(node.rumor)

    def _roll_persuasion(self, ctx: DialogueContext,
                         attempt: PersuasionAttempt) -> bool:
        stats = ctx.world.get_component(ctx.npc, Stats)
        personality = ctx.world.get_component(ctx.npc, Personality)
        difficulty = attempt.difficulty
        if personality:
            if attempt.kind == "persuade":
                difficulty -= PersonalitySystem.trust(personality) * 5
            elif attempt.kind == "intimidate":
                difficulty += PersonalitySystem.bravery(personality) * 10
            elif attempt.kind == "deceive":
                difficulty -= PersonalitySystem.trust(personality) * 8
            elif attempt.kind == "barter":
                difficulty -= 2
        # Skill check
        skill_map = {"persuade": "persuasion", "intimidate": "intimidation",
                     "deceive": "deception", "barter": "barter"}
        skill_id = skill_map.get(attempt.kind, "persuasion")
        result = self.skills.check(ctx.player, skill_id, difficulty, self.rng)
        if result.botch:
            # Adjust NPC relation down
            ctx.npc_memory.adjust_relation(ctx.player.id, -0.2)
        elif result.success:
            ctx.npc_memory.adjust_relation(ctx.player.id, 0.1)
        return result.success


# ---------- Default dialogue trees ----------

def _greeting_node(ctx: DialogueContext) -> None:
    npc_id = ctx.npc.id
    rel = ctx.npc_memory.relation_to(ctx.player.id)
    if rel > 0.3:
        ctx.history.append("(They greet you warmly.)")
    elif rel < -0.3:
        ctx.history.append("(They eye you warily.)")
    else:
        ctx.history.append("(They regard you neutrally.)")


DEFAULT_DIALOGUES: list[DialogueTree] = [
    DialogueTree(
        tree_id="commoner_greeting",
        root_id="start",
        nodes={
            "start": DialogueNode(
                id="start",
                speaker_text="Hello, traveller. What brings you here?",
                on_enter=_greeting_node,
                choices=[
                    DialogueChoice(
                        text="Tell me about this place.",
                        next_node="about_place",
                    ),
                    DialogueChoice(
                        text="Any news or rumors?",
                        next_node="rumors",
                    ),
                    DialogueChoice(
                        text="Where can I find work?",
                        next_node="work",
                    ),
                    DialogueChoice(
                        text="Goodbye.",
                        ends_conversation=True,
                    ),
                ],
            ),
            "about_place": DialogueNode(
                id="about_place",
                speaker_text="It's a quiet town. Mostly farmers and traders. Nothing much happens here, mostly.",
                choices=[
                    DialogueChoice(text="Thanks.", next_node="start"),
                ],
            ),
            "rumors": DialogueNode(
                id="rumors",
                speaker_text="I heard there's been strange lights in the old ruin to the east. Some say ghosts, some say treasure hunters.",
                rumor="strange_lights_east_ruin",
                choices=[
                    DialogueChoice(text="Interesting. Thanks.", next_node="start"),
                ],
            ),
            "work": DialogueNode(
                id="work",
                speaker_text="The mayor usually has tasks. Try the town hall. Or there's bounties at the inn.",
                choices=[
                    DialogueChoice(text="Thanks for the tip.", next_node="start"),
                ],
            ),
        },
    ),
    DialogueTree(
        tree_id="merchant_greeting",
        root_id="start",
        nodes={
            "start": DialogueNode(
                id="start",
                speaker_text="Welcome to my shop! Looking for something specific, or just browsing?",
                choices=[
                    DialogueChoice(text="Let me see your wares.", next_node="trade"),
                    DialogueChoice(text="What's the news?", next_node="news"),
                    DialogueChoice(text="Just looking.", ends_conversation=True),
                ],
            ),
            "trade": DialogueNode(
                id="trade",
                speaker_text="Of course! Show me your coin and I'll show you my best.",
                choices=[
                    DialogueChoice(text="(Begin trade)", ends_conversation=True),
                ],
            ),
            "news": DialogueNode(
                id="news",
                speaker_text="Caravans from the south have been scarce lately. Bandits, they say. Prices are up.",
                rumor="bandits_south_caravans",
                choices=[
                    DialogueChoice(text="Thanks for the warning.", next_node="start"),
                ],
            ),
        },
    ),
    DialogueTree(
        tree_id="guard_greeting",
        root_id="start",
        nodes={
            "start": DialogueNode(
                id="start",
                speaker_text="Halt. State your business.",
                choices=[
                    DialogueChoice(text="Just passing through.", next_node="pass"),
                    DialogueChoice(
                        text="[Intimidate] Step aside. I have no time for this.",
                        persuasion=PersuasionAttempt("intimidate", 25,
                                                     success_node="intimidated",
                                                     failure_node="angry"),
                    ),
                    DialogueChoice(text="I'm looking for bounties.", next_node="bounty"),
                    DialogueChoice(text="Sorry, I'll be going.", ends_conversation=True),
                ],
            ),
            "pass": DialogueNode(
                id="pass",
                speaker_text="...Fine. Move along, then. And stay out of trouble.",
                choices=[DialogueChoice(text="(leave)", ends_conversation=True)],
            ),
            "intimidated": DialogueNode(
                id="intimidated",
                speaker_text="(The guard steps aside, looking cowed.) ...My apologies. Carry on.",
                choices=[DialogueChoice(text="(leave)", ends_conversation=True)],
            ),
            "angry": DialogueNode(
                id="angry",
                speaker_text="You dare threaten me?! Move along before I arrest you!",
                choices=[DialogueChoice(text="(leave quickly)", ends_conversation=True)],
            ),
            "bounty": DialogueNode(
                id="bounty",
                speaker_text="Check the bounty board in the square. We've got bandits, wolves, and worse.",
                choices=[DialogueChoice(text="Thanks.", next_node="pass")],
            ),
        },
    ),
]
