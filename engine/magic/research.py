"""Spell research — procedural spell creation and discovery."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from engine.core.ecs import Entity
from engine.magic.schools import SchoolLibrary
from engine.magic.spells import Spell, SpellEffect, SpellLibrary, SpellTarget
from engine.combat.damage import DamageType
from engine.utils.rng import RNG


@dataclass
class ResearchProject:
    """An ongoing spell research project."""

    id: str
    name: str
    school_id: str
    researcher_id: int
    progress: float = 0.0       # 0..1
    difficulty: float = 1.0
    required_progress: float = 100.0
    xp_per_tick: float = 0.5
    description: str = ""
    discovered_effects: list[SpellEffect] = field(default_factory=list)

    def advance(self, skill_level: int, dt: float) -> None:
        gain = skill_level * self.xp_per_tick * dt / self.difficulty
        self.progress += gain

    @property
    def is_complete(self) -> bool:
        return self.progress >= self.required_progress


class SpellResearcher:
    """Manages spell research and procedural spell generation."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._projects: dict[str, ResearchProject] = {}

    def start_project(self, name: str, school_id: str, researcher: Entity,
                      difficulty: float = 1.0) -> ResearchProject:
        project_id = f"{researcher.id}:{name}"
        project = ResearchProject(
            id=project_id, name=name, school_id=school_id,
            researcher_id=researcher.id, difficulty=difficulty,
            required_progress=100.0 * difficulty,
        )
        self._projects[project_id] = project
        return project

    def update(self, researcher_skill: dict[int, dict[str, int]],
               dt: float) -> list[Spell]:
        """Advance all research projects and return any spells completed."""
        completed: list[Spell] = []
        to_remove: list[str] = []
        for pid, project in self._projects.items():
            skills = researcher_skill.get(project.researcher_id, {})
            level = skills.get(SchoolLibrary.get(project.school_id).skill_id
                               if SchoolLibrary.get(project.school_id) else "", 0)
            project.advance(level, dt)
            if project.is_complete:
                spell = self._finalise_project(project)
                if spell is not None:
                    completed.append(spell)
                to_remove.append(pid)
        for pid in to_remove:
            del self._projects[pid]
        return completed

    def _finalise_project(self, project: ResearchProject) -> Optional[Spell]:
        school = SchoolLibrary.get(project.school_id)
        if school is None:
            return None
        # Generate a procedural spell
        effects = self._generate_effects(school.id, project.difficulty)
        spell = Spell(
            id=f"custom_{project.id}",
            name=project.name,
            school_id=school.id,
            description=f"A research-discovered spell of {school.name}.",
            mana_cost=int(20 * project.difficulty + self.rng.randint(0, 30)),
            cast_time=0.5 + self.rng.uniform(0, 2.5),
            cooldown=self.rng.uniform(0, 5),
            target=self.rng.choice([SpellTarget.ENEMY, SpellTarget.AREA,
                                    SpellTarget.SELF, SpellTarget.ALLY]),
            range_=self.rng.uniform(5, 40),
            level=int(project.difficulty * 10),
            skill_id=school.skill_id,
            effects=effects,
            tags=["researched"],
        )
        SpellLibrary.register(spell)
        return spell

    def _generate_effects(self, school_id: str, difficulty: float) -> list[SpellEffect]:
        effects: list[SpellEffect] = []
        if school_id == "evocation":
            dtype = self.rng.choice([DamageType.FIRE, DamageType.COLD,
                                     DamageType.LIGHTNING, DamageType.TRUE])
            effects.append(SpellEffect(
                kind="damage",
                magnitude=20 * difficulty * self.rng.uniform(0.8, 1.5),
                damage_type=dtype,
                area_radius=self.rng.choice([0, 0, 3, 5]),
            ))
        elif school_id == "abjuration":
            effects.append(SpellEffect(
                kind="heal", magnitude=15 * difficulty * self.rng.uniform(0.8, 1.5),
            ))
            if self.rng.chance(0.5):
                effects.append(SpellEffect(
                    kind="buff", duration=30, status_effect="blessed",
                ))
        elif school_id == "necromancy":
            effects.append(SpellEffect(
                kind="damage", magnitude=15 * difficulty,
                damage_type=DamageType.NECROTIC,
            ))
            if self.rng.chance(0.5):
                effects.append(SpellEffect(
                    kind="debuff", duration=5, status_effect="weakened",
                ))
        elif school_id == "enchantment":
            effects.append(SpellEffect(
                kind="debuff", duration=10,
                status_effect=self.rng.choice(["fear", "stunned", "weakened"]),
            ))
        elif school_id == "conjuration":
            effects.append(SpellEffect(
                kind="summon", duration=600,
                data={"creature": self.rng.choice(["familiar", "spirit", "elemental"])},
            ))
        else:
            effects.append(SpellEffect(
                kind="buff", duration=30, status_effect="blessed",
                magnitude=2 * difficulty,
            ))
        return effects

    def projects(self) -> list[ResearchProject]:
        return list(self._projects.values())
