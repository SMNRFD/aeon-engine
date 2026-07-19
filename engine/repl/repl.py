"""Game REPL — a polished interactive command-line interface.

This module is the SINGLE entry point for Aeon Engine. It replaces the
old ``main.py`` and integrates EVERY gameplay system the engine ships
with — combat, magic, crafting, economy, quests, factions, kingdoms,
espionage, rebellions, dungeons, artifacts, auctions, black market,
life simulation, stealth, animals, reputation, runes, skill books,
themes, dimensions, body parts, trade, bookmarks, procedural dialogue,
all combat variants (naval / siege / aerial / space / realtime /
mounted), background simulation, content packs, plugins and more.

Features
--------
* Single-key movement (hjkl, wasd, arrows) — no Enter required (TTY).
* Full command parser with aliases, autocomplete and history.
* Pretty formatted output with ANSI 256-colour support.
* Combat, magic, inventory, dialogue, crafting all fully playable.
* In-game help system organised by category.
* Macros and command aliases.
* Graceful fall-back to line mode when stdin is not a TTY (pipes, CI).

Movement keys (vi-style)
------------------------
  h/←   west      j/↓   south     k/↑   north     l/→   east
  y     NW        u     NE        b     SW        n     SE
  .     wait      >     descend   <     ascend

Other single-key actions
------------------------
  i     inventory       c     character sheet
  m     world map       ?     help
  q     quit            Esc   cancel/close panel

Run the game
------------
    python -m engine.repl.repl
    python -m engine.repl.repl --seed 42 --name Hero
    python -m engine.repl.repl --load quicksave
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import time
from pathlib import Path
from typing import Any, Optional

from engine.core.ecs import Entity
from engine.core.logging import get_logger
from engine.commands.system import (
    CommandContext, CommandResult, Permission,
)
from engine.entities.components import (
    AI as AIComp, Combat as CombatComp, Health, Identity, Needs, Position,
    Stats, Wealth, Race, Personality, Tag,
)
from engine.magic.spells import Mana
from engine.render.terminal import Color, ANSI
from engine.ui.screens import MessageLog


log = get_logger("repl")


# --------------------------------------------------------------------------- #
# Direction mapping
# --------------------------------------------------------------------------- #

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


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _colour(text: str, color: Optional[int], enabled: bool) -> str:
    if color is not None and enabled:
        return f"\033[38;5;{color}m{text}\033[0m"
    return text


def _format_money(copper_total: int) -> str:
    """Format a copper amount as gold/silver/copper."""
    if copper_total < 0:
        return f"-{_format_money(-copper_total)}"
    gold, rem = divmod(copper_total, 10000)
    silver, copper = divmod(rem, 100)
    parts = []
    if gold:
        parts.append(f"{gold}g")
    if silver or gold:
        parts.append(f"{silver}s")
    parts.append(f"{copper}c")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Main REPL class
# --------------------------------------------------------------------------- #

class GameREPL:
    """Interactive game REPL — the single front-end for Aeon Engine."""

    # ----- construction ---------------------------------------------------- #

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

        # Lazily-instantiated non-Engine systems, created on first use so we
        # don't pay the cost for players who never touch them.
        self._extras: dict[str, Any] = {}

        # Cache whether colour is enabled.
        self._color: bool = bool(getattr(self.engine.config.ui, "color_enabled", True))

    # ----- lazy extra-system accessors ------------------------------------ #

    def _extra(self, key: str, factory: Any) -> Any:
        """Get-or-create an auxiliary system not owned by the Engine."""
        if key not in self._extras:
            try:
                self._extras[key] = factory()
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to initialise system %s: %s", key, exc)
                return None
        return self._extras[key]

    @property
    def stealth(self):
        return self._extra("stealth", lambda: __import__(
            "engine.stealth.system", fromlist=["StealthSystem"]).StealthSystem(self.engine.rng))

    @property
    def runes(self):
        return self._extra("runes", lambda: __import__(
            "engine.runes.system", fromlist=["RuneSystem"]).RuneSystem(self.engine.rng))

    @property
    def artifacts(self):
        return self._extra("artifacts", lambda: __import__(
            "engine.artifacts.system", fromlist=["ArtifactSystem"]).ArtifactSystem(self.engine.rng))

    @property
    def auctions(self):
        return self._extra("auctions", lambda: __import__(
            "engine.auctions.system", fromlist=["AuctionHouse"]).AuctionHouse(self.engine.rng))

    @property
    def blackmarket(self):
        return self._extra("blackmarket", lambda: __import__(
            "engine.blackmarket.system", fromlist=["BlackMarketSystem"]).BlackMarketSystem(self.engine.rng))

    @property
    def bodyparts(self):
        return self._extra("bodyparts", lambda: __import__(
            "engine.bodyparts.system", fromlist=["BodyPartsSystem"]).BodyPartsSystem(self.engine.rng))

    @property
    def bookmarks(self):
        return self._extra("bookmarks", lambda: __import__(
            "engine.bookmarks.system", fromlist=["BookmarkManager"]).BookmarkManager())

    @property
    def companies(self):
        return self._extra("companies", lambda: __import__(
            "engine.companies.system", fromlist=["CompanySystem"]).CompanySystem(self.engine.rng))

    @property
    def dimensions(self):
        return self._extra("dimensions", lambda: __import__(
            "engine.dimensions.system", fromlist=["DimensionManager"]).DimensionManager(self.engine.rng))

    @property
    def dungeons(self):
        return self._extra("dungeons", lambda: __import__(
            "engine.dungeons.system", fromlist=["DungeonGenerator"]).DungeonGenerator(self.engine.rng))

    @property
    def espionage(self):
        return self._extra("espionage", lambda: __import__(
            "engine.espionage.system", fromlist=["EspionageSystem"]).EspionageSystem(self.engine.rng))

    @property
    def kingdoms(self):
        return self._extra("kingdoms", lambda: __import__(
            "engine.kingdoms.system", fromlist=["KingdomSystem"]).KingdomSystem(self.engine.rng))

    @property
    def life(self):
        return self._extra("life", lambda: __import__(
            "engine.life.system", fromlist=["LifeSimulator"]).LifeSimulator(self.engine.rng))

    @property
    def animals(self):
        return self._extra("animals", lambda: __import__(
            "engine.animals.system", fromlist=["AnimalSimulator"]).AnimalSimulator(self.engine.rng))

    @property
    def reputation(self):
        return self._extra("reputation", lambda: __import__(
            "engine.reputation.system", fromlist=["ReputationSystem"]).ReputationSystem())

    @property
    def rebellions(self):
        return self._extra("rebellions", lambda: __import__(
            "engine.rebellions.system", fromlist=["RebellionSystem"]).RebellionSystem(self.engine.rng))

    @property
    def trade(self):
        return self._extra("trade", lambda: __import__(
            "engine.trade.system", fromlist=["TradeSystem"]).TradeSystem(self.engine.rng))

    @property
    def proc_dialogue(self):
        return self._extra("proc_dialogue", lambda: __import__(
            "engine.procedural_dialogue.system",
            fromlist=["ProceduralDialogueEngine"]).ProceduralDialogueEngine(self.engine.rng))

    @property
    def skill_books(self):
        return self._extra("skill_books", lambda: __import__(
            "engine.skill_books.system", fromlist=["BookReadingSystem"]).BookReadingSystem(self.engine.rng))

    @property
    def skill_discovery(self):
        return self._extra("skill_discovery", lambda: __import__(
            "engine.skill_books.system",
            fromlist=["SkillDiscoverySystem"]).SkillDiscoverySystem(self.engine.rng))

    @property
    def naval_combat(self):
        return self._extra("naval_combat", lambda: __import__(
            "engine.naval_combat.system", fromlist=["NavalCombatSystem"]).NavalCombatSystem(self.engine.rng))

    @property
    def siege_combat(self):
        return self._extra("siege_combat", lambda: __import__(
            "engine.siege_combat.system", fromlist=["SiegeCombatSystem"]).SiegeCombatSystem(self.engine.rng))

    @property
    def aerial_combat(self):
        return self._extra("aerial_combat", lambda: __import__(
            "engine.aerial_combat.system", fromlist=["AerialCombatSystem"]).AerialCombatSystem(
                self.engine.rng, self.engine.combat))

    @property
    def space_combat(self):
        return self._extra("space_combat", lambda: __import__(
            "engine.space_combat.system", fromlist=["SpaceCombatSystem"]).SpaceCombatSystem(self.engine.rng))

    @property
    def realtime_combat(self):
        return self._extra("realtime_combat", lambda: __import__(
            "engine.realtime_combat.system",
            fromlist=["RealtimeCombatSystem"]).RealtimeCombatSystem(self.engine.rng, self.engine.combat))

    @property
    def mounted_combat(self):
        return self._extra("mounted_combat", lambda: __import__(
            "engine.mounted_combat.system",
            fromlist=["MountedCombatSystem"]).MountedCombatSystem(self.engine.rng, self.engine.combat))

    @property
    def background_sim(self):
        return self._extra("background_sim", lambda: __import__(
            "engine.background_sim.system",
            fromlist=["BackgroundSimulator"]).BackgroundSimulator(self.engine.rng))

    # ----- terminal setup -------------------------------------------------- #

    def enable_raw_mode(self) -> None:
        """Enable raw terminal mode for single-key input."""
        try:
            import termios
            import tty
            self._saved_term_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
            self._raw_mode = True
        except Exception:  # noqa: BLE001 — termios.error, ImportError, OSError, AttributeError…
            # Not a TTY or not Unix — fall back to line mode.
            self._raw_mode = False
            self._saved_term_settings = None

    def disable_raw_mode(self) -> None:
        """Restore terminal settings."""
        if self._saved_term_settings is not None:
            try:
                import termios
                termios.tcsetattr(
                    sys.stdin.fileno(), termios.TCSADRAIN, self._saved_term_settings,
                )
            except Exception:  # noqa: BLE001
                pass
        self._raw_mode = False
        self._saved_term_settings = None

    def _read_key(self) -> str:
        """Read a single keypress in raw mode."""
        try:
            ch = sys.stdin.read(1)
            if ch == "\x1b":  # escape sequence
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

    # ----- output ---------------------------------------------------------- #

    def print(self, text: str = "", color: Optional[int] = None,
              end: str = "\n") -> None:
        """Print coloured text — buffered if a panel is active."""
        line = _colour(text, color, self._color)
        if end == "\n":
            self._panel_buffer.append(line)
        else:
            if self._panel_buffer:
                self._panel_buffer[-1] += line
            else:
                self._panel_buffer.append(line)

    def print_header(self, text: str, color: int = Color.GOLD) -> None:
        width = 60
        line = "═" * width
        self.print(f"\n{text.center(width)}", color=color)
        self.print(line, color=color)

    def print_separator(self, color: int = Color.GRAY) -> None:
        self.print("─" * 60, color=color)

    def print_bar(self, label: str, current: float, maximum: float,
                  width: int = 20, color: int = Color.HEALTH) -> None:
        if maximum <= 0:
            fraction = 0
        else:
            fraction = current / maximum
        fraction = max(0.0, min(1.0, fraction))
        filled = int(width * fraction)
        bar = "█" * filled + "░" * (width - filled)
        self.print(f"  {label:12s} [{bar}] {int(current)}/{int(maximum)}",
                   color=color)

    def msg(self, text: str, color: int = Color.WHITE) -> None:
        """Add a message to the engine message log."""
        self.engine.message_log.add(text, color)

    # ----- game-state display --------------------------------------------- #

    def show_status_panel(self) -> None:
        if self.engine.player is None:
            return
        player = self.engine.player
        world = self.engine.world
        identity = world.get_component(player, Identity)
        health = world.get_component(player, Health)
        stats = world.get_component(player, Stats)
        needs = world.get_component(player, Needs)
        wealth = world.get_component(player, Wealth)
        position = world.get_component(player, Position)
        mana = world.get_component(player, Mana)
        name = identity.display_name if identity else "Hero"
        self.print_header(name, Color.GOLD)
        if health:
            self.print_bar("HP", health.current, health.maximum, color=Color.HEALTH)
        if mana:
            self.print_bar("MP", mana.current, mana.maximum, color=Color.MANA)
        if needs:
            self.print_bar("Hunger", needs.hunger, 100, color=Color.YELLOW)
            self.print_bar("Thirst", needs.thirst, 100, color=Color.CYAN)
            self.print_bar("Fatigue", needs.fatigue, 100, color=Color.MUTED)
            self.print_bar("Sleep", needs.sleep, 100, color=Color.PURPLE)
        if position:
            self.print(f"  Position: ({position.x}, {position.y})", Color.GRAY)
        if wealth:
            self.print(f"  Gold: {wealth.gold}  Silver: {wealth.silver}  Copper: {wealth.copper}",
                       color=Color.GOLD)
        try:
            time_str = self.engine.clock.time.display()
            weather_str = (self.engine.weather.current.description()
                           if self.engine.weather else "unknown")
            self.print(f"  {time_str} | {weather_str}", Color.CYAN)
        except Exception:  # noqa: BLE001
            pass
        self.print_separator()

    def show_map_view(self, radius: int = 12) -> None:
        if self.engine.player is None or self.engine.world_map is None:
            return
        player = self.engine.player
        pos = self.engine.world.get_component(player, Position)
        if pos is None:
            return
        world_map = self.engine.world_map
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
                entity_here = False
                for ent, (ep,) in self.engine.world.view(Position):
                    if ep.x == wx and ep.y == wy:
                        if ent.id == player.id:
                            row += "@"
                            entity_here = True
                            break
                        identity = self.engine.world.get_component(ent, Identity)
                        glyph = identity.glyph if identity else "?"
                        row += glyph
                        entity_here = True
                        break
                if not entity_here:
                    row += tile.terrain.glyph
            self.print(row)
        self.print_separator()

    def show_messages(self, n: int = 5) -> None:
        if not self.engine.message_log.messages:
            return
        self.print_header("Messages", Color.GOLD)
        for msg, color in self.engine.message_log.recent(n):
            self.print(f"  {msg}", color=color)
        self.print_separator()

    def show_inventory(self) -> None:
        if self.engine.player is None:
            return
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            self.print("You have no inventory.", Color.GRAY)
            return
        self.print_header("Inventory", Color.GOLD)
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
        if self.engine.player is None:
            return
        player = self.engine.player
        identity = self.engine.world.get_component(player, Identity)
        health = self.engine.world.get_component(player, Health)
        stats = self.engine.world.get_component(player, Stats)
        race = self.engine.world.get_component(player, Race)
        wealth = self.engine.world.get_component(player, Wealth)
        self.print_header("Character", Color.GOLD)
        if identity:
            self.print(f"  Name: {identity.display_name}", Color.WHITE)
            if identity.description:
                self.print(f"  Description: {identity.description}", Color.GRAY)
        if race:
            self.print(f"  Race: {race.race_id.title()}  Age: {race.age}",
                       color=Color.WHITE)
        if health:
            self.print(f"  HP: {health.current}/{health.maximum}", Color.HEALTH)
        if wealth:
            self.print(f"  Wealth: {_format_money(wealth.total_copper())}",
                       color=Color.GOLD)
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
        from engine.magic.spells import SpellLibrary
        self.print_header("Spells", Color.GOLD)
        mana = (self.engine.world.get_component(self.engine.player, Mana)
                if self.engine.player else None)
        if mana:
            self.print(f"  MP: {mana.current:.0f}/{mana.maximum:.0f}", Color.MANA)
            self.print()
        spells = list(SpellLibrary.all())
        if not spells:
            self.print("  No spells are known to exist.", Color.GRAY)
        for spell in spells:
            line = f"  {spell.name:25s} cost: {spell.mana_cost:3d} MP"
            if spell.target.value != "self":
                line += f"  ({spell.target.value})"
            self.print(line, color=Color.MANA)
        self.print_separator()

    def show_skills(self) -> None:
        from engine.entities.components import Skills as SkillsComp
        from engine.skills.system import SkillLibrary
        comp = (self.engine.world.get_component(self.engine.player, SkillsComp)
                if self.engine.player else None)
        self.print_header("Skills", Color.GOLD)
        if comp is None or not comp.skills:
            self.print("  You have no skills yet.", Color.GRAY)
            self.print("  Try: train <skill> with self", Color.GRAY)
        else:
            for skill_id, sl in sorted(comp.skills.items(),
                                        key=lambda x: -x[1].level):
                skill = SkillLibrary.get(skill_id)
                name = skill.name if skill else skill_id
                self.print(f"  {name:25s} Lv: {sl.level:3d}  XP: {sl.xp:.0f}",
                           color=Color.WHITE)
        self.print_separator()

    # ----- movement & look ------------------------------------------------- #

    def cmd_look(self, args: list[str]) -> None:
        if self.engine.player is None or self.engine.world_map is None:
            return
        player = self.engine.player
        pos = self.engine.world.get_component(player, Position)
        if pos is None:
            return
        if args:
            target = self._find_entity_by_name(" ".join(args))
            if target is not None:
                self._describe_entity(target)
                return
            self.print(f"You don't see any '{' '.join(args)}' here.", Color.GRAY)
            return
        self.print_header("You see...", Color.GOLD)
        tile = self.engine.world_map.get_tile(pos.x, pos.y)
        if tile:
            biome_name = tile.biome_type.replace("_", " ").title()
            self.print(f"  Terrain: {tile.terrain.glyph} {biome_name}", Color.GRAY)
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
        if not args:
            self.print("Go where? Try: go north (or just: k)", Color.GRAY)
            return
        direction = args[0].lower()
        if direction not in DIRECTIONS:
            self.print(f"Unknown direction: {direction}", Color.RED)
            self.print(f"Valid: {', '.join(sorted(set(DIRECTIONS.keys())))}",
                       color=Color.GRAY)
            return
        dx, dy, name = DIRECTIONS[direction]
        self.engine.move_player(dx, dy)

    def cmd_attack(self, args: list[str]) -> None:
        if not args:
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
        player_pos = self.engine.world.get_component(self.engine.player, Position)
        target_pos = self.engine.world.get_component(target, Position)
        if player_pos and target_pos:
            dist = max(abs(player_pos.x - target_pos.x),
                       abs(player_pos.y - target_pos.y))
            if dist > 1:
                self.print("Target is too far away.", Color.RED)
                return
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

    # ----- magic ----------------------------------------------------------- #

    def cmd_cast(self, args: list[str]) -> None:
        from engine.magic.spells import SpellLibrary
        if not args:
            self.print("Cast what? Try: cast fireball", Color.GRAY)
            self.show_spells()
            return
        spell_name = " ".join(args).lower()
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
        target = None
        if spell.target.value in ("enemy", "ally", "item"):
            target = self._find_adjacent_hostile()
            if target is None:
                target = self._find_nearest_entity(exclude_player=True)
        result = self.engine.spell_caster.cast(
            self.engine.world, self.engine.player, spell, target,
        )
        if result.message:
            self.engine.message_log.add(result.message,
                                         Color.YELLOW if result.success else Color.RED)
        if result.damage_dealt > 0:
            self.engine.message_log.add(
                f"  Dealt {result.damage_dealt:.0f} damage!", Color.RED,
            )
        if result.healing_done > 0:
            self.engine.message_log.add(
                f"  Restored {result.healing_done:.0f} HP!", Color.GREEN,
            )
        if result.killed_targets if hasattr(result, 'killed_targets') else False:
            for dead in getattr(result, 'killed_targets', []):
                self.engine._handle_death(dead, self.engine.player)

    def cmd_research(self, args: list[str]) -> None:
        """Start a spell-research project: research <name> <school_id>."""
        if len(args) < 2:
            self.print("Usage: research <name> <school_id>", Color.GRAY)
            self.print("Schools: evocation, conjuration, enchantment, necromancy,",
                       color=Color.GRAY)
            self.print("         abjuration, transmutation, divination, illusion",
                       color=Color.GRAY)
            return
        name = args[0]
        school_id = args[1]
        project = self.engine.spell_researcher.start_project(
            name=name, school_id=school_id, researcher=self.engine.player,
        )
        self.msg(f"Started research project '{name}' (school: {school_id}).",
                 Color.MANA)
        self.msg(f"  Required progress: {project.required_progress:.0f}",
                 Color.GRAY)

    def cmd_meditate(self, args: list[str]) -> None:
        """Advance research by meditating for some hours (default 1)."""
        hours = 1.0
        if args:
            try:
                hours = float(args[0])
            except ValueError:
                self.print("Usage: meditate [hours]", Color.GRAY)
                return
        from engine.entities.components import Skills as SkillsComp
        comp = self.engine.world.get_component(self.engine.player, SkillsComp)
        skill_levels: dict[str, int] = {}
        if comp:
            for sid, sl in comp.skills.items():
                skill_levels[sid] = sl.level
        new_spells = self.engine.spell_researcher.update(
            {self.engine.player.id: skill_levels}, hours,
        )
        self.msg(f"You meditate for {hours:.1f} hours.", Color.MANA)
        for sp in new_spells:
            self.msg(f"  Discovery! You've researched a new spell: {sp.name}.",
                     Color.GREEN)

    def cmd_schools(self, args: list[str]) -> None:
        from engine.magic.schools import SchoolLibrary
        self.print_header("Magic Schools", Color.GOLD)
        for s in SchoolLibrary.all():
            self.print(f"  {s.id:15s} {s.name}", Color.MANA)
            if s.description:
                self.print(f"    {s.description}", Color.GRAY)
        self.print_separator()

    # ----- items & inventory ---------------------------------------------- #

    def cmd_use(self, args: list[str]) -> None:
        if not args:
            self.print("Use what? Try: use health potion", Color.GRAY)
            return
        item_name = " ".join(args).lower()
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            return
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower() or item_name in item.name.lower():
                self._use_item(item)
                return
        self.print(f"You don't have any '{item_name}'.", Color.RED)

    def _use_item(self, item: Any) -> None:
        from engine.entities.components import Needs as NeedsComp
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
            inv = self.engine.inventories.get(self.engine.player.id)
            if inv:
                inv.remove(item.id, 1)
        else:
            self.print(f"You can't use {item.display_name}.", Color.GRAY)

    def cmd_equip(self, args: list[str]) -> None:
        if not args:
            self.print("Equip what? Try: equip dagger", Color.GRAY)
            return
        item_name = " ".join(args).lower()
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            return
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower() or item_name in item.name.lower():
                if item.category == "weapon":
                    comp = self.engine.world.get_component(self.engine.player, CombatComp)
                    if comp is None:
                        comp = CombatComp()
                        self.engine.world.add_component(self.engine.player, comp)
                    inv.remove(item.id, 1)
                    if comp.weapon_id is not None:
                        old = self.engine.items.get(comp.weapon_id)
                        if old:
                            inv.add(old, 1)
                    comp.weapon_id = item.id
                    self.engine.message_log.add(
                        f"You equip {item.display_name}.", Color.GREEN,
                    )
                    return
                elif item.category == "armor":
                    comp = self.engine.world.get_component(self.engine.player, CombatComp)
                    if comp is None:
                        comp = CombatComp()
                        self.engine.world.add_component(self.engine.player, comp)
                    slot_name = "chest"
                    inv.remove(item.id, 1)
                    old_id = comp.armor_ids.get(slot_name)
                    if old_id is not None:
                        old = self.engine.items.get(old_id)
                        if old:
                            inv.add(old, 1)
                    comp.armor_ids[slot_name] = item.id
                    self.engine.message_log.add(
                        f"You equip {item.display_name}.", Color.GREEN,
                    )
                    return
                else:
                    self.print(f"You can't equip {item.display_name}.", Color.GRAY)
                    return
        self.print(f"You don't have any '{item_name}'.", Color.RED)

    def cmd_drop(self, args: list[str]) -> None:
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
                pos = self.engine.world.get_component(self.engine.player, Position)
                if pos:
                    self.engine.factory.create_item_entity(item.id, pos.x, pos.y)
                self.engine.message_log.add(
                    f"You drop {item.display_name}.", Color.GRAY,
                )
                return
        self.print(f"You don't have any '{item_name}'.", Color.RED)

    def cmd_pickup(self, args: list[str]) -> None:
        if self.engine.player is None:
            return
        pos = self.engine.world.get_component(self.engine.player, Position)
        if pos is None:
            return
        picked_up = False
        for ent, (ep,) in list(self.engine.world.view(Position)):
            if ep.x != pos.x or ep.y != pos.y:
                continue
            if not self.engine.world.has_tag(ent, "item"):
                continue
            tag_comp = self.engine.world.get_component(ent, Tag)
            if tag_comp is None:
                continue
            item_id = None
            for t in tag_comp.tags:
                if t.startswith("item:"):
                    try:
                        item_id = int(t.split(":")[1])
                    except (ValueError, IndexError):
                        continue
                    break
            if item_id is None:
                continue
            item = self.engine.items.get(item_id)
            if item is None:
                continue
            inv = self.engine.inventories.get(self.engine.player.id)
            if inv:
                inv.add(item, 1)
                self.engine.message_log.add(
                    f"You pick up {item.display_name}.", Color.GREEN,
                )
                picked_up = True
            self.engine.world.destroy_entity(ent)
        if not picked_up:
            self.engine.message_log.add("There's nothing to pick up.", Color.GRAY)

    def cmd_unequip(self, args: list[str]) -> None:
        comp = (self.engine.world.get_component(self.engine.player, CombatComp)
                if self.engine.player else None)
        if comp is None:
            self.print("You have nothing equipped.", Color.GRAY)
            return
        if not args:
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

    # ----- dialogue & trade ----------------------------------------------- #

    def cmd_trade(self, args: list[str]) -> None:
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
        identity = self.engine.world.get_component(target, Identity)
        name = identity.display_name if identity else "Merchant"
        self.print_header(f"Trading with {name}", Color.GOLD)
        wealth = self.engine.world.get_component(self.engine.player, Wealth)
        self.print(f"  Your money: {_format_money(wealth.total_copper()) if wealth else '0c'}",
                   color=Color.GOLD)
        self.print("  Available goods (use 'buy <good> <qty>'):", Color.YELLOW)
        from engine.economy.market import TradeGoodLibrary
        for g in list(TradeGoodLibrary.all())[:10]:
            self.print(f"    {g.id:20s} base {g.base_price}cp  ({g.name})", Color.WHITE)
        self.print_separator()

    def cmd_buy(self, args: list[str]) -> None:
        if len(args) < 1:
            self.print("Usage: buy <good_id> [quantity]", Color.GRAY)
            return
        good_id = args[0]
        qty = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
        # Use the engine economy's first market if available
        if not self.engine.economy.markets:
            self.engine.economy.create_market("m1", "General Store", (0, 0))
        market = list(self.engine.economy.markets.values())[0]
        wealth = self.engine.world.get_component(self.engine.player, Wealth)
        if wealth is None:
            self.print("You have no wealth component.", Color.RED)
            return
        bought, cost = market.buy(good_id, qty, wealth.total_copper())
        if bought > 0:
            # Deduct copper-first, then silver, then gold.
            remaining = cost
            if wealth.copper >= remaining:
                wealth.copper -= remaining
                remaining = 0
            else:
                remaining -= wealth.copper
                wealth.copper = 0
            if remaining > 0:
                cs = remaining // 100
                if wealth.silver >= cs:
                    wealth.silver -= cs
                    remaining -= cs * 100
                else:
                    remaining -= wealth.silver * 100
                    wealth.silver = 0
            if remaining > 0:
                cg = (remaining + 9999) // 10000
                wealth.gold = max(0, wealth.gold - cg)
            self.msg(f"You buy {bought}x {good_id} for {cost}cp.", Color.GREEN)
        else:
            self.msg(f"Could not buy {good_id} (insufficient gold or supply).",
                     Color.RED)

    def cmd_sell(self, args: list[str]) -> None:
        if len(args) < 1:
            self.print("Usage: sell <good_id> [quantity]", Color.GRAY)
            return
        good_id = args[0]
        qty = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
        if not self.engine.economy.markets:
            self.engine.economy.create_market("m1", "General Store", (0, 0))
        market = list(self.engine.economy.markets.values())[0]
        sold, revenue = market.sell(good_id, qty)
        wealth = self.engine.world.get_component(self.engine.player, Wealth)
        if wealth and revenue > 0:
            wealth.copper += revenue
        self.msg(f"You sell {sold}x {good_id} for {revenue}cp.", Color.GREEN)

    def cmd_market(self, args: list[str]) -> None:
        from engine.economy.market import TradeGoodLibrary
        if not self.engine.economy.markets:
            self.engine.economy.create_market("m1", "General Store", (0, 0))
        market = list(self.engine.economy.markets.values())[0]
        self.print_header(f"Market: {market.name}", Color.GOLD)
        for g in TradeGoodLibrary.all():
            price = market.price_for(g.id)
            self.print(f"  {g.id:20s} {price:5d}cp  ({g.name})", Color.WHITE)
        self.print_separator()

    def cmd_talk(self, args: list[str]) -> None:
        from engine.dialogue.system import DialogueEngine, DialogueLibrary
        if args:
            target = self._find_entity_by_name(" ".join(args))
        else:
            target = self._find_adjacent_npc()
        if target is None:
            self.print("There's no one to talk to.", Color.GRAY)
            return
        identity = self.engine.world.get_component(target, Identity)
        name = identity.display_name if identity else "stranger"
        tree_id = "commoner_greeting"
        if self.engine.world.has_tag(target, "merchant"):
            tree_id = "merchant_greeting"
        elif self.engine.world.has_tag(target, "guard"):
            tree_id = "guard_greeting"
        tree = DialogueLibrary.get(tree_id)
        if tree is None:
            tree = DialogueLibrary.get("commoner_greeting")
        if tree is None:
            # Use procedural dialogue as a fallback.
            self._procedural_talk(target)
            return
        self._dialogue_tree = tree
        self._dialogue_ctx = self.engine.dialogue.start(
            self.engine.world, self.engine.player, target, tree,
        )
        self._in_dialogue = True
        self._show_dialogue_node()

    def _procedural_talk(self, target: Entity) -> None:
        """Fall back to procedural dialogue when no tree is registered."""
        identity = self.engine.world.get_component(target, Identity)
        name = identity.display_name if identity else "stranger"
        from engine.procedural_dialogue.system import NPCContext
        ctx = NPCContext(npc_name=name, npc_occupation="commoner",
                         npc_mood="neutral", relationship_to_player=0.0)
        line = self.proc_dialogue.generate_greeting(ctx)
        self.print_header(f"Conversation with {name}", Color.GOLD)
        self.print(f"  {name}: {line.text}", Color.YELLOW)
        self.print("  [1] Ask about rumours", Color.WHITE)
        self.print("  [2] Ask about the weather", Color.WHITE)
        self.print("  [3] Ask about trade", Color.WHITE)
        self.print("  [0] End conversation", Color.GRAY)
        self.print_separator()
        # We re-use the dialogue machinery with a synthetic tree-less state.
        self._in_dialogue = True
        self._dialogue_tree = None  # mark procedural
        self._dialogue_ctx = (target, ctx)

    def _show_dialogue_node(self) -> None:
        if self._dialogue_tree is None or self._dialogue_ctx is None:
            self._in_dialogue = False
            return
        node = self._dialogue_tree.get(self._dialogue_ctx.current_node_id)
        if node is None:
            self._in_dialogue = False
            return
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
        # Procedural dialogue path.
        if self._dialogue_tree is None and isinstance(self._dialogue_ctx, tuple):
            target, ctx = self._dialogue_ctx
            identity = self.engine.world.get_component(target, Identity)
            npc_name = identity.display_name if identity else "NPC"
            topic = {"1": "rumours", "2": "weather", "3": "trade"}.get(line)
            if topic is None:
                self.print("Invalid choice.", Color.RED)
                return True
            line_obj = self.proc_dialogue.generate_topic_line(topic, ctx)
            self.print(f"  {npc_name}: {line_obj.text}", Color.YELLOW)
            self.print("  [1] Ask about rumours", Color.WHITE)
            self.print("  [2] Ask about the weather", Color.WHITE)
            self.print("  [3] Ask about trade", Color.WHITE)
            self.print("  [0] End conversation", Color.GRAY)
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
        for effect in choice.effects:
            try:
                effect(self._dialogue_ctx)
            except Exception:  # noqa: BLE001
                pass
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

    # ----- time, rest, sleep ---------------------------------------------- #

    def cmd_wait(self, args: list[str]) -> None:
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
        from engine.entities.components import Needs as NeedsComp
        hour = self.engine.clock.time.hour
        if hour < 6:
            hours_to_sleep = 6 - hour
        else:
            hours_to_sleep = 24 - hour + 6
        ticks = hours_to_sleep * 60 * self.engine.clock.ticks_per_game_minute
        self.engine.clock.advance_ticks(ticks)
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

    # ----- help & status --------------------------------------------------- #

    def cmd_help(self, args: list[str]) -> None:
        self.print_header("Aeon Engine — Help", Color.GOLD)
        categories = [
            ("Movement", [
                "h j k l (vi-keys) or wasd or arrows",
                "y u b n for diagonals",
                "go <direction>   move in a direction",
                ".                wait one tick",
            ]),
            ("Actions", [
                "look [target]    look around or at a target (l)",
                "attack <target>  attack an entity (a)",
                "cast <spell>     cast a spell",
                "use <item>       use an item (eat/drink)",
                "equip <item>     equip a weapon or armor",
                "unequip <slot>   unequip (weapon/chest)",
                "drop <item>      drop an item",
                "pickup           pick up items on the ground",
                "talk [npc]       talk to an NPC (t)",
                "trade [npc]      trade with a merchant",
            ]),
            ("Character", [
                "inventory        show inventory (i)",
                "character        show character sheet (c)",
                "status           show status panel (st)",
                "spells           list known spells (sp)",
                "skills           list skills (sk)",
                "schools          list magic schools",
            ]),
            ("Magic", [
                "cast <spell>     cast a spell",
                "research <name> <school>   start a research project",
                "meditate [hours] advance research",
            ]),
            ("Crafting & Skills", [
                "craft <recipe>   craft an item",
                "recipes          list recipes",
                "train <skill> [hours]  train a skill",
                "use_skill <skill> [difficulty]  attempt a skill check",
                "read <book_id>   read a skill book",
                "books            list available books",
                "inscribe <rune> on <item>  inscribe a rune",
                "runes            list runes",
            ]),
            ("Economy", [
                "market           show market prices",
                "buy <good> [qty] buy a trade good",
                "sell <good> [qty] sell a trade good",
                "bank <deposit|withdraw|balance> [amount]",
                "loan <take|repay> <amount> [months]",
                "caravan <route> <good> <qty>  dispatch caravan",
                "ship <route> <good> <qty>     dispatch trade ship",
                "trade_routes     list trade routes",
            ]),
            ("Auctions & Black Market", [
                "auction list     list active auctions",
                "auction sell <item> <price>  schedule auction",
                "bid <id> <amount> place a bid",
                "blackmarket list  list black market goods",
                "blackmarket buy <listing>",
                "fence <item>     fence a stolen item",
                "hire_assassin <target>  hire an assassin",
            ]),
            ("Quests & Factions", [
                "quests           show quest log",
                "quest list       list available quests",
                "quest accept <id>  accept a quest",
                "quest advance <id> <stage> <obj> [n]",
                "quest complete <id>",
                "quest abandon <id>",
                "factions         list factions",
                "faction <id>     show faction info",
            ]),
            ("Kingdoms & Politics", [
                "kingdoms         list kingdoms",
                "kingdom <id>     show kingdom info",
                "war <a> <b>      declare war",
                "peace <a> <b>    make peace",
                "alliance <a> <b> form alliance",
                "annex <kingdom> <territory>",
                "election <kingdom>",
            ]),
            ("Espionage & Rebellion", [
                "recruit_spy <entity_id> <name>",
                "mission <spy_id> <type> <target>",
                "resolve_mission <id>",
                "spies            list your spies",
                "rebellion <type> <faction>  start rebellion",
                "suppress <id>    suppress a rebellion",
                "negotiate <id>   negotiate settlement",
            ]),
            ("Combat Variants", [
                "naval <bombard|board> <ship_id>",
                "siege <create|bombard|assault> ...",
                "aerial <mount|dive|attack> ...",
                "space <fire|launch> ...",
                "realtime <queue|cancel> ...",
                "mount <mount|dismount|charge> ...",
            ]),
            ("Survival & Life", [
                "rest             rest for an hour",
                "sleep            sleep until morning",
                "wait [minutes]   wait (. for default)",
                "diseases         list known diseases",
                "cure <disease>   attempt to cure",
                "marry <partner>  marry an NPC",
                "divorce <partner>",
                "family           show family info",
                "job              find a job",
            ]),
            ("Dungeons & Exploration", [
                "dungeon <type> [depth]  generate a dungeon",
                "enter_dungeon <id>",
                "bookmark add <name>",
                "bookmark list",
                "pin <x> <y> [label]",
            ]),
            ("Animals & Hunting", [
                "hunt <species>   hunt an animal",
                "tame <species>   attempt to tame",
                "livestock        list livestock",
                "animals          list species",
            ]),
            ("Artifacts", [
                "artifacts        list known artifacts",
                "wield <artifact>",
                "power <artifact> <power>",
                "talk_artifact <artifact>",
                "destroy <artifact> <method>",
            ]),
            ("Reputation", [
                "reputation       show your reputation",
                "hero <deed>      perform a heroic deed",
                "crime <type>     commit a crime",
            ]),
            ("Stealth", [
                "stealth on       enter stealth",
                "stealth off      exit stealth",
                "backstab <target>",
            ]),
            ("World & Time", [
                "map              show world map (m)",
                "time             show game time",
                "weather          show weather",
                "simulate [hours] simulate background time",
            ]),
            ("Themes & Dimensions", [
                "theme list       list themes",
                "theme set <name> switch theme",
                "dimensions       list dimensions",
                "portal <from> <to>  open portal",
                "travel <dim>     travel to dimension",
            ]),
            ("Body Parts", [
                "bodyparts        show body part status",
                "heal_part <part> [amount]",
            ]),
            ("System", [
                "save [name]      save the game",
                "load <name>      load a save",
                "plugins          list plugins",
                "contentpacks     list content packs",
                "help             this message (?)",
                "Quit             exit the game (q)",
            ]),
        ]
        for cat, lines in categories:
            self.print(f"  {cat}:", Color.CYAN)
            for ln in lines:
                self.print(f"    {ln}", Color.WHITE)
            self.print()
        self.print_separator()

    def cmd_status(self, args: list[str]) -> None:
        self.show_status_panel()

    def cmd_inventory(self, args: list[str]) -> None:
        self.show_inventory()

    def cmd_character(self, args: list[str]) -> None:
        self.show_character_sheet()

    def cmd_map(self, args: list[str]) -> None:
        self.show_map_view(radius=20)

    def cmd_spells(self, args: list[str]) -> None:
        self.show_spells()

    def cmd_skills(self, args: list[str]) -> None:
        self.show_skills()

    def cmd_quests(self, args: list[str]) -> None:
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

    def cmd_quest(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: quest <list|accept|advance|complete|abandon> ...",
                       color=Color.GRAY)
            return
        sub = args[0].lower()
        from engine.quests.system import QuestLibrary
        tracker = self.engine.quest_trackers.get(self.engine.player.id)
        if tracker is None:
            tracker = self.engine.quest_trackers.setdefault(
                self.engine.player.id, type(tracker)() if tracker else
                __import__("engine.quests.system", fromlist=["QuestTracker"]).QuestTracker())
        if sub == "list":
            self.print_header("Available Quests", Color.GOLD)
            for q in QuestLibrary.all():
                self.print(f"  #{q.id}  {q.name}", Color.WHITE)
                self.print(f"    {q.description}", Color.GRAY)
            self.print_separator()
        elif sub == "accept":
            if len(args) < 2:
                self.print("Usage: quest accept <quest_id>", Color.GRAY)
                return
            q = QuestLibrary.get(args[1])
            if q is None:
                self.print(f"Unknown quest: {args[1]}", Color.RED)
                return
            tracker.start(q, self.engine.clock.time.tick)
            self.msg(f"Quest accepted: {q.name}", Color.GREEN)
        elif sub == "advance":
            if len(args) < 4:
                self.print("Usage: quest advance <quest_id> <stage> <obj> [n]",
                           color=Color.GRAY)
                return
            amount = int(args[4]) if len(args) > 4 and args[4].isdigit() else 1
            tracker.advance_objective(args[1], args[2], args[3], amount)
            self.msg(f"Objective advanced: {args[3]} (+{amount})", Color.GREEN)
        elif sub == "complete":
            if len(args) < 2:
                self.print("Usage: quest complete <quest_id>", Color.GRAY)
                return
            tracker.complete_quest(args[1])
            self.msg(f"Quest completed: {args[1]}", Color.GREEN)
        elif sub == "abandon":
            if len(args) < 2:
                self.print("Usage: quest abandon <quest_id>", Color.GRAY)
                return
            tracker.abandon_quest(args[1])
            self.msg(f"Quest abandoned: {args[1]}", Color.YELLOW)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_time(self, args: list[str]) -> None:
        time_str = self.engine.clock.time.display()
        phase = self.engine.clock.time.phase_of_day().display_name
        season = self.engine.clock.time.season_name()
        self.print_header("Time", Color.GOLD)
        self.print(f"  {time_str}", Color.CYAN)
        self.print(f"  Phase: {phase}", Color.GRAY)
        self.print(f"  Season: {season}", Color.GRAY)
        self.print(f"  Tick: {self.engine.clock.time.tick}", Color.GRAY)
        self.print_separator()

    def cmd_weather(self, args: list[str]) -> None:
        if self.engine.weather is None:
            return
        self.print_header("Weather", Color.GOLD)
        self.print(f"  {self.engine.weather.current.description()}", Color.CYAN)
        self.print_separator()

    def cmd_plugins(self, args: list[str]) -> None:
        self.print_header("Plugins", Color.GOLD)
        try:
            for s in self.engine.plugins.status():
                self.print(f"  {s['name']:25s} v{s['version']:8s} [{s['state']}]",
                           color=Color.WHITE)
        except Exception as exc:  # noqa: BLE001
            self.print(f"  Error listing plugins: {exc}", Color.RED)
        self.print_separator()

    def cmd_save(self, args: list[str]) -> None:
        name = args[0] if args else "quicksave"
        try:
            self.engine.save_game(name)
            self.engine.message_log.add(f"Game saved as '{name}'.", Color.GREEN)
        except Exception as exc:  # noqa: BLE001
            self.engine.message_log.add(f"Save failed: {exc}", Color.RED)

    def cmd_load(self, args: list[str]) -> None:
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
        self.running = False
        self.engine.shutdown()

    def cmd_fish(self, args: list[str]) -> None:
        if self.engine.player is None:
            return
        pos = self.engine.world.get_component(self.engine.player, Position)
        if pos is None or self.engine.world_map is None:
            return
        water_adjacent = False
        for n in self.engine.world_map.neighbours(pos.x, pos.y):
            if n.terrain.is_liquid:
                water_adjacent = True
                break
        if not water_adjacent:
            self.engine.message_log.add("You need to be near water to fish.",
                                         Color.GRAY)
            return
        if self.engine.rng.chance(0.5):
            from engine.items.generator import ItemGenerationParams
            fish_types = ["fish", "salmon", "trout"]
            fish_name = self.engine.rng.choice(fish_types)
            params = ItemGenerationParams(
                archetype="bread",
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

    # ----- crafting & skills ---------------------------------------------- #

    def cmd_craft(self, args: list[str]) -> None:
        if not args:
            self.print("Craft what? Try: craft iron_dagger", Color.GRAY)
            self.cmd_recipes([])
            return
        from engine.crafting.system import RecipeLibrary
        recipe = RecipeLibrary.get(args[0])
        if recipe is None:
            self.print(f"Unknown recipe: {args[0]}", Color.RED)
            return
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            self.print("You have no inventory.", Color.RED)
            return
        # Gather available materials from inventory.
        materials: dict[str, int] = {}
        for _, item, count in inv.iter_items(self.engine.items):
            for tag in item.tags:
                materials[tag] = materials.get(tag, 0) + count
            materials[item.base_type] = materials.get(item.base_type, 0) + count
        from engine.entities.components import Skills as SkillsComp
        comp = self.engine.world.get_component(self.engine.player, SkillsComp)
        skill_level = 0
        if comp and recipe.skill_id in comp.skills:
            skill_level = comp.skills[recipe.skill_id].level
        result = self.engine.crafting.craft(
            recipe, self.engine.player, materials, skill_level,
            item_id=self.engine.items.next_id(),
        )
        if result.success and result.item:
            self.engine.items.register(result.item)
            inv.add(result.item)
            if comp is None:
                from engine.entities.components import Skills as SkillsComp2
                comp = SkillsComp2()
                self.engine.world.add_component(self.engine.player, comp)
            self.engine.skills.add_xp(self.engine.player, recipe.skill_id,
                                       result.xp_gained, self.engine.world)
            self.msg(f"You craft {result.item.display_name}! (+{result.xp_gained:.0f} XP)",
                     Color.GREEN)
        else:
            self.msg(f"Crafting failed: {result.message}", Color.RED)

    def cmd_recipes(self, args: list[str]) -> None:
        from engine.crafting.system import RecipeLibrary
        self.print_header("Recipes", Color.GOLD)
        for r in RecipeLibrary.all():
            self.print(f"  {r.id:20s} {r.name}", Color.WHITE)
            self.print(f"    skill: {r.skill_id} (level {r.skill_level_required})",
                       color=Color.GRAY)
            mats = ", ".join(f"{n}x{k}" for k, n in r.materials.items())
            self.print(f"    materials: {mats}", Color.GRAY)
        self.print_separator()

    def cmd_train(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: train <skill> [hours]", Color.GRAY)
            return
        skill_id = args[0]
        hours = float(args[1]) if len(args) > 1 else 1.0
        new_level = self.engine.skills.train(
            self.engine.player, skill_id, 10, hours, self.engine.world,
        )
        self.msg(f"You train {skill_id} for {hours:.1f} hours. Now level {new_level}.",
                 Color.GREEN)

    def cmd_use_skill(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: use_skill <skill> [difficulty]", Color.GRAY)
            return
        skill_id = args[0]
        difficulty = float(args[1]) if len(args) > 1 else 10.0
        result = self.engine.skills.check(
            self.engine.player, skill_id, difficulty, self.engine.rng,
        )
        if result.success:
            self.msg(f"Success! {skill_id} check (roll {result.roll:.1f} vs {difficulty:.1f}).",
                     Color.GREEN)
        else:
            self.msg(f"Failure. {skill_id} check (roll {result.roll:.1f} vs {difficulty:.1f}).",
                     Color.RED)

    def cmd_read(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: read <book_id>", Color.GRAY)
            return
        from engine.skill_books.system import SkillBookLibrary
        book = SkillBookLibrary.get(args[0])
        if book is None:
            self.print(f"Unknown book: {args[0]}", Color.RED)
            return
        ok, msg = self.skill_books.start_reading(self.engine.player, book)
        self.msg(msg, Color.GREEN if ok else Color.RED)

    def cmd_books(self, args: list[str]) -> None:
        from engine.skill_books.system import SkillBookLibrary
        self.print_header("Skill Books", Color.GOLD)
        for b in SkillBookLibrary.all():
            self.print(f"  {b.book_id:25s} {b.title}", Color.WHITE)
            self.print(f"    type: {b.book_type.value}  skill: {b.skill_id}",
                       color=Color.GRAY)
        self.print_separator()

    def cmd_inscribe(self, args: list[str]) -> None:
        """inscribe <rune_id> on <item_name>"""
        if len(args) < 3 or args[1] != "on":
            self.print("Usage: inscribe <rune_id> on <item_name>", Color.GRAY)
            return
        rune_id = args[0]
        item_name = " ".join(args[2:]).lower()
        from engine.runes.system import RuneLibrary
        rune = RuneLibrary.get(rune_id)
        if rune is None:
            self.print(f"Unknown rune: {rune_id}", Color.RED)
            return
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            return
        target_item = None
        for _, item, _ in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower() or item_name in item.name.lower():
                target_item = item
                break
        if target_item is None:
            self.print(f"You don't have any '{item_name}'.", Color.RED)
            return
        from engine.entities.components import Skills as SkillsComp
        comp = self.engine.world.get_component(self.engine.player, SkillsComp)
        skill_level = (comp.skills.get("rune_carving").level
                       if comp and "rune_carving" in comp.skills else 0)
        ok, msg, insc = self.runes.inscribe(
            target_item.id, rune, inscribed_by=self.engine.player.id,
            skill_level=skill_level, current_tick=self.engine.clock.time.tick,
        )
        self.msg(msg, Color.GREEN if ok else Color.RED)

    def cmd_runes(self, args: list[str]) -> None:
        from engine.runes.system import RuneLibrary
        self.print_header("Runes", Color.GOLD)
        for r in RuneLibrary.all():
            self.print(f"  {r.rune_id:20s} {r.name}", Color.WHITE)
            self.print(f"    type: {r.rune_type.value}  power: {r.base_power}",
                       color=Color.GRAY)
        self.print_separator()

    # ----- economy: bank / loan ------------------------------------------- #

    def cmd_bank(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: bank <deposit|withdraw|balance> [amount]",
                       color=Color.GRAY)
            return
        sub = args[0].lower()
        if not self.engine.economy.banks:
            self.engine.economy.create_bank("b1", "Central Bank", (0, 0))
        bank = list(self.engine.economy.banks.values())[0]
        pid = self.engine.player.id
        if sub == "balance":
            acct = bank.accounts.get(pid)
            if acct:
                self.msg(f"Bank balance: {_format_money(acct.balance)}", Color.GOLD)
            else:
                self.msg("You have no bank account.", Color.GRAY)
        elif sub == "deposit":
            if len(args) < 2 or not args[1].isdigit():
                self.print("Usage: bank deposit <amount_copper>", Color.GRAY)
                return
            amount = int(args[1])
            wealth = self.engine.world.get_component(self.engine.player, Wealth)
            if wealth is None or wealth.total_copper() < amount:
                self.msg("You don't have that much money.", Color.RED)
                return
            # Deduct from wealth.
            bank.open_account(pid)
            bank.deposit(pid, amount)
            wealth.copper = max(0, wealth.copper - amount)
            self.msg(f"Deposited {_format_money(amount)}.", Color.GREEN)
        elif sub == "withdraw":
            if len(args) < 2 or not args[1].isdigit():
                self.print("Usage: bank withdraw <amount_copper>", Color.GRAY)
                return
            amount = int(args[1])
            withdrawn = bank.withdraw(pid, amount)
            if withdrawn > 0:
                wealth = self.engine.world.get_component(self.engine.player, Wealth)
                if wealth:
                    wealth.copper += withdrawn
                self.msg(f"Withdrew {_format_money(withdrawn)}.", Color.GREEN)
            else:
                self.msg("Insufficient bank balance.", Color.RED)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_loan(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: loan <take|repay> <amount> [months]", Color.GRAY)
            return
        sub = args[0].lower()
        if not self.engine.economy.banks:
            self.engine.economy.create_bank("b1", "Central Bank", (0, 0))
        bank = list(self.engine.economy.banks.values())[0]
        pid = self.engine.player.id
        if sub == "take":
            if len(args) < 2 or not args[1].isdigit():
                self.print("Usage: loan take <amount> [months]", Color.GRAY)
                return
            amount = int(args[1])
            months = int(args[2]) if len(args) > 2 and args[2].isdigit() else 12
            loan = bank.take_loan(pid, amount, months,
                                   current_tick=self.engine.clock.time.tick)
            if loan:
                wealth = self.engine.world.get_component(self.engine.player, Wealth)
                if wealth:
                    wealth.copper += amount
                self.msg(f"Loan of {_format_money(amount)} taken for {months} months.",
                         Color.GREEN)
            else:
                self.msg("Loan denied.", Color.RED)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_caravan(self, args: list[str]) -> None:
        """caravan <route_id> <good> <qty>"""
        if len(args) < 3:
            self.print("Usage: caravan <route_id> <good> <qty>", Color.GRAY)
            return
        route_id, good_id, qty = args[0], args[1], int(args[2])
        cargo = {good_id: qty}
        caravan = self.trade.dispatch_caravan(
            route_id, cargo, cargo_value=qty * 100,
            current_tick=self.engine.clock.time.tick,
        )
        if caravan:
            self.msg(f"Caravan dispatched on route {route_id}.", Color.GREEN)
        else:
            self.msg("Could not dispatch caravan.", Color.RED)

    def cmd_ship(self, args: list[str]) -> None:
        if len(args) < 3:
            self.print("Usage: ship <route_id> <good> <qty>", Color.GRAY)
            return
        route_id, good_id, qty = args[0], args[1], int(args[2])
        cargo = {good_id: qty}
        ship = self.trade.dispatch_ship(
            route_id, cargo, cargo_value=qty * 100,
            current_tick=self.engine.clock.time.tick,
        )
        if ship:
            self.msg(f"Ship dispatched on route {route_id}.", Color.GREEN)
        else:
            self.msg("Could not dispatch ship.", Color.RED)

    def cmd_trade_routes(self, args: list[str]) -> None:
        self.print_header("Trade Routes", Color.GOLD)
        for r in self.trade.routes():
            self.print(f"  {r.route_id}  {r.name}  ({r.origin_market_id} → {r.destination_market_id})",
                       color=Color.WHITE)
        if not self.trade.routes():
            self.print("  No trade routes established.", Color.GRAY)
        self.print_separator()

    # ----- auctions & black market ---------------------------------------- #

    def cmd_auction(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: auction <list|sell> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "list":
            self.print_header("Auctions", Color.GOLD)
            auctions = list(self.auctions.all())
            for a in auctions:
                self.print(f"  #{a.auction_id} {a.title}  price: {a.current_price}cp  [{a.state.name}]",
                           color=Color.WHITE)
                if a.description:
                    self.print(f"    {a.description}", Color.GRAY)
            if not auctions:
                self.print("  No auctions. Use 'auction sell <item> <price>' to start one.",
                           color=Color.GRAY)
            self.print_separator()
        elif sub == "sell":
            if len(args) < 3:
                self.print("Usage: auction sell <item_name> <starting_price>",
                           color=Color.GRAY)
                return
            try:
                price = int(args[-1])
            except ValueError:
                self.print(f"Invalid price: {args[-1]}", Color.RED)
                return
            item_name = " ".join(args[1:-1]).lower()
            inv = self.engine.inventories.get(self.engine.player.id)
            target = None
            for _, item, _ in inv.iter_items(self.engine.items):
                if item_name in item.display_name.lower():
                    target = item
                    break
            if target is None:
                self.print(f"You don't have any '{item_name}'.", Color.RED)
                return
            a = self.auctions.schedule_auction(
                title=target.display_name, description="",
                seller_id=self.engine.player.id, item_id=target.id,
                item_name=target.display_name, starting_price=price,
                current_tick=self.engine.clock.time.tick,
            )
            self.msg(f"Auction #{a.auction_id} scheduled for {target.display_name}.",
                     Color.GREEN)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_bid(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: bid <auction_id> <amount>", Color.GRAY)
            return
        ok, msg = self.auctions.place_bid(
            int(args[0]), self.engine.player.id, int(args[1]),
            current_tick=self.engine.clock.time.tick,
        )
        self.msg(msg, Color.GREEN if ok else Color.RED)

    def cmd_blackmarket(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: blackmarket <list|buy> ...", Color.GRAY)
            return
        sub = args[0].lower()
        markets = self.blackmarket.markets()
        if not markets:
            self.blackmarket.create_market("Underground Market", (0, 0))
            markets = self.blackmarket.markets()
        market = markets[0]
        market_id = market.market_id
        if sub == "list":
            self.print_header("Black Market", Color.GOLD)
            for lst in market.listings:
                self.print(f"  #{lst.listing_id} {lst.item_name}  {lst.price}cp",
                           color=Color.RED)
            if not market.listings:
                self.print("  Nothing for sale.", Color.GRAY)
            self.print_separator()
        elif sub == "buy":
            if len(args) < 2:
                self.print("Usage: blackmarket buy <listing_id>", Color.GRAY)
                return
            wealth = self.engine.world.get_component(self.engine.player, Wealth)
            result = self.blackmarket.buy_from_market(
                market_id, int(args[1]), self.engine.player.id,
                wealth.total_copper() if wealth else 0,
            )
            self.msg(result.get("message", "Done"),
                     Color.GREEN if result.get("success") else Color.RED)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_fence(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: fence <item_name>", Color.GRAY)
            return
        item_name = " ".join(args).lower()
        inv = self.engine.inventories.get(self.engine.player.id)
        for _, item, _ in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower():
                markets = self.blackmarket.markets()
                if not markets:
                    self.blackmarket.create_market("Underground Market", (0, 0))
                    markets = self.blackmarket.markets()
                market_id = markets[0].market_id
                result = self.blackmarket.fence_item(
                    market_id, item.id, item.total_value, is_stolen=True,
                )
                self.msg(result.get("message", "Fenced."),
                         Color.GREEN if result.get("success") else Color.RED)
                if result.get("success"):
                    inv.remove(item.id, 1)
                    wealth = self.engine.world.get_component(self.engine.player, Wealth)
                    if wealth:
                        wealth.copper += result.get("payout", 0)
                return
        self.print(f"You don't have any '{item_name}'.", Color.RED)

    def cmd_hire_assassin(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: hire_assassin <target_id>", Color.GRAY)
            return
        markets = self.blackmarket.markets()
        if not markets:
            self.blackmarket.create_market("Underground Market", (0, 0))
            markets = self.blackmarket.markets()
        market_id = markets[0].market_id
        wealth = self.engine.world.get_component(self.engine.player, Wealth)
        result = self.blackmarket.hire_assassin(
            market_id, int(args[0]), self.engine.player.id,
            wealth.total_copper() if wealth else 0,
        )
        self.msg(result.get("message", "Done"),
                 Color.GREEN if result.get("success") else Color.RED)

    # ----- factions -------------------------------------------------------- #

    def cmd_factions(self, args: list[str]) -> None:
        from engine.factions.system import FactionLibrary
        self.print_header("Factions", Color.GOLD)
        for f in FactionLibrary.all():
            self.print(f"  #{f.id} {f.name}  ({f.type.value})", Color.WHITE)
            self.print(f"    {f.description}", Color.GRAY)
        self.print_separator()

    def cmd_faction(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: faction <id>", Color.GRAY)
            return
        from engine.factions.system import FactionLibrary
        f = FactionLibrary.get(int(args[0]))
        if f is None:
            self.print(f"Unknown faction: {args[0]}", Color.RED)
            return
        self.print_header(f.name, Color.GOLD)
        self.print(f"  Type: {f.type.value}", Color.WHITE)
        self.print(f"  Leader: {f.leader_id}", Color.WHITE)
        self.print(f"  Population: {f.population}", Color.WHITE)
        self.print(f"  Military: {f.military_strength}", Color.WHITE)
        self.print(f"  Treasury: {_format_money(f.treasury)}", Color.GOLD)
        self.print(f"  {f.description}", Color.GRAY)
        self.print_separator()

    # ----- kingdoms -------------------------------------------------------- #

    def cmd_kingdoms(self, args: list[str]) -> None:
        from engine.kingdoms.system import KingdomLibrary
        self.print_header("Kingdoms", Color.GOLD)
        for k in KingdomLibrary.all():
            self.print(f"  #{k.id} {k.name}  ({k.kingdom_type.name})",
                       color=Color.WHITE)
        self.print_separator()

    def cmd_kingdom(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: kingdom <id>", Color.GRAY)
            return
        from engine.kingdoms.system import KingdomLibrary
        k = KingdomLibrary.get(int(args[0]))
        if k is None:
            self.print(f"Unknown kingdom: {args[0]}", Color.RED)
            return
        self.print_header(k.name, Color.GOLD)
        self.print(f"  Type: {k.kingdom_type.name}", Color.WHITE)
        self.print(f"  Ruler: {getattr(k, 'ruler_id', 'unknown')}", Color.WHITE)
        self.print(f"  Stability: {getattr(k, 'stability', 0):.1f}", Color.WHITE)
        self.print(f"  Legitimacy: {getattr(k, 'legitimacy', 0):.1f}", Color.WHITE)
        self.print(f"  Treasury: {_format_money(getattr(k, 'treasury', 0))}", Color.GOLD)
        self.print_separator()

    def cmd_war(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: war <faction_a> <faction_b>", Color.GRAY)
            return
        self.engine.factions.declare_war(int(args[0]), int(args[1]),
                                          current_tick=self.engine.clock.time.tick)
        self.msg(f"War declared between {args[0]} and {args[1]}.", Color.RED)

    def cmd_peace(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: peace <faction_a> <faction_b>", Color.GRAY)
            return
        self.engine.factions.make_peace(int(args[0]), int(args[1]),
                                         current_tick=self.engine.clock.time.tick)
        self.msg(f"Peace made between {args[0]} and {args[1]}.", Color.GREEN)

    def cmd_alliance(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: alliance <kingdom_a> <kingdom_b>", Color.GRAY)
            return
        ok = self.kingdoms.form_alliance(int(args[0]), int(args[1]),
                                          current_tick=self.engine.clock.time.tick)
        self.msg(f"Alliance {'formed' if ok else 'failed'} between {args[0]} and {args[1]}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_annex(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: annex <kingdom_id> <territory_id>", Color.GRAY)
            return
        ok = self.kingdoms.annex_territory(int(args[0]), int(args[1]))
        self.msg(f"Annexation {'succeeded' if ok else 'failed'}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_election(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: election <kingdom_id>", Color.GRAY)
            return
        winner = self.kingdoms.hold_election(int(args[0]),
                                              current_tick=self.engine.clock.time.tick)
        self.msg(f"Election winner: {winner}", Color.GREEN if winner else Color.RED)

    # ----- espionage ------------------------------------------------------- #

    def cmd_recruit_spy(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: recruit_spy <entity_id> <name>", Color.GRAY)
            return
        spy = self.espionage.recruit_spy(
            int(args[0]), args[1], current_tick=self.engine.clock.time.tick,
        )
        self.msg(f"Spy recruited: {spy.name} (id {spy.spy_id})", Color.GREEN)

    def cmd_mission(self, args: list[str]) -> None:
        if len(args) < 3:
            self.print("Usage: mission <spy_id> <type> <target_faction>",
                       color=Color.GRAY)
            return
        from engine.espionage.system import MissionType
        try:
            mtype = MissionType[args[1].upper()]
        except KeyError:
            self.print(f"Unknown mission type: {args[1]}", Color.RED)
            return
        m = self.espionage.assign_mission(
            int(args[0]), mtype, target_faction_id=int(args[2]),
            current_tick=self.engine.clock.time.tick,
        )
        if m:
            self.msg(f"Mission {m.mission_id} assigned.", Color.GREEN)
        else:
            self.msg("Mission assignment failed.", Color.RED)

    def cmd_resolve_mission(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: resolve_mission <mission_id>", Color.GRAY)
            return
        result = self.espionage.resolve_mission(int(args[0]),
                                                  current_tick=self.engine.clock.time.tick)
        self.msg(f"Mission result: {result.state.name}", Color.YELLOW)

    def cmd_spies(self, args: list[str]) -> None:
        self.print_header("Spies", Color.GOLD)
        for s in self.espionage.spies():
            self.print(f"  #{s.spy_id} {s.name}  stealth {s.stealth}",
                       color=Color.WHITE)
        if not self.espionage.spies():
            self.print("  No spies recruited.", Color.GRAY)
        self.print_separator()

    # ----- rebellions ------------------------------------------------------ #

    def cmd_rebellion(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: rebellion <type> <faction_id>", Color.GRAY)
            return
        from engine.rebellions.system import RebellionType
        try:
            rtype = RebellionType[args[0].upper()]
        except KeyError:
            self.print(f"Unknown rebellion type: {args[0]}", Color.RED)
            return
        r = self.rebellions.start_rebellion(
            name=f"{rtype.value} #{args[1]}", rebellion_type=rtype,
            faction_id=int(args[1]), current_tick=self.engine.clock.time.tick,
        )
        self.msg(f"Rebellion {r.rebellion_id} started.", Color.RED)

    def cmd_suppress(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: suppress <rebellion_id>", Color.GRAY)
            return
        ok = self.rebellions.suppress_rebellion(int(args[0]),
                                                  current_tick=self.engine.clock.time.tick)
        self.msg(f"Rebellion {'suppressed' if ok else 'not suppressed'}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_negotiate(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: negotiate <rebellion_id>", Color.GRAY)
            return
        ok = self.rebellions.negotiate_settlement(int(args[0]),
                                                    current_tick=self.engine.clock.time.tick)
        self.msg(f"Negotiation {'succeeded' if ok else 'failed'}.",
                 Color.GREEN if ok else Color.RED)

    # ----- survival & life ------------------------------------------------- #

    def cmd_diseases(self, args: list[str]) -> None:
        from engine.survival.system import DiseaseLibrary
        self.print_header("Diseases", Color.GOLD)
        for d in DiseaseLibrary.all():
            self.print(f"  {d.id:20s} {d.name}", Color.RED)
            self.print(f"    {d.description}", Color.GRAY)
        self.print_separator()

    def cmd_cure(self, args: list[str]) -> None:
        diseases = self.engine.survival.diseases_of(self.engine.player)
        if not diseases:
            self.msg("You have no diseases.", Color.GREEN)
            return
        if not args:
            self.print("Usage: cure <disease_id>", Color.GRAY)
            self.print("You have:", Color.YELLOW)
            for d in diseases:
                self.print(f"  {d.disease_id} (severity {d.severity:.1f})", Color.RED)
            return
        # Simple cure: just remove the disease
        for d in diseases:
            if d.disease_id == args[0]:
                d.severity = 0
                d.remaining_duration = 0
                self.msg(f"You cure {d.disease_id}.", Color.GREEN)
                return
        self.msg(f"You don't have {args[0]}.", Color.RED)

    def cmd_marry(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: marry <partner_name>", Color.GRAY)
            return
        partner = self._find_entity_by_name(" ".join(args))
        if partner is None:
            self.print("No such person nearby.", Color.RED)
            return
        marriage = self.life.marry(
            self.engine.world, self.engine.player, partner,
            current_tick=self.engine.clock.time.tick,
        )
        if marriage:
            ident = self.engine.world.get_component(partner, Identity)
            self.msg(f"You marry {ident.display_name if ident else 'your partner'}.",
                     Color.GREEN)
        else:
            self.msg("Marriage not possible.", Color.RED)

    def cmd_divorce(self, args: list[str]) -> None:
        marriage = self.life.marriage_of(self.engine.player.id)
        if marriage is None:
            self.msg("You are not married.", Color.GRAY)
            return
        self.life.divorce(self.engine.world, marriage,
                          current_tick=self.engine.clock.time.tick)
        self.msg("You are now divorced.", Color.YELLOW)

    def cmd_family(self, args: list[str]) -> None:
        family = self.life.family_of(self.engine.player.id)
        self.print_header("Family", Color.GOLD)
        if family is None:
            self.print("  You have no family.", Color.GRAY)
        else:
            self.print(f"  Family: {family.surname}", Color.WHITE)
            self.print(f"  Wealth class: {family.wealth_class}", Color.WHITE)
            self.print(f"  Members: {len(family.members)}", Color.WHITE)
        marriage = self.life.marriage_of(self.engine.player.id)
        if marriage:
            self.print(f"  Married to entity #{marriage.spouse_a if marriage.spouse_b == self.engine.player.id else marriage.spouse_b}",
                       color=Color.PINK)
        self.print_separator()

    def cmd_job(self, args: list[str]) -> None:
        postings = self.life.job_market.all()
        self.print_header("Job Market", Color.GOLD)
        for p in postings[:10]:
            self.print(f"  #{p.posting_id} {p.title}  salary: {p.salary}cp/mo",
                       color=Color.WHITE)
        if not postings:
            self.print("  No jobs available.", Color.GRAY)
        self.print_separator()

    # ----- dungeons & exploration ----------------------------------------- #

    def cmd_dungeon(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: dungeon <type> [depth]", Color.GRAY)
            return
        from engine.dungeons.system import DungeonType
        try:
            dtype = DungeonType[args[0].upper()]
        except KeyError:
            self.print(f"Unknown dungeon type: {args[0]}", Color.RED)
            return
        depth = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
        pos = self.engine.world.get_component(self.engine.player, Position)
        loc = (pos.x, pos.y) if pos else (0, 0)
        d = self.dungeons.generate(
            name=f"{dtype.value} #{self.engine.rng.randint(1000, 9999)}",
            dungeon_type=dtype, location=loc, depth=depth,
            dungeon_id=self.engine.rng.randint(1, 99999),
        )
        self.msg(f"Dungeon generated: {d.name} ({d.depth} levels)", Color.GREEN)
        self.print_header(d.name, Color.GOLD)
        self.print(f"  Type: {d.dungeon_type.value}", Color.WHITE)
        self.print(f"  Depth: {d.depth}", Color.WHITE)
        self.print(f"  Location: {d.location}", Color.GRAY)
        self.print_separator()

    def cmd_bookmark(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: bookmark <add|list|remove> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "add":
            if len(args) < 2:
                self.print("Usage: bookmark add <name>", Color.GRAY)
                return
            name = " ".join(args[1:])
            pos = self.engine.world.get_component(self.engine.player, Position)
            b = self.bookmarks.add_bookmark(name, pos.x if pos else 0,
                                             pos.y if pos else 0)
            self.msg(f"Bookmark '{b.name}' added at ({b.x}, {b.y}).", Color.GREEN)
        elif sub == "list":
            self.print_header("Bookmarks", Color.GOLD)
            for b in self.bookmarks.all_bookmarks():
                self.print(f"  #{b.bookmark_id} {b.name} ({b.x}, {b.y})",
                           color=Color.WHITE)
            if not self.bookmarks.all_bookmarks():
                self.print("  No bookmarks.", Color.GRAY)
            self.print_separator()
        elif sub == "remove":
            if len(args) < 2:
                self.print("Usage: bookmark remove <id>", Color.GRAY)
                return
            ok = self.bookmarks.remove_bookmark(int(args[1]))
            self.msg("Bookmark removed." if ok else "Not found.",
                     Color.GREEN if ok else Color.RED)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_pin(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: pin <x> <y> [label]", Color.GRAY)
            return
        x, y = int(args[0]), int(args[1])
        label = " ".join(args[2:]) if len(args) > 2 else ""
        pin = self.bookmarks.add_pin(x, y, label=label)
        self.msg(f"Pin '{pin.label}' placed at ({x}, {y}).", Color.GREEN)

    # ----- animals & hunting ---------------------------------------------- #

    def cmd_hunt(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: hunt <species_id>", Color.GRAY)
            return
        from engine.entities.components import Skills as SkillsComp
        comp = self.engine.world.get_component(self.engine.player, SkillsComp)
        skill_level = (comp.skills.get("hunting").level
                       if comp and "hunting" in comp.skills else 1)
        yield_ = self.animals.hunt(args[0], "region_0", (0, 0), 1, skill_level)
        self.msg(f"You hunt {args[0]} and acquire {yield_} units.", Color.GREEN)

    def cmd_tame(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: tame <species_id>", Color.GRAY)
            return
        result = self.animals.domestication.tame_attempt(
            args[0], self.engine.player.id, skill_level=1,
            current_tick=self.engine.clock.time.tick,
        )
        self.msg(f"Tame attempt: {result}", Color.YELLOW)

    def cmd_livestock(self, args: list[str]) -> None:
        self.print_header("Livestock", Color.GOLD)
        herds = self.animals.livestock.herd_of(self.engine.player.id)
        if herds:
            for species_id, count in herds.items():
                self.print(f"  {species_id:20s} x{count}", Color.WHITE)
        else:
            self.print("  No livestock.", Color.GRAY)
        self.print_separator()

    def cmd_animals(self, args: list[str]) -> None:
        from engine.animals.system import AnimalLibrary
        self.print_header("Animal Species", Color.GOLD)
        for s in AnimalLibrary.all():
            sid = getattr(s, 'id', getattr(s, 'species_id', '?'))
            self.print(f"  {sid:20s} {s.name}", Color.WHITE)
        self.print_separator()

    # ----- artifacts ------------------------------------------------------- #

    def cmd_artifacts(self, args: list[str]) -> None:
        from engine.artifacts.system import ArtifactLibrary
        self.print_header("Artifacts", Color.GOLD)
        for a in ArtifactLibrary.all():
            self.print(f"  {a.artifact_id:25s} {a.name}", Color.WHITE)
            self.print(f"    rarity: {a.rarity.value}  owner: {a.owner_id}",
                       color=Color.GRAY)
        self.print_separator()

    def cmd_wield(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: wield <artifact_id>", Color.GRAY)
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.print(f"Unknown artifact: {args[0]}", Color.RED)
            return
        self.artifacts.wield(artifact, self.engine.player.id)
        self.msg(f"You wield {artifact.name}.", Color.GREEN)

    def cmd_power(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: power <artifact_id> <power_name>", Color.GRAY)
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.print(f"Unknown artifact: {args[0]}", Color.RED)
            return
        ok, msg = self.artifacts.use_power(artifact, args[1],
                                            current_tick=self.engine.clock.time.tick)
        self.msg(msg, Color.GREEN if ok else Color.RED)

    def cmd_talk_artifact(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: talk_artifact <artifact_id>", Color.GRAY)
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.print(f"Unknown artifact: {args[0]}", Color.RED)
            return
        response = self.artifacts.communicate(artifact, "Hello, mighty artifact.")
        if response:
            self.msg(f"{artifact.name}: {response}", Color.MANA)
        else:
            self.msg(f"{artifact.name} is silent.", Color.GRAY)

    def cmd_destroy(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: destroy <artifact_id> <method>", Color.GRAY)
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.print(f"Unknown artifact: {args[0]}", Color.RED)
            return
        ok, msg = self.artifacts.attempt_destroy(artifact, args[1])
        self.msg(msg, Color.GREEN if ok else Color.RED)

    # ----- reputation ------------------------------------------------------ #

    def cmd_reputation(self, args: list[str]) -> None:
        from engine.reputation.system import ReputationType
        self.print_header("Reputation", Color.GOLD)
        for rt in ReputationType:
            level = self.reputation.level(self.engine.player.id, rt)
            value = self.reputation.get(self.engine.player.id, rt)
            level_name = level.name if hasattr(level, 'name') else str(level)
            rt_name = rt.name if hasattr(rt, 'name') else str(rt)
            self.print(f"  {rt_name:12s} {level_name:12s} ({value:+.0f})",
                       color=Color.WHITE)
        self.print_separator()

    def cmd_hero(self, args: list[str]) -> None:
        deed = " ".join(args) if args else "a heroic deed"
        self.reputation.adjust(self.engine.player.id,
                               __import__("engine.reputation.system",
                                          fromlist=["ReputationType"]).ReputationType.HEROIC,
                               10, reason=deed,
                               current_tick=self.engine.clock.time.tick)
        self.msg(f"You perform {deed}. (+10 heroic reputation)", Color.GREEN)

    def cmd_crime(self, args: list[str]) -> None:
        crime = " ".join(args) if args else "a petty crime"
        self.reputation.adjust(self.engine.player.id,
                               __import__("engine.reputation.system",
                                          fromlist=["ReputationType"]).ReputationType.CRIMINAL,
                               -10, reason=crime,
                               current_tick=self.engine.clock.time.tick)
        self.msg(f"You commit {crime}. (-10 criminal reputation)", Color.RED)

    # ----- stealth --------------------------------------------------------- #

    def cmd_stealth(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: stealth <on|off>", Color.GRAY)
            return
        if args[0].lower() == "on":
            ok = self.stealth.enter_stealth(self.engine.player)
            self.msg("You enter stealth." if ok else "Cannot enter stealth.",
                     Color.GREEN if ok else Color.RED)
        elif args[0].lower() == "off":
            self.stealth.exit_stealth(self.engine.player)
            self.msg("You exit stealth.", Color.GRAY)
        else:
            self.print("Usage: stealth <on|off>", Color.GRAY)

    def cmd_backstab(self, args: list[str]) -> None:
        if not args:
            target = self._find_adjacent_hostile()
            if target is None:
                self.print("Backstab what?", Color.GRAY)
                return
        else:
            target = self._find_entity_by_name(" ".join(args))
            if target is None:
                self.print(f"You don't see any '{' '.join(args)}' here.", Color.RED)
                return
        bonus = self.stealth.backstab_bonus(self.engine.player, target)
        comp = self.engine.world.get_component(self.engine.player, CombatComp)
        weapon = None
        if comp and comp.weapon_id is not None:
            weapon = self.engine.items.get(comp.weapon_id)
        result = self.engine.combat.attack(self.engine.world, self.engine.player,
                                            target, weapon)
        if result.message:
            self.engine.message_log.add(
                f"BACKSTAB (x{bonus:.1f}): {result.message}", Color.YELLOW,
            )
        if result.killed:
            self.engine._handle_death(target, self.engine.player)

    # ----- themes & dimensions -------------------------------------------- #

    def cmd_theme(self, args: list[str]) -> None:
        from engine.themes.system import ThemeLibrary
        if not args:
            self.print("Usage: theme <list|set> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "list":
            self.print_header("Themes", Color.GOLD)
            for name in ThemeLibrary.names():
                self.print(f"  {name}", Color.WHITE)
            self.print_separator()
        elif sub == "set":
            if len(args) < 2:
                self.print("Usage: theme set <name>", Color.GRAY)
                return
            theme = ThemeLibrary.get(args[1])
            if theme is None:
                self.print(f"Unknown theme: {args[1]}", Color.RED)
                return
            self._theme = theme
            self.msg(f"Theme set to {theme.name}.", Color.GREEN)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_dimensions(self, args: list[str]) -> None:
        self.print_header("Dimensions", Color.GOLD)
        for d in self.dimensions.all_dimensions():
            self.print(f"  #{d.dimension_id} {d.name}  ({d.dimension_type.value})",
                       color=Color.WHITE)
        if not self.dimensions.all_dimensions():
            self.print("  No dimensions discovered.", Color.GRAY)
        self.print_separator()

    def cmd_portal(self, args: list[str]) -> None:
        if len(args) < 2:
            self.print("Usage: portal <from_dim> <to_dim>", Color.GRAY)
            return
        ok = self.dimensions.open_portal(int(args[0]), int(args[1]))
        self.msg(f"Portal {'opened' if ok else 'failed to open'}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_travel(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: travel <dimension_id>", Color.GRAY)
            return
        ok, msg = self.dimensions.can_travel(0, int(args[0]))
        self.msg(msg, Color.GREEN if ok else Color.RED)

    # ----- body parts ------------------------------------------------------ #

    def cmd_bodyparts(self, args: list[str]) -> None:
        parts = self.bodyparts.body_parts(self.engine.player)
        self.print_header("Body Parts", Color.GOLD)
        for p in parts:
            status = "OK" if p.status.name == "HEALTHY" else p.status.name
            self.print(f"  {p.part_type.value:12s} HP {p.current_hp}/{p.max_hp}  {status}",
                       color=Color.WHITE)
        if not parts:
            self.bodyparts.assign_body(self.engine.player, "humanoid")
            self.print("  Body assigned. Use 'bodyparts' again to view.",
                       color=Color.GRAY)
        self.print_separator()

    def cmd_heal_part(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: heal_part <part_type> [amount]", Color.GRAY)
            return
        from engine.bodyparts.system import BodyPartType
        try:
            ptype = BodyPartType[args[0].upper()]
        except KeyError:
            self.print(f"Unknown part: {args[0]}", Color.RED)
            return
        amount = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
        self.bodyparts.heal_part(self.engine.player, ptype, amount)
        self.msg(f"Healed {args[0]} by {amount}.", Color.GREEN)

    # ----- world & time ---------------------------------------------------- #

    def cmd_simulate(self, args: list[str]) -> None:
        hours = float(args[0]) if args and args[0].replace(".", "").isdigit() else 24.0
        report = self.background_sim.simulate(hours,
                                               start_tick=self.engine.clock.time.tick)
        self.print_header(f"Background Simulation ({hours:.0f}h)", Color.GOLD)
        total = getattr(report, 'total_events', 0)
        major = getattr(report, 'major_events', [])
        self.print(f"  Total events: {total}", Color.WHITE)
        self.print(f"  Major events: {len(major)}", Color.WHITE)
        for ev in major[:5]:
            etype = getattr(ev, 'event_type', None)
            etype_name = etype.name if hasattr(etype, 'name') else str(etype)
            desc = getattr(ev, 'description', '')
            self.print(f"    {etype_name}: {desc}", Color.YELLOW)
        self.print_separator()

    def cmd_contentpacks(self, args: list[str]) -> None:
        from engine.content_packs.system import ContentPackManager
        cpm = ContentPackManager()
        count = cpm.discover()
        self.print_header("Content Packs", Color.GOLD)
        self.print(f"  Discovered: {count}", Color.WHITE)
        for p in cpm.registry.all():
            self.print(f"  {p.pack_id:25s} {p.name} v{p.version}", Color.WHITE)
        self.print_separator()

    # ----- combat variants ------------------------------------------------- #

    def cmd_naval(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: naval <bombard|board> <ship_id>", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "bombard":
            if len(args) < 2:
                self.print("Usage: naval bombard <target_ship_id>", Color.GRAY)
                return
            ships = self.naval_combat.all_ships()
            if not ships:
                ship = self.naval_combat.create_ship("Player Frigate", "frigate")
                target = self.naval_combat.create_ship("Enemy", "frigate")
            else:
                ship = ships[0]
                target = next((s for s in ships if s.ship_id == int(args[1])), ships[-1])
            result = self.naval_combat.bombard(ship, target)
            self.msg(result.message, Color.YELLOW)
        elif sub == "board":
            if len(args) < 2:
                self.print("Usage: naval board <target_ship_id>", Color.GRAY)
                return
            ships = self.naval_combat.all_ships()
            if not ships:
                self.msg("No ships available.", Color.RED)
                return
            ship = ships[0]
            target = next((s for s in ships if s.ship_id == int(args[1])), ships[-1])
            result = self.naval_combat.board(ship, target)
            self.msg(result.message, Color.YELLOW)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_siege(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: siege <create|bombard|assault> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "create":
            if len(args) < 3:
                self.print("Usage: siege create <attacker_faction> <defender_faction>",
                           color=Color.GRAY)
                return
            s = self.siege_combat.create_siege(
                int(args[1]), int(args[2]), "Fortress",
                current_tick=self.engine.clock.time.tick,
            )
            self.msg(f"Siege {s.siege_id} created.", Color.RED)
        elif sub == "bombard":
            if len(args) < 2:
                self.print("Usage: siege bombard <siege_id>", Color.GRAY)
                return
            result = self.siege_combat.bombard(int(args[1]))
            self.msg(f"Bombardment: {result}", Color.YELLOW)
        elif sub == "assault":
            if len(args) < 3:
                self.print("Usage: siege assault <siege_id> <troops>", Color.GRAY)
                return
            result = self.siege_combat.assault(int(args[1]), int(args[2]))
            self.msg(f"Assault: {result}", Color.YELLOW)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_aerial(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: aerial <mount|dive|attack> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "mount":
            m = self.aerial_combat.create_mount("eagle", "Windrider")
            self.aerial_combat.mount_up(self.engine.player, m)
            self.msg(f"You mount {m.name}.", Color.GREEN)
        elif sub == "dive":
            self.aerial_combat.change_altitude(self.engine.player, -50)
            self.msg("You dive.", Color.CYAN)
        elif sub == "attack":
            target = self._find_adjacent_hostile()
            if target is None:
                self.print("No target.", Color.GRAY)
                return
            result = self.aerial_combat.aerial_attack(
                self.engine.world, self.engine.player, target,
            )
            self.msg(f"Aerial attack: {result.message if hasattr(result, 'message') else result}",
                     Color.YELLOW)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_space(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: space <fire|launch> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "fire":
            ships = self.space_combat.all_ships()
            if not ships:
                self.msg("No ships. Create one first.", Color.RED)
                return
            attacker = ships[0]
            target = ships[-1] if len(ships) > 1 else None
            if target is None:
                self.print("Need a target ship.", Color.GRAY)
                return
            if not attacker.weapons:
                self.space_combat.add_weapon(attacker, "laser", "Main Laser")
            result = self.space_combat.fire_weapon(attacker, target, attacker.weapons[0])
            self.msg(f"Fire: {result}", Color.YELLOW)
        elif sub == "launch":
            ships = self.space_combat.all_ships()
            if not ships:
                self.msg("No carrier.", Color.RED)
                return
            result = self.space_combat.launch_fighters(ships[0], ships[-1])
            self.msg(f"Launch: {result}", Color.YELLOW)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_realtime(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: realtime <queue|cancel> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "queue":
            target = self._find_adjacent_hostile()
            if target is None:
                self.print("No target.", Color.GRAY)
                return
            action = self.realtime_combat.queue_attack(self.engine.player, target)
            self.msg(f"Attack queued (action {action.action_id}).", Color.YELLOW)
        elif sub == "cancel":
            n = self.realtime_combat.cancel_actions(self.engine.player)
            self.msg(f"Cancelled {n} actions.", Color.GRAY)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    def cmd_mount(self, args: list[str]) -> None:
        if not args:
            self.print("Usage: mount <mount|dismount|charge> ...", Color.GRAY)
            return
        sub = args[0].lower()
        if sub == "mount":
            m = self.mounted_combat.create_mount("horse", "Thunder")
            self.mounted_combat.mount_up(self.engine.player, m)
            self.msg(f"You mount {m.name}.", Color.GREEN)
        elif sub == "dismount":
            m = self.mounted_combat.dismount(self.engine.player)
            self.msg(f"You dismount {m.name if m else ''}.", Color.GRAY)
        elif sub == "charge":
            target = self._find_adjacent_hostile()
            if target is None:
                self.print("No target.", Color.GRAY)
                return
            result = self.mounted_combat.mounted_attack(
                self.engine.world, self.engine.player, target, is_charging=True,
            )
            self.msg(f"Charge: {result.message if hasattr(result, 'message') else result}",
                     Color.YELLOW)
        else:
            self.print(f"Unknown subcommand: {sub}", Color.RED)

    # ----- entity lookup --------------------------------------------------- #

    def _find_entity_by_name(self, name: str) -> Optional[Entity]:
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

    # ----- main loop ------------------------------------------------------- #

    def run(self) -> None:
        self.running = True
        self.enable_raw_mode()
        try:
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
            if self._raw_mode:
                self.print("Use hjkl/wasd/arrows for movement (no Enter needed).",
                           color=Color.CYAN)
            else:
                self.print("Line mode: type a command and press Enter.", Color.CYAN)
            self.print()
            self._refresh_display()
            while self.running:
                try:
                    self._tick()
                except KeyboardInterrupt:
                    self.print("\nUse 'quit' to exit.", Color.YELLOW)
                except Exception as exc:  # noqa: BLE001
                    log.exception("REPL error")
                    self.print(f"Error: {exc}", Color.RED)
        finally:
            self.disable_raw_mode()

    def _tick(self) -> None:
        if self._in_dialogue:
            sys.stdout.write("Choice> ")
        else:
            sys.stdout.write("> ")
        sys.stdout.flush()
        line = ""
        if self._raw_mode:
            key = self._read_key()
            if key == "quit":
                self.running = False
                return
            if key == "enter":
                self.engine.tick_simulation(0.05)
                self._refresh_display()
                return
            if key in ("up", "down"):
                if key == "up" and self._history:
                    self._history_idx = max(0, self._history_idx - 1)
                    line = self._history[self._history_idx] if self._history_idx >= 0 else ""
                elif key == "down" and self._history:
                    self._history_idx = min(len(self._history) - 1, self._history_idx + 1)
                    line = self._history[self._history_idx] if self._history_idx >= 0 else ""
                sys.stdout.write("\r" + " " * 40 + "\r> " + line)
                sys.stdout.flush()
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
                if key in SINGLE_KEYS:
                    line = SINGLE_KEYS[key]
                    sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                else:
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
                return
        else:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                self.running = False
                return

        line = line.strip()
        if not line:
            self.engine.tick_simulation(0.05)
            self._refresh_display()
            return
        self._history.append(line)
        self._history_idx = -1
        if self._in_dialogue:
            if self._handle_dialogue_input(line):
                self.engine.tick_simulation(0.05)
                self._refresh_display()
                return
        self._execute_command(line)
        self.engine.tick_simulation(0.05)
        if (self.engine.clock.time.tick - self.engine._last_autosave_tick
                >= self.engine.config.save.autosave_interval_ticks):
            try:
                self.engine.save_game("autosave")
                self.engine._last_autosave_tick = self.engine.clock.time.tick
            except Exception as exc:  # noqa: BLE001
                log.error("Autosave failed: %s", exc)
        self._refresh_display()

    def _execute_command(self, line: str) -> None:
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            self.print(f"Parse error: {exc}", Color.RED)
            return
        if not tokens:
            return
        cmd = tokens[0].lower()
        args = tokens[1:]
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
            "status": "status", "st": "status", "stat": "status",
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
            "craft": "craft",
            "recipes": "recipes",
            "train": "train",
            "use_skill": "use_skill",
            "read": "read",
            "books": "books",
            "inscribe": "inscribe",
            "runes": "runes",
            "bank": "bank",
            "loan": "loan",
            "caravan": "caravan",
            "ship": "ship",
            "trade_routes": "trade_routes",
            "auction": "auction",
            "bid": "bid",
            "blackmarket": "blackmarket",
            "fence": "fence",
            "hire_assassin": "hire_assassin",
            "quest": "quest",
            "factions": "factions",
            "faction": "faction",
            "kingdoms": "kingdoms",
            "kingdom": "kingdom",
            "war": "war",
            "peace": "peace",
            "alliance": "alliance",
            "annex": "annex",
            "election": "election",
            "recruit_spy": "recruit_spy",
            "mission": "mission",
            "resolve_mission": "resolve_mission",
            "spies": "spies",
            "rebellion": "rebellion",
            "suppress": "suppress",
            "negotiate": "negotiate",
            "diseases": "diseases",
            "cure": "cure",
            "marry": "marry",
            "divorce": "divorce",
            "family": "family",
            "job": "job",
            "dungeon": "dungeon",
            "bookmark": "bookmark",
            "pin": "pin",
            "hunt": "hunt",
            "tame": "tame",
            "livestock": "livestock",
            "animals": "animals",
            "artifacts": "artifacts",
            "wield": "wield",
            "power": "power",
            "talk_artifact": "talk_artifact",
            "destroy": "destroy",
            "reputation": "reputation",
            "hero": "hero",
            "crime": "crime",
            "stealth": "stealth",
            "backstab": "backstab",
            "theme": "theme",
            "dimensions": "dimensions",
            "portal": "portal",
            "travel": "travel",
            "bodyparts": "bodyparts",
            "heal_part": "heal_part",
            "simulate": "simulate",
            "contentpacks": "contentpacks",
            "naval": "naval",
            "siege": "siege",
            "aerial": "aerial",
            "space": "space",
            "realtime": "realtime",
            "mount": "mount",
            "buy": "buy",
            "sell": "sell",
            "market": "market",
            "research": "research",
            "meditate": "meditate",
            "schools": "schools",
        }
        if cmd in DIRECTIONS:
            args = [cmd]
            cmd = "go"
        else:
            cmd = aliases.get(cmd, cmd)
        handler = getattr(self, f"cmd_{cmd}", None)
        if handler is None:
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
            else:
                self.print(f"Unknown command: {tokens[0]}. Type 'help' for help.",
                           color=Color.RED)
            return
        try:
            handler(args)
        except Exception as exc:  # noqa: BLE001
            log.exception("Command %s failed", cmd)
            self.print(f"Error: {exc}", Color.RED)

    def _refresh_display(self) -> None:
        if self._color:
            sys.stdout.write(ANSI.CLEAR_SCREEN)
        else:
            sys.stdout.write("\n" * 2)
        sys.stdout.flush()
        self._write_main_view()
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()
        if self._in_dialogue:
            self._show_dialogue_node()
            if self._panel_buffer:
                sys.stdout.write("\n".join(self._panel_buffer) + "\n")
                self._panel_buffer.clear()
        sys.stdout.flush()

    def _write_main_view(self) -> None:
        self._panel_buffer.clear()
        self.show_status_panel()
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()
        self.show_map_view()
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()
        self.show_messages()
        if self._panel_buffer:
            sys.stdout.write("\n".join(self._panel_buffer) + "\n")
            self._panel_buffer.clear()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="aeon",
        description="Aeon Engine — a text-based open-world RPG.",
    )
    parser.add_argument("--seed", type=int, default=None,
                        help="World generation seed.")
    parser.add_argument("--width", type=int, default=None,
                        help="World width.")
    parser.add_argument("--height", type=int, default=None,
                        help="World height.")
    parser.add_argument("--headless", action="store_true",
                        help="Run a single tick and exit (for testing).")
    parser.add_argument("--load", type=str, default=None,
                        help="Load a save slot instead of starting a new game.")
    parser.add_argument("--no-plugins", action="store_true",
                        help="Skip plugin loading.")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug/cheat mode.")
    parser.add_argument("--name", type=str, default="Hero",
                        help="Player character name.")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable ANSI colour output.")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """Single entry point for Aeon Engine."""
    args = parse_args(argv)
    # Make sure the project root is on sys.path so `engine` resolves.
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from engine.core.config import EngineConfig, load_config, set_config
    from engine.core.logging import configure_logging
    from engine.engine import Engine
    from engine.world.generator import WorldGenParams

    config_path = project_root / "engine.toml"
    config = load_config(config_path) if config_path.exists() else EngineConfig()
    if args.debug:
        config.debug = True
    if args.no_color:
        config.ui.color_enabled = False
    if args.seed is not None:
        config.world.world_seed = args.seed
    set_config(config)

    import logging
    configure_logging(
        level=logging.DEBUG if config.debug else logging.INFO,
        log_file=Path(config.log_file) if config.log_file else None,
    )
    log.info("Starting Aeon Engine v%s", config.version)

    # The REPL provides its own UI, so we always run the engine headless.
    engine = Engine(config, headless=True)
    if args.no_plugins:
        engine.config.plugins.autoload_enabled = False

    if args.load:
        try:
            engine.load_game(args.load)
            log.info("Loaded save: %s", args.load)
        except FileNotFoundError:
            log.error("Save not found: %s — generating new world", args.load)
            params = WorldGenParams(
                seed=config.world.world_seed,
                width=args.width or (config.world.world_tiles_x // 2),
                height=args.height or (config.world.world_tiles_y // 2),
            )
            engine.generate_world(params)
            engine.create_player(args.name)
    else:
        params = WorldGenParams(
            seed=config.world.world_seed,
            width=args.width or (config.world.world_tiles_x // 2),
            height=args.height or (config.world.world_tiles_y // 2),
        )
        engine.generate_world(params)
        engine.create_player(args.name)

    if args.headless:
        engine.tick_simulation(0.05)
        log.info("Headless tick complete. Player id: %s",
                 engine.player.id if engine.player else None)
        return 0

    # Load plugins.
    if engine.config.plugins.autoload_enabled:
        try:
            success, failure = engine.plugins.load_all()
            if success:
                engine.plugins.enable_all()
            log.info("Plugins loaded: %d success, %d failed", success, failure)
        except Exception as exc:  # noqa: BLE001
            log.error("Plugin loading failed: %s", exc)

    try:
        repl = GameREPL(engine)
        repl.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        engine.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
