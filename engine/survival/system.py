"""Survival — disease, exposure, poisoning, mental health."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Health, Needs, Stats
from engine.weather.system import Weather, WeatherType
from engine.utils.rng import RNG


class ExposureLevel(IntEnum):
    COMFORTABLE = 0
    MILD = 1
    UNCOMFORTABLE = 2
    HARSH = 3
    EXTREME = 4


@dataclass
class Disease:
    """A disease definition."""

    id: str
    name: str
    description: str
    base_duration: float        # seconds
    severity: float             # 1..10
    contagious: bool = False
    contagious_radius: float = 0.0
    symptoms: list[str] = field(default_factory=list)
    stat_modifiers: dict[str, float] = field(default_factory=dict)
    damage_per_tick: float = 0.0
    cure_item: Optional[str] = None
    cure_skill: Optional[str] = None
    cure_skill_level: int = 0


class DiseaseLibrary:
    _diseases: ClassVar[dict[str, Disease]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, d: Disease) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._diseases[d.id] = d

    @classmethod
    def get(cls, disease_id: str) -> Optional[Disease]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._diseases.get(disease_id)

    @classmethod
    def all(cls) -> list[Disease]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._diseases.values())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for d in DEFAULT_DISEASES:
            cls._diseases[d.id] = d
        cls._defaults_loaded = True


@dataclass
class DiseaseInstance:
    disease_id: str
    duration: float
    severity: float
    infected_at: float = 0.0
    source: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "disease_id": self.disease_id, "duration": self.duration,
            "severity": self.severity, "infected_at": self.infected_at,
            "source": self.source,
        }


class SurvivalSystem:
    """Resolves survival mechanics: exposure, disease, poison, sanity."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()
        self._diseases: dict[int, list[DiseaseInstance]] = {}
        self._poisoning: dict[int, float] = {}  # entity_id -> magnitude

    def update(self, world: World, dt: float, weather: Optional[Weather] = None) -> None:
        for entity, (needs, health, stats) in world.view(Needs, Health, Stats):
            self._update_exposure(entity, needs, stats, health, weather, dt)
            self._update_diseases(entity, health, stats, dt)
            self._update_poisoning(entity, health, dt)
            self._update_mental(entity, needs, dt)

    # ---------- exposure ----------

    def _update_exposure(self, entity: Entity, needs: Needs, stats: Stats,
                         health: Health, weather: Optional[Weather], dt: float) -> None:
        if weather is None:
            return
        # Compute comfort delta
        ambient = weather.temperature
        # Wind chill
        effective = ambient - (weather.wind_speed * 0.05)
        # Wetness makes cold worse
        if weather.type in (WeatherType.RAIN, WeatherType.HEAVY_RAIN,
                            WeatherType.THUNDERSTORM, WeatherType.SNOW,
                            WeatherType.BLIZZARD):
            effective -= 3.0
        # Entity warmth drifts toward effective temperature
        delta = effective - needs.warmth
        # Endurance slows the change
        rate = 0.05 * (1.0 - min(0.7, stats.endurance / 30.0))
        needs.warmth += delta * rate * dt
        # Damage from extreme warmth
        if needs.warmth < 25:
            exposure = ExposureLevel.EXTREME
            damage = (25 - needs.warmth) * 0.05 * dt
            health.current = max(0, int(health.current - damage))
            needs.fatigue += damage * 0.5
        elif needs.warmth < 32:
            exposure = ExposureLevel.HARSH
            needs.fatigue += 0.1 * dt
        elif needs.warmth > 42:
            exposure = ExposureLevel.HARSH
            damage = (needs.warmth - 42) * 0.04 * dt
            health.current = max(0, int(health.current - damage))
            needs.thirst += damage * 2.0
        else:
            exposure = ExposureLevel.COMFORTABLE

    # ---------- disease ----------

    def infect(self, entity: Entity, disease_id: str,
               severity: Optional[float] = None,
               source: Optional[int] = None,
               current_tick: float = 0.0) -> Optional[DiseaseInstance]:
        d = DiseaseLibrary.get(disease_id)
        if d is None:
            return None
        instance = DiseaseInstance(
            disease_id=disease_id,
            duration=d.base_duration,
            severity=severity or d.severity,
            infected_at=current_tick,
            source=source,
        )
        self._diseases.setdefault(entity.id, []).append(instance)
        return instance

    def _update_diseases(self, entity: Entity, health: Health, stats: Stats,
                         dt: float) -> None:
        instances = self._diseases.get(entity.id, [])
        if not instances:
            return
        remaining: list[DiseaseInstance] = []
        for inst in instances:
            inst.duration -= dt
            disease = DiseaseLibrary.get(inst.disease_id)
            if disease is None:
                continue
            if inst.duration <= 0:
                continue
            # Apply damage
            if disease.damage_per_tick > 0:
                dmg = disease.damage_per_tick * inst.severity * dt
                health.current = max(0, int(health.current - dmg))
            # Recovery chance scales with endurance
            if self.rng.chance(stats.endurance * 0.0001 * dt):
                inst.duration = min(inst.duration, 1.0)
            remaining.append(inst)
        self._diseases[entity.id] = remaining

    def diseases_of(self, entity: Entity) -> list[DiseaseInstance]:
        return list(self._diseases.get(entity.id, []))

    # ---------- poison ----------

    def poison(self, entity: Entity, magnitude: float) -> None:
        self._poisoning[entity.id] = self._poisoning.get(entity.id, 0.0) + magnitude

    def _update_poisoning(self, entity: Entity, health: Health, dt: float) -> None:
        mag = self._poisoning.get(entity.id, 0.0)
        if mag <= 0:
            return
        # Damage per second
        damage = mag * 0.1 * dt
        health.current = max(0, int(health.current - damage))
        # Body fights off poison slowly
        self._poisoning[entity.id] = max(0.0, mag - 0.01 * dt)

    # ---------- mental health ----------

    def _update_mental(self, entity: Entity, needs: Needs, dt: float) -> None:
        # Low morale drags sanity down
        if needs.morale < 30:
            needs.sanity = max(0.0, needs.sanity - 0.005 * dt)
        # Critical sanity causes morale drop
        if needs.sanity < 20:
            needs.morale = max(0.0, needs.morale - 0.01 * dt)


# ---------- Default diseases ----------

DEFAULT_DISEASES: list[Disease] = [
    Disease("common_cold", "Common Cold", "A mild respiratory infection.",
            base_duration=86400, severity=2.0,
            symptoms=["sneezing", "cough", "fatigue"],
            stat_modifiers={"agility": -2, "endurance": -2},
            damage_per_tick=0.05,
            cure_item="health_potion", cure_skill="first_aid", cure_skill_level=1),
    Disease("influenza", "Influenza", "A serious viral infection.",
            base_duration=172800, severity=4.0, contagious=True, contagious_radius=2.0,
            symptoms=["fever", "chills", "weakness"],
            stat_modifiers={"strength": -3, "agility": -3, "endurance": -4},
            damage_per_tick=0.2,
            cure_item="health_potion", cure_skill="medicine", cure_skill_level=3),
    Disease("dysentery", "Dysentery", "Painful intestinal infection.",
            base_duration=86400, severity=3.5, contagious=True, contagious_radius=1.5,
            symptoms=["diarrhea", "fever", "dehydration"],
            stat_modifiers={"endurance": -4, "strength": -2},
            damage_per_tick=0.15,
            cure_skill="medicine", cure_skill_level=2),
    Disease("tetanus", "Tetanus", "Lockjaw from infected wounds.",
            base_duration=259200, severity=6.0,
            symptoms=["muscle_spasms", "lockjaw", "fever"],
            stat_modifiers={"agility": -5, "strength": -3},
            damage_per_tick=0.3,
            cure_skill="medicine", cure_skill_level=5),
    Disease("plague", "The Plague", "A deadly bacterial infection.",
            base_duration=432000, severity=9.0, contagious=True, contagious_radius=3.0,
            symptoms=["buboes", "fever", "coughing_blood"],
            stat_modifiers={"strength": -5, "endurance": -5, "agility": -3},
            damage_per_tick=0.6,
            cure_skill="medicine", cure_skill_level=8),
    Disease("red_death", "Red Death", "A mysterious wasting disease.",
            base_duration=604800, severity=10.0, contagious=True, contagious_radius=5.0,
            symptoms=["pale_skin", "coughing_blood", "madness"],
            stat_modifiers={"strength": -7, "endurance": -7, "willpower": -5},
            damage_per_tick=0.8,
            cure_skill="medicine", cure_skill_level=10),
    Disease("frostbite", "Frostbite", "Tissue damage from extreme cold.",
            base_duration=86400, severity=4.0,
            symptoms=["numbness", "blackened_skin"],
            stat_modifiers={"agility": -4},
            damage_per_tick=0.1,
            cure_skill="first_aid", cure_skill_level=3),
    Disease("heatstroke", "Heatstroke", "Overheating illness.",
            base_duration=43200, severity=5.0,
            symptoms=["confusion", "hot_skin", "unconsciousness"],
            stat_modifiers={"intelligence": -3, "agility": -3},
            damage_per_tick=0.2,
            cure_skill="first_aid", cure_skill_level=2),
]
