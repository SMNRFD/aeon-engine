"""Magic schools — schools of magic and their characteristics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


@dataclass
class MagicSchool:
    """A school of magic."""

    id: str
    name: str
    description: str
    color: int
    opposing_school: Optional[str] = None
    skill_id: str = ""
    tags: list[str] = field(default_factory=list)


class SchoolLibrary:
    _schools: ClassVar[dict[str, MagicSchool]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, school: MagicSchool) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._schools[school.id] = school

    @classmethod
    def get(cls, school_id: str) -> MagicSchool | None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._schools.get(school_id)

    @classmethod
    def all(cls) -> list[MagicSchool]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._schools.values())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for s in DEFAULT_SCHOOLS:
            cls._schools[s.id] = s
        cls._defaults_loaded = True


DEFAULT_SCHOOLS: list[MagicSchool] = [
    MagicSchool("evocation", "Evocation",
                "Energy and elemental magic — fireballs, lightning, frost.",
                196, opposing_school="abjuration", skill_id="evocation",
                tags=["destructive", "elemental"]),
    MagicSchool("conjuration", "Conjuration",
                "Summoning creatures, objects, and energies from elsewhere.",
                33, opposing_school="divination", skill_id="conjuration",
                tags=["summoning"]),
    MagicSchool("enchantment", "Enchantment",
                "Mind-affecting magic — charms, compulsions, glamour.",
                165, opposing_school="necromancy", skill_id="enchantment",
                tags=["mental"]),
    MagicSchool("necromancy", "Necromancy",
                "Death magic — raising undead, draining life, decay.",
                90, opposing_school="enchantment", skill_id="necromancy",
                tags=["forbidden", "death"]),
    MagicSchool("abjuration", "Abjuration",
                "Protective magic — wards, banishment, dispelling.",
                75, opposing_school="evocation", skill_id="abjuration",
                tags=["protective"]),
    MagicSchool("transmutation", "Transmutation",
                "Changing matter — shape, form, properties.",
                215, opposing_school="divination", skill_id="transmutation",
                tags=["alteration"]),
    MagicSchool("divination", "Divination",
                "Knowledge and seeing — clairvoyance, prophecy.",
                75, opposing_school="conjuration", skill_id="divination",
                tags=["knowledge"]),
    MagicSchool("illusion", "Illusion",
                "False sensations — light, sound, phantom images.",
                165, opposing_school="abjuration", skill_id="divination",
                tags=["deception"]),
]
