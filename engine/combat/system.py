"""Combat resolution — turn-based with equipment and stat lookups."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from engine.core.ecs import Entity, World
from engine.entities.components import (
    AI as AIComponent, Combat as CombatComponent, Health, Position, Stats,
)
from engine.combat.damage import Damage, DamageCalculator, DamageType
from engine.combat.effects import StatusEffectSystem
from engine.utils.rng import RNG


@dataclass
class AttackResult:
    """Result of a single attack."""

    attacker: int
    target: int
    hit: bool
    damage: float
    damage_type: DamageType
    crit: bool
    killed: bool
    status_effects_applied: list[str] = field(default_factory=list)
    message: str = ""


@dataclass
class CombatResult:
    """Result of a complete combat exchange."""

    attacks: list[AttackResult] = field(default_factory=list)
    winner: Optional[int] = None
    fled: bool = False
    rounds: int = 0

    def total_damage_dealt(self) -> float:
        return sum(a.damage for a in self.attacks)


class CombatSystem:
    """Resolves combat between entities."""

    def __init__(self, rng: Optional[RNG] = None,
                 status_system: Optional[StatusEffectSystem] = None,
                 item_registry=None) -> None:
        self.rng = rng or RNG()
        self.status = status_system or StatusEffectSystem()
        self.items = item_registry

    # ---------- attack resolution ----------

    def attack(self, world: World, attacker: Entity, target: Entity,
               weapon_item=None) -> AttackResult:
        """Resolve a single attack from `attacker` to `target`."""
        atk_stats = world.get_component(attacker, Stats)
        atk_combat = world.get_component(attacker, CombatComponent)
        tgt_stats = world.get_component(target, Stats)
        tgt_health = world.get_component(target, Health)
        tgt_combat = world.get_component(target, CombatComponent)

        if not (atk_stats and tgt_stats and tgt_health):
            return AttackResult(
                attacker=attacker.id, target=target.id, hit=False, damage=0.0,
                damage_type=DamageType.TRUE, crit=False, killed=False,
                message="Invalid combatants",
            )

        # Apply status-driven stat modifiers
        atk_mods = self.status.active_stat_modifiers(world, attacker)
        tgt_mods = self.status.active_stat_modifiers(world, target)

        def effective(stats: Stats, mods: dict[str, float]) -> dict[str, float]:
            base = {
                "strength": stats.strength, "agility": stats.agility,
                "endurance": stats.endurance, "perception": stats.perception,
                "luck": stats.luck,
            }
            for k, v in mods.items():
                base[k] = base.get(k, 0) + v
            return base

        atk_eff = effective(atk_stats, atk_mods)
        tgt_eff = effective(tgt_stats, tgt_mods)

        # Compute attack parameters
        base_damage = self._compute_weapon_damage(weapon_item, atk_eff["strength"])
        attack_speed = self._compute_attack_speed(weapon_item, atk_eff["agility"])
        crit_chance = self._compute_crit_chance(weapon_item, atk_eff["perception"],
                                                atk_eff["luck"])
        crit_mult = self._compute_crit_mult(weapon_item)
        armor_pen = self._compute_armor_pen(weapon_item)

        # Compute target defenses
        target_armor = self._compute_armor(world, target)
        target_dodge = max(0, tgt_eff["agility"] + 5)
        target_block = self._compute_block(world, target)

        # Roll to hit
        hit_roll = self.rng.random() * 100
        hit_chance = 75 + atk_eff["perception"] - target_dodge
        if hit_roll > hit_chance:
            return AttackResult(
                attacker=attacker.id, target=target.id, hit=False, damage=0.0,
                damage_type=DamageType.TRUE, crit=False, killed=False,
                message=f"{self._entity_name(world, attacker)} misses {self._entity_name(world, target)}.",
            )

        # Roll block
        if self.rng.chance(target_block / 100.0):
            return AttackResult(
                attacker=attacker.id, target=target.id, hit=True, damage=0.0,
                damage_type=DamageType.TRUE, crit=False, killed=False,
                message=f"{self._entity_name(world, target)} blocks the attack!",
            )

        # Roll crit
        is_crit = self.rng.chance(crit_chance / 100.0)

        # Compute damage
        damage_amount = base_damage
        if is_crit:
            damage_amount *= crit_mult
        # Add small variance
        damage_amount *= self.rng.uniform(0.85, 1.15)

        # Determine damage type
        damage_type = self._weapon_damage_type(weapon_item)

        # Apply armor and resistances
        damage = Damage(
            amount=damage_amount,
            type=damage_type,
            source=f"entity:{attacker.id}",
            armor_pen=armor_pen,
            crit=is_crit,
            crit_multiplier=crit_mult,
        )
        final_damage = DamageCalculator.compute(
            damage, target_stats=tgt_stats, target_armor=target_armor,
        )

        # Apply damage
        if not tgt_health.invulnerable:
            tgt_health.current = max(0, int(tgt_health.current - final_damage))

        # Apply on-hit status effects
        applied: list[str] = []
        if weapon_item:
            for enchant in weapon_item.enchantments:
                ench_type = enchant.get("type", "")
                if ench_type == "fire_damage" and self.rng.chance(0.25):
                    self.status.apply(world, target, "burning",
                                      magnitude=enchant.get("magnitude", 2.0),
                                      source=attacker.id)
                    applied.append("burning")
                elif ench_type == "cold_damage" and self.rng.chance(0.20):
                    self.status.apply(world, target, "frozen", source=attacker.id)
                    applied.append("frozen")
                elif ench_type == "lightning_damage" and self.rng.chance(0.15):
                    self.status.apply(world, target, "stunned", source=attacker.id)
                    applied.append("stunned")
                elif ench_type == "lifesteal":
                    heal = final_damage * enchant.get("magnitude", 0.1)
                    atk_health = world.get_component(attacker, Health)
                    if atk_health:
                        atk_health.current = min(atk_health.maximum,
                                                  int(atk_health.current + heal))
        # Poison from affixes
        if weapon_item and weapon_item.property_value("poison_chance", 0) > 0:
            if self.rng.chance(weapon_item.property_value("poison_chance")):
                self.status.apply(world, target, "poison", source=attacker.id)
                applied.append("poison")

        killed = tgt_health.current <= 0

        # Build message — use entity names instead of IDs
        from engine.entities.components import Identity as IdentityComp
        atk_identity = world.get_component(attacker, IdentityComp)
        tgt_identity = world.get_component(target, IdentityComp)
        atk_name = atk_identity.display_name if atk_identity else f"entity#{attacker.id}"
        tgt_name = tgt_identity.display_name if tgt_identity else f"entity#{target.id}"
        msg = f"{atk_name} hits {tgt_name} for {final_damage:.0f} {damage_type.value} damage"
        if is_crit:
            msg += " (CRITICAL!)"
        if killed:
            msg += f" — {tgt_name} is slain!"

        return AttackResult(
            attacker=attacker.id, target=target.id, hit=True,
            damage=final_damage, damage_type=damage_type, crit=is_crit,
            killed=killed, status_effects_applied=applied, message=msg,
        )

    # ---------- full combat resolution ----------

    def resolve_combat(self, world: World, attacker: Entity, target: Entity,
                       max_rounds: int = 20) -> CombatResult:
        """Resolve a full combat between two entities until one dies or flees."""
        result = CombatResult()
        atk_combat = world.get_component(attacker, CombatComponent)
        tgt_combat = world.get_component(target, CombatComponent)
        if atk_combat:
            atk_combat.in_combat = True
        if tgt_combat:
            tgt_combat.in_combat = True
        for _ in range(max_rounds):
            result.rounds += 1
            # Attacker attacks
            atk_weapon = self._get_equipped_weapon(world, attacker)
            r1 = self.attack(world, attacker, target, atk_weapon)
            result.attacks.append(r1)
            if r1.killed:
                result.winner = attacker.id
                break
            # Target retaliates if alive
            tgt_health = world.get_component(target, Health)
            if not tgt_health or tgt_health.current <= 0:
                break
            tgt_weapon = self._get_equipped_weapon(world, target)
            r2 = self.attack(world, target, attacker, tgt_weapon)
            result.attacks.append(r2)
            if r2.killed:
                result.winner = target.id
                break
            atk_health = world.get_component(attacker, Health)
            if not atk_health or atk_health.current <= 0:
                result.winner = target.id
                break
        if atk_combat:
            atk_combat.in_combat = False
        if tgt_combat:
            tgt_combat.in_combat = False
        return result

    # ---------- helpers ----------

    def _entity_name(self, world: World, entity: Entity) -> str:
        """Get an entity's display name, falling back to its ID."""
        from engine.entities.components import Identity as IdentityComp
        identity = world.get_component(entity, IdentityComp)
        if identity and identity.display_name:
            return identity.display_name
        return f"entity#{entity.id}"

    def _get_equipped_weapon(self, world: World, entity: Entity):
        if self.items is None:
            return None
        comp = world.get_component(entity, CombatComponent)
        if comp is None or comp.weapon_id is None:
            return None
        return self.items.get(comp.weapon_id)

    def _compute_weapon_damage(self, weapon, strength: float) -> float:
        if weapon is None:
            return 2.0 + strength * 0.5
        base = weapon.property_value("damage", 5.0)
        return base + strength * 0.3

    def _compute_attack_speed(self, weapon, agility: float) -> float:
        if weapon is None:
            return 1.0 + agility * 0.02
        return weapon.property_value("attack_speed", 1.0) + agility * 0.02

    def _compute_crit_chance(self, weapon, perception: float, luck: float) -> float:
        if weapon is None:
            return 5.0 + perception * 0.2 + luck * 0.3
        return weapon.property_value("crit_chance", 0.05) * 100 + perception * 0.2 + luck * 0.3

    def _compute_crit_mult(self, weapon) -> float:
        if weapon is None:
            return 2.0
        return 2.0 + weapon.property_value("crit_mult", 0.0)

    def _compute_armor_pen(self, weapon) -> float:
        if weapon is None:
            return 0.0
        return weapon.property_value("armor_pen", 0.0)

    def _compute_armor(self, world: World, entity: Entity) -> float:
        if self.items is None:
            return 0.0
        comp = world.get_component(entity, CombatComponent)
        if comp is None:
            return 0.0
        total = 0.0
        for slot, item_id in comp.armor_ids.items():
            if item_id is None:
                continue
            item = self.items.get(item_id)
            if item:
                total += item.property_value("armor", 0.0)
        return total

    def _compute_block(self, world: World, entity: Entity) -> float:
        if self.items is None:
            return 0.0
        comp = world.get_component(entity, CombatComponent)
        if comp is None:
            return 0.0
        # Check off-hand for shield
        off_hand_id = comp.armor_ids.get("off_hand")
        if off_hand_id is None:
            return 0.0
        item = self.items.get(off_hand_id)
        if item and "shield" in item.tags:
            return item.property_value("block_chance", 0.0) * 100
        return 0.0

    def _weapon_damage_type(self, weapon) -> DamageType:
        if weapon is None:
            return DamageType.BLUDGEONING
        # Check enchantments for elemental damage
        for enchant in weapon.enchantments:
            t = enchant.get("type", "")
            if t == "fire_damage":
                return DamageType.FIRE
            if t == "cold_damage":
                return DamageType.COLD
            if t == "lightning_damage":
                return DamageType.LIGHTNING
        # Affix-based
        if weapon.property_value("fire_damage", 0) > 0:
            return DamageType.FIRE
        if weapon.property_value("cold_damage", 0) > 0:
            return DamageType.COLD
        if weapon.property_value("lightning_damage", 0) > 0:
            return DamageType.LIGHTNING
        if weapon.property_value("poison_chance", 0) > 0:
            return DamageType.POISON
        # Default by base type
        bt = weapon.base_type
        if bt in ("dagger", "shortsword", "longsword", "spear"):
            return DamageType.PIERCING if bt in ("dagger", "spear") else DamageType.SLASHING
        if bt in ("mace", "warhammer"):
            return DamageType.BLUDGEONING
        if bt in ("axe", "battleaxe"):
            return DamageType.SLASHING
        return DamageType.SLASHING
