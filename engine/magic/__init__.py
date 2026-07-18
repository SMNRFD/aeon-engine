"""Magic system — spell schools, procedural spell creation, casting."""

from engine.magic.schools import MagicSchool, SchoolLibrary, DEFAULT_SCHOOLS
from engine.magic.spells import (
    Spell, SpellEffect, SpellTarget, SpellCastResult, SpellLibrary,
    SpellCaster, DEFAULT_SPELLS,
)
from engine.magic.research import SpellResearcher, ResearchProject
