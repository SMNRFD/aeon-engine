"""Personality traits and decision biasing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from engine.entities.components import Personality as PersonalityComponent


class PersonalityTrait(IntEnum):
    OPENNESS = 0
    CONSCIENTIOUSNESS = 1
    EXTRAVERSION = 2
    AGREEABLENESS = 3
    NEUROTICISM = 4
    COURAGE = 5
    GREED = 6
    CURIOSITY = 7


class PersonalitySystem:
    """Reads personality data and produces decision biases."""

    @staticmethod
    def get(comp: PersonalityComponent, trait: PersonalityTrait) -> float:
        return {
            PersonalityTrait.OPENNESS: comp.openness,
            PersonalityTrait.CONSCIENTIOUSNESS: comp.conscientiousness,
            PersonalityTrait.EXTRAVERSION: comp.extraversion,
            PersonalityTrait.AGREEABLENESS: comp.agreeableness,
            PersonalityTrait.NEUROTICISM: comp.neuroticism,
            PersonalityTrait.COURAGE: comp.courage,
            PersonalityTrait.GREED: comp.greed,
            PersonalityTrait.CURIOSITY: comp.curiosity,
        }[trait]

    @staticmethod
    def aggression(comp: PersonalityComponent) -> float:
        """Likelihood to choose violence (0..1)."""
        return max(0.0, min(1.0,
            0.5 - comp.agreeableness * 0.3 + comp.neuroticism * 0.2 - comp.conscientiousness * 0.1))

    @staticmethod
    def bravery(comp: PersonalityComponent) -> float:
        return max(0.0, min(1.0, 0.5 + comp.courage * 0.5 - comp.neuroticism * 0.2))

    @staticmethod
    def greed(comp: PersonalityComponent) -> float:
        return max(0.0, min(1.0, 0.5 + comp.greed * 0.5))

    @staticmethod
    def sociability(comp: PersonalityComponent) -> float:
        return max(0.0, min(1.0, 0.5 + comp.extraversion * 0.5 + comp.agreeableness * 0.2))

    @staticmethod
    def curiosity(comp: PersonalityComponent) -> float:
        return max(0.0, min(1.0, 0.5 + comp.curiosity * 0.4 + comp.openness * 0.2))

    @staticmethod
    def work_ethic(comp: PersonalityComponent) -> float:
        return max(0.0, min(1.0, 0.5 + comp.conscientiousness * 0.5))

    @staticmethod
    def risk_tolerance(comp: PersonalityComponent) -> float:
        return max(0.0, min(1.0,
            0.5 + comp.courage * 0.3 - comp.neuroticism * 0.3 + comp.openness * 0.1))

    @staticmethod
    def trust(comp: PersonalityComponent) -> float:
        return max(0.0, min(1.0, 0.5 + comp.agreeableness * 0.4 - comp.neuroticism * 0.2))

    @staticmethod
    def description(comp: PersonalityComponent) -> str:
        """A short human-readable summary."""
        parts = []
        if comp.openness > 0.4:
            parts.append("imaginative")
        elif comp.openness < -0.4:
            parts.append("conventional")
        if comp.conscientiousness > 0.4:
            parts.append("dutiful")
        elif comp.conscientiousness < -0.4:
            parts.append("carefree")
        if comp.extraversion > 0.4:
            parts.append("outgoing")
        elif comp.extraversion < -0.4:
            parts.append("reserved")
        if comp.agreeableness > 0.4:
            parts.append("kind")
        elif comp.agreeableness < -0.4:
            parts.append("brusque")
        if comp.neuroticism > 0.4:
            parts.append("anxious")
        elif comp.neuroticism < -0.4:
            parts.append("calm")
        if comp.courage > 0.4:
            parts.append("brave")
        elif comp.courage < -0.4:
            parts.append("timid")
        if comp.greed > 0.4:
            parts.append("avaricious")
        if comp.curiosity > 0.4:
            parts.append("curious")
        return ", ".join(parts) if parts else "unremarkable"
