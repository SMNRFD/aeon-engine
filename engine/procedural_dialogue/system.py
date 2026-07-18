"""Procedural dialogue generation.

Generates dynamic NPC dialogue based on:
* NPC personality (Big Five traits)
* NPC mood (current emotional state)
* Relationship with player
* Recent events (memory)
* Time of day / weather
* NPC occupation and social class
* Faction membership and reputation

Templates are filled with context-specific content.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional

from engine.utils.rng import RNG


@dataclass
class NPCContext:
    """Context for procedural dialogue generation."""

    npc_name: str = "stranger"
    npc_occupation: str = "commoner"
    npc_social_class: str = "commoner"  # peasant, commoner, merchant, noble, royal
    npc_faction: str = ""
    npc_personality: dict[str, float] = field(default_factory=dict)
    # openness, conscientiousness, extraversion, agreeableness, neuroticism
    npc_mood: str = "neutral"  # happy, sad, angry, fearful, neutral
    npc_age: int = 30
    npc_gender: str = "neutral"
    relationship_to_player: float = 0.0  # -1..1
    player_name: str = "traveler"
    player_reputation: float = 0.0
    recent_event: str = ""
    time_of_day: str = "day"  # dawn, day, dusk, night
    weather: str = "clear"
    season: str = "spring"
    location_type: str = "town"  # town, wilderness, dungeon, shop
    topics_discussed: list[str] = field(default_factory=list)
    knowledge: dict[str, float] = field(default_factory=dict)


@dataclass
class GeneratedLine:
    """A single generated line of dialogue."""

    speaker: str
    text: str
    emotion: str = "neutral"
    is_greeting: bool = False
    is_farewell: bool = False
    is_question: bool = False
    topic: str = ""
    follow_up_options: list[str] = field(default_factory=list)


@dataclass
class DialogueTemplate:
    """A template for procedural dialogue."""

    template_id: str
    template: str  # with placeholders like {npc_name}, {player_name}
    context_requirements: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    tags: list[str] = field(default_factory=list)

    def render(self, context: NPCContext) -> str:
        """Render the template with context values."""
        try:
            return self.template.format(**self._build_format_args(context))
        except (KeyError, IndexError, ValueError):
            return self.template

    def _build_format_args(self, context: NPCContext) -> dict[str, Any]:
        return {
            "npc_name": context.npc_name,
            "player_name": context.player_name,
            "occupation": context.npc_occupation,
            "social_class": context.npc_social_class,
            "faction": context.npc_faction,
            "mood": context.npc_mood,
            "time_of_day": context.time_of_day,
            "weather": context.weather,
            "season": context.season,
            "location": context.location_type,
            "recent_event": context.recent_event or "the weather",
            "age": context.npc_age,
            "gender": context.npc_gender,
        }


class ProceduralDialogueEngine:
    """Generates procedural dialogue."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._templates: dict[str, list[DialogueTemplate]] = {}
        self._init_defaults()

    def _init_defaults(self) -> None:
        for category, templates in DEFAULT_TEMPLATES.items():
            self._templates[category] = templates

    def generate_greeting(self, context: NPCContext) -> GeneratedLine:
        """Generate a greeting line."""
        # Choose based on relationship
        if context.relationship_to_player > 0.5:
            category = "greeting_friendly"
        elif context.relationship_to_player < -0.5:
            category = "greeting_hostile"
        else:
            category = "greeting_neutral"
        templates = self._templates.get(category, self._templates["greeting_neutral"])
        template = self.rng.choice(templates)
        return GeneratedLine(
            speaker=context.npc_name,
            text=template.render(context),
            emotion=context.npc_mood,
            is_greeting=True,
            topic="greeting",
        )

    def generate_farewell(self, context: NPCContext) -> GeneratedLine:
        """Generate a farewell line."""
        if context.relationship_to_player > 0.5:
            category = "farewell_friendly"
        elif context.relationship_to_player < -0.5:
            category = "farewell_hostile"
        else:
            category = "farewell_neutral"
        templates = self._templates.get(category, self._templates["farewell_neutral"])
        template = self.rng.choice(templates)
        return GeneratedLine(
            speaker=context.npc_name,
            text=template.render(context),
            emotion=context.npc_mood,
            is_farewell=True,
            topic="farewell",
        )

    def generate_topic_line(self, topic: str,
                             context: NPCContext) -> GeneratedLine:
        """Generate a line about a specific topic."""
        category = f"topic_{topic}"
        templates = self._templates.get(category)
        if not templates:
            # Generic fallback
            templates = self._templates.get("topic_generic",
                                             self._templates["greeting_neutral"])
        template = self.rng.choice(templates)
        text = template.render(context)
        # Generate follow-up options
        follow_ups = self._generate_follow_ups(topic, context)
        return GeneratedLine(
            speaker=context.npc_name,
            text=text,
            emotion=context.npc_mood,
            topic=topic,
            follow_up_options=follow_ups,
        )

    def _generate_follow_ups(self, topic: str,
                              context: NPCContext) -> list[str]:
        """Generate follow-up options for the player."""
        follow_ups: list[str] = []
        # Standard options
        follow_ups.append("Tell me more.")
        follow_ups.append("That's interesting.")
        # Topic-specific
        if topic == "rumors":
            follow_ups.append("Have you heard any other rumors?")
            follow_ups.append("Where did you hear that?")
        elif topic == "weather":
            follow_ups.append("Will it storm?")
            follow_ups.append("I love this weather.")
        elif topic == "trade":
            follow_ups.append("What do you have for sale?")
            follow_ups.append("I'm looking for something specific.")
        elif topic == "quests":
            follow_ups.append("I can help with that.")
            follow_ups.append("What's the reward?")
        # Mood-based
        if context.npc_mood == "sad":
            follow_ups.append("Are you alright?")
        elif context.npc_mood == "angry":
            follow_ups.append("Calm down.")
        # End conversation
        follow_ups.append("Goodbye.")
        return follow_ups[:4]  # limit to 4 options

    def generate_response_to_question(self, question: str,
                                        context: NPCContext) -> GeneratedLine:
        """Generate a response to a player question."""
        # Very simple keyword-based response
        question_lower = question.lower()
        if "name" in question_lower:
            return GeneratedLine(
                speaker=context.npc_name,
                text=f"I am {context.npc_name}, a {context.npc_occupation}.",
                topic="identity",
            )
        if "weather" in question_lower:
            return self.generate_topic_line("weather", context)
        if "rumor" in question_lower or "news" in question_lower:
            return self.generate_topic_line("rumors", context)
        if "quest" in question_lower or "work" in question_lower:
            return self.generate_topic_line("quests", context)
        if "trade" in question_lower or "buy" in question_lower:
            return self.generate_topic_line("trade", context)
        # Default
        templates = self._templates.get("response_unknown",
                                         self._templates["greeting_neutral"])
        template = self.rng.choice(templates)
        return GeneratedLine(
            speaker=context.npc_name,
            text=template.render(context),
            topic="unknown",
        )

    def add_template(self, category: str, template: DialogueTemplate) -> None:
        self._templates.setdefault(category, []).append(template)


# ---------- Default templates ----------

DEFAULT_TEMPLATES: dict[str, list[DialogueTemplate]] = {
    "greeting_neutral": [
        DialogueTemplate("gn1", "Hello, {player_name}. What brings you here?", weight=1.0),
        DialogueTemplate("gn2", "Good {time_of_day}, traveler.", weight=1.0),
        DialogueTemplate("gn3", "Hail, {player_name}. Lovely {weather} we're having.", weight=0.5),
        DialogueTemplate("gn4", "Ah, a new face. Welcome to our {location}.", weight=0.8),
        DialogueTemplate("gn5", "Greetings. I am {npc_name}, the {occupation}.", weight=0.9),
    ],
    "greeting_friendly": [
        DialogueTemplate("gf1", "{player_name}! It's good to see you again!", weight=1.0),
        DialogueTemplate("gf2", "My friend {player_name}! How have you been?", weight=1.0),
        DialogueTemplate("gf3", "Welcome back, {player_name}! Come in, come in.", weight=0.9),
        DialogueTemplate("gf4", "Ah, {player_name}! Just the person I wanted to see.", weight=0.7),
    ],
    "greeting_hostile": [
        DialogueTemplate("gh1", "You. What do you want?", weight=1.0),
        DialogueTemplate("gh2", "{player_name}. I should have known.", weight=0.8),
        DialogueTemplate("gh3", "Get out. You're not welcome here.", weight=0.7),
        DialogueTemplate("gh4", "Hmph. You again.", weight=0.9),
    ],
    "farewell_neutral": [
        DialogueTemplate("fn1", "Farewell, {player_name}.", weight=1.0),
        DialogueTemplate("fn2", "Safe travels.", weight=1.0),
        DialogueTemplate("fn3", "Goodbye, then.", weight=0.9),
        DialogueTemplate("fn4", "May your path be clear.", weight=0.7),
    ],
    "farewell_friendly": [
        DialogueTemplate("ff1", "Take care, {player_name}! Come back soon!", weight=1.0),
        DialogueTemplate("ff2", "Until we meet again, my friend.", weight=0.9),
        DialogueTemplate("ff3", "Safe travels, {player_name}. I'll be here.", weight=0.8),
    ],
    "farewell_hostile": [
        DialogueTemplate("fh1", "Good. Leave.", weight=1.0),
        DialogueTemplate("fh2", "Don't come back.", weight=0.9),
        DialogueTemplate("fh3", "And don't let the door hit you.", weight=0.7),
    ],
    "topic_weather": [
        DialogueTemplate("tw1", "The {weather} is typical for {season}, I suppose.", weight=1.0),
        DialogueTemplate("tw2", "I've seen worse {weather} in my time.", weight=0.8),
        DialogueTemplate("tw3", "This {weather} is good for the crops.", weight=0.7),
        DialogueTemplate("tw4", "Strange {weather} for {season}, isn't it?", weight=0.6),
    ],
    "topic_rumors": [
        DialogueTemplate("tr1", "I heard there's been trouble at the old ruins.", weight=1.0),
        DialogueTemplate("tr2", "They say a merchant was robbed on the road recently.", weight=0.9),
        DialogueTemplate("tr3", "Strange lights in the sky last night, they say.", weight=0.7),
        DialogueTemplate("tr4", "The {faction} has been quiet lately. Too quiet.", weight=0.6),
        DialogueTemplate("tr5", "Word is the {occupation}'s guild is hiring.", weight=0.8),
    ],
    "topic_trade": [
        DialogueTemplate("tt1", "I have some fine wares. Care to browse?", weight=1.0),
        DialogueTemplate("tt2", "Business has been slow lately, but I've got goods.", weight=0.8),
        DialogueTemplate("tt3", "For you, {player_name}, special prices.", weight=0.7),
        DialogueTemplate("tt4", "The {weather} is bad for trade, but I'm open.", weight=0.6),
    ],
    "topic_quests": [
        DialogueTemplate("tq1", "Actually, there's something you could help with...", weight=1.0),
        DialogueTemplate("tq2", "We've been having a problem with bandits.", weight=0.9),
        DialogueTemplate("tq3", "I lost something precious. Could you find it?", weight=0.7),
        DialogueTemplate("tq4", "The mayor is looking for someone of your skills.", weight=0.8),
    ],
    "topic_generic": [
        DialogueTemplate("tg1", "Hmm, I'm not sure about that.", weight=1.0),
        DialogueTemplate("tg2", "That's an interesting question.", weight=0.9),
        DialogueTemplate("tg3", "I hadn't thought about it that way.", weight=0.7),
        DialogueTemplate("tg4", "You'd have to ask someone else about that.", weight=0.6),
    ],
    "response_unknown": [
        DialogueTemplate("ru1", "I don't know much about that, {player_name}.", weight=1.0),
        DialogueTemplate("ru2", "Hmm. That's not really my area.", weight=0.9),
        DialogueTemplate("ru3", "You'd better ask someone else.", weight=0.7),
        DialogueTemplate("ru4", "I'm just a {occupation}, I wouldn't know.", weight=0.8),
    ],
}
