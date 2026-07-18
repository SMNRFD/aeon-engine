"""Damage types, instances, and the damage calculator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.entities.components import Stats


class DamageType(Enum):
    SLASHING = "slashing"
    PIERCING = "piercing"
    BLUDGEONING = "bludgeoning"
    FIRE = "fire"
    COLD = "cold"
    LIGHTNING = "lightning"
    POISON = "poison"
    ACID = "acid"
    HOLY = "holy"
    NECROTIC = "necrotic"
    PSYCHIC = "psychic"
    TRUE = "true"  # bypasses all resistances


@dataclass
class Damage:
    """A damage instance."""

    amount: float
    type: DamageType
    source: Optional[str] = None
    armor_pen: float = 0.0          # 0..1 — fraction of armor to ignore
    crit: bool = False
    crit_multiplier: float = 2.0
    knockback: float = 0.0

    def apply_multiplier(self, mult: float) -> "Damage":
        return Damage(
            amount=self.amount * mult,
            type=self.type,
            source=self.source,
            armor_pen=self.armor_pen,
            crit=self.crit,
            crit_multiplier=self.crit_multiplier,
            knockback=self.knockback,
        )


class DamageCalculator:
    """Computes the final damage from a raw damage instance."""

    @staticmethod
    def compute(damage: Damage, target_stats: Optional[Stats],
                target_armor: float = 0.0,
                target_resistances: Optional[dict[DamageType, float]] = None,
                target_vulnerabilities: Optional[dict[DamageType, float]] = None,
                ) -> float:
        """Compute the effective damage after armor, resistance, and vulnerabilities."""
        amount = damage.amount

        # Apply resistance / vulnerability
        resist = 0.0
        if target_resistances and damage.type in target_resistances:
            resist = target_resistances[damage.type]
        vuln = 0.0
        if target_vulnerabilities and damage.type in target_vulnerabilities:
            vuln = target_vulnerabilities[damage.type]
        amount *= (1.0 - resist + vuln)

        # Armor applies to physical damage only
        if damage.type in (DamageType.SLASHING, DamageType.PIERCING,
                           DamageType.BLUDGEONING):
            effective_armor = max(0.0, target_armor * (1.0 - damage.armor_pen))
            # Armor reduces damage by a percentage.
            amount *= max(0.05, 1.0 - effective_armor / (effective_armor + 50.0))

        # True damage bypasses everything.
        if damage.type == DamageType.TRUE:
            return damage.amount

        # Stats-based reduction (endurance gives flat reduction)
        if target_stats:
            amount = max(1.0, amount - target_stats.endurance * 0.1)

        return max(0.0, amount)
