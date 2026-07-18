"""Artifact system — unique legendary items.

Artifacts are one-of-a-kind magical items of great power:
* Each artifact has a unique name, history, and set of powers
* Artifacts can level up with use
* Some artifacts have sentience and can communicate with their wielder
* Some artifacts carry curses alongside their power
* Artifacts can be destroyed only by specific means
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


class ArtifactRarity(IntEnum):
    UNCOMMON = 0
    RARE = 1
    EPIC = 2
    LEGENDARY = 3
    MYTHIC = 4
    DIVINE = 5


@dataclass
class Artifact:
    """A unique artifact."""

    artifact_id: str
    name: str
    description: str
    rarity: ArtifactRarity = ArtifactRarity.LEGENDARY
    item_archetype: str = "longsword"  # base item type
    material: str = "mithril"
    level: int = 1
    max_level: int = 10
    xp: float = 0.0
    xp_to_next: float = 100.0
    is_sentient: bool = False
    sentience_level: float = 0.0  # 0..1
    personality: str = ""  # for sentient artifacts
    is_cursed: bool = False
    curse_description: str = ""
    curse_effect: str = ""
    destruction_method: str = "Only the fires of Mount Doom can destroy it."
    is_destroyed: bool = False
    owner_id: Optional[int] = None
    previous_owners: list[int] = field(default_factory=list)
    location: Optional[tuple[int, int]] = None
    powers: list[dict[str, Any]] = field(default_factory=list)
    # powers: [{"name": "fireball", "uses_per_day": 3, "mana_cost": 20}, ...]
    passive_effects: dict[str, float] = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    discovered_at_tick: float = 0.0
    is_known_to_player: bool = False
    color: int = 215
    glyph: str = "†"

    def add_xp(self, amount: float) -> int:
        """Add XP to the artifact. Returns the new level."""
        if self.level >= self.max_level:
            return self.level
        self.xp += amount
        while self.level < self.max_level and self.xp >= self.xp_to_next:
            self.xp -= self.xp_to_next
            self.level += 1
            self.xp_to_next = int(self.xp_to_next * 1.5)
        return self.level

    def add_owner(self, entity_id: int) -> None:
        if self.owner_id is not None and self.owner_id != entity_id:
            self.previous_owners.append(self.owner_id)
        self.owner_id = entity_id

    def add_history(self, entry: str) -> None:
        self.history.append(entry)
        if len(self.history) > 100:
            self.history = self.history[-100:]

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["rarity"] = int(self.rarity)
        if self.location:
            d["location"] = list(self.location)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Artifact":
        d = dict(data)
        d["rarity"] = ArtifactRarity(d.get("rarity", 3))
        if d.get("location"):
            d["location"] = tuple(d["location"])
        return cls(**d)


class ArtifactLibrary:
    """Registry of all artifacts in the world."""

    _artifacts: ClassVar[dict[str, Artifact]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, artifact: Artifact) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._artifacts[artifact.artifact_id] = artifact

    @classmethod
    def get(cls, artifact_id: str) -> Optional[Artifact]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._artifacts.get(artifact_id)

    @classmethod
    def all(cls) -> list[Artifact]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._artifacts.values())

    @classmethod
    def by_owner(cls, owner_id: int) -> list[Artifact]:
        return [a for a in cls.all() if a.owner_id == owner_id]

    @classmethod
    def by_rarity(cls, rarity: ArtifactRarity) -> list[Artifact]:
        return [a for a in cls.all() if a.rarity == rarity]

    @classmethod
    def undiscovered(cls) -> list[Artifact]:
        return [a for a in cls.all() if not a.is_known_to_player]

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for a in DEFAULT_ARTIFACTS:
            cls._artifacts[a.artifact_id] = a
        cls._defaults_loaded = True


class ArtifactSystem:
    """Manages artifact state, leveling, and communication."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._cooldowns: dict[str, dict[str, float]] = {}  # artifact_id -> {power_name: cooldown}

    def wield(self, artifact: Artifact, entity_id: int) -> None:
        """An entity wields an artifact."""
        artifact.add_owner(entity_id)
        artifact.add_history(f"Wielded by entity {entity_id}.")

    def unwield(self, artifact: Artifact) -> None:
        """Artifact is set aside."""
        if artifact.owner_id is not None:
            artifact.previous_owners.append(artifact.owner_id)
            artifact.owner_id = None

    def use_power(self, artifact: Artifact, power_name: str,
                  current_tick: float = 0.0) -> tuple[bool, str]:
        """Use one of the artifact's powers."""
        power = next((p for p in artifact.powers if p["name"] == power_name), None)
        if power is None:
            return False, f"{artifact.name} has no power '{power_name}'"
        # Check cooldown
        cooldowns = self._cooldowns.setdefault(artifact.artifact_id, {})
        last_used = cooldowns.get(power_name, -1e18)  # never used = far in the past
        cooldown_duration = power.get("cooldown_seconds", 0)
        if current_tick - last_used < cooldown_duration:
            remaining = cooldown_duration - (current_tick - last_used)
            return False, f"Power on cooldown for {remaining:.1f}s"
        # Check uses
        if "uses_remaining" in power and power["uses_remaining"] <= 0:
            return False, "No uses remaining today"
        if "uses_remaining" in power:
            power["uses_remaining"] -= 1
        cooldowns[power_name] = current_tick
        artifact.add_xp(10)
        return True, f"{artifact.name} unleashes {power_name}!"

    def tick(self, dt: float) -> None:
        """Daily reset of artifact uses."""
        for artifact in ArtifactLibrary.all():
            for power in artifact.powers:
                if "uses_per_day" in power:
                    power["uses_remaining"] = power["uses_per_day"]

    def communicate(self, artifact: Artifact, message: str) -> Optional[str]:
        """If the artifact is sentient, it responds."""
        if not artifact.is_sentient or artifact.sentience_level < 0.3:
            return None
        # Very simple response based on personality
        responses = {
            "wise": f"The artifact considers your words: '{message}'... and whispers ancient counsel.",
            "wrathful": f"The artifact seethes at '{message}'! Its power surges restlessly.",
            "playful": f"The artifact chuckles at '{message}' and tugs at your will.",
            "sorrowful": f"The artifact sighs at '{message}', remembering ages past.",
            "curious": f"The artifact inquires: 'Tell me more about {message}.'",
        }
        personality = artifact.personality or "wise"
        return responses.get(personality, responses["wise"])

    def attempt_destroy(self, artifact: Artifact, method: str) -> tuple[bool, str]:
        """Attempt to destroy an artifact."""
        if method.lower() in artifact.destruction_method.lower():
            artifact.is_destroyed = True
            artifact.add_history(f"Destroyed by {method}.")
            return True, f"{artifact.name} has been destroyed!"
        return False, f"{method} cannot destroy {artifact.name}."

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifacts": {aid: a.to_dict() for aid, a in ArtifactLibrary.all().__class__._artifacts.items()},
            "cooldowns": {
                aid: {pname: cd for pname, cd in cds.items()}
                for aid, cds in self._cooldowns.items()
            },
        }


# ---------- Default artifacts ----------

DEFAULT_ARTIFACTS: list[Artifact] = [
    Artifact(
        artifact_id="sunsteel_blade", name="Sunsteel Blade",
        description="A blade forged from a fallen star, humming with celestial power.",
        rarity=ArtifactRarity.LEGENDARY,
        item_archetype="longsword", material="orichalcum",
        level=1, max_level=10,
        is_sentient=True, sentience_level=0.6,
        personality="wise",
        destruction_method="Only the heart of a dying star can unmake it.",
        powers=[
            {"name": "solar_flare", "uses_per_day": 3, "uses_remaining": 3,
             "cooldown_seconds": 60, "description": "Blinds all enemies in 30m"},
            {"name": "radiant_strike", "uses_per_day": 5, "uses_remaining": 5,
             "cooldown_seconds": 10, "description": "Deals bonus radiant damage"},
        ],
        passive_effects={"damage": 15.0, "fire_damage": 10.0, "crit_chance": 0.1},
        history=["Forged by the smith-god Hephaestus in the heart of a fallen star."],
        color=215, glyph="/",
    ),
    Artifact(
        artifact_id="shadowveil_cloak", name="Shadowveil Cloak",
        description="A cloak woven from shadows, granting the wearer near-invisibility.",
        rarity=ArtifactRarity.EPIC,
        item_archetype="cloak", material="silk",
        level=1, max_level=5,
        is_cursed=True,
        curse_description="The cloak feeds on the wearer's memories.",
        curse_effect="Forgets 1 random memory per day of use",
        destruction_method="Must be burned in sunlight at noon on the summer solstice.",
        powers=[
            {"name": "invisibility", "uses_per_day": 3, "uses_remaining": 3,
             "cooldown_seconds": 30, "description": "Become invisible for 60s"},
        ],
        passive_effects={"stealth_bonus": 0.5, "magic_resist": 0.1},
        history=["Woven by the shadow-weavers of the Underdark."],
        color=90, glyph="(",
    ),
    Artifact(
        artifact_id="orb_of_dragonkind", name="Orb of Dragonkind",
        description="A pulsing orb that grants control over dragons.",
        rarity=ArtifactRarity.MYTHIC,
        item_archetype="amulet", material="crystal",
        level=1, max_level=20,
        is_sentient=True, sentience_level=0.9,
        personality="wrathful",
        is_cursed=True,
        curse_description="The orb dominates its wielder's mind, demanding dragon-subjugation.",
        curse_effect="Charisma reduced by 5; compulsion to seek dragons",
        destruction_method="Can only be shattered by a dragon's breath while in a dragon's hoard.",
        powers=[
            {"name": "dominate_dragon", "uses_per_day": 1, "uses_remaining": 1,
             "cooldown_seconds": 600, "description": "Control a dragon for 1 hour"},
            {"name": "dragon_breath", "uses_per_day": 3, "uses_remaining": 3,
             "cooldown_seconds": 60, "description": "Breathe fire like a dragon"},
        ],
        passive_effects={"magic_power": 0.5, "dragon_affinity": 1.0},
        history=["Created in the First Age by the dragon-god Bahamut."],
        color=196, glyph="o",
    ),
    Artifact(
        artifact_id="staff_of_magi", name="Staff of the Magi",
        description="An ancient staff that amplifies magical power a hundredfold.",
        rarity=ArtifactRarity.LEGENDARY,
        item_archetype="staff", material="ironwood",
        level=1, max_level=15,
        powers=[
            {"name": "amplify_spell", "uses_per_day": 10, "uses_remaining": 10,
             "cooldown_seconds": 5, "description": "Double the power of the next spell"},
            {"name": "mana_burst", "uses_per_day": 2, "uses_remaining": 2,
             "cooldown_seconds": 120, "description": "Restore 100 MP instantly"},
        ],
        passive_effects={"magic_power": 1.0, "mana_regen": 2.0, "max_mana": 50.0},
        history=["Carved from the World Tree by the first archmage."],
        color=165, glyph="|",
    ),
    Artifact(
        artifact_id="crown_of_kings", name="Crown of Kings",
        description="The crown of the ancient kingdom, granting leadership and wisdom.",
        rarity=ArtifactRarity.LEGENDARY,
        item_archetype="helmet", material="gold",
        level=1, max_level=10,
        is_sentient=True, sentience_level=0.5,
        personality="sorrowful",
        powers=[
            {"name": "royal_decree", "uses_per_day": 3, "uses_remaining": 3,
             "cooldown_seconds": 60, "description": "Inspire allies, +20 morale"},
            {"name": "true_judgment", "uses_per_day": 1, "uses_remaining": 1,
             "cooldown_seconds": 600, "description": "See the truth of any statement"},
        ],
        passive_effects={"charisma": 10.0, "leadership": 5.0, "wisdom": 5.0},
        history=["Worn by the first king of Aldor; lost when the kingdom fell."],
        color=220, glyph="*",
    ),
    Artifact(
        artifact_id="voidblade", name="Voidblade",
        description="A dagger that cuts through dimensions, bypassing all armor.",
        rarity=ArtifactRarity.MYTHIC,
        item_archetype="dagger", material="voidstone",
        level=1, max_level=20,
        is_cursed=True,
        curse_description="The blade hungers for souls.",
        curse_effect="Each kill corrupts the wielder slightly",
        destruction_method="Must be cast into the Void at the heart of the multiverse.",
        powers=[
            {"name": "void_step", "uses_per_day": 5, "uses_remaining": 5,
             "cooldown_seconds": 30, "description": "Teleport up to 30m"},
            {"name": "soul_rend", "uses_per_day": 1, "uses_remaining": 1,
             "cooldown_seconds": 300, "description": "Instant kill on weak targets"},
        ],
        passive_effects={"true_damage": 15.0, "lifesteal": 0.3, "crit_chance": 0.2},
        history=["Forged in the Void by an entity that should not be named."],
        color=232, glyph="/",
    ),
    Artifact(
        artifact_id="phoenix_feather", name="Phoenix Feather",
        description="A single feather from a phoenix, granting rebirth.",
        rarity=ArtifactRarity.DIVINE,
        item_archetype="amulet", material="crystal",
        level=1, max_level=5,
        powers=[
            {"name": "rebirth", "uses_per_day": 1, "uses_remaining": 1,
             "cooldown_seconds": 3600, "description": "Resurrect on death"},
            {"name": "fire_burst", "uses_per_day": 5, "uses_remaining": 5,
             "cooldown_seconds": 30, "description": "Explode in flame, damaging enemies"},
        ],
        passive_effects={"fire_resist": 1.0, "hp_regen": 5.0},
        history=["Gifted by the last phoenix before its final rebirth."],
        color=215, glyph="¶",
    ),
]
