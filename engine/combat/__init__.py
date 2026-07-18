"""Combat subsystem — turn-based resolution, damage, status effects."""

from engine.combat.system import CombatSystem, CombatResult, AttackResult
from engine.combat.damage import DamageType, Damage, DamageCalculator
from engine.combat.effects import StatusEffectSystem, StatusEffectInstance
