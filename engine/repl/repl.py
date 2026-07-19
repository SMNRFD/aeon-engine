"""Game REPL — a polished interactive command-line interface.

Features:
* Single-key movement (hjkl, wasd, arrows) — no Enter required
* Full command parser with aliases and autocomplete
* Pretty formatted output with ANSI colors
* Combat, magic, inventory, dialogue all fully playable
* In-game help system
* History navigation with up/down arrows
* Tab completion
* Macros and command aliases

Movement keys (vi-style):
  h/←   west      j/↓   south     k/↑   north     l/→   east
  y     NW        u     NE        b     SW        n     SE
  .     wait      >     descend   <     ascend

Other single-key actions:
  i     inventory       c     character sheet
  m     world map       ?     help
  q     quit            Esc   cancel/close panel

Commands (typed at the prompt):
  look [target]          look around or at a target
  go <direction>         move in a direction
  attack <target>        attack an entity
  cast <spell> [target]  cast a spell
  use <item>             use an item
  equip <item>           equip an item
  unequip <slot>         unequip from a slot
  drop <item>            drop an item
  pick up                pick up items on the ground
  talk [npc]             talk to an NPC
  trade [npc]            trade with an NPC
  rest                   rest for an hour
  sleep                  sleep until morning
  save [name]            save the game
  load <name>            load a save
  status                 show player status
  inventory              show inventory
  character              show character sheet
  map                    show world map
  spells                 list known spells
  skills                 list skills
  quests                 show quest log
  time                   show game time
  weather                show weather
  help [command]         show help
  plugins                list plugins
  quit                   exit the game
"""

from __future__ import annotations

import os
import shlex
import sys
import time
from typing import Any, Optional

from engine.core.ecs import Entity
from engine.core.logging import get_logger
from engine.commands.system import (
    CommandContext, CommandResult, Permission,
)
from engine.entities.components import (
    AI as AIComp, Combat as CombatComp, Health, Identity, Needs, Position,
    Stats, Wealth, Race, Personality,
)
from engine.magic.spells import Mana
from engine.render.terminal import Color, ANSI
from engine.ui.screens import MessageLog


log = get_logger("repl")


# Direction mapping
DIRECTIONS: dict[str, tuple[int, int, str]] = {
    # vi-keys
    "h": (-1, 0, "west"),  "left":  (-1, 0, "west"),  "west":  (-1, 0, "west"),
    "l": (1, 0, "east"),   "right": (1, 0, "east"),   "east":  (1, 0, "east"),
    "k": (0, -1, "north"), "up":    (0, -1, "north"), "north": (0, -1, "north"),
    "j": (0, 1, "south"),  "down":  (0, 1, "south"),  "south": (0, 1, "south"),
    "y": (-1, -1, "NW"),   "northwest": (-1, -1, "NW"),
    "u": (1, -1, "NE"),    "northeast": (1, -1, "NE"),
    "b": (-1, 1, "SW"),    "southwest": (-1, 1, "SW"),
    "n": (1, 1, "SE"),     "southeast": (1, 1, "SE"),
    # wasd
    "a": (-1, 0, "west"),  "d": (1, 0, "east"),
    "w": (0, -1, "north"), "s": (0, 1, "south"),
}

# Single-key commands that don't require Enter when raw mode is active
SINGLE_KEYS: dict[str, str] = {
    "h": "go west", "j": "go south", "k": "go north", "l": "go east",
    "y": "go NW", "u": "go NE", "b": "go SW", "n": "go SE",
    ".": "wait",
    "i": "inventory", "c": "character", "m": "map", "?": "help",
    "q": "quit",
}


class GameREPL:
    """Interactive game REPL."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.running: bool = False
        self._history: list[str] = []
        self._history_idx: int = -1
        self._current_input: str = ""
        self._in_dialogue: bool = False
        self._dialogue_ctx: Any = None
        self._dialogue_tree: Any = None
        self._raw_mode: bool = False
        self._saved_term_settings: Any = None
        self._panel_buffer: list[str] = []  # one-off display output

    # ---------- Terminal setup ----------

    def enable_raw_mode(self) -> None:
        """Enable raw terminal mode for single-key input."""
        try:
            import termios
            import tty
            self._saved_term_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
            self._raw_mode = True
        except (ImportError, AttributeError, OSError):
            # Not a TTY or not Unix — fall back to line mode
            self._raw_mode = False

    def disable_raw_mode(self) -> None:
        """Restore terminal settings."""
        if self._saved_term_settings is not None:
            try:
                import termios
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, self._saved_term_settings,
                )
            except (ImportError, OSError):
                pass
        self._raw_mode = False

    def _read_key(self) -> str:
        """Read a single keypress in raw mode."""
        try:
            ch = sys.stdin.read(1)
            if ch == "\x1b":  # escape sequence
                # Read the rest
                ch2 = sys.stdin.read(1)
                if ch2 == "[":
                    ch3 = sys.stdin.read(1)
                    if ch3 == "A": return "up"
                    if ch3 == "B": return "down"
                    if ch3 == "C": return "right"
                    if ch3 == "D": return "left"
                    if ch3 == "H": return "home"
                    if ch3 == "F": return "end"
                    return f"esc[{ch3}"
                if ch2 == "O":
                    ch3 = sys.stdin.read(1)
                    return f"escO{ch3}"
                return "esc"
            if ch == "\r" or ch == "\n":
                return "enter"
            if ch == "\t":
                return "tab"
            if ch == "\x7f" or ch == "\x08":
                return "backspace"
            if ch == "\x03":  # Ctrl-C
                return "quit"
            if ch == "\x04":  # Ctrl-D
                return "quit"
            return ch
        except (EOFError, KeyboardInterrupt):
            return "quit"

    # ---------- Output ----------

    def print(self, text: str = "", color: Optional[int] = None,
              end: str = "\n") -> None:
        """Print colored text — buffered if a panel is active."""
        if color is not None and self.engine.config.ui.color_enabled:
            line = f"\033[38;5;{color}m{text}\033[0m"
        else:
            line = text
        if end == "\n":
            self._panel_buffer.append(line)
        else:
            # Continuation of previous line
            if self._panel_buffer:
                self._panel_buffer[-1] += line
            else:
                self._panel_buffer.append(line)

    def print_header(self, text: str, color: int = Color.GOLD) -> None:
        """Print a section header."""
        width = 60
        line = "═" * width
        self.print(f"\n{text.center(width)}", color=color)
        self.print(line, color=color)

    def print_separator(self, color: int = Color.GRAY) -> None:
        self.print("─" * 60, color=color)

    def print_bar(self, label: str, current: float, maximum: float,
                  width: int = 20, color: int = Color.HEALTH) -> None:
        """Print a progress bar."""
        if maximum <= 0:
            fraction = 0
        else:
            fraction = current / maximum
        filled = int(width * fraction)
        bar = "█" * filled + "░" * (width - filled)
        self.print(f"  {label:12s} [{bar}] {int(current)}/{int(maximum)}",
                   color=color)

    # ---------- Game state display ----------

    def show_status_panel(self) -> None:
        """Show a compact status panel."""
        if self.engine.player is None:
            return
        player = self.engine.player
        world = self.engine.world
        # Get components
        identity = world.get_component(player, Identity)
        health = world.get_component(player, Health)
        stats = world.get_component(player, Stats)
        needs = world.get_component(player, Needs)
        wealth = world.get_component(player, Wealth)
        position = world.get_component(player, Position)
        mana = world.get_component(player, Mana)
        # Header
        name = identity.display_name if identity else "Hero"
        self.print_header(name, Color.GOLD)
        # HP and Mana
        if health:
            self.print_bar("HP", health.current, health.maximum, color=Color.HEALTH)
        if mana:
            self.print_bar("MP", mana.current, mana.maximum, color=Color.MANA)
        if needs:
            self.print_bar("Hunger", needs.hunger, 100, color=Color.YELLOW)
            self.print_bar("Thirst", needs.thirst, 100, color=Color.CYAN)
            self.print_bar("Fatigue", needs.fatigue, 100, color=Color.MUTED)
            self.print_bar("Sleep", needs.sleep, 100, color=Color.PURPLE)
        # Position
        if position:
            self.print(f"  Position: ({position.x}, {position.y})", Color.GRAY)
        # Wealth
        if wealth:
            self.print(f"  Gold: {wealth.gold}  Silver: {wealth.silver}  Copper: {wealth.copper}",
                       color=Color.GOLD)
        # Time and weather
        time_str = self.engine.clock.time.display()
        weather_str = (self.engine.weather.current.description()
                       if self.engine.weather else "unknown")
        self.print(f"  {time_str} | {weather_str}", Color.CYAN)
        self.print_separator()

    def show_map_view(self, radius: int = 12) -> None:
        """Show a local map view."""
        if self.engine.player is None or self.engine.world_map is None:
            return
        player = self.engine.player
        pos = self.engine.world.get_component(player, Position)
        if pos is None:
            return
        world_map = self.engine.world_map
        # Determine viewport
        viewport_w = min(50, world_map.width)
        viewport_h = min(15, world_map.height)
        ox = pos.x - viewport_w // 2
        oy = pos.y - viewport_h // 2
        self.print_header("Map", Color.GOLD)
        for j in range(viewport_h):
            row = ""
            for i in range(viewport_w):
                wx = ox + i
                wy = oy + j
                tile = world_map.get_tile(wx, wy)
                if tile is None:
                    row += " "
                    continue
                if not tile.is_explored and not self.engine.cheat_mode:
                    row += " "
                    continue
                # Check for entities at this position
                entity_here = False
                for ent, (ep,) in self.engine.world.view(Position):
                    if ep.x == wx and ep.y == wy:
                        if ent.id == player.id:
                            row += "@"
                            entity_here = True
                            break
                        identity = self.engine.world.get_component(ent, Identity)
                        glyph = identity.glyph if identity else "?"
                        # Override color for hostile
                        if self.engine.world.has_tag(ent, "hostile"):
                            glyph = glyph  # just use the glyph
                        row += glyph
                        entity_here = True
                        break
                if not entity_here:
                    if tile.is_visible or self.engine.cheat_mode:
                        row += tile.terrain.glyph
                    else:
                        row += tile.terrain.glyph  # explored but not visible
            self.print(row)
        self.print_separator()

    def show_messages(self, n: int = 5) -> None:
        """Show recent messages."""
        if not self.engine.message_log.messages:
            return
        self.print_header("Messages", Color.GOLD)
        for msg, color in self.engine.message_log.recent(n):
            self.print(f"  {msg}", color=color)
        self.print_separator()

    def show_inventory(self) -> None:
        """Show the player's inventory."""
        if self.engine.player is None:
            return
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            self.print("You have no inventory.", Color.GRAY)
            return
        self.print_header("Inventory", Color.GOLD)
        # Equipment
        self.print("Equipment:", Color.YELLOW)
        for slot, item_id in inv.all_equipped().items():
            if item_id is None:
                self.print(f"  {slot.value:15s} (empty)", Color.GRAY)
            else:
                item = self.engine.items.get(item_id)
                if item:
                    self.print(f"  {slot.value:15s} {item.display_name}",
                               color=item.rarity.color)
        self.print()
        # Backpack
        self.print("Backpack:", Color.YELLOW)
        any_items = False
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            any_items = True
            line = f"  [{slot_idx:2d}] {item.display_name}"
            if count > 1:
                line += f" x{count}"
            line += f"  ({item.weight:.1f}kg, {item.total_value}cp)"
            self.print(line, color=item.rarity.color)
        if not any_items:
            self.print("  (empty)", Color.GRAY)
        weight = inv.total_weight(self.engine.items)
        self.print(f"\nTotal weight: {weight:.1f}/{inv.max_weight:.1f} kg",
                   color=Color.GRAY)
        self.print_separator()

    def show_character_sheet(self) -> None:
        """Show detailed character info."""
        if self.engine.player is None:
            return
        player = self.engine.player
        identity = self.engine.world.get_component(player, Identity)
        health = self.engine.world.get_component(player, Health)
        stats = self.engine.world.get_component(player, Stats)
        race = self.engine.world.get_component(player, Race)
        self.print_header("Character", Color.GOLD)
        if identity:
            self.print(f"  Name: {identity.display_name}", Color.WHITE)
            self.print(f"  Description: {identity.description}", Color.GRAY)
        if race:
            self.print(f"  Race: {race.race_id.title()}  Age: {race.age}",
                       color=Color.WHITE)
        if health:
            self.print(f"  HP: {health.current}/{health.maximum}", Color.HEALTH)
        if stats:
            self.print()
            self.print("  Attributes:", Color.YELLOW)
            for attr in ("strength", "agility", "endurance", "intelligence",
                         "willpower", "charisma", "perception", "luck"):
                val = getattr(stats, attr)
                self.print(f"    {attr:14s}: {val}", Color.WHITE)
            self.print()
            self.print("  Derived:", Color.YELLOW)
            derived = stats.derived()
            for k, v in derived.items():
                self.print(f"    {k:18s}: {v}", Color.WHITE)
        self.print_separator()

    def show_spells(self) -> None:
        """Show known spells."""
        from engine.magic.spells import SpellLibrary
        self.print_header("Spells", Color.GOLD)
        mana = self.engine.world.get_component(self.engine.player, Mana) if self.engine.player else None
        if mana:
            self.print(f"  MP: {mana.current:.0f}/{mana.maximum:.0f}", Color.MANA)
            self.print()
        for spell in SpellLibrary.all():
            line = f"  {spell.name:25s} cost: {spell.mana_cost:3d} MP"
            if spell.target.value != "self":
                line += f"  ({spell.target.value})"
            self.print(line, color=Color.MANA)
        self.print_separator()

    def show_skills(self) -> None:
        """Show player skills."""
        from engine.entities.components import Skills as SkillsComp
        from engine.skills.system import SkillLibrary
        comp = self.engine.world.get_component(self.engine.player, SkillsComp) if self.engine.player else None
        self.print_header("Skills", Color.GOLD)
        if comp is None or not comp.skills:
            self.print("  You have no skills yet.", Color.GRAY)
        else:
            for skill_id, sl in sorted(comp.skills.items(),
                                        key=lambda x: -x[1].level):
                skill = SkillLibrary.get(skill_id)
                name = skill.name if skill else skill_id
                self.print(f"  {name:25s} Lv: {sl.level:3d}  XP: {sl.xp:.0f}",
                           color=Color.WHITE)
        self.print_separator()

    # ---------- Commands ----------

    def cmd_look(self, args: list[str]) -> None:
        """Look around or at a specific target."""
        if self.engine.player is None or self.engine.world_map is None:
            return
        player = self.engine.player
        pos = self.engine.world.get_component(player, Position)
        if pos is None:
            return
        # Look at specific target
        if args:
            target = self._find_entity_by_name(" ".join(args))
            if target is not None:
                self._describe_entity(target)
                return
            self.print(f"You don't see any '{' '.join(args)}' here.", Color.GRAY)
            return
        # Look around
        self.print_header("You see...", Color.GOLD)
        # Current tile
        tile = self.engine.world_map.get_tile(pos.x, pos.y)
        if tile:
            biome_name = tile.biome_type.replace("_", " ").title()
            self.print(f"  Terrain: {tile.terrain.glyph} {biome_name}", Color.GRAY)
        # Nearby entities
        any_entity = False
        for ent, (ep,) in self.engine.world.view(Position):
            if ent.id == player.id:
                continue
            dist = max(abs(ep.x - pos.x), abs(ep.y - pos.y))
            if dist > 12:
                continue
            identity = self.engine.world.get_component(ent, Identity)
            name = identity.display_name if identity else f"entity#{ent.id}"
            glyph = identity.glyph if identity else "?"
            tag = ""
            if self.engine.world.has_tag(ent, "hostile"):
                tag = " (hostile)"
                color = Color.RED
            elif self.engine.world.has_tag(ent, "npc"):
                tag = " (NPC)"
                color = Color.YELLOW
            else:
                color = Color.WHITE
            self.print(f"  {glyph} {name}{tag} at ({ep.x}, {ep.y}) — dist {dist}",
                       color=color)
            any_entity = True
        if not any_entity:
            self.print("  Nothing of interest nearby.", Color.GRAY)
        self.print_separator()

    def cmd_go(self, args: list[str]) -> None:
        """Move in a direction."""
        if not args:
            self.print("Go where? Try: go north (or just: k)", Color.GRAY)
            return
        direction = args[0].lower()
        if direction not in DIRECTIONS:
            self.print(f"Unknown direction: {direction}", Color.RED)
            self.print(f"Valid: {', '.join(sorted(set(DIRECTIONS.keys())))}", Color.GRAY)
            return
        dx, dy, name = DIRECTIONS[direction]
        moved = self.engine.move_player(dx, dy)
        if not moved:
            # Show latest messages (might be attack or blocked)
            pass

    def cmd_attack(self, args: list[str]) -> None:
        """Attack an entity."""
        if not args:
            # Attack adjacent hostile
            target = self._find_adjacent_hostile()
            if target is None:
                self.print("Attack what? Try: attack goblin", Color.GRAY)
                return
        else:
            target = self._find_entity_by_name(" ".join(args))
            if target is None:
                self.print(f"You don't see any '{' '.join(args)}' here.", Color.RED)
                return
        if target is None:
            return
        # Check distance
        player_pos = self.engine.world.get_component(self.engine.player, Position)
        target_pos = self.engine.world.get_component(target, Position)
        if player_pos and target_pos:
            dist = max(abs(player_pos.x - target_pos.x),
                       abs(player_pos.y - target_pos.y))
            if dist > 1:
                self.print("Target is too far away.", Color.RED)
                return
        # Get weapon
        comp = self.engine.world.get_component(self.engine.player, CombatComp)
        weapon = None
        if comp and comp.weapon_id is not None:
            weapon = self.engine.items.get(comp.weapon_id)
        result = self.engine.combat.attack(self.engine.world, self.engine.player,
                                            target, weapon)
        if result.message:
            self.engine.message_log.add(result.message,
                                         Color.YELLOW if result.hit else Color.GRAY)
        if result.killed:
            self.engine._handle_death(target, self.engine.player)

    def cmd_cast(self, args: list[str]) -> None:
        """Cast a spell."""
        from engine.magic.spells import SpellLibrary
        if not args:
            self.print("Cast what? Try: cast fireball", Color.GRAY)
            self.show_spells()
            return
        spell_name = " ".join(args).lower()
        # Find spell by name (case-insensitive)
        spell = None
        for s in SpellLibrary.all():
            if s.name.lower() == spell_name or s.id == spell_name:
                spell = s
                break
            if spell_name in s.name.lower():
                spell = s
                break
        if spell is None:
            self.print(f"Unknown spell: {spell_name}", Color.RED)
            return
        # Find target if needed
        target = None
        if spell.target.value in ("enemy", "ally", "item"):
            target = self._find_adjacent_hostile()
            if target is None:
                # Look for any nearby entity
                target = self._find_nearest_entity(exclude_player=True)
        result = self.engine.spell_caster.cast(
            self.engine.world, self.engine.player, spell, target,
        )
        if result.message:
            self.engine.message_log.add(result.message,
                                         Color.YELLOW if result.success else Color.RED)
        if result.damage_dealt > 0:
            self.engine.message_log.add(
                f"  Dealt {result.damage_dealt:.0f} damage!",
                Color.RED,
            )
        if result.healing_done > 0:
            self.engine.message_log.add(
                f"  Restored {result.healing_done:.0f} HP!",
                Color.GREEN,
            )

    def cmd_use(self, args: list[str]) -> None:
        """Use an item."""
        if not args:
            self.print("Use what? Try: use health potion", Color.GRAY)
            return
        item_name = " ".join(args).lower()
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            return
        # Find item by name
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower() or item_name in item.name.lower():
                self._use_item(item)
                return
        self.print(f"You don't have any '{item_name}'.", Color.RED)

    def _use_item(self, item: Any) -> None:
        """Use a specific item."""
        from engine.entities.components import Needs as NeedsComp
        # Consumables
        if item.category == "consumable":
            heal = item.property_value("heal", 0)
            mana_restore = item.property_value("restore_mana", 0)
            food = item.property_value("food", 0)
            drink = item.property_value("drink", 0)
            if heal > 0:
                health = self.engine.world.get_component(self.engine.player, Health)
                if health:
                    health.current = min(health.maximum, int(health.current + heal))
                    self.engine.message_log.add(
                        f"You use {item.display_name}, restoring {heal:.0f} HP.",
                        Color.GREEN,
                    )
            if mana_restore > 0:
                mana = self.engine.world.get_component(self.engine.player, Mana)
                if mana:
                    mana.current = min(mana.maximum, mana.current + mana_restore)
                    self.engine.message_log.add(
                        f"You use {item.display_name}, restoring {mana_restore:.0f} MP.",
                        Color.MANA,
                    )
            if food > 0:
                needs = self.engine.world.get_component(self.engine.player, NeedsComp)
                if needs:
                    needs.hunger = max(0, needs.hunger - food)
                    self.engine.message_log.add(
                        f"You eat {item.display_name}. Hunger reduced by {food:.0f}.",
                        Color.YELLOW,
                    )
            if drink > 0:
                needs = self.engine.world.get_component(self.engine.player, NeedsComp)
                if needs:
                    needs.thirst = max(0, needs.thirst - drink)
                    self.engine.message_log.add(
                        f"You drink {item.display_name}. Thirst reduced by {drink:.0f}.",
                        Color.CYAN,
                    )
            # Remove from inventory
            inv = self.engine.inventories.get(self.engine.player.id)
            if inv:
                inv.remove(item.id, 1)
        else:
            self.print(f"You can't use {item.display_name}.", Color.GRAY)

    def cmd_equip(self, args: list[str]) -> None:
        """Equip an item."""
        if not args:
            self.print("Equip what? Try: equip dagger", Color.GRAY)
            return
        item_name = " ".join(args).lower()
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            return
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower() or item_name in item.name.lower():
                # Equip
                if item.category == "weapon":
                    comp = self.engine.world.get_component(self.engine.player, CombatComp)
                    if comp is None:
                        comp = CombatComp()
                        self.engine.world.add_component(self.engine.player, comp)
                    inv.remove(item.id, 1)
                    # Unequip old weapon
                    if comp.weapon_id is not None:
                        old = self.engine.items.get(comp.weapon_id)
                        if old:
                            inv.add(old, 1)
                    comp.weapon_id = item.id
                    self.engine.message_log.add(
                        f"You equip {item.display_name}.",
                        Color.GREEN,
                    )
                    return
                elif item.category == "armor":
                    comp = self.engine.world.get_component(self.engine.player, CombatComp)
                    if comp is None:
                        comp = CombatComp()
                        self.engine.world.add_component(self.engine.player, comp)
                    slot_name = "chest"  # default
                    inv.remove(item.id, 1)
                    old_id = comp.armor_ids.get(slot_name)
                    if old_id is not None:
                        old = self.engine.items.get(old_id)
                        if old:
                            inv.add(old, 1)
                    comp.armor_ids[slot_name] = item.id
                    self.engine.message_log.add(
                        f"You equip {item.display_name}.",
                        Color.GREEN,
                    )
                    return
                else:
                    self.print(f"You can't equip {item.display_name}.", Color.GRAY)
                    return
        self.print(f"You don't have any '{item_name}'.", Color.RED)

    def cmd_drop(self, args: list[str]) -> None:
        """Drop an item."""
        if not args:
            self.print("Drop what?", Color.GRAY)
            return
        item_name = " ".join(args).lower()
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            return
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower() or item_name in item.name.lower():
                inv.remove(item.id, 1)
                # Drop on ground
                pos = self.engine.world.get_component(self.engine.player, Position)
                if pos:
                    self.engine.factory.create_item_entity(item.id, pos.x, pos.y)
                self.engine.message_log.add(
                    f"You drop {item.display_name}.",
                    Color.GRAY,
                )
                return
        self.print(f"You don't have any '{item_name}'.", Color.RED)

    def cmd_pickup(self, args: list[str]) -> None:
        """Pick up items from the ground."""
        if self.engine.player is None:
            return
        pos = self.engine.world.get_component(self.engine.player, Position)
        if pos is None:
            return
        # Find items at player position
        picked_up = False
        for ent, (ep,) in self.engine.world.view(Position):
            if ep.x != pos.x or ep.y != pos.y:
                continue
            identity = self.engine.world.get_component(ent, Identity)
            if identity and "item" in identity.tags:
                # Get item data
                item_data_id = identity.item_data_id if hasattr(identity, "item_data_id") else None
                if item_data_id is None:
                    continue
                item = self.engine.items.get(item_data_id)
                if item is None:
                    continue
                inv = self.engine.inventories.get(self.engine.player.id)
                if inv:
                    inv.add(item, 1)
                    self.engine.message_log.add(
                        f"You pick up {item.display_name}.",
                        Color.GREEN,
                    )
                    picked_up = True
                # Remove the entity
                self.engine.world.destroy_entity(ent)
        if not picked_up:
            self.engine.message_log.add("There's nothing to pick up.", Color.GRAY)

    def cmd_trade(self, args: list[str]) -> None:
        """Trade with an NPC."""
        # Find NPC
        if args:
            target = self._find_entity_by_name(" ".join(args))
        else:
            target = self._find_adjacent_npc()
        if target is None:
            self.print("There's no one to trade with.", Color.GRAY)
            return
        if not self.engine.world.has_tag(target, "merchant"):
            identity = self.engine.world.get_component(target, Identity)
            name = identity.display_name if identity else "them"
            self.print(f"{name} is not interested in trading.", Color.GRAY)
            return
        # Open trade interface (simplified)
        identity = self.engine.world.get_component(target, Identity)
        name = identity.display_name if identity else "Merchant"
        self.print_header(f"Trading with {name}", Color.GOLD)
        self.print("  (Trade functionality coming soon)", Color.GRAY)
        self.print_separator()

    def cmd_unequip(self, args: list[str]) -> None:
        """Unequip an item from a slot."""
        comp = self.engine.world.get_component(self.engine.player, CombatComp) if self.engine.player else None
        if comp is None:
            self.print("You have nothing equipped.", Color.GRAY)
            return
        if not args:
            # Unequip all
            unequipped = False
            inv = self.engine.inventories.get(self.engine.player.id) if self.engine.player else None
            for slot, item_id in list(comp.armor_ids.items()):
                if item_id is not None and inv:
                    item = self.engine.items.get(item_id)
                    if item:
                        inv.add(item, 1)
                        unequipped = True
                    comp.armor_ids[slot] = None
            if comp.weapon_id is not None and inv:
                item = self.engine.items.get(comp.weapon_id)
                if item:
                    inv.add(item, 1)
                    unequipped = True
                comp.weapon_id = None
            if unequipped:
                self.engine.message_log.add("You unequip all items.", Color.GREEN)
            else:
                self.print("You have nothing equipped.", Color.GRAY)
            return
        slot_name = args[0].lower()
        if slot_name in ("weapon", "main_hand", "hand"):
            if comp.weapon_id is not None:
                inv = self.engine.inventories.get(self.engine.player.id) if self.engine.player else None
                if inv:
                    item = self.engine.items.get(comp.weapon_id)
                    if item:
                        inv.add(item, 1)
                        self.engine.message_log.add(f"You unequip {item.display_name}.", Color.GREEN)
                    comp.weapon_id = None
            else:
                self.print("You don't have a weapon equipped.", Color.GRAY)
        elif slot_name in ("chest", "armor", "body"):
            if comp.armor_ids.get("chest") is not None:
                inv = self.engine.inventories.get(self.engine.player.id) if self.engine.player else None
                if inv:
                    item = self.engine.items.get(comp.armor_ids["chest"])
                    if item:
                        inv.add(item, 1)
                        self.engine.message_log.add(f"You unequip {item.display_name}.", Color.GREEN)
                    comp.armor_ids["chest"] = None
            else:
                self.print("You don't have chest armor equipped.", Color.GRAY)
        else:
            self.print(f"Unknown slot: {slot_name}", Color.GRAY)
            self.print("Valid slots: weapon, chest", Color.GRAY)

    def cmd_talk(self, args: list[str]) -> None:
        """Talk to an NPC."""
        from engine.dialogue.system import DialogueEngine, DialogueLibrary
        # Find NPC
        if args:
            target = self._find_entity_by_name(" ".join(args))
        else:
            target = self._find_adjacent_npc()
        if target is None:
            self.print("There's no one to talk to.", Color.GRAY)
            return
        identity = self.engine.world.get_component(target, Identity)
        name = identity.display_name if identity else "stranger"
        # Pick a dialogue tree
        tree_id = "commoner_greeting"
        if self.engine.world.has_tag(target, "merchant"):
            tree_id = "merchant_greeting"
        elif self.engine.world.has_tag(target, "guard"):
            tree_id = "guard_greeting"
        tree = DialogueLibrary.get(tree_id)
        if tree is None:
            tree = DialogueLibrary.get("commoner_greeting")
        if tree is None:
            self.print(f"{name} has nothing to say.", Color.GRAY)
            return
        self._dialogue_tree = tree
        self._dialogue_ctx = self.engine.dialogue.start(
            self.engine.world, self.engine.player, target, tree,
        )
        self._in_dialogue = True
        self._show_dialogue_node()

    def _show_dialogue_node(self) -> None:
        """Show the current dialogue node."""
        if self._dialogue_tree is None or self._dialogue_ctx is None:
            self._in_dialogue = False
            return
        node = self._dialogue_tree.get(self._dialogue_ctx.current_node_id)
        if node is None:
            self._in_dialogue = False
            return
        # Get NPC name
        identity = self.engine.world.get_component(self._dialogue_ctx.npc, Identity)
        npc_name = identity.display_name if identity else "NPC"
        self.print_header(f"Conversation with {npc_name}", Color.GOLD)
        self.print(f"  {npc_name}: {node.speaker_text}", Color.YELLOW)
        if node.choices:
            self.print()
            self.print("  Choices:", Color.GRAY)
            for i, choice in enumerate(node.choices):
                self.print(f"    [{i + 1}] {choice.text}", Color.WHITE)
            self.print(f"    [0] End conversation", Color.GRAY)
        else:
            self._in_dialogue = False
        self.print_separator()

    def _handle_dialogue_input(self, line: str) -> bool:
        """Handle input during a dialogue. Returns True if handled."""
        if not self._in_dialogue:
            return False
        line = line.strip()
        if not line:
            return True
        if line == "0" or line.lower() in ("q", "quit", "exit", "bye"):
            self._in_dialogue = False
            self._dialogue_tree = None
            self._dialogue_ctx = None
            self.print("You end the conversation.", Color.GRAY)
            return True
        try:
            choice_idx = int(line) - 1
        except ValueError:
            self.print("Invalid choice. Enter a number.", Color.RED)
            return True
        if self._dialogue_tree is None or self._dialogue_ctx is None:
            self._in_dialogue = False
            return True
        node = self._dialogue_tree.get(self._dialogue_ctx.current_node_id)
        if node is None or choice_idx < 0 or choice_idx >= len(node.choices):
            self.print("Invalid choice.", Color.RED)
            return True
        choice = node.choices[choice_idx]
        # Apply effects
        for effect in choice.effects:
            try:
                effect(self._dialogue_ctx)
            except Exception:  # noqa: BLE001
                pass
        # Move to next node
        next_id = choice.next_node
        if choice.ends_conversation or next_id is None:
            self._in_dialogue = False
            self._dialogue_tree = None
            self._dialogue_ctx = None
            self.print("You end the conversation.", Color.GRAY)
            return True
        next_node = self._dialogue_tree.get(next_id)
        if next_node is None:
            self._in_dialogue = False
            return True
        self._dialogue_ctx.current_node_id = next_id
        self._dialogue_ctx.visited_nodes.add(next_id)
        self._dialogue_ctx.history.append(next_node.speaker_text)
        self._show_dialogue_node()
        return True

    def cmd_wait(self, args: list[str]) -> None:
        """Wait for some time."""
        minutes = 60
        if args:
            try:
                minutes = int(args[0])
            except ValueError:
                self.print("Usage: wait [minutes]", Color.GRAY)
                return
        ticks = minutes * self.engine.clock.ticks_per_game_minute
        self.engine.clock.advance_ticks(ticks)
        self.engine.message_log.add(f"You wait for {minutes} minutes.", Color.GRAY)

    def cmd_rest(self, args: list[str]) -> None:
        """Rest for an hour — restores some HP and fatigue."""
        from engine.entities.components import Needs as NeedsComp
        health = self.engine.world.get_component(self.engine.player, Health)
        needs = self.engine.world.get_component(self.engine.player, NeedsComp)
        if health:
            heal = int(health.maximum * 0.1)
            health.current = min(health.maximum, health.current + heal)
        if needs:
            needs.fatigue = max(0, needs.fatigue - 20)
            needs.sleep = max(0, needs.sleep - 20)
        self.engine.clock.advance_ticks(60 * self.engine.clock.ticks_per_game_minute)
        self.engine.message_log.add("You rest for an hour.", Color.GREEN)

    def cmd_sleep(self, args: list[str]) -> None:
        """Sleep until morning."""
        from engine.entities.components import Needs as NeedsComp
        # Advance time to next 6 AM
        hour = self.engine.clock.time.hour
        if hour < 6:
            hours_to_sleep = 6 - hour
        else:
            hours_to_sleep = 24 - hour + 6
        ticks = hours_to_sleep * 60 * self.engine.clock.ticks_per_game_minute
        self.engine.clock.advance_ticks(ticks)
        # Restore HP and needs
        health = self.engine.world.get_component(self.engine.player, Health)
        needs = self.engine.world.get_component(self.engine.player, NeedsComp)
        if health:
            heal = int(health.maximum * 0.5)
            health.current = min(health.maximum, health.current + heal)
        if needs:
            needs.fatigue = 0
            needs.sleep = 0
        self.engine.message_log.add(
            f"You sleep for {hours_to_sleep} hours. HP and fatigue restored.",
            Color.GREEN,
        )

    def cmd_help(self, args: list[str]) -> None:
        """Show help."""
        self.print_header("Aeon Engine — Help", Color.GOLD)
        helps = [
            ("Movement", "h j k l (vi-keys) or wasd or arrows; y u b n for diagonals"),
            ("Look", "look [target]  (or just 'l')"),
            ("Attack", "attack <target>  (or just 'a <target>')"),
            ("Cast spell", "cast <spell> [target]"),
            ("Use item", "use <item>"),
            ("Equip", "equip <item>"),
            ("Drop", "drop <item>"),
            ("Talk", "talk [npc]  (or just 't')"),
            ("Inventory", "inventory  (or just 'i')"),
            ("Character", "character  (or just 'c')"),
            ("Map", "map  (or just 'm')"),
            ("Spells", "spells"),
            ("Skills", "skills"),
            ("Wait", "wait minutes  (or just '.')"),
            ("Rest", "rest  (restores HP and fatigue)"),
            ("Sleep", "sleep  (until morning)"),
            ("Status", "status"),
            ("Time", "time"),
            ("Weather", "weather"),
            ("Save", "save name"),
            ("Load", "load name"),
            ("Help", "help  (this message)"),
            ("Quit", "quit  (or 'q')"),
        ]
        for label, desc in helps:
            self.print(f"  {label:15s} {desc}", Color.WHITE)
        self.print_separator()

    def cmd_status(self, args: list[str]) -> None:
        """Show player status."""
        self.show_status_panel()

    def cmd_inventory(self, args: list[str]) -> None:
        """Show inventory."""
        self.show_inventory()

    def cmd_character(self, args: list[str]) -> None:
        """Show character sheet."""
        self.show_character_sheet()

    def cmd_map(self, args: list[str]) -> None:
        """Show world map."""
        self.show_map_view(radius=20)

    def cmd_spells(self, args: list[str]) -> None:
        """Show spells."""
        self.show_spells()

    def cmd_skills(self, args: list[str]) -> None:
        """Show skills."""
        self.show_skills()

    def cmd_quests(self, args: list[str]) -> None:
        """Show quest log."""
        if self.engine.player is None:
            return
        tracker = self.engine.quest_trackers.get(self.engine.player.id)
        if tracker is None:
            self.print("You have no quest log.", Color.GRAY)
            return
        self.print_header("Quest Log", Color.GOLD)
        if tracker.active:
            self.print("Active Quests:", Color.YELLOW)
            from engine.quests.system import QuestLibrary
            for quest_id, stage_id in tracker.active.items():
                quest = QuestLibrary.get(quest_id)
                if quest:
                    self.print(f"  {quest.name} (stage: {stage_id})",
                               color=Color.WHITE)
                    self.print(f"    {quest.description}", Color.GRAY)
        else:
            self.print("  No active quests.", Color.GRAY)
        if tracker.completed:
            self.print()
            self.print(f"Completed: {len(tracker.completed)}", Color.GREEN)
        if tracker.failed:
            self.print(f"Failed: {len(tracker.failed)}", Color.RED)
        self.print_separator()

    def cmd_time(self, args: list[str]) -> None:
        """Show game time."""
        time_str = self.engine.clock.time.display()
        phase = self.engine.clock.time.phase_of_day().display_name
        self.print_header("Time", Color.GOLD)
        self.print(f"  {time_str}", Color.CYAN)
        self.print(f"  Phase: {phase}", Color.GRAY)
        self.print(f"  Tick: {self.engine.clock.time.tick}", Color.GRAY)
        self.print_separator()

    def cmd_weather(self, args: list[str]) -> None:
        """Show weather."""
        if self.engine.weather is None:
            return
        self.print_header("Weather", Color.GOLD)
        self.print(f"  {self.engine.weather.current.description()}", Color.CYAN)
        self.print_separator()

    def cmd_plugins(self, args: list[str]) -> None:
        """List plugins."""
        self.print_header("Plugins", Color.GOLD)
        for s in self.engine.plugins.status():
            self.print(f"  {s['name']:25s} v{s['version']:8s} [{s['state']}]",
                       color=Color.WHITE)
        self.print_separator()

    def cmd_save(self, args: list[str]) -> None:
        """Save the game."""
        name = args[0] if args else "quicksave"
        try:
            self.engine.save_game(name)
            self.engine.message_log.add(f"Game saved as '{name}'.", Color.GREEN)
        except Exception as exc:  # noqa: BLE001
            self.engine.message_log.add(f"Save failed: {exc}", Color.RED)

    def cmd_load(self, args: list[str]) -> None:
        """Load a save."""
        if not args:
            self.print("Load what? Try: load my_save", Color.GRAY)
            return
        try:
            self.engine.load_game(args[0])
            self.engine.message_log.add(f"Loaded save '{args[0]}'.", Color.GREEN)
        except FileNotFoundError:
            self.engine.message_log.add(f"Save '{args[0]}' not found.", Color.RED)
        except Exception as exc:  # noqa: BLE001
            self.engine.message_log.add(f"Load failed: {exc}", Color.RED)

    def cmd_quit(self, args: list[str]) -> None:
        """Quit the game."""
        self.running = False
        self.engine.shutdown()

    def cmd_fish(self, args: list[str]) -> None:
        """Try fishing (if near water)."""
        if self.engine.player is None:
            return
        from engine.entities.components import Position
        pos = self.engine.world.get_component(self.engine.player, Position)
        if pos is None or self.engine.world_map is None:
            return
        # Check for adjacent water
        water_adjacent = False
        for n in self.engine.world_map.neighbours(pos.x, pos.y):
            if n.terrain.is_liquid:
                water_adjacent = True
                break
        if not water_adjacent:
            self.engine.message_log.add("You need to be near water to fish.",
                                         Color.GRAY)
            return
        # Try fishing
        if self.engine.rng.chance(0.5):
            # Generate a fish item
            from engine.items.generator import ItemGenerationParams
            fish_types = ["fish", "salmon", "trout"]
            fish_name = self.engine.rng.choice(fish_types)
            params = ItemGenerationParams(
                archetype="bread",  # reuse consumable
                material_id="organic",
            )
            item = self.engine.item_generator.generate(params, self.engine.items.next_id())
            item.name = fish_name.title()
            item.description = f"A fresh-caught {fish_name}."
            item.tags.append("food")
            item.add_property("food", 35.0)
            self.engine.items.register(item)
            inv = self.engine.inventories.get(self.engine.player.id)
            if inv:
                inv.add(item)
            self.engine.message_log.add(f"You caught a {fish_name}!", Color.GREEN)
        else:
            self.engine.message_log.add("You wait, but nothing bites...", Color.GRAY)

    # ---------- Entity lookup ----------

    def _find_entity_by_name(self, name: str) -> Optional[Entity]:
        """Find an entity by name near the player."""
        if self.engine.player is None:
            return None
        player_pos = self.engine.world.get_component(self.engine.player, Position)
        if player_pos is None:
            return None
        name_lower = name.lower()
        best: Optional[Entity] = None
        best_dist = 999
        for ent, (ep,) in self.engine.world.view(Position):
            if ent.id == self.engine.player.id:
                continue
            dist = max(abs(ep.x - player_pos.x), abs(ep.y - player_pos.y))
            if dist > 12:
                continue
            identity = self.engine.world.get_component(ent, Identity)
            ent_name = identity.display_name if identity else ""
            if name_lower in ent_name.lower():
                if dist < best_dist:
                    best = ent
                    best_dist = dist
        return best

    def _find_adjacent_hostile(self) -> Optional[Entity]:
        """Find the nearest adjacent hostile entity."""
        if self.engine.player is None:
            return None
        player_pos = self.engine.world.get_component(self.engine.player, Position)
        if player_pos is None:
            return None
        for ent, (ep,) in self.engine.world.view(Position):
            if ent.id == self.engine.player.id:
                continue
            dist = max(abs(ep.x - player_pos.x), abs(ep.y - player_pos.y))
            if dist <= 1 and self.engine.world.has_tag(ent, "hostile"):
                return ent
        return None

    def _find_adjacent_npc(self) -> Optional[Entity]:
        """Find the nearest adjacent NPC."""
        if self.engine.player is None:
            return None
        player_pos = self.engine.world.get_component(self.engine.player, Position)
        if player_pos is None:
            return None
        for ent, (ep,) in self.engine.world.view(Position):
            if ent.id == self.engine.player.id:
                continue
            dist = max(abs(ep.x - player_pos.x), abs(ep.y - player_pos.y))
            if dist <= 1 and self.engine.world.has_tag(ent, "npc"):
                return ent
        return None

    def _find_nearest_entity(self, exclude_player: bool = True) -> Optional[Entity]:
        """Find the nearest entity."""
        if self.engine.player is None:
            return None
        player_pos = self.engine.world.get_component(self.engine.player, Position)
        if player_pos is None:
            return None
        best: Optional[Entity] = None
        best_dist = 999
        for ent, (ep,) in self.engine.world.view(Position):
            if exclude_player and ent.id == self.engine.player.id:
                continue
            dist = max(abs(ep.x - player_pos.x), abs(ep.y - player_pos.y))
            if dist < best_dist:
                best = ent
                best_dist = dist
        return best

    def _describe_entity(self, entity: Entity) -> None:
        """Show details about an entity."""
        identity = self.engine.world.get_component(entity, Identity)
        health = self.engine.world.get_component(entity, Health)
        position = self.engine.world.get_component(entity, Position)
        if identity is None:
            self.print("You see nothing of interest.", Color.GRAY)
            return
        self.print_header(identity.display_name, identity.color)
        if identity.description:
            self.print(f"  {identity.description}", Color.GRAY)
        if health:
            self.print(f"  HP: {health.current}/{health.maximum}", Color.HEALTH)
        if position:
            self.print(f"  Position: ({position.x}, {position.y})", Color.GRAY)
        # Tags
        tags = []
        if self.engine.world.has_tag(entity, "hostile"):
            tags.append("hostile")
        if self.engine.world.has_tag(entity, "npc"):
            tags.append("npc")
        if self.engine.world.has_tag(entity, "creature"):
            tags.append("creature")
        if tags:
            self.print(f"  Tags: {', '.join(tags)}", Color.GRAY)
        self.print_separator()

    # ---------- Main loop ----------

    def run(self) -> None:
        """Run the REPL main loop."""
        self.running = True
        # Enable raw mode for single-key input
        self.enable_raw_mode()
        try:
            # Print welcome
            self.print()
            self.print("╔══════════════════════════════════════════════════════════╗",
                       color=Color.GOLD)
            self.print("║                                                          ║",
                       color=Color.GOLD)
            self.print("║            A E O N   E N G I N E                         ║",
                       color=Color.GOLD)
            self.print("║       A Text-Based Open-World RPG                        ║",
                       color=Color.GOLD)
            self.print("║                                                          ║",
                       color=Color.GOLD)
            self.print("╚══════════════════════════════════════════════════════════╝",
                       color=Color.GOLD)
            self.print()
            self.print("Type 'help' for commands, 'q' to quit.", Color.CYAN)
            self.print("Use hjkl/wasd/arrows for movement (no Enter needed).", Color.CYAN)
            self.print()
            # Show initial state
            self._refresh_display()
            # Main loop
            while self.running:
                try:
                    self._tick()
                except KeyboardInterrupt:
                    self.print("\nUse 'quit' to exit.", Color.YELLOW)
                except Exception as exc:  # noqa: BLE001
                    log.exception("REPL error")
                    self.print(f"Error: {exc}", Color.RED)
        finally:
            # Always restore terminal settings
            self.disable_raw_mode()

    def _tick(self) -> None:
        """One iteration of the REPL loop."""
        # Show prompt
        if self._in_dialogue:
            sys.stdout.write("Choice> ")
        else:
            sys.stdout.write("> ")
        sys.stdout.flush()
        # Read input - use raw key reading if available, otherwise fall back to input()
        line = ""
        if self._raw_mode:
            # Read single key or sequence
            key = self._read_key()
            # Handle special keys
            if key == "quit":
                self.running = False
                return
            if key == "enter":
                # Empty enter just advances time
                self.engine.tick_simulation(0.05)
                self._refresh_display()
                return
            if key in ("up", "down"):
                # History navigation
                if key == "up" and self._history:
                    self._history_idx = max(0, self._history_idx - 1)
                    line = self._history[self._history_idx] if self._history_idx >= 0 else ""
                elif key == "down" and self._history:
                    self._history_idx = min(len(self._history) - 1, self._history_idx + 1)
                    line = self._history[self._history_idx] if self._history_idx >= 0 else ""
                # Echo the line
                sys.stdout.write("\r" + " " * 40 + "\r> " + line)
                sys.stdout.flush()
                # Continue reading until enter
                while True:
                    k = self._read_key()
                    if k == "enter":
                        break
                    if k == "quit":
                        self.running = False
                        return
                    if k == "backspace" and line:
                        line = line[:-1]
                        sys.stdout.write("\r> " + line + " ")
                        sys.stdout.write("\r> " + line)
                        sys.stdout.flush()
                    elif len(k) == 1 and k.isprintable():
                        line += k
                        sys.stdout.write(line[-1])
                        sys.stdout.flush()
                sys.stdout.write("\n")
                sys.stdout.flush()
            elif len(key) == 1 and key.isprintable():
                # Single character command - check for movement or action
                if key in SINGLE_KEYS:
                    line = SINGLE_KEYS[key]
                    sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                else:
                    # Accumulate characters until enter
                    line = key
                    while True:
                        k = self._read_key()
                        if k == "enter":
                            break
                        if k == "quit":
                            self.running = False
                            return
                        if k == "backspace" and line:
                            line = line[:-1]
                            sys.stdout.write("\r> " + line + " ")
                            sys.stdout.write("\r> " + line)
                            sys.stdout.flush()
                        elif len(k) == 1 and k.isprintable():
                            line += k
                            sys.stdout.write(k)
                            sys.stdout.flush()
                    sys.stdout.write("\n")
                    sys.stdout.flush()
            else:
                # Unknown key, ignore
                return
        else:
            # Fallback to standard input
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                self.running = False
                return
        
        line = line.strip()
        if not line:
            # Just advance time a bit
            self.engine.tick_simulation(0.05)
            self._refresh_display()
            return
        # Add to history
        self._history.append(line)
        self._history_idx = -1
        # Handle dialogue
        if self._in_dialogue:
            if self._handle_dialogue_input(line):
                self.engine.tick_simulation(0.05)
                self._refresh_display()
                return
        # Parse and execute
        self._execute_command(line)
        # Advance simulation
        self.engine.tick_simulation(0.05)
        # Autosave check
        if (self.engine.clock.time.tick - self.engine._last_autosave_tick
                >= self.engine.config.save.autosave_interval_ticks):
            try:
                self.engine.save_game("autosave")
                self.engine._last_autosave_tick = self.engine.clock.time.tick
            except Exception as exc:  # noqa: BLE001
                log.error("Autosave failed: %s", exc)
        # Refresh display
        self._refresh_display()

    def _execute_command(self, line: str) -> None:
        """Parse and execute a command line."""
        # Tokenize
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            self.print(f"Parse error: {exc}", Color.RED)
            return
        if not tokens:
            return
        cmd = tokens[0].lower()
        args = tokens[1:]
        # Aliases
        aliases = {
            "l": "look", "look": "look",
            "i": "inventory", "inv": "inventory", "inventory": "inventory",
            "c": "character", "char": "character", "character": "character",
            "m": "map", "map": "map",
            "a": "attack", "att": "attack", "attack": "attack",
            "t": "talk", "talk": "talk",
            "go": "go", "move": "go", "g": "go",
            "cast": "cast", "spell": "cast",
            "use": "use", "drink": "use", "eat": "use",
            "equip": "equip", "eq": "equip",
            "unequip": "unequip", "uneq": "unequip",
            "drop": "drop",
            "pickup": "pickup", "pick": "pickup", "get": "pickup",
            "trade": "trade",
            "wait": "wait", ".": "wait",
            "rest": "rest",
            "sleep": "sleep",
            "status": "status", "st": "status",
            "time": "time",
            "weather": "weather",
            "spells": "spells", "sp": "spells",
            "skills": "skills", "sk": "skills",
            "quests": "quests",
            "save": "save",
            "load": "load",
            "help": "help", "?": "help", "h": "help",
            "plugins": "plugins",
            "quit": "quit", "q": "quit", "exit": "quit",
            "fish": "fish",
        }
        # If the command is a direction, treat as "go <direction>"
        if cmd in DIRECTIONS:
            args = [cmd]
            cmd = "go"
        else:
            cmd = aliases.get(cmd, cmd)
        # Dispatch
        handler = getattr(self, f"cmd_{cmd}", None)
        if handler is None:
            # Try engine commands
            ctx = CommandContext(
                world=self.engine.world, player=self.engine.player,
                raw_input=line, engine=self.engine,
                caller_id=self.engine.player.id if self.engine.player else None,
                permission=Permission.OWNER if self.engine.cheat_mode else Permission.PLAYER,
            )
            result = self.engine.command_processor.execute(line, ctx)
            if result.output:
                self.engine.message_log.add(result.output, Color.WHITE)
            elif result.error:
                self.engine.message_log.add(result.error, Color.RED)
            return
        try:
            handler(args)
        except Exception as exc:  # noqa: BLE001
            log.exception("Command %s failed", cmd)
            self.print(f"Error: {exc}", Color.RED)

    def _refresh_display(self) -> None:
        """Refresh the display after each command."""
        # Clear screen
        if self.engine.config.ui.color_enabled:
            sys.stdout.write(ANSI.CLEAR_SCREEN)
        else:
            sys.stdout.write("\n" * 2)
        sys.stdout.flush()
        # Capture panel output for status/map/messages
        # We'll bypass the buffer for the main view by writing directly
        self._write_main_view()
        # Write any panel buffer (from commands like inventory, help)
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()
        # Show dialogue if active
        if self._in_dialogue:
            # Capture dialogue output
            self._dialogue_buffer: list[str] = []
            self._show_dialogue_node()
            if self._panel_buffer:
                sys.stdout.write("\n".join(self._panel_buffer) + "\n")
                self._panel_buffer.clear()
        sys.stdout.flush()

    def _write_main_view(self) -> None:
        """Write the main view directly to stdout."""
        # Status panel
        self._panel_buffer.clear()
        self.show_status_panel()
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()
        # Map
        self.show_map_view()
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()
        # Messages
        self.show_messages()
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()
