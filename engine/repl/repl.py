"""Game REPL — a polished, dynamic interactive command-line interface.

This module is the SINGLE entry point for Aeon Engine. It replaces the
old ``main.py`` and integrates EVERY gameplay system the engine ships
with — combat, magic, crafting, economy, quests, factions, kingdoms,
espionage, rebellions, dungeons, artifacts, auctions, black market,
life simulation, stealth, animals, reputation, runes, skill books,
themes, dimensions, body parts, trade, bookmarks, procedural dialogue,
all combat variants (naval / siege / aerial / space / realtime /
mounted), background simulation, content packs, plugins and more.

UI design (rich-based)
-----------------------
* Persistent three-panel layout:
    - Status panel (HP/MP/needs/wealth/time/weather)
    - Map panel (local viewport with entities)
    - Messages panel (recent message log)
* Command output panel — surfaces inventory, character sheet, help, etc.
  and persists across the next refresh so the player can actually read it.
* Big banner shown at startup and on demand via the ``banner`` command.
* Pretty formatted output using rich Panels, Tables, Bars and Rules.
* Colour-rich logs that go to a log file by default (the console is
  reserved for the game UI).
* Graceful fall-back to plain line mode when stdin is not a TTY (pipes,
  CI environments) — the rich layout is replaced with a flat render
  that still shows every panel.

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


# rich is a hard dependency of the REPL UI.
from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

# stdlib threading for non-blocking input in live mode.
import threading
import queue as _queue


log = get_logger("repl")


# --------------------------------------------------------------------------- #
# Direction mapping
# --------------------------------------------------------------------------- #

DIRECTIONS: dict[str, tuple[int, int, str]] = {
    "h": (-1, 0, "west"),  "left":  (-1, 0, "west"),  "west":  (-1, 0, "west"),
    "l": (1, 0, "east"),   "right": (1, 0, "east"),   "east":  (1, 0, "east"),
    "k": (0, -1, "north"), "up":    (0, -1, "north"), "north": (0, -1, "north"),
    "j": (0, 1, "south"),  "down":  (0, 1, "south"),  "south": (0, 1, "south"),
    "y": (-1, -1, "NW"),   "northwest": (-1, -1, "NW"),
    "u": (1, -1, "NE"),    "northeast": (1, -1, "NE"),
    "b": (-1, 1, "SW"),    "southwest": (-1, 1, "SW"),
    "n": (1, 1, "SE"),     "southeast": (1, 1, "SE"),
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


def _ansi_to_text(s: str) -> str:
    """Strip ANSI escape codes from a string."""
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def _make_bar(current: float, maximum: float, width: int = 16,
              fill_char: str = "█", empty_char: str = "░") -> str:
    """Return a textual progress bar."""
    if maximum <= 0:
        fraction = 0.0
    else:
        fraction = current / maximum
    fraction = max(0.0, min(1.0, fraction))
    filled = int(width * fraction)
    return fill_char * filled + empty_char * (width - filled)


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
        self._in_dialogue: bool = False
        self._dialogue_ctx: Any = None
        self._dialogue_tree: Any = None
        self._raw_mode: bool = False
        self._saved_term_settings: Any = None

        # The current "command output" panel — persists until the next
        # command produces new output. This is the key fix for the
        # "inventory shows nothing" bug.
        self._command_output: Optional[RenderableType] = None
        self._command_output_title: str = "Welcome"

        # Backwards-compat: legacy tests introspect `_panel_buffer` after
        # running `_execute_command`. We populate it with the plain-text
        # rendering of the most recent command output.
        self._panel_buffer: list[str] = []

        # Lazily-instantiated non-Engine systems.
        self._extras: dict[str, Any] = {}

        # Rich console — configured for the game UI.
        self._color: bool = bool(getattr(self.engine.config.ui, "color_enabled", True))
        self.console: Console = Console(
            force_terminal=self._is_tty(),
            color_system="auto" if self._color else None,
            highlight=False,
            soft_wrap=False,
            width=max(80, min(120, os.get_terminal_size().columns if self._is_tty() else 100)),
        )

        # Whether we have a real TTY for input (raw mode).
        self._interactive: bool = self._is_tty()

        # ----- live-dashboard mode state -----
        # When True, run() uses rich.live.Live to continuously auto-refresh
        # the layout in real time. Input is read non-blocking on the main
        # thread (single-threaded design — no race with Live's terminal
        # state manipulation).
        self.live_mode: bool = False
        # Target frame rate for live refresh (frames per second).
        self._live_fps: float = 8.0
        # Real-time simulation cadence — how often to advance the engine
        # simulation tick (seconds of wall-clock time between ticks).
        self._sim_dt: float = 0.25
        # Time of last simulation tick (for real-time world advancement).
        self._last_sim_time: float = 0.0
        # Input queue — completed command lines from the non-blocking
        # reader are pushed here and drained by the main loop.
        self._input_queue: "_queue.Queue[Optional[str]]" = _queue.Queue()
        # Current input line being typed (echoed in the live input panel).
        self._live_input: str = ""
        # Last command entered (shown briefly in the input panel hint).
        self._last_command: str = ""
        # ----- output panel scroll state -----
        # Vertical scroll offset (in lines) for the command-output panel.
        # 0 = bottom (most recent). Positive = scrolled up.
        self._output_scroll: int = 0
        # Rendered lines of the current command output (cached each frame
        # so the scroll logic knows how many lines there are).
        self._output_line_count: int = 0
        # ----- game-over state -----
        # When True, the hero is dead and the game shows a game-over panel
        # instead of the normal layout. The player can press R to respawn,
        # N to start a new game, or Q to quit.
        self._game_over: bool = False

    # ----- terminal helpers ----------------------------------------------- #

    @staticmethod
    def _is_tty() -> bool:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:  # noqa: BLE001
            return False

    def _extra(self, key: str, factory: Any) -> Any:
        if key not in self._extras:
            try:
                self._extras[key] = factory()
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to initialise system %s: %s", key, exc)
                return None
        return self._extras[key]

    # ----- lazy extra-system accessors ------------------------------------ #

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

    # ----- raw-mode terminal setup ---------------------------------------- #

    def enable_raw_mode(self) -> None:
        try:
            import termios
            import tty
            self._saved_term_settings = termios.tcgetattr(sys.stdin.fileno())
            tty.setraw(sys.stdin.fileno())
            self._raw_mode = True
        except Exception:  # noqa: BLE001
            self._raw_mode = False
            self._saved_term_settings = None

    def disable_raw_mode(self) -> None:
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
        try:
            ch = sys.stdin.read(1)
            if ch == "\x1b":
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
            if ch == "\x03":
                return "quit"
            if ch == "\x04":
                return "quit"
            return ch
        except (EOFError, KeyboardInterrupt):
            return "quit"

    # ----- output & message helpers --------------------------------------- #

    def msg(self, text: str, color: int = Color.WHITE) -> None:
        """Add a message to the engine message log (shown in messages panel)."""
        self.engine.message_log.add(text, color)

    def set_output(self, renderable: RenderableType, title: str = "Output") -> None:
        """Set the persistent command-output panel."""
        self._command_output = renderable
        self._command_output_title = title
        # Backwards-compat: render the rich object to plain text so legacy
        # tests that inspect `_panel_buffer` can still find keywords.
        try:
            from io import StringIO
            buf = StringIO()
            tmp_console = Console(
                file=buf, force_terminal=False, color_system=None,
                highlight=False, soft_wrap=True, width=100,
            )
            tmp_console.print(renderable)
            self._panel_buffer = buf.getvalue().splitlines()
        except Exception:  # noqa: BLE001
            self._panel_buffer = [str(renderable)]

    def clear_output(self) -> None:
        self._command_output = None
        self._command_output_title = ""
        self._panel_buffer = []

    # ----- rich panel builders -------------------------------------------- #

    def _banner_panel(self) -> Panel:
        banner_text = Text()
        banner_text.append("╔══════════════════════════════════════════════════════════╗\n",
                           style="bold gold1")
        banner_text.append("║                                                          ║\n",
                           style="bold gold1")
        banner_text.append("║            A E O N   E N G I N E                         ║\n",
                           style="bold gold1")
        banner_text.append("║       A Text-Based Open-World RPG                        ║\n",
                           style="bold gold1")
        banner_text.append("║                                                          ║\n",
                           style="bold gold1")
        banner_text.append("╚══════════════════════════════════════════════════════════╝\n",
                           style="bold gold1")
        banner_text.append("\nType 'help' for commands, 'q' to quit.", style="cyan")
        if self._raw_mode:
            banner_text.append("  hjkl/wasd/arrows move.", style="cyan")
        else:
            banner_text.append("  Line mode: type a command and press Enter.", style="cyan")
        return Panel(banner_text, border_style="gold1", title="[bold gold1]Aeon Engine[/]",
                     expand=True)

    def _status_panel(self) -> Panel:
        if self.engine.player is None:
            return Panel(Text("No player.", style="red"), title="[bold]Status[/]",
                         border_style="red")
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

        # Build the status body as a Table for clean column alignment.
        table = Table.grid(padding=(0, 1))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column()

        if health:
            hp_bar = _make_bar(health.current, health.maximum)
            table.add_row("HP", f"[red]{hp_bar}[/] {int(health.current)}/{int(health.maximum)}",
                          "", "")
        if mana:
            mp_bar = _make_bar(mana.current, mana.maximum)
            table.add_row("MP", f"[blue]{mp_bar}[/] {mana.current:.0f}/{mana.maximum:.0f}",
                          "", "")
        if needs:
            table.add_row("Hunger", f"[yellow]{_make_bar(needs.hunger, 100)}[/] {int(needs.hunger)}/100",
                          "Thirst", f"[cyan]{_make_bar(needs.thirst, 100)}[/] {int(needs.thirst)}/100")
            table.add_row("Fatigue", f"[grey]{_make_bar(needs.fatigue, 100)}[/] {int(needs.fatigue)}/100",
                          "Sleep", f"[magenta]{_make_bar(needs.sleep, 100)}[/] {int(needs.sleep)}/100")
        if position:
            table.add_row("Pos", f"({position.x}, {position.y})", "", "")
        if wealth:
            table.add_row("Wealth", f"[gold1]{_format_money(wealth.total_copper())}[/]", "", "")
        try:
            time_str = self.engine.clock.time.display()
            weather_str = (self.engine.weather.current.description()
                           if self.engine.weather else "unknown")
            table.add_row("Time", f"[cyan]{time_str}[/]", "", "")
            table.add_row("Weather", f"[cyan]{weather_str}[/]", "", "")
        except Exception:  # noqa: BLE001
            pass
        return Panel(table, title=f"[bold gold1]{name}[/]", border_style="gold1", expand=True)

    def _map_panel(self) -> Panel:
        if self.engine.player is None or self.engine.world_map is None:
            return Panel(Text("No map.", style="red"), title="[bold]Map[/]",
                         border_style="red")
        player = self.engine.player
        pos = self.engine.world.get_component(player, Position)
        if pos is None:
            return Panel(Text("No position.", style="red"), title="[bold]Map[/]",
                         border_style="red")
        world_map = self.engine.world_map
        viewport_w = min(50, world_map.width)
        viewport_h = min(15, world_map.height)
        ox = pos.x - viewport_w // 2
        oy = pos.y - viewport_h // 2
        lines: list[Text] = []
        for j in range(viewport_h):
            row = Text()
            for i in range(viewport_w):
                wx = ox + i
                wy = oy + j
                tile = world_map.get_tile(wx, wy)
                if tile is None:
                    row.append(" ")
                    continue
                if not tile.is_explored and not self.engine.cheat_mode:
                    row.append(" ")
                    continue
                entity_here = False
                for ent, (ep,) in self.engine.world.view(Position):
                    if ep.x == wx and ep.y == wy:
                        if ent.id == player.id:
                            row.append("@", style="bold yellow")
                            entity_here = True
                            break
                        identity = self.engine.world.get_component(ent, Identity)
                        glyph = identity.glyph if identity else "?"
                        color = "red" if self.engine.world.has_tag(ent, "hostile") else "white"
                        row.append(glyph, style=color)
                        entity_here = True
                        break
                if not entity_here:
                    row.append(tile.terrain.glyph)
            lines.append(row)
        return Panel(Group(*lines), title="[bold]Map[/]", border_style="cyan", expand=True)

    def _messages_panel(self) -> Panel:
        msgs = self.engine.message_log.messages[-8:] if self.engine.message_log.messages else []
        if not msgs:
            body = Text("(no messages)", style="dim")
        else:
            lines: list[Text] = []
            color_map = {
                Color.RED: "red",
                Color.GREEN: "green",
                Color.YELLOW: "yellow",
                Color.CYAN: "cyan",
                Color.GOLD: "gold1",
                Color.MANA: "blue",
                Color.GRAY: "dim",
                Color.WHITE: "white",
            }
            for msg, color in msgs:
                style = color_map.get(color, "white")
                lines.append(Text(f"• {msg}", style=style))
            body = Group(*lines)
        return Panel(body, title="[bold]Messages[/]", border_style="green", expand=True)

    def _command_output_panel(self) -> Optional[Panel]:
        if self._command_output is None:
            return None
        return Panel(
            self._command_output,
            title=f"[bold magenta]{self._command_output_title}[/]",
            border_style="magenta",
            expand=True,
        )

    # ----- top-level render ------------------------------------------------ #

    def _render(self) -> None:
        """Render the full game UI."""
        self.console.clear()
        # Banner always visible at top.
        self.console.print(self._banner_panel())
        # Status + Map side-by-side if terminal is wide enough.
        try:
            width = self.console.width
        except Exception:  # noqa: BLE001
            width = 80
        if width >= 100:
            from rich.columns import Columns
            cols = Columns([self._status_panel(), self._map_panel()], expand=True, equal=True)
            self.console.print(cols)
        else:
            self.console.print(self._status_panel())
            self.console.print(self._map_panel())
        # Messages always visible.
        self.console.print(self._messages_panel())
        # Command output (inventory, help, etc.) — persists across refreshes.
        out_panel = self._command_output_panel()
        if out_panel is not None:
            self.console.print(out_panel)
        # Dialogue overlay if active.
        if self._in_dialogue:
            self._render_dialogue()
        # Prompt.
        if self._in_dialogue:
            self.console.print("[bold yellow]Choice>[/] ", end="")
        else:
            self.console.print("[bold green]>[/] ", end="")

    def _render_dialogue(self) -> None:
        if self._dialogue_tree is None or self._dialogue_ctx is None:
            return
        node = self._dialogue_tree.get(self._dialogue_ctx.current_node_id)
        if node is None:
            return
        identity = self.engine.world.get_component(self._dialogue_ctx.npc, Identity)
        npc_name = identity.display_name if identity else "NPC"
        body = Text()
        body.append(f"{npc_name}: ", style="bold yellow")
        body.append(node.speaker_text, style="white")
        body.append("\n\nChoices:\n", style="dim")
        for i, choice in enumerate(node.choices):
            body.append(f"  [{i + 1}] {choice.text}\n", style="white")
        body.append("  [0] End conversation", style="dim")
        self.console.print(Panel(body, title=f"[bold yellow]Conversation with {npc_name}[/]",
                                 border_style="yellow"))

    # ----- game-state display commands ------------------------------------ #

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
            self.msg(f"You don't see any '{' '.join(args)}' here.", Color.GRAY)
            return
        body_lines: list[Text] = []
        tile = self.engine.world_map.get_tile(pos.x, pos.y)
        if tile:
            biome_name = tile.biome_type.replace("_", " ").title()
            body_lines.append(Text(f"Terrain: {tile.terrain.glyph} {biome_name}", style="dim"))
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
            if self.engine.world.has_tag(ent, "hostile"):
                style = "red"
                tag = " (hostile)"
            elif self.engine.world.has_tag(ent, "npc"):
                style = "yellow"
                tag = " (NPC)"
            else:
                style = "white"
                tag = ""
            body_lines.append(Text(f"{glyph} {name}{tag} at ({ep.x}, {ep.y}) — dist {dist}",
                                   style=style))
            any_entity = True
        if not any_entity:
            body_lines.append(Text("Nothing of interest nearby.", style="dim"))
        self.set_output(Group(*body_lines), title="You see...")

    def cmd_go(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Go where? Try: go north (or just: k)", style="dim"),
                            title="Move")
            return
        direction = args[0].lower()
        if direction not in DIRECTIONS:
            self.set_output(
                Text(f"Unknown direction: {direction}\nValid: {', '.join(sorted(set(DIRECTIONS.keys())))}",
                     style="red"),
                title="Move")
            return
        dx, dy, name = DIRECTIONS[direction]
        self.engine.move_player(dx, dy)
        # Clear command output so movement shows the world.
        self.clear_output()

    def cmd_attack(self, args: list[str]) -> None:
        if not args:
            target = self._find_adjacent_hostile()
            if target is None:
                self.set_output(Text("Attack what? Try: attack goblin", style="dim"),
                                title="Attack")
                return
        else:
            target = self._find_entity_by_name(" ".join(args))
            if target is None:
                self.set_output(Text(f"You don't see any '{' '.join(args)}' here.",
                                     style="red"), title="Attack")
                return
        if target is None:
            return
        player_pos = self.engine.world.get_component(self.engine.player, Position)
        target_pos = self.engine.world.get_component(target, Position)
        if player_pos and target_pos:
            dist = max(abs(player_pos.x - target_pos.x),
                       abs(player_pos.y - target_pos.y))
            if dist > 1:
                self.set_output(Text("Target is too far away.", style="red"),
                                title="Attack")
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
            self.cmd_spells([])
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
            self.set_output(Text(f"Unknown spell: {spell_name}", style="red"),
                            title="Cast")
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
        if hasattr(result, 'killed_targets') and result.killed_targets:
            for dead in result.killed_targets:
                self.engine._handle_death(dead, self.engine.player)

    def cmd_research(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text(
                "Usage: research <name> <school_id>\n"
                "Schools: evocation, conjuration, enchantment, necromancy, "
                "abjuration, transmutation, divination, illusion",
                style="dim"), title="Research")
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
        hours = 1.0
        if args:
            try:
                hours = float(args[0])
            except ValueError:
                self.set_output(Text("Usage: meditate [hours]", style="dim"),
                                title="Meditate")
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
        table = Table(title="Magic Schools", border_style="blue", show_lines=False)
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="white")
        table.add_column("Description", style="dim")
        for s in SchoolLibrary.all():
            table.add_row(s.id, s.name, s.description or "")
        self.set_output(table, title="Magic Schools")

    # ----- items & inventory ---------------------------------------------- #

    def cmd_use(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Use what? Try: use health potion", style="dim"),
                            title="Use")
            return
        item_name = " ".join(args).lower()
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            return
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            if item_name in item.display_name.lower() or item_name in item.name.lower():
                self._use_item(item)
                return
        self.set_output(Text(f"You don't have any '{item_name}'.", style="red"),
                        title="Use")

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
                    self.msg(f"You use {item.display_name}, restoring {heal:.0f} HP.",
                             Color.GREEN)
            if mana_restore > 0:
                mana = self.engine.world.get_component(self.engine.player, Mana)
                if mana:
                    mana.current = min(mana.maximum, mana.current + mana_restore)
                    self.msg(f"You use {item.display_name}, restoring {mana_restore:.0f} MP.",
                             Color.MANA)
            if food > 0:
                needs = self.engine.world.get_component(self.engine.player, NeedsComp)
                if needs:
                    needs.hunger = max(0, needs.hunger - food)
                    self.msg(f"You eat {item.display_name}. Hunger reduced by {food:.0f}.",
                             Color.YELLOW)
            if drink > 0:
                needs = self.engine.world.get_component(self.engine.player, NeedsComp)
                if needs:
                    needs.thirst = max(0, needs.thirst - drink)
                    self.msg(f"You drink {item.display_name}. Thirst reduced by {drink:.0f}.",
                             Color.CYAN)
            inv = self.engine.inventories.get(self.engine.player.id)
            if inv:
                inv.remove(item.id, 1)
        else:
            self.set_output(Text(f"You can't use {item.display_name}.", style="dim"),
                            title="Use")

    def cmd_equip(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Equip what? Try: equip dagger", style="dim"),
                            title="Equip")
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
                    self.msg(f"You equip {item.display_name}.", Color.GREEN)
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
                    self.msg(f"You equip {item.display_name}.", Color.GREEN)
                    return
                else:
                    self.set_output(Text(f"You can't equip {item.display_name}.",
                                         style="dim"), title="Equip")
                    return
        self.set_output(Text(f"You don't have any '{item_name}'.", style="red"),
                        title="Equip")

    def cmd_drop(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Drop what?", style="dim"), title="Drop")
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
                self.msg(f"You drop {item.display_name}.", Color.GRAY)
                return
        self.set_output(Text(f"You don't have any '{item_name}'.", style="red"),
                        title="Drop")

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
                self.msg(f"You pick up {item.display_name}.", Color.GREEN)
                picked_up = True
            self.engine.world.destroy_entity(ent)
        if not picked_up:
            self.msg("There's nothing to pick up.", Color.GRAY)

    def cmd_unequip(self, args: list[str]) -> None:
        comp = (self.engine.world.get_component(self.engine.player, CombatComp)
                if self.engine.player else None)
        if comp is None:
            self.set_output(Text("You have nothing equipped.", style="dim"),
                            title="Unequip")
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
                self.msg("You unequip all items.", Color.GREEN)
            else:
                self.set_output(Text("You have nothing equipped.", style="dim"),
                                title="Unequip")
            return
        slot_name = args[0].lower()
        if slot_name in ("weapon", "main_hand", "hand"):
            if comp.weapon_id is not None:
                inv = self.engine.inventories.get(self.engine.player.id) if self.engine.player else None
                if inv:
                    item = self.engine.items.get(comp.weapon_id)
                    if item:
                        inv.add(item, 1)
                        self.msg(f"You unequip {item.display_name}.", Color.GREEN)
                    comp.weapon_id = None
            else:
                self.set_output(Text("You don't have a weapon equipped.", style="dim"),
                                title="Unequip")
        elif slot_name in ("chest", "armor", "body"):
            if comp.armor_ids.get("chest") is not None:
                inv = self.engine.inventories.get(self.engine.player.id) if self.engine.player else None
                if inv:
                    item = self.engine.items.get(comp.armor_ids["chest"])
                    if item:
                        inv.add(item, 1)
                        self.msg(f"You unequip {item.display_name}.", Color.GREEN)
                    comp.armor_ids["chest"] = None
            else:
                self.set_output(Text("You don't have chest armor equipped.",
                                     style="dim"), title="Unequip")
        else:
            self.set_output(Text(f"Unknown slot: {slot_name}\nValid slots: weapon, chest",
                                 style="dim"), title="Unequip")

    # ----- dialogue & trade ----------------------------------------------- #

    def cmd_trade(self, args: list[str]) -> None:
        if args:
            target = self._find_entity_by_name(" ".join(args))
        else:
            target = self._find_adjacent_npc()
        if target is None:
            self.set_output(Text("There's no one to trade with.", style="dim"),
                            title="Trade")
            return
        if not self.engine.world.has_tag(target, "merchant"):
            identity = self.engine.world.get_component(target, Identity)
            name = identity.display_name if identity else "them"
            self.set_output(Text(f"{name} is not interested in trading.",
                                 style="dim"), title="Trade")
            return
        identity = self.engine.world.get_component(target, Identity)
        name = identity.display_name if identity else "Merchant"
        wealth = self.engine.world.get_component(self.engine.player, Wealth)
        body = Text()
        body.append(f"Trading with {name}\n", style="bold gold1")
        body.append(f"Your money: {_format_money(wealth.total_copper()) if wealth else '0c'}\n\n",
                    style="gold1")
        body.append("Available goods (use 'buy <good> <qty>'):\n", style="yellow")
        from engine.economy.market import TradeGoodLibrary
        for g in list(TradeGoodLibrary.all())[:10]:
            body.append(f"  {g.id:20s} base {g.base_price}cp  ({g.name})\n", style="white")
        self.set_output(body, title=f"Trade — {name}")

    def cmd_buy(self, args: list[str]) -> None:
        if len(args) < 1:
            self.set_output(Text("Usage: buy <good_id> [quantity]", style="dim"),
                            title="Buy")
            return
        good_id = args[0]
        qty = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
        if not self.engine.economy.markets:
            self.engine.economy.create_market("m1", "General Store", (0, 0))
        market = list(self.engine.economy.markets.values())[0]
        wealth = self.engine.world.get_component(self.engine.player, Wealth)
        if wealth is None:
            self.set_output(Text("You have no wealth component.", style="red"),
                            title="Buy")
            return
        bought, cost = market.buy(good_id, qty, wealth.total_copper())
        if bought > 0:
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
            self.msg(f"Could not buy {good_id} (insufficient gold or supply).", Color.RED)

    def cmd_sell(self, args: list[str]) -> None:
        if len(args) < 1:
            self.set_output(Text("Usage: sell <good_id> [quantity]", style="dim"),
                            title="Sell")
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
        table = Table(title=f"Market — {market.name}", border_style="gold1")
        table.add_column("Good ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="white")
        table.add_column("Price (cp)", style="gold1", justify="right")
        for g in TradeGoodLibrary.all():
            price = market.price_for(g.id)
            table.add_row(g.id, g.name, str(price))
        self.set_output(table, title=f"Market — {market.name}")

    def cmd_talk(self, args: list[str]) -> None:
        from engine.dialogue.system import DialogueEngine, DialogueLibrary
        if args:
            target = self._find_entity_by_name(" ".join(args))
        else:
            target = self._find_adjacent_npc()
        if target is None:
            self.set_output(Text("There's no one to talk to.", style="dim"),
                            title="Talk")
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
            self._procedural_talk(target)
            return
        self._dialogue_tree = tree
        self._dialogue_ctx = self.engine.dialogue.start(
            self.engine.world, self.engine.player, target, tree,
        )
        self._in_dialogue = True

    def _procedural_talk(self, target: Entity) -> None:
        identity = self.engine.world.get_component(target, Identity)
        name = identity.display_name if identity else "stranger"
        from engine.procedural_dialogue.system import NPCContext
        ctx = NPCContext(npc_name=name, npc_occupation="commoner",
                         npc_mood="neutral", relationship_to_player=0.0)
        line = self.proc_dialogue.generate_greeting(ctx)
        body = Text()
        body.append(f"{name}: {line.text}\n\n", style="yellow")
        body.append("[1] Ask about rumours\n", style="white")
        body.append("[2] Ask about the weather\n", style="white")
        body.append("[3] Ask about trade\n", style="white")
        body.append("[0] End conversation", style="dim")
        self.set_output(body, title=f"Conversation with {name}")
        self._in_dialogue = True
        self._dialogue_tree = None
        self._dialogue_ctx = (target, ctx)

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
            self.msg("You end the conversation.", Color.GRAY)
            return True
        if self._dialogue_tree is None and isinstance(self._dialogue_ctx, tuple):
            target, ctx = self._dialogue_ctx
            identity = self.engine.world.get_component(target, Identity)
            npc_name = identity.display_name if identity else "NPC"
            topic = {"1": "rumours", "2": "weather", "3": "trade"}.get(line)
            if topic is None:
                self.set_output(Text("Invalid choice.", style="red"),
                                title="Conversation")
                return True
            line_obj = self.proc_dialogue.generate_topic_line(topic, ctx)
            body = Text()
            body.append(f"{npc_name}: {line_obj.text}\n\n", style="yellow")
            body.append("[1] Ask about rumours\n", style="white")
            body.append("[2] Ask about the weather\n", style="white")
            body.append("[3] Ask about trade\n", style="white")
            body.append("[0] End conversation", style="dim")
            self.set_output(body, title=f"Conversation with {npc_name}")
            return True
        try:
            choice_idx = int(line) - 1
        except ValueError:
            self.set_output(Text("Invalid choice. Enter a number.", style="red"),
                            title="Conversation")
            return True
        if self._dialogue_tree is None or self._dialogue_ctx is None:
            self._in_dialogue = False
            return True
        node = self._dialogue_tree.get(self._dialogue_ctx.current_node_id)
        if node is None or choice_idx < 0 or choice_idx >= len(node.choices):
            self.set_output(Text("Invalid choice.", style="red"),
                            title="Conversation")
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
            self.msg("You end the conversation.", Color.GRAY)
            return True
        next_node = self._dialogue_tree.get(next_id)
        if next_node is None:
            self._in_dialogue = False
            return True
        self._dialogue_ctx.current_node_id = next_id
        self._dialogue_ctx.visited_nodes.add(next_id)
        self._dialogue_ctx.history.append(next_node.speaker_text)
        return True

    # ----- time, rest, sleep ---------------------------------------------- #

    def cmd_wait(self, args: list[str]) -> None:
        minutes = 60
        if args:
            try:
                minutes = int(args[0])
            except ValueError:
                self.set_output(Text("Usage: wait [minutes]", style="dim"),
                                title="Wait")
                return
        ticks = minutes * self.engine.clock.ticks_per_game_minute
        self.engine.clock.advance_ticks(ticks)
        self.msg(f"You wait for {minutes} minutes.", Color.GRAY)

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
        self.msg("You rest for an hour.", Color.GREEN)

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
        self.msg(f"You sleep for {hours_to_sleep} hours. HP and fatigue restored.",
                 Color.GREEN)

    # ----- help & status --------------------------------------------------- #

    def cmd_help(self, args: list[str]) -> None:
        table = Table(title="Aeon Engine — Commands", border_style="gold1",
                      show_lines=False, title_style="bold gold1")
        table.add_column("Category", style="bold cyan", no_wrap=True)
        table.add_column("Commands", style="white")
        categories = [
            ("Movement", "h j k l (vi-keys) or wasd or arrows; y u b n diagonals; "
                         "go <dir>; . wait"),
            ("Actions", "look [target] (l); attack <t> (a); cast <spell>; use <item>; "
                        "equip <item>; unequip <slot>; drop <item>; pickup; talk [npc] (t); "
                        "trade [npc]"),
            ("Character", "inventory (i); character (c); status (st); spells (sp); "
                          "skills (sk); schools"),
            ("Magic", "cast <spell>; research <name> <school>; meditate [hours]"),
            ("Crafting", "craft <recipe>; recipes; train <skill> [hours]; "
                         "use_skill <skill> [diff]; read <book>; books; "
                         "inscribe <rune> on <item>; runes"),
            ("Economy", "market; buy <good> [qty]; sell <good> [qty]; "
                        "bank <deposit|withdraw|balance> [amt]; loan <take> <amt> [months]; "
                        "caravan <route> <good> <qty>; ship <route> <good> <qty>; trade_routes"),
            ("Auctions", "auction list; auction sell <item> <price>; bid <id> <amt>; "
                         "blackmarket list; blackmarket buy <id>; fence <item>; hire_assassin <id>"),
            ("Quests", "quests; quest list; quest accept <id>; quest advance <q> <s> <o>; "
                       "quest complete <id>; quest abandon <id>"),
            ("Factions", "factions; faction <id>; kingdoms; kingdom <id>; war <a> <b>; "
                         "peace <a> <b>; alliance <a> <b>; annex <k> <t>; election <k>"),
            ("Espionage", "recruit_spy <id> <name>; mission <spy> <type> <target>; "
                          "resolve_mission <id>; spies"),
            ("Rebellion", "rebellion <type> <faction>; suppress <id>; negotiate <id>"),
            ("Combat Var.", "naval <bombard|board> <id>; siege <create|bombard|assault> ...; "
                            "aerial <mount|dive|attack>; space <fire|launch>; "
                            "realtime <queue|cancel>; mount <mount|dismount|charge>"),
            ("Survival", "rest; sleep; wait [min]; diseases; cure <disease>; "
                         "marry <partner>; divorce; family; job"),
            ("Dungeons", "dungeon <type> [depth]; bookmark <add|list|remove>; pin <x> <y> [label]"),
            ("Animals", "hunt <species>; tame <species>; livestock; animals"),
            ("Artifacts", "artifacts; wield <id>; power <id> <name>; "
                          "talk_artifact <id>; destroy <id> <method>"),
            ("Reputation", "reputation; hero <deed>; crime <type>"),
            ("Stealth", "stealth <on|off>; backstab [target]"),
            ("World", "map (m); time; weather; simulate [hours]; contentpacks"),
            ("Themes", "theme list; theme set <name>"),
            ("Dimensions", "dimensions; portal <from> <to>; travel <dim>"),
            ("Body Parts", "bodyparts; heal_part <part> [amount]"),
            ("System", "save [name]; load <name>; plugins; help (?); banner; respawn; "
                         "new_game; memory [npc]; schedule; Quit (q)"),
        ]
        for cat, lines in categories:
            table.add_row(cat, lines)
        self.set_output(table, title="Help")

    def cmd_banner(self, args: list[str]) -> None:
        """Show the welcome banner as a persistent panel."""
        self.set_output(self._banner_panel().renderable, title="Aeon Engine")

    def cmd_status(self, args: list[str]) -> None:
        # Status is always visible in the top panel, but we also surface it
        # as a command output panel so legacy tests can introspect it.
        if self.engine.player is None:
            return
        player = self.engine.player
        world = self.engine.world
        identity = world.get_component(player, Identity)
        health = world.get_component(player, Health)
        name = identity.display_name if identity else "Hero"
        body = Text()
        body.append(f"Name: {name}\n", style="bold gold1")
        if health:
            body.append(f"HP: {health.current}/{health.maximum}\n", style="red")
        self.set_output(body, title="Status")

    def cmd_inventory(self, args: list[str]) -> None:
        if self.engine.player is None:
            return
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            self.set_output(Text("You have no inventory.", style="dim"),
                            title="Inventory")
            return
        body = Text()
        body.append("Equipment:\n", style="bold yellow")
        for slot, item_id in inv.all_equipped().items():
            if item_id is None:
                body.append(f"  {slot.value:15s} (empty)\n", style="dim")
            else:
                item = self.engine.items.get(item_id)
                if item:
                    body.append(f"  {slot.value:15s} {item.display_name}\n", style="white")
        body.append("\nBackpack:\n", style="bold yellow")
        any_items = False
        for slot_idx, item, count in inv.iter_items(self.engine.items):
            any_items = True
            line = f"  [{slot_idx:2d}] {item.display_name}"
            if count > 1:
                line += f" x{count}"
            line += f"  ({item.weight:.1f}kg, {item.total_value}cp)\n"
            body.append(line, style="white")
        if not any_items:
            body.append("  (empty)\n", style="dim")
        weight = inv.total_weight(self.engine.items)
        body.append(f"\nTotal weight: {weight:.1f}/{inv.max_weight:.1f} kg\n",
                    style="dim")
        self.set_output(body, title="Inventory")

    def cmd_character(self, args: list[str]) -> None:
        if self.engine.player is None:
            return
        player = self.engine.player
        identity = self.engine.world.get_component(player, Identity)
        health = self.engine.world.get_component(player, Health)
        stats = self.engine.world.get_component(player, Stats)
        race = self.engine.world.get_component(player, Race)
        wealth = self.engine.world.get_component(player, Wealth)
        body = Text()
        if identity:
            body.append(f"Name: {identity.display_name}\n", style="bold gold1")
            if identity.description:
                body.append(f"Description: {identity.description}\n", style="dim")
        if race:
            body.append(f"Race: {race.race_id.title()}  Age: {race.age}\n", style="white")
        if health:
            body.append(f"HP: {health.current}/{health.maximum}\n", style="red")
        if wealth:
            body.append(f"Wealth: {_format_money(wealth.total_copper())}\n",
                        style="gold1")
        if stats:
            body.append("\nAttributes:\n", style="bold yellow")
            for attr in ("strength", "agility", "endurance", "intelligence",
                         "willpower", "charisma", "perception", "luck"):
                val = getattr(stats, attr)
                body.append(f"  {attr:14s}: {val}\n", style="white")
            body.append("\nDerived:\n", style="bold yellow")
            derived = stats.derived()
            for k, v in derived.items():
                body.append(f"  {k:18s}: {v}\n", style="white")
        self.set_output(body, title="Character")

    def cmd_map(self, args: list[str]) -> None:
        # The map is already always visible; just clear command output.
        self.clear_output()

    def cmd_spells(self, args: list[str]) -> None:
        from engine.magic.spells import SpellLibrary
        mana = (self.engine.world.get_component(self.engine.player, Mana)
                if self.engine.player else None)
        table = Table(title="Spells", border_style="blue")
        table.add_column("Name", style="blue")
        table.add_column("Mana", style="cyan", justify="right")
        table.add_column("Target", style="dim")
        if mana:
            table.caption = f"MP: {mana.current:.0f}/{mana.maximum:.0f}"
        for spell in SpellLibrary.all():
            target_str = spell.target.value if spell.target.value != "self" else "—"
            table.add_row(spell.name, str(spell.mana_cost), target_str)
        self.set_output(table, title="Spells")

    def cmd_skills(self, args: list[str]) -> None:
        from engine.entities.components import Skills as SkillsComp
        from engine.skills.system import SkillLibrary
        comp = (self.engine.world.get_component(self.engine.player, SkillsComp)
                if self.engine.player else None)
        table = Table(title="Skills", border_style="cyan")
        table.add_column("Skill", style="cyan")
        table.add_column("Level", style="white", justify="right")
        table.add_column("XP", style="dim", justify="right")
        if comp is None or not comp.skills:
            table.add_row("(no skills yet — try: train <skill>)", "", "")
        else:
            for skill_id, sl in sorted(comp.skills.items(),
                                        key=lambda x: -x[1].level):
                skill = SkillLibrary.get(skill_id)
                name = skill.name if skill else skill_id
                table.add_row(name, str(sl.level), f"{sl.xp:.0f}")
        self.set_output(table, title="Skills")

    def cmd_quests(self, args: list[str]) -> None:
        if self.engine.player is None:
            return
        tracker = self.engine.quest_trackers.get(self.engine.player.id)
        if tracker is None:
            self.set_output(Text("You have no quest log.", style="dim"),
                            title="Quests")
            return
        body = Text()
        if tracker.active:
            body.append("Active Quests:\n", style="bold yellow")
            from engine.quests.system import QuestLibrary
            for quest_id, stage_id in tracker.active.items():
                quest = QuestLibrary.get(quest_id)
                if quest:
                    body.append(f"  {quest.name} (stage: {stage_id})\n", style="white")
                    body.append(f"    {quest.description}\n", style="dim")
        else:
            body.append("No active quests.\n", style="dim")
        if tracker.completed:
            body.append(f"\nCompleted: {len(tracker.completed)}\n", style="green")
        if tracker.failed:
            body.append(f"Failed: {len(tracker.failed)}\n", style="red")
        self.set_output(body, title="Quest Log")

    def cmd_quest(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text(
                "Usage: quest <list|accept|advance|complete|abandon> ...",
                style="dim"), title="Quest")
            return
        sub = args[0].lower()
        from engine.quests.system import QuestLibrary, QuestTracker
        tracker = self.engine.quest_trackers.get(self.engine.player.id)
        if tracker is None:
            tracker = self.engine.quest_trackers.setdefault(
                self.engine.player.id, QuestTracker())
        if sub == "list":
            table = Table(title="Available Quests", border_style="gold1")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Name", style="white")
            table.add_column("Description", style="dim")
            for q in QuestLibrary.all():
                table.add_row(str(q.id), q.name, q.description)
            self.set_output(table, title="Available Quests")
        elif sub == "accept":
            if len(args) < 2:
                self.set_output(Text("Usage: quest accept <quest_id>", style="dim"),
                                title="Quest")
                return
            try:
                qid = int(args[1])
            except ValueError:
                qid = args[1]
            q = QuestLibrary.get(qid)
            if q is None:
                self.set_output(Text(f"Unknown quest: {args[1]}", style="red"),
                                title="Quest")
                return
            tracker.start(q, self.engine.clock.time.tick)
            self.msg(f"Quest accepted: {q.name}", Color.GREEN)
        elif sub == "advance":
            if len(args) < 4:
                self.set_output(Text(
                    "Usage: quest advance <quest_id> <stage> <obj> [n]",
                    style="dim"), title="Quest")
                return
            amount = int(args[4]) if len(args) > 4 and args[4].isdigit() else 1
            tracker.advance_objective(args[1], args[2], args[3], amount)
            self.msg(f"Objective advanced: {args[3]} (+{amount})", Color.GREEN)
        elif sub == "complete":
            if len(args) < 2:
                self.set_output(Text("Usage: quest complete <quest_id>", style="dim"),
                                title="Quest")
                return
            tracker.complete_quest(args[1])
            self.msg(f"Quest completed: {args[1]}", Color.GREEN)
        elif sub == "abandon":
            if len(args) < 2:
                self.set_output(Text("Usage: quest abandon <quest_id>", style="dim"),
                                title="Quest")
                return
            tracker.abandon_quest(args[1])
            self.msg(f"Quest abandoned: {args[1]}", Color.YELLOW)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Quest")

    def cmd_time(self, args: list[str]) -> None:
        time_str = self.engine.clock.time.display()
        phase = self.engine.clock.time.phase_of_day().display_name
        season = self.engine.clock.time.season_name()
        body = Text()
        body.append(f"{time_str}\n", style="cyan")
        body.append(f"Phase: {phase}\n", style="dim")
        body.append(f"Season: {season}\n", style="dim")
        body.append(f"Tick: {self.engine.clock.time.tick}\n", style="dim")
        self.set_output(body, title="Time")

    def cmd_weather(self, args: list[str]) -> None:
        if self.engine.weather is None:
            return
        body = Text(self.engine.weather.current.description(), style="cyan")
        self.set_output(body, title="Weather")

    def cmd_plugins(self, args: list[str]) -> None:
        table = Table(title="Plugins", border_style="magenta")
        table.add_column("Name", style="white")
        table.add_column("Version", style="cyan")
        table.add_column("State", style="dim")
        try:
            for s in self.engine.plugins.status():
                table.add_row(s["name"], s["version"], s["state"])
        except Exception as exc:  # noqa: BLE001
            table.add_row(f"Error: {exc}", "", "")
        self.set_output(table, title="Plugins")

    def cmd_save(self, args: list[str]) -> None:
        name = args[0] if args else "quicksave"
        try:
            self.engine.save_game(name)
            self.msg(f"Game saved as '{name}'.", Color.GREEN)
        except Exception as exc:  # noqa: BLE001
            self.msg(f"Save failed: {exc}", Color.RED)

    def cmd_load(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Load what? Try: load my_save", style="dim"),
                            title="Load")
            return
        try:
            self.engine.load_game(args[0])
            self.msg(f"Loaded save '{args[0]}'.", Color.GREEN)
        except FileNotFoundError:
            self.msg(f"Save '{args[0]}' not found.", Color.RED)
        except Exception as exc:  # noqa: BLE001
            self.msg(f"Load failed: {exc}", Color.RED)

    def cmd_quit(self, args: list[str]) -> None:
        self.running = False
        self.engine.shutdown()

    def cmd_respawn(self, args: list[str]) -> None:
        """Manually respawn (useful if the player gets stuck or dies)."""
        if self.engine.player is None:
            return
        self.engine.respawn_player()
        self._game_over = False
        self.set_output(Text("You have been restored to full health at the spawn point.",
                             style="green"), title="Respawned")

    def cmd_new_game(self, args: list[str]) -> None:
        """Start a brand new game with a fresh world."""
        name = args[0] if args else "Hero"
        self.engine.new_game(name)
        self._game_over = False
        self.set_output(Text("A new world has been generated. Your adventure begins anew.",
                             style="cyan"), title="New Game")

    def cmd_memory(self, args: list[str]) -> None:
        """Show an NPC's memories (integrates the NPC memory system)."""
        if args:
            target = self._find_entity_by_name(" ".join(args))
        else:
            target = self._find_adjacent_npc()
        if target is None:
            self.set_output(Text("No NPC nearby to inspect. Usage: memory [npc_name]",
                                 style="dim"), title="Memory")
            return
        from engine.entities.components import Memory as MemoryComp, Identity
        mem = self.engine.world.get_component(target, MemoryComp)
        ident = self.engine.world.get_component(target, Identity)
        name = ident.display_name if ident else "NPC"
        body = Text()
        body.append(f"{name}'s memories:\n", style="bold gold1")
        if mem is None or not mem.memories:
            body.append("  (no memories yet)\n", style="dim")
        else:
            for i, m in enumerate(mem.memories[-15:]):
                desc = m.get("description", str(m)) if isinstance(m, dict) else str(m)
                body.append(f"  [{i}] {desc[:80]}\n", style="white")
            body.append(f"\nKnowledge: {len(mem.knowledge)} facts\n", style="dim")
            for k, v in list(mem.knowledge.items())[:10]:
                body.append(f"  {k}: {v:.1f}\n", style="dim")
        self.set_output(body, title=f"Memory — {name}")

    def cmd_schedule(self, args: list[str]) -> None:
        """Show the current daily schedule phase (integrates the schedule system)."""
        try:
            phase = self.engine.clock.time.phase_of_day()
            phase_name = phase.display_name
        except Exception:  # noqa: BLE001
            phase_name = "Unknown"
        hour = self.engine.clock.time.hour
        body = Text()
        body.append(f"Current phase: {phase_name}\n", style="cyan")
        body.append(f"Hour: {hour:02d}:00\n", style="white")
        body.append("\nNPC routine targets:\n", style="bold yellow")
        body.append("  Dawn (4-7):   gather at market\n", style="white")
        body.append("  Day (7-17):   scatter to work\n", style="white")
        body.append("  Dusk (17-20): gather at tavern\n", style="white")
        body.append("  Night (20-4): return home to sleep\n", style="white")
        self.set_output(body, title="Daily Schedule")

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
            self.msg("You need to be near water to fish.", Color.GRAY)
            return
        if self.engine.rng.chance(0.5):
            from engine.items.generator import ItemGenerationParams
            fish_types = ["fish", "salmon", "trout"]
            fish_name = self.engine.rng.choice(fish_types)
            params = ItemGenerationParams(archetype="bread", material_id="organic")
            item = self.engine.item_generator.generate(params, self.engine.items.next_id())
            item.name = fish_name.title()
            item.description = f"A fresh-caught {fish_name}."
            item.tags.append("food")
            item.add_property("food", 35.0)
            self.engine.items.register(item)
            inv = self.engine.inventories.get(self.engine.player.id)
            if inv:
                inv.add(item)
            self.msg(f"You caught a {fish_name}!", Color.GREEN)
        else:
            self.msg("You wait, but nothing bites...", Color.GRAY)

    # ----- crafting & skills ---------------------------------------------- #

    def cmd_craft(self, args: list[str]) -> None:
        if not args:
            self.cmd_recipes([])
            return
        from engine.crafting.system import RecipeLibrary
        recipe = RecipeLibrary.get(args[0])
        if recipe is None:
            self.set_output(Text(f"Unknown recipe: {args[0]}", style="red"),
                            title="Craft")
            return
        inv = self.engine.inventories.get(self.engine.player.id)
        if inv is None:
            self.set_output(Text("You have no inventory.", style="red"),
                            title="Craft")
            return
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
        table = Table(title="Recipes", border_style="yellow")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Skill", style="dim")
        table.add_column("Lv", style="dim", justify="right")
        table.add_column("Materials", style="white")
        for r in RecipeLibrary.all():
            mats = ", ".join(f"{n}x{k}" for k, n in r.materials.items())
            table.add_row(r.id, r.name, r.skill_id, str(r.skill_level_required), mats)
        self.set_output(table, title="Recipes")

    def cmd_train(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: train <skill> [hours]", style="dim"),
                            title="Train")
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
            self.set_output(Text("Usage: use_skill <skill> [difficulty]",
                                 style="dim"), title="Use Skill")
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
            self.set_output(Text("Usage: read <book_id>", style="dim"),
                            title="Read")
            return
        from engine.skill_books.system import SkillBookLibrary
        book = SkillBookLibrary.get(args[0])
        if book is None:
            self.set_output(Text(f"Unknown book: {args[0]}", style="red"),
                            title="Read")
            return
        ok, msg = self.skill_books.start_reading(self.engine.player, book)
        self.msg(msg, Color.GREEN if ok else Color.RED)

    def cmd_books(self, args: list[str]) -> None:
        from engine.skill_books.system import SkillBookLibrary
        table = Table(title="Skill Books", border_style="yellow")
        table.add_column("ID", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Type", style="dim")
        table.add_column("Skill", style="dim")
        for b in SkillBookLibrary.all():
            table.add_row(b.book_id, b.title, b.book_type.value, b.skill_id)
        self.set_output(table, title="Skill Books")

    def cmd_inscribe(self, args: list[str]) -> None:
        if len(args) < 3 or args[1] != "on":
            self.set_output(Text("Usage: inscribe <rune_id> on <item_name>",
                                 style="dim"), title="Inscribe")
            return
        rune_id = args[0]
        item_name = " ".join(args[2:]).lower()
        from engine.runes.system import RuneLibrary
        rune = RuneLibrary.get(rune_id)
        if rune is None:
            self.set_output(Text(f"Unknown rune: {rune_id}", style="red"),
                            title="Inscribe")
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
            self.set_output(Text(f"You don't have any '{item_name}'.", style="red"),
                            title="Inscribe")
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
        table = Table(title="Runes", border_style="red")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Type", style="dim")
        table.add_column("Power", style="dim", justify="right")
        for r in RuneLibrary.all():
            table.add_row(r.rune_id, r.name, r.rune_type.value, str(r.base_power))
        self.set_output(table, title="Runes")

    # ----- economy: bank / loan ------------------------------------------- #

    def cmd_bank(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: bank <deposit|withdraw|balance> [amount]",
                                 style="dim"), title="Bank")
            return
        sub = args[0].lower()
        if not self.engine.economy.banks:
            self.engine.economy.create_bank("b1", "Central Bank", (0, 0))
        bank = list(self.engine.economy.banks.values())[0]
        pid = self.engine.player.id
        if sub == "balance":
            acct = bank.accounts.get(pid)
            if acct:
                self.set_output(Text(f"Bank balance: {_format_money(acct.balance)}",
                                     style="gold1"), title="Bank Balance")
            else:
                self.set_output(Text("You have no bank account.", style="dim"),
                                title="Bank Balance")
        elif sub == "deposit":
            if len(args) < 2 or not args[1].isdigit():
                self.set_output(Text("Usage: bank deposit <amount_copper>",
                                     style="dim"), title="Bank")
                return
            amount = int(args[1])
            wealth = self.engine.world.get_component(self.engine.player, Wealth)
            if wealth is None or wealth.total_copper() < amount:
                self.msg("You don't have that much money.", Color.RED)
                return
            bank.open_account(pid)
            bank.deposit(pid, amount)
            wealth.copper = max(0, wealth.copper - amount)
            self.msg(f"Deposited {_format_money(amount)}.", Color.GREEN)
        elif sub == "withdraw":
            if len(args) < 2 or not args[1].isdigit():
                self.set_output(Text("Usage: bank withdraw <amount_copper>",
                                     style="dim"), title="Bank")
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
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Bank")

    def cmd_loan(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: loan <take|repay> <amount> [months]",
                                 style="dim"), title="Loan")
            return
        sub = args[0].lower()
        if not self.engine.economy.banks:
            self.engine.economy.create_bank("b1", "Central Bank", (0, 0))
        bank = list(self.engine.economy.banks.values())[0]
        pid = self.engine.player.id
        if sub == "take":
            if len(args) < 2 or not args[1].isdigit():
                self.set_output(Text("Usage: loan take <amount> [months]",
                                     style="dim"), title="Loan")
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
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Loan")

    def cmd_caravan(self, args: list[str]) -> None:
        if len(args) < 3:
            self.set_output(Text("Usage: caravan <route_id> <good> <qty>",
                                 style="dim"), title="Caravan")
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
            self.set_output(Text("Usage: ship <route_id> <good> <qty>",
                                 style="dim"), title="Ship")
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
        table = Table(title="Trade Routes", border_style="cyan")
        table.add_column("Route", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("From → To", style="dim")
        routes = list(self.trade.routes())
        for r in routes:
            table.add_row(r.route_id, r.name,
                          f"{r.origin_market_id} → {r.destination_market_id}")
        if not routes:
            table.add_row("(none)", "", "")
        self.set_output(table, title="Trade Routes")

    # ----- auctions & black market ---------------------------------------- #

    def cmd_auction(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: auction <list|sell> ...", style="dim"),
                            title="Auction")
            return
        sub = args[0].lower()
        if sub == "list":
            table = Table(title="Auctions", border_style="magenta")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Title", style="white")
            table.add_column("Price", style="gold1", justify="right")
            table.add_column("State", style="dim")
            auctions = list(self.auctions.all())
            for a in auctions:
                table.add_row(str(a.auction_id), a.title,
                              f"{a.current_price}cp", a.state.name)
            if not auctions:
                table.add_row("—", "(none — use 'auction sell <item> <price>')", "", "")
            self.set_output(table, title="Auctions")
        elif sub == "sell":
            if len(args) < 3:
                self.set_output(Text("Usage: auction sell <item_name> <starting_price>",
                                     style="dim"), title="Auction")
                return
            try:
                price = int(args[-1])
            except ValueError:
                self.set_output(Text(f"Invalid price: {args[-1]}", style="red"),
                                title="Auction")
                return
            item_name = " ".join(args[1:-1]).lower()
            inv = self.engine.inventories.get(self.engine.player.id)
            target = None
            for _, item, _ in inv.iter_items(self.engine.items):
                if item_name in item.display_name.lower():
                    target = item
                    break
            if target is None:
                self.set_output(Text(f"You don't have any '{item_name}'.",
                                     style="red"), title="Auction")
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
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Auction")

    def cmd_bid(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: bid <auction_id> <amount>", style="dim"),
                            title="Bid")
            return
        ok, msg = self.auctions.place_bid(
            int(args[0]), self.engine.player.id, int(args[1]),
            current_tick=self.engine.clock.time.tick,
        )
        self.msg(msg, Color.GREEN if ok else Color.RED)

    def cmd_blackmarket(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: blackmarket <list|buy> ...", style="dim"),
                            title="Black Market")
            return
        sub = args[0].lower()
        markets = self.blackmarket.markets()
        if not markets:
            self.blackmarket.create_market("Underground Market", (0, 0))
            markets = self.blackmarket.markets()
        market = markets[0]
        market_id = market.market_id
        if sub == "list":
            table = Table(title="Black Market", border_style="red")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Item", style="white")
            table.add_column("Price", style="gold1", justify="right")
            for lst in market.listings:
                table.add_row(str(lst.listing_id), lst.item_name, f"{lst.price}cp")
            if not market.listings:
                table.add_row("—", "(nothing for sale)", "")
            self.set_output(table, title="Black Market")
        elif sub == "buy":
            if len(args) < 2:
                self.set_output(Text("Usage: blackmarket buy <listing_id>",
                                     style="dim"), title="Black Market")
                return
            wealth = self.engine.world.get_component(self.engine.player, Wealth)
            result = self.blackmarket.buy_from_market(
                market_id, int(args[1]), self.engine.player.id,
                wealth.total_copper() if wealth else 0,
            )
            self.msg(result.get("message", "Done"),
                     Color.GREEN if result.get("success") else Color.RED)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Black Market")

    def cmd_fence(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: fence <item_name>", style="dim"),
                            title="Fence")
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
        self.set_output(Text(f"You don't have any '{item_name}'.", style="red"),
                        title="Fence")

    def cmd_hire_assassin(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: hire_assassin <target_id>", style="dim"),
                            title="Hire Assassin")
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
        table = Table(title="Factions", border_style="yellow")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="white")
        table.add_column("Type", style="dim")
        table.add_column("Description", style="dim")
        for f in FactionLibrary.all():
            table.add_row(str(f.id), f.name, f.type.value, f.description[:60])
        self.set_output(table, title="Factions")

    def cmd_faction(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: faction <id>", style="dim"),
                            title="Faction")
            return
        from engine.factions.system import FactionLibrary
        f = FactionLibrary.get(int(args[0]))
        if f is None:
            self.set_output(Text(f"Unknown faction: {args[0]}", style="red"),
                            title="Faction")
            return
        body = Text()
        body.append(f"{f.name}\n", style="bold gold1")
        body.append(f"Type: {f.type.value}\n", style="white")
        body.append(f"Leader: {f.leader_id}\n", style="white")
        body.append(f"Population: {f.population}\n", style="white")
        body.append(f"Military: {f.military_strength}\n", style="white")
        body.append(f"Treasury: {_format_money(f.treasury)}\n", style="gold1")
        body.append(f"\n{f.description}\n", style="dim")
        self.set_output(body, title=f.name)

    # ----- kingdoms -------------------------------------------------------- #

    def cmd_kingdoms(self, args: list[str]) -> None:
        from engine.kingdoms.system import KingdomLibrary
        table = Table(title="Kingdoms", border_style="gold1")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="white")
        table.add_column("Type", style="dim")
        for k in KingdomLibrary.all():
            table.add_row(str(k.id), k.name, k.kingdom_type.name)
        self.set_output(table, title="Kingdoms")

    def cmd_kingdom(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: kingdom <id>", style="dim"),
                            title="Kingdom")
            return
        from engine.kingdoms.system import KingdomLibrary
        k = KingdomLibrary.get(int(args[0]))
        if k is None:
            self.set_output(Text(f"Unknown kingdom: {args[0]}", style="red"),
                            title="Kingdom")
            return
        body = Text()
        body.append(f"{k.name}\n", style="bold gold1")
        body.append(f"Type: {k.kingdom_type.name}\n", style="white")
        body.append(f"Ruler: {getattr(k, 'ruler_id', 'unknown')}\n", style="white")
        body.append(f"Stability: {getattr(k, 'stability', 0):.1f}\n", style="white")
        body.append(f"Legitimacy: {getattr(k, 'legitimacy', 0):.1f}\n", style="white")
        body.append(f"Treasury: {_format_money(getattr(k, 'treasury', 0))}\n",
                    style="gold1")
        self.set_output(body, title=k.name)

    def cmd_war(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: war <faction_a> <faction_b>", style="dim"),
                            title="War")
            return
        self.engine.factions.declare_war(int(args[0]), int(args[1]),
                                          current_tick=self.engine.clock.time.tick)
        self.msg(f"War declared between {args[0]} and {args[1]}.", Color.RED)

    def cmd_peace(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: peace <faction_a> <faction_b>", style="dim"),
                            title="Peace")
            return
        self.engine.factions.make_peace(int(args[0]), int(args[1]),
                                         current_tick=self.engine.clock.time.tick)
        self.msg(f"Peace made between {args[0]} and {args[1]}.", Color.GREEN)

    def cmd_alliance(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: alliance <kingdom_a> <kingdom_b>",
                                 style="dim"), title="Alliance")
            return
        ok = self.kingdoms.form_alliance(int(args[0]), int(args[1]),
                                          current_tick=self.engine.clock.time.tick)
        self.msg(f"Alliance {'formed' if ok else 'failed'} between {args[0]} and {args[1]}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_annex(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: annex <kingdom_id> <territory_id>",
                                 style="dim"), title="Annex")
            return
        ok = self.kingdoms.annex_territory(int(args[0]), int(args[1]))
        self.msg(f"Annexation {'succeeded' if ok else 'failed'}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_election(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: election <kingdom_id>", style="dim"),
                            title="Election")
            return
        winner = self.kingdoms.hold_election(int(args[0]),
                                              current_tick=self.engine.clock.time.tick)
        self.msg(f"Election winner: {winner}",
                 Color.GREEN if winner else Color.RED)

    # ----- espionage ------------------------------------------------------- #

    def cmd_recruit_spy(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: recruit_spy <entity_id> <name>",
                                 style="dim"), title="Recruit Spy")
            return
        spy = self.espionage.recruit_spy(
            int(args[0]), args[1], current_tick=self.engine.clock.time.tick,
        )
        self.msg(f"Spy recruited: {spy.name} (id {spy.spy_id})", Color.GREEN)

    def cmd_mission(self, args: list[str]) -> None:
        if len(args) < 3:
            self.set_output(Text(
                "Usage: mission <spy_id> <type> <target_faction>",
                style="dim"), title="Mission")
            return
        from engine.espionage.system import MissionType
        try:
            mtype = MissionType[args[1].upper()]
        except KeyError:
            self.set_output(Text(f"Unknown mission type: {args[1]}", style="red"),
                            title="Mission")
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
            self.set_output(Text("Usage: resolve_mission <mission_id>",
                                 style="dim"), title="Resolve Mission")
            return
        result = self.espionage.resolve_mission(int(args[0]),
                                                  current_tick=self.engine.clock.time.tick)
        self.msg(f"Mission result: {result.state.name}", Color.YELLOW)

    def cmd_spies(self, args: list[str]) -> None:
        table = Table(title="Spies", border_style="red")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="white")
        table.add_column("Stealth", style="dim", justify="right")
        for s in self.espionage.spies():
            table.add_row(str(s.spy_id), s.name, str(s.stealth))
        if not self.espionage.spies():
            table.add_row("—", "(no spies recruited)", "")
        self.set_output(table, title="Spies")

    # ----- rebellions ------------------------------------------------------ #

    def cmd_rebellion(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: rebellion <type> <faction_id>",
                                 style="dim"), title="Rebellion")
            return
        from engine.rebellions.system import RebellionType
        try:
            rtype = RebellionType[args[0].upper()]
        except KeyError:
            self.set_output(Text(f"Unknown rebellion type: {args[0]}",
                                 style="red"), title="Rebellion")
            return
        r = self.rebellions.start_rebellion(
            name=f"{rtype.value} #{args[1]}", rebellion_type=rtype,
            faction_id=int(args[1]), current_tick=self.engine.clock.time.tick,
        )
        self.msg(f"Rebellion {r.rebellion_id} started.", Color.RED)

    def cmd_suppress(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: suppress <rebellion_id>", style="dim"),
                            title="Suppress")
            return
        ok = self.rebellions.suppress_rebellion(int(args[0]),
                                                  current_tick=self.engine.clock.time.tick)
        self.msg(f"Rebellion {'suppressed' if ok else 'not suppressed'}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_negotiate(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: negotiate <rebellion_id>", style="dim"),
                            title="Negotiate")
            return
        ok = self.rebellions.negotiate_settlement(int(args[0]),
                                                    current_tick=self.engine.clock.time.tick)
        self.msg(f"Negotiation {'succeeded' if ok else 'failed'}.",
                 Color.GREEN if ok else Color.RED)

    # ----- survival & life ------------------------------------------------- #

    def cmd_diseases(self, args: list[str]) -> None:
        from engine.survival.system import DiseaseLibrary
        table = Table(title="Diseases", border_style="red")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="red")
        table.add_column("Description", style="dim")
        for d in DiseaseLibrary.all():
            table.add_row(d.id, d.name, d.description[:60])
        self.set_output(table, title="Diseases")

    def cmd_cure(self, args: list[str]) -> None:
        diseases = self.engine.survival.diseases_of(self.engine.player)
        if not diseases:
            self.msg("You have no diseases.", Color.GREEN)
            return
        if not args:
            body = Text("You have:\n", style="yellow")
            for d in diseases:
                body.append(f"  {d.disease_id} (severity {d.severity:.1f})\n",
                            style="red")
            body.append("\nUsage: cure <disease_id>", style="dim")
            self.set_output(body, title="Cure")
            return
        for d in diseases:
            if d.disease_id == args[0]:
                d.severity = 0
                d.remaining_duration = 0
                self.msg(f"You cure {d.disease_id}.", Color.GREEN)
                return
        self.msg(f"You don't have {args[0]}.", Color.RED)

    def cmd_marry(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: marry <partner_name>", style="dim"),
                            title="Marry")
            return
        partner = self._find_entity_by_name(" ".join(args))
        if partner is None:
            self.set_output(Text("No such person nearby.", style="red"),
                            title="Marry")
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
        body = Text()
        if family is None:
            body.append("You have no family.\n", style="dim")
        else:
            body.append(f"Family: {family.surname}\n", style="white")
            body.append(f"Wealth class: {family.wealth_class}\n", style="white")
            body.append(f"Members: {len(family.members)}\n", style="white")
        marriage = self.life.marriage_of(self.engine.player.id)
        if marriage:
            body.append(f"Married to entity #{marriage.spouse_a if marriage.spouse_b == self.engine.player.id else marriage.spouse_b}\n",
                        style="magenta")
        self.set_output(body, title="Family")

    def cmd_job(self, args: list[str]) -> None:
        postings = self.life.job_market.all()
        table = Table(title="Job Market", border_style="yellow")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Title", style="white")
        table.add_column("Salary", style="gold1", justify="right")
        for p in postings[:10]:
            table.add_row(str(p.posting_id), p.title, f"{p.salary}cp/mo")
        if not postings:
            table.add_row("—", "(no jobs available)", "")
        self.set_output(table, title="Job Market")

    # ----- dungeons & exploration ----------------------------------------- #

    def cmd_dungeon(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: dungeon <type> [depth]", style="dim"),
                            title="Dungeon")
            return
        from engine.dungeons.system import DungeonType
        try:
            dtype = DungeonType[args[0].upper()]
        except KeyError:
            self.set_output(Text(f"Unknown dungeon type: {args[0]}", style="red"),
                            title="Dungeon")
            return
        depth = int(args[1]) if len(args) > 1 and args[1].isdigit() else 5
        pos = self.engine.world.get_component(self.engine.player, Position)
        loc = (pos.x, pos.y) if pos else (0, 0)
        d = self.dungeons.generate(
            name=f"{dtype.value} #{self.engine.rng.randint(1000, 9999)}",
            dungeon_type=dtype, location=loc, depth=depth,
            dungeon_id=self.engine.rng.randint(1, 99999),
        )
        body = Text()
        body.append(f"{d.name}\n", style="bold gold1")
        body.append(f"Type: {d.dungeon_type.value}\n", style="white")
        body.append(f"Depth: {d.depth}\n", style="white")
        body.append(f"Location: {d.location}\n", style="dim")
        self.msg(f"Dungeon generated: {d.name} ({d.depth} levels)", Color.GREEN)
        self.set_output(body, title="Dungeon")

    def cmd_bookmark(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: bookmark <add|list|remove> ...",
                                 style="dim"), title="Bookmark")
            return
        sub = args[0].lower()
        if sub == "add":
            if len(args) < 2:
                self.set_output(Text("Usage: bookmark add <name>", style="dim"),
                                title="Bookmark")
                return
            name = " ".join(args[1:])
            pos = self.engine.world.get_component(self.engine.player, Position)
            b = self.bookmarks.add_bookmark(name, pos.x if pos else 0,
                                             pos.y if pos else 0)
            self.msg(f"Bookmark '{b.name}' added at ({b.x}, {b.y}).", Color.GREEN)
        elif sub == "list":
            table = Table(title="Bookmarks", border_style="cyan")
            table.add_column("ID", style="cyan", justify="right")
            table.add_column("Name", style="white")
            table.add_column("Location", style="dim")
            bms = list(self.bookmarks.all_bookmarks())
            for b in bms:
                table.add_row(str(b.bookmark_id), b.name, f"({b.x}, {b.y})")
            if not bms:
                table.add_row("—", "(no bookmarks)", "")
            self.set_output(table, title="Bookmarks")
        elif sub == "remove":
            if len(args) < 2:
                self.set_output(Text("Usage: bookmark remove <id>", style="dim"),
                                title="Bookmark")
                return
            ok = self.bookmarks.remove_bookmark(int(args[1]))
            self.msg("Bookmark removed." if ok else "Not found.",
                     Color.GREEN if ok else Color.RED)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Bookmark")

    def cmd_pin(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: pin <x> <y> [label]", style="dim"),
                            title="Pin")
            return
        x, y = int(args[0]), int(args[1])
        label = " ".join(args[2:]) if len(args) > 2 else ""
        pin = self.bookmarks.add_pin(x, y, label=label)
        self.msg(f"Pin '{pin.label}' placed at ({x}, {y}).", Color.GREEN)

    # ----- animals & hunting ---------------------------------------------- #

    def cmd_hunt(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: hunt <species_id>", style="dim"),
                            title="Hunt")
            return
        from engine.entities.components import Skills as SkillsComp
        comp = self.engine.world.get_component(self.engine.player, SkillsComp)
        skill_level = (comp.skills.get("hunting").level
                       if comp and "hunting" in comp.skills else 1)
        yield_ = self.animals.hunt(args[0], "region_0", (0, 0), 1, skill_level)
        self.msg(f"You hunt {args[0]} and acquire {yield_} units.", Color.GREEN)

    def cmd_tame(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: tame <species_id>", style="dim"),
                            title="Tame")
            return
        result = self.animals.domestication.tame_attempt(
            args[0], self.engine.player.id, skill_level=1,
            current_tick=self.engine.clock.time.tick,
        )
        self.msg(f"Tame attempt: {result}", Color.YELLOW)

    def cmd_livestock(self, args: list[str]) -> None:
        herds = self.animals.livestock.herd_of(self.engine.player.id)
        table = Table(title="Livestock", border_style="yellow")
        table.add_column("Species", style="cyan")
        table.add_column("Count", style="white", justify="right")
        if herds:
            for species_id, count in herds.items():
                table.add_row(species_id, str(count))
        else:
            table.add_row("(none)", "")
        self.set_output(table, title="Livestock")

    def cmd_animals(self, args: list[str]) -> None:
        from engine.animals.system import AnimalLibrary
        table = Table(title="Animal Species", border_style="green")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        for s in AnimalLibrary.all():
            sid = getattr(s, "id", getattr(s, "species_id", "?"))
            table.add_row(sid, s.name)
        self.set_output(table, title="Animals")

    # ----- artifacts ------------------------------------------------------- #

    def cmd_artifacts(self, args: list[str]) -> None:
        from engine.artifacts.system import ArtifactLibrary
        table = Table(title="Artifacts", border_style="magenta")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Rarity", style="magenta")
        table.add_column("Owner", style="dim", justify="right")
        for a in ArtifactLibrary.all():
            table.add_row(a.artifact_id, a.name, a.rarity.value,
                          str(a.owner_id) if a.owner_id is not None else "—")
        self.set_output(table, title="Artifacts")

    def cmd_wield(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: wield <artifact_id>", style="dim"),
                            title="Wield")
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.set_output(Text(f"Unknown artifact: {args[0]}", style="red"),
                            title="Wield")
            return
        self.artifacts.wield(artifact, self.engine.player.id)
        self.msg(f"You wield {artifact.name}.", Color.GREEN)

    def cmd_power(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: power <artifact_id> <power_name>",
                                 style="dim"), title="Power")
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.set_output(Text(f"Unknown artifact: {args[0]}", style="red"),
                            title="Power")
            return
        ok, msg = self.artifacts.use_power(artifact, args[1],
                                            current_tick=self.engine.clock.time.tick)
        self.msg(msg, Color.GREEN if ok else Color.RED)

    def cmd_talk_artifact(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: talk_artifact <artifact_id>",
                                 style="dim"), title="Talk Artifact")
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.set_output(Text(f"Unknown artifact: {args[0]}", style="red"),
                            title="Talk Artifact")
            return
        response = self.artifacts.communicate(artifact, "Hello, mighty artifact.")
        if response:
            self.msg(f"{artifact.name}: {response}", Color.MANA)
        else:
            self.msg(f"{artifact.name} is silent.", Color.GRAY)

    def cmd_destroy(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: destroy <artifact_id> <method>",
                                 style="dim"), title="Destroy")
            return
        from engine.artifacts.system import ArtifactLibrary
        artifact = ArtifactLibrary.get(args[0])
        if artifact is None:
            self.set_output(Text(f"Unknown artifact: {args[0]}", style="red"),
                            title="Destroy")
            return
        ok, msg = self.artifacts.attempt_destroy(artifact, args[1])
        self.msg(msg, Color.GREEN if ok else Color.RED)

    # ----- reputation ------------------------------------------------------ #

    def cmd_reputation(self, args: list[str]) -> None:
        from engine.reputation.system import ReputationType
        table = Table(title="Reputation", border_style="yellow")
        table.add_column("Type", style="cyan")
        table.add_column("Level", style="white")
        table.add_column("Value", style="dim", justify="right")
        for rt in ReputationType:
            level = self.reputation.level(self.engine.player.id, rt)
            value = self.reputation.get(self.engine.player.id, rt)
            level_name = level.name if hasattr(level, "name") else str(level)
            rt_name = rt.name if hasattr(rt, "name") else str(rt)
            table.add_row(rt_name, level_name, f"{value:+.0f}")
        self.set_output(table, title="Reputation")

    def cmd_hero(self, args: list[str]) -> None:
        deed = " ".join(args) if args else "a heroic deed"
        from engine.reputation.system import ReputationType
        self.reputation.adjust(self.engine.player.id, ReputationType.HEROIC,
                               10, reason=deed,
                               current_tick=self.engine.clock.time.tick)
        self.msg(f"You perform {deed}. (+10 heroic reputation)", Color.GREEN)

    def cmd_crime(self, args: list[str]) -> None:
        crime = " ".join(args) if args else "a petty crime"
        from engine.reputation.system import ReputationType
        self.reputation.adjust(self.engine.player.id, ReputationType.CRIMINAL,
                               -10, reason=crime,
                               current_tick=self.engine.clock.time.tick)
        self.msg(f"You commit {crime}. (-10 criminal reputation)", Color.RED)

    # ----- stealth --------------------------------------------------------- #

    def cmd_stealth(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: stealth <on|off>", style="dim"),
                            title="Stealth")
            return
        if args[0].lower() == "on":
            ok = self.stealth.enter_stealth(self.engine.player)
            self.msg("You enter stealth." if ok else "Cannot enter stealth.",
                     Color.GREEN if ok else Color.RED)
        elif args[0].lower() == "off":
            self.stealth.exit_stealth(self.engine.player)
            self.msg("You exit stealth.", Color.GRAY)
        else:
            self.set_output(Text("Usage: stealth <on|off>", style="dim"),
                            title="Stealth")

    def cmd_backstab(self, args: list[str]) -> None:
        if not args:
            target = self._find_adjacent_hostile()
            if target is None:
                self.set_output(Text("Backstab what?", style="dim"),
                                title="Backstab")
                return
        else:
            target = self._find_entity_by_name(" ".join(args))
            if target is None:
                self.set_output(Text(f"You don't see any '{' '.join(args)}' here.",
                                     style="red"), title="Backstab")
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
            self.set_output(Text("Usage: theme <list|set> ...", style="dim"),
                            title="Theme")
            return
        sub = args[0].lower()
        if sub == "list":
            table = Table(title="Themes", border_style="magenta")
            table.add_column("Name", style="white")
            for name in ThemeLibrary.names():
                table.add_row(name)
            self.set_output(table, title="Themes")
        elif sub == "set":
            if len(args) < 2:
                self.set_output(Text("Usage: theme set <name>", style="dim"),
                                title="Theme")
                return
            theme = ThemeLibrary.get(args[1])
            if theme is None:
                self.set_output(Text(f"Unknown theme: {args[1]}", style="red"),
                                title="Theme")
                return
            self.msg(f"Theme set to {theme.name}.", Color.GREEN)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Theme")

    def cmd_dimensions(self, args: list[str]) -> None:
        table = Table(title="Dimensions", border_style="cyan")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="white")
        table.add_column("Type", style="dim")
        for d in self.dimensions.all_dimensions():
            table.add_row(str(d.dimension_id), d.name, d.dimension_type.value)
        if not self.dimensions.all_dimensions():
            table.add_row("—", "(none discovered)", "")
        self.set_output(table, title="Dimensions")

    def cmd_portal(self, args: list[str]) -> None:
        if len(args) < 2:
            self.set_output(Text("Usage: portal <from_dim> <to_dim>", style="dim"),
                            title="Portal")
            return
        ok = self.dimensions.open_portal(int(args[0]), int(args[1]))
        self.msg(f"Portal {'opened' if ok else 'failed to open'}.",
                 Color.GREEN if ok else Color.RED)

    def cmd_travel(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: travel <dimension_id>", style="dim"),
                            title="Travel")
            return
        ok, msg = self.dimensions.can_travel(0, int(args[0]))
        self.msg(msg, Color.GREEN if ok else Color.RED)

    # ----- body parts ------------------------------------------------------ #

    def cmd_bodyparts(self, args: list[str]) -> None:
        parts = self.bodyparts.body_parts(self.engine.player)
        if not parts:
            self.bodyparts.assign_body(self.engine.player, "humanoid")
            parts = self.bodyparts.body_parts(self.engine.player)
        table = Table(title="Body Parts", border_style="red")
        table.add_column("Part", style="cyan")
        table.add_column("HP", style="red", justify="right")
        table.add_column("Status", style="white")
        for p in parts:
            status = "OK" if p.status.name == "HEALTHY" else p.status.name
            table.add_row(p.part_type.value, f"{p.current_hp}/{p.max_hp}", status)
        self.set_output(table, title="Body Parts")

    def cmd_heal_part(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: heal_part <part_type> [amount]",
                                 style="dim"), title="Heal Part")
            return
        from engine.bodyparts.system import BodyPartType
        try:
            ptype = BodyPartType[args[0].upper()]
        except KeyError:
            self.set_output(Text(f"Unknown part: {args[0]}", style="red"),
                            title="Heal Part")
            return
        amount = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
        self.bodyparts.heal_part(self.engine.player, ptype, amount)
        self.msg(f"Healed {args[0]} by {amount}.", Color.GREEN)

    # ----- world & time ---------------------------------------------------- #

    def cmd_simulate(self, args: list[str]) -> None:
        hours = float(args[0]) if args and args[0].replace(".", "").isdigit() else 24.0
        report = self.background_sim.simulate(hours,
                                               start_tick=self.engine.clock.time.tick)
        body = Text()
        total = getattr(report, "total_events", 0)
        major = getattr(report, "major_events", [])
        body.append(f"Total events: {total}\n", style="white")
        body.append(f"Major events: {len(major)}\n", style="white")
        for ev in major[:5]:
            etype = getattr(ev, "event_type", None)
            etype_name = etype.name if hasattr(etype, "name") else str(etype)
            desc = getattr(ev, "description", "")
            body.append(f"  {etype_name}: {desc}\n", style="yellow")
        self.set_output(body, title=f"Simulation ({hours:.0f}h)")

    def cmd_contentpacks(self, args: list[str]) -> None:
        from engine.content_packs.system import ContentPackManager
        cpm = ContentPackManager()
        count = cpm.discover()
        table = Table(title="Content Packs", border_style="magenta")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Version", style="dim")
        body = Text(f"Discovered: {count}\n", style="white")
        for p in cpm.registry.all():
            table.add_row(p.pack_id, p.name, p.version)
        if not cpm.registry.all():
            table.add_row("—", "(none)", "")
        self.set_output(Group(body, table), title="Content Packs")

    # ----- combat variants ------------------------------------------------- #

    def cmd_naval(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: naval <bombard|board> <ship_id>",
                                 style="dim"), title="Naval")
            return
        sub = args[0].lower()
        if sub == "bombard":
            if len(args) < 2:
                self.set_output(Text("Usage: naval bombard <target_ship_id>",
                                     style="dim"), title="Naval")
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
                self.set_output(Text("Usage: naval board <target_ship_id>",
                                     style="dim"), title="Naval")
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
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Naval")

    def cmd_siege(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: siege <create|bombard|assault> ...",
                                 style="dim"), title="Siege")
            return
        sub = args[0].lower()
        if sub == "create":
            if len(args) < 3:
                self.set_output(Text(
                    "Usage: siege create <attacker_faction> <defender_faction>",
                    style="dim"), title="Siege")
                return
            s = self.siege_combat.create_siege(
                int(args[1]), int(args[2]), "Fortress",
                current_tick=self.engine.clock.time.tick,
            )
            self.msg(f"Siege {s.siege_id} created.", Color.RED)
        elif sub == "bombard":
            if len(args) < 2:
                self.set_output(Text("Usage: siege bombard <siege_id>",
                                     style="dim"), title="Siege")
                return
            result = self.siege_combat.bombard(int(args[1]))
            self.msg(f"Bombardment: {result}", Color.YELLOW)
        elif sub == "assault":
            if len(args) < 3:
                self.set_output(Text("Usage: siege assault <siege_id> <troops>",
                                     style="dim"), title="Siege")
                return
            result = self.siege_combat.assault(int(args[1]), int(args[2]))
            self.msg(f"Assault: {result}", Color.YELLOW)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Siege")

    def cmd_aerial(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: aerial <mount|dive|attack> ...",
                                 style="dim"), title="Aerial")
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
                self.set_output(Text("No target.", style="dim"),
                                title="Aerial")
                return
            result = self.aerial_combat.aerial_attack(
                self.engine.world, self.engine.player, target,
            )
            msg = result.message if hasattr(result, "message") else str(result)
            self.msg(f"Aerial attack: {msg}", Color.YELLOW)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Aerial")

    def cmd_space(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: space <fire|launch> ...", style="dim"),
                            title="Space")
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
                self.set_output(Text("Need a target ship.", style="dim"),
                                title="Space")
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
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Space")

    def cmd_realtime(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: realtime <queue|cancel> ...",
                                 style="dim"), title="Realtime")
            return
        sub = args[0].lower()
        if sub == "queue":
            target = self._find_adjacent_hostile()
            if target is None:
                self.set_output(Text("No target.", style="dim"),
                                title="Realtime")
                return
            action = self.realtime_combat.queue_attack(self.engine.player, target)
            self.msg(f"Attack queued (action {action.action_id}).", Color.YELLOW)
        elif sub == "cancel":
            n = self.realtime_combat.cancel_actions(self.engine.player)
            self.msg(f"Cancelled {n} actions.", Color.GRAY)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Realtime")

    def cmd_mount(self, args: list[str]) -> None:
        if not args:
            self.set_output(Text("Usage: mount <mount|dismount|charge> ...",
                                 style="dim"), title="Mount")
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
                self.set_output(Text("No target.", style="dim"),
                                title="Mount")
                return
            result = self.mounted_combat.mounted_attack(
                self.engine.world, self.engine.player, target, is_charging=True,
            )
            msg = result.message if hasattr(result, "message") else str(result)
            self.msg(f"Charge: {msg}", Color.YELLOW)
        else:
            self.set_output(Text(f"Unknown subcommand: {sub}", style="red"),
                            title="Mount")

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
            self.set_output(Text("You see nothing of interest.", style="dim"),
                            title="Look")
            return
        body = Text()
        body.append(f"{identity.display_name}\n", style="bold gold1")
        if identity.description:
            body.append(f"{identity.description}\n", style="dim")
        if health:
            body.append(f"HP: {health.current}/{health.maximum}\n", style="red")
        if position:
            body.append(f"Position: ({position.x}, {position.y})\n", style="dim")
        tags = []
        if self.engine.world.has_tag(entity, "hostile"):
            tags.append("hostile")
        if self.engine.world.has_tag(entity, "npc"):
            tags.append("npc")
        if self.engine.world.has_tag(entity, "creature"):
            tags.append("creature")
        if tags:
            body.append(f"Tags: {', '.join(tags)}\n", style="dim")
        self.set_output(body, title=identity.display_name)

    # ----- main loop ------------------------------------------------------- #

    def run(self) -> None:
        self.running = True
        # Live-dashboard mode: use rich.live.Live for continuous auto-refresh.
        # Falls back to the static render loop when stdin isn't a TTY (piped
        # input, CI) or when live_mode was explicitly disabled.
        if self.live_mode and self._interactive:
            self._run_live()
            return
        # Enable raw mode only when stdin is a real TTY.
        if self._interactive:
            self.enable_raw_mode()
        try:
            # Initial render — banner is always visible at the top of the layout.
            self._render()
            while self.running:
                try:
                    self._tick()
                except KeyboardInterrupt:
                    self.msg("Use 'quit' to exit.", Color.YELLOW)
                    self._render()
                except Exception as exc:  # noqa: BLE001
                    log.exception("REPL error")
                    self.set_output(Text(f"Error: {exc}", style="red"),
                                    title="Error")
                    self._render()
        finally:
            self.disable_raw_mode()
            # Print a final newline so the shell prompt isn't on the same line.
            try:
                print()
            except Exception:  # noqa: BLE001
                pass

    # ----- live-dashboard mode -------------------------------------------- #

    def _build_live_layout(self) -> Layout:
        """Build the rich Layout used for live-dashboard mode.

        Layout structure (top-to-bottom):
            - banner      (size 7)  — the Aeon Engine welcome banner
            - middle      (ratio 2) — status (left) + map (right)
            - lower       (ratio 2) — messages (left) + command output (right)
            - input       (size 3)  — prompt + current input line

        When the player is dead (``_game_over`` is True), the layout is
        replaced with a full-screen game-over panel.
        """
        # Game-over screen takes over the whole layout.
        if self._game_over:
            layout = Layout()
            layout.update(self._game_over_panel())
            return layout

        layout = Layout()
        layout.split_column(
            Layout(self._banner_panel(), name="banner", size=7),
            Layout(name="middle", ratio=2),
            Layout(name="lower", ratio=2),
            Layout(name="input", size=3),
        )
        # Split middle into status + map.
        layout["middle"].split_row(
            Layout(self._status_panel(), name="status"),
            Layout(self._map_panel(), name="map"),
        )
        # Split lower into messages + command output (with scrollbar).
        layout["lower"].split_row(
            Layout(self._messages_panel(), name="messages"),
            Layout(self._scrollable_output_panel(), name="output"),
        )
        # Input line.
        layout["input"].update(self._input_panel())
        return layout

    def _game_over_panel(self) -> Panel:
        """Full-screen game-over panel shown when the hero dies."""
        from engine.entities.components import Identity
        identity = (self.engine.world.get_component(self.engine.player, Identity)
                    if self.engine.player else None)
        name = identity.display_name if identity else "Hero"
        body = Text()
        body.append("\n")
        body.append("╔══════════════════════════════════════════════════════════╗\n",
                    style="bold red")
        body.append("║                                                          ║\n",
                    style="bold red")
        body.append("║                    G A M E   O V E R                     ║\n",
                    style="bold red")
        body.append("║                                                          ║\n",
                    style="bold red")
        body.append("╚══════════════════════════════════════════════════════════╝\n",
                    style="bold red")
        body.append("\n")
        body.append(f"  {name} has fallen.\n\n", style="bold white")
        body.append("  Choose your fate:\n\n", style="yellow")
        body.append("    [R]  ", style="bold green")
        body.append("Respawn at spawn point (lose half of carried wealth)\n", style="white")
        body.append("    [N]  ", style="bold cyan")
        body.append("Start a new game (new world, new character)\n", style="white")
        body.append("    [Q]  ", style="bold red")
        body.append("Quit the game\n", style="white")
        body.append("\n  Press a key to continue...\n", style="dim")
        return Panel(body, title="[bold red]Game Over[/]", border_style="red",
                     expand=True)

    def _scrollable_output_panel(self) -> Panel:
        """Command-output panel with scrollbar and vertical scrolling.

        The output renderable is rendered to a plain-text string, then
        split into lines. We apply the current scroll offset (lines from
        the bottom) and show a scrollbar on the right edge so the player
        can tell where they are in a long listing.
        """
        from io import StringIO
        renderable = self._command_output_panel()
        if renderable is None:
            self._output_line_count = 0
            return Panel(Text("(no command output yet — try 'help')", style="dim"),
                         title="[bold magenta]Output[/]",
                         border_style="magenta", expand=True)
        # Render the inner renderable to plain text to count lines.
        try:
            buf = StringIO()
            tmp = Console(file=buf, force_terminal=False, color_system=None,
                          highlight=False, soft_wrap=True, width=60)
            tmp.print(renderable.renderable if hasattr(renderable, "renderable") else renderable)
            all_lines = buf.getvalue().splitlines()
        except Exception:  # noqa: BLE001
            all_lines = [str(renderable)]
        self._output_line_count = len(all_lines)
        # Determine the visible window. The panel height is roughly
        # determined by the layout ratio; assume ~15 lines visible.
        visible_h = 15
        total = len(all_lines)
        if total <= visible_h:
            # Everything fits — no scroll needed.
            self._output_scroll = 0
            content = Text("\n".join(all_lines))
        else:
            # Clamp scroll offset.
            max_scroll = total - visible_h
            if self._output_scroll < 0:
                self._output_scroll = 0
            if self._output_scroll > max_scroll:
                self._output_scroll = max_scroll
            # Window: bottom-anchored. scroll=0 shows the last `visible_h`
            # lines. scroll=N shows lines [total-visible_h-N : total-N].
            start = max(0, total - visible_h - self._output_scroll)
            end = start + visible_h
            visible_lines = all_lines[start:end]
            content = Text("\n".join(visible_lines))
        # Build a scrollbar indicator for the title.
        if self._output_line_count > visible_h:
            scroll_pct = (self._output_scroll / max(1, self._output_line_count - visible_h))
            title = (f"[bold magenta]Output[/]  "
                     f"[dim]{self._output_line_count} lines  "
                     f"↑↓ scroll  ({int(scroll_pct * 100)}%)[/]")
        else:
            title = "[bold magenta]Output[/]"
        return Panel(content, title=title, border_style="magenta", expand=True)

    def _input_panel(self) -> Panel:
        """The bottom input line — shows the prompt and current input."""
        prompt = "Choice> " if self._in_dialogue else "> "
        body = Text()
        body.append(prompt, style="bold green" if not self._in_dialogue else "bold yellow")
        body.append(self._live_input, style="white")
        # Add a blinking cursor block.
        body.append("_", style="bold white")
        hint = ""
        if self._last_command:
            hint = f"  (last: {self._last_command[:40]})"
        body.append(hint, style="dim")
        return Panel(body, title="[bold green]Input[/]  (type 'help' for commands, 'q' to quit)",
                     border_style="green", expand=True, height=3)

    def _input_reader_loop(self) -> None:
        """Background thread input reader — DEPRECATED.

        Kept for backwards compatibility but no longer used by
        ``_run_live``. The single-threaded non-blocking reader in
        ``_run_live`` replaced this because the threaded version raced
        with ``Live``'s terminal state manipulation, causing input to
        not register reliably.
        """
        # No-op — the single-threaded loop in _run_live handles input now.
        return

    def _read_live_input_nonblocking(self) -> None:
        """Read any pending stdin input without blocking.

        Cross-platform:
        - On Windows: uses ``msvcrt.kbhit`` / ``msvcrt.getch`` (the
          ``termios``/``select`` modules don't exist on Windows).
        - On Unix: uses ``select.select`` to poll the stdin file
          descriptor with a zero timeout (non-blocking).

        For each byte read:
        - Enter (\\r / \\n) commits the current ``_live_input`` as a
          completed command and pushes it onto the input queue.
        - Backspace deletes the last char of ``_live_input``.
        - Ctrl-C / Ctrl-D signals quit.
        - Escape sequences (arrows etc.) are consumed and discarded.
        - Printable chars are appended to ``_live_input``.

        This runs on the MAIN thread (not a background thread) so there's
        no race with ``Live``'s terminal state.
        """
        if sys.platform == "win32":
            self._read_live_input_windows()
        else:
            self._read_live_input_unix()

    def _read_live_input_unix(self) -> None:
        """Non-blocking stdin reader for Unix (Linux/macOS).

        Handles:
        - Game-over keys (R/N/Q) when ``_game_over`` is True
        - Arrow Up/Down to scroll the output panel
        - Enter to commit the input line
        - Backspace, Ctrl-C, Ctrl-D
        - Printable chars appended to ``_live_input``
        """
        import select as _select
        import os as _os
        try:
            fd = sys.stdin.fileno()
        except Exception:  # noqa: BLE001
            return
        # Drain all available bytes without blocking (max 50ms per drain).
        deadline = time.perf_counter() + 0.05
        while time.perf_counter() < deadline:
            try:
                r, _, _ = _select.select([fd], [], [], 0.0)
            except (OSError, ValueError):
                return
            if not r:
                return  # no data available right now
            try:
                ch = _os.read(fd, 1).decode("utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                return
            if not ch:
                self._input_queue.put(None)
                return
            # Game-over mode: only accept R, N, Q.
            if self._game_over:
                key = ch.upper()
                if key in ("R", "N", "Q"):
                    self._input_queue.put(f"__gameover_{key}__")
                continue
            # Map special chars.
            if ch in ("\r", "\n"):
                line = self._live_input
                self._live_input = ""
                self._input_queue.put(line)
                continue
            if ch in ("\x7f", "\x08"):
                if self._live_input:
                    self._live_input = self._live_input[:-1]
                continue
            if ch == "\x03":  # Ctrl-C
                self._input_queue.put(None)
                return
            if ch == "\x04":  # Ctrl-D
                self._input_queue.put(None)
                return
            if ch == "\x1b":
                # Escape sequence — parse arrow keys for scrolling.
                try:
                    r2, _, _ = _select.select([fd], [], [], 0.01)
                    if r2:
                        ch2 = _os.read(fd, 1).decode("utf-8", errors="replace")
                        if ch2 in ("[", "O"):
                            r3, _, _ = _select.select([fd], [], [], 0.01)
                            if r3:
                                ch3 = _os.read(fd, 1).decode("utf-8", errors="replace")
                                if ch3 == "A":  # Up arrow
                                    self._output_scroll += 3
                                elif ch3 == "B":  # Down arrow
                                    self._output_scroll -= 3
                                    if self._output_scroll < 0:
                                        self._output_scroll = 0
                                # Left/Right (C/D) ignored for now.
                                continue
                except OSError:
                    pass
                continue
            if ch == "\t":
                continue
            # Any new typing resets the scroll to bottom.
            if ch.isprintable():
                self._output_scroll = 0
                self._live_input += ch

    def _read_live_input_windows(self) -> None:
        """Non-blocking stdin reader for Windows using ``msvcrt``.

        Handles:
        - Game-over keys (R/N/Q) when ``_game_over`` is True
        - Arrow Up/Down to scroll the output panel (via extended keys)
        - Enter to commit the input line
        - Backspace, Ctrl-C, Ctrl-D
        - Printable chars appended to ``_live_input``
        """
        import msvcrt  # type: ignore[import-not-found]
        # Drain all available keystrokes without blocking.
        deadline = time.perf_counter() + 0.05
        while time.perf_counter() < deadline:
            if not msvcrt.kbhit():
                return  # no key available right now
            try:
                ch_bytes = msvcrt.getch()
            except OSError:
                return
            if not ch_bytes:
                return
            # Extended key prefix — read the second byte for arrow keys.
            if ch_bytes in (b"\x00", b"\xe0"):
                try:
                    ext = msvcrt.getch()
                except OSError:
                    ext = b""
                # Windows arrow key codes: H=up, P=down, K=left, M=right
                if ext == b"H":  # Up arrow
                    if not self._game_over:
                        self._output_scroll += 3
                elif ext == b"P":  # Down arrow
                    if not self._game_over:
                        self._output_scroll -= 3
                        if self._output_scroll < 0:
                            self._output_scroll = 0
                continue
            ch = ch_bytes.decode("latin-1", errors="replace")
            if not ch:
                continue
            # Game-over mode: only accept R, N, Q.
            if self._game_over:
                key = ch.upper()
                if key in ("R", "N", "Q"):
                    self._input_queue.put(f"__gameover_{key}__")
                continue
            # Map special chars.
            if ch in ("\r", "\n"):
                line = self._live_input
                self._live_input = ""
                self._input_queue.put(line)
                continue
            if ch in ("\x7f", "\x08"):  # Backspace
                if self._live_input:
                    self._live_input = self._live_input[:-1]
                continue
            if ch == "\x03":  # Ctrl-C
                self._input_queue.put(None)
                return
            if ch == "\x04":  # Ctrl-D
                self._input_queue.put(None)
                return
            if ch == "\x1b":  # Escape — discard
                continue
            if ch == "\t":
                continue
            # Any new typing resets the scroll to bottom.
            if ch.isprintable():
                self._output_scroll = 0
                self._live_input += ch

    def _run_live(self) -> None:
        """Run the game in live-dashboard mode with rich.live.Live.

        SINGLE-THREADED, NON-BLOCKING INPUT design (cross-platform):
        - On Unix: switch stdin to raw no-echo mode once at startup
          (using ``termios``/``tty``), then poll stdin with ``select``
          each animation frame.
        - On Windows: no terminal-mode switch is needed (``msvcrt``
          reads keys directly without cooked-mode echo), so we just poll
          ``msvcrt.kbhit`` each frame.
        Each animation frame: poll stdin -> drain chars -> update
        ``_live_input`` -> push completed lines onto queue -> drain
        queue -> execute commands -> advance simulation -> update Live
        display -> sleep one frame.
        """
        is_windows = (sys.platform == "win32")
        old_term_settings = None
        fd = None

        if not is_windows:
            # Unix: switch stdin to raw, no-echo mode for the duration of
            # live mode so the terminal doesn't echo typed chars (which
            # would clobber the live layout).
            try:
                import termios
                import tty
                fd = sys.stdin.fileno()
                old_term_settings = termios.tcgetattr(fd)
                tty.setraw(fd)
                new = termios.tcgetattr(fd)
                new[3] = new[3] & ~termios.ECHO  # lflags &= ~ECHO
                termios.tcsetattr(fd, termios.TCSANOW, new)
            except Exception:  # noqa: BLE001 — not a TTY or termios unavailable
                old_term_settings = None
                fd = None
        # Windows: msvcrt reads keys without terminal-mode manipulation,
        # and rich's Live(screen=True) handles the console buffer itself.

        self._last_sim_time = time.perf_counter()
        try:
            with Live(
                self._build_live_layout(),
                console=self.console,
                refresh_per_second=self._live_fps,
                screen=True,  # alternate screen buffer — full-screen takeover
                transient=False,
            ) as live:
                while self.running:
                    # 1. Read any pending input (non-blocking, main thread).
                    #    On Unix we need fd != None (raw mode active);
                    #    on Windows we always try.
                    if is_windows or fd is not None:
                        self._read_live_input_nonblocking()
                    # 2. Drain completed command lines from the queue.
                    try:
                        while True:
                            line = self._input_queue.get_nowait()
                            if line is None:
                                self.running = False
                                break
                            self._handle_live_input(line)
                            if not self.running:
                                break
                    except _queue.Empty:
                        pass
                    if not self.running:
                        break
                    # 2b. Detect player death — switch to game-over screen.
                    if getattr(self.engine, "player_dead", False) and not self._game_over:
                        self._game_over = True
                    # 3. Advance the simulation in real time — but pause
                    #    when the player is dead (the world waits for the
                    #    player to choose respawn / new game / quit).
                    if not self._game_over:
                        now = time.perf_counter()
                        if now - self._last_sim_time >= self._sim_dt:
                            try:
                                self.engine.tick_simulation(self._sim_dt)
                            except Exception as exc:  # noqa: BLE001
                                log.exception("Simulation tick failed")
                                self.set_output(Text(f"Sim error: {exc}", style="red"),
                                                title="Error")
                            # Autosave check.
                            if (self.engine.clock.time.tick - self.engine._last_autosave_tick
                                    >= self.engine.config.save.autosave_interval_ticks):
                                try:
                                    self.engine.save_game("autosave")
                                    self.engine._last_autosave_tick = self.engine.clock.time.tick
                                except Exception as exc:  # noqa: BLE001
                                    log.error("Autosave failed: %s", exc)
                            self._last_sim_time = now
                    # 4. Update the live display with a fresh layout.
                    live.update(self._build_live_layout())
                    # 5. Sleep roughly one frame.
                    time.sleep(1.0 / self._live_fps)
        except KeyboardInterrupt:
            pass
        finally:
            # Restore terminal state (Unix only).
            if old_term_settings is not None and fd is not None:
                try:
                    import termios
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_term_settings)
                except Exception:  # noqa: BLE001
                    pass

    def _handle_live_input(self, line: str) -> None:
        """Process a completed input line in live mode."""
        line = line.strip() if line else ""
        self._live_input = ""
        # Game-over key handling (R/N/Q).
        if line == "__gameover_R__":
            self._game_over = False
            self.engine.respawn_player()
            self.set_output(Text("You have been restored to full health at the spawn point.",
                                 style="green"), title="Respawned")
            return
        if line == "__gameover_N__":
            self._game_over = False
            self.engine.new_game("Hero")
            self.set_output(Text("A new world has been generated. Your adventure begins anew.",
                                 style="cyan"), title="New Game")
            return
        if line == "__gameover_Q__":
            self.running = False
            self.engine.shutdown()
            return
        if not line:
            return
        # If the player is dead, ignore all other input.
        if self._game_over:
            return
        self._last_command = line
        self._history.append(line)
        self._history_idx = -1
        log.debug("Live input received: %r", line)
        # Dialogue takes precedence.
        if self._in_dialogue:
            if self._handle_dialogue_input(line):
                return
        # Otherwise execute as a command.
        try:
            self._execute_command(line)
        except Exception as exc:  # noqa: BLE001
            log.exception("Live command %s failed", line)
            self.set_output(Text(f"Error: {exc}", style="red"), title="Error")

    def _tick(self) -> None:
        # Read input.
        line = ""
        if self._raw_mode:
            sys.stdout.flush()
            key = self._read_key()
            if key == "quit":
                self.running = False
                return
            if key == "enter":
                self.engine.tick_simulation(0.05)
                self._render()
                return
            if key in ("up", "down"):
                if key == "up" and self._history:
                    self._history_idx = max(0, self._history_idx - 1)
                    line = self._history[self._history_idx] if self._history_idx >= 0 else ""
                elif key == "down" and self._history:
                    self._history_idx = min(len(self._history) - 1, self._history_idx + 1)
                    line = self._history[self._history_idx] if self._history_idx >= 0 else ""
                sys.stdout.write("\r" + " " * 60 + "\r" + line)
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
                        sys.stdout.write("\r" + line + "  \r" + line)
                        sys.stdout.flush()
                    elif len(k) == 1 and k.isprintable():
                        line += k
                        sys.stdout.write(k)
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
                    sys.stdout.write(key)
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
                            sys.stdout.write("\r" + line + "  \r" + line)
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
            # Line-mode: prompt via rich to keep styling consistent.
            try:
                if self._in_dialogue:
                    line = input("Choice> ")
                else:
                    line = input("> ")
            except (EOFError, KeyboardInterrupt):
                self.running = False
                return

        line = line.strip()
        if not line:
            self.engine.tick_simulation(0.05)
            self._render()
            return
        self._history.append(line)
        self._history_idx = -1
        if self._in_dialogue:
            if self._handle_dialogue_input(line):
                self.engine.tick_simulation(0.05)
                self._render()
                return
        self._execute_command(line)
        self.engine.tick_simulation(0.05)
        # Autosave check.
        if (self.engine.clock.time.tick - self.engine._last_autosave_tick
                >= self.engine.config.save.autosave_interval_ticks):
            try:
                self.engine.save_game("autosave")
                self.engine._last_autosave_tick = self.engine.clock.time.tick
            except Exception as exc:  # noqa: BLE001
                log.error("Autosave failed: %s", exc)
        self._render()

    def _execute_command(self, line: str) -> None:
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            self.set_output(Text(f"Parse error: {exc}", style="red"),
                            title="Error")
            return
        if not tokens:
            return
        cmd = tokens[0].lower()
        args = tokens[1:]
        aliases = self._aliases()
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
                self.set_output(
                    Text(f"Unknown command: {tokens[0]}. Type 'help' for help.",
                         style="red"),
                    title="Error",
                )
            return
        try:
            handler(args)
        except Exception as exc:  # noqa: BLE001
            log.exception("Command %s failed", cmd)
            self.set_output(Text(f"Error: {exc}", style="red"), title="Error")

    @staticmethod
    def _aliases() -> dict[str, str]:
        return {
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
            "banner": "banner",
            "plugins": "plugins",
            "quit": "quit", "q": "quit", "exit": "quit",
            "respawn": "respawn",
            "new_game": "new_game", "newgame": "new_game", "new": "new_game",
            "memory": "memory", "mem": "memory",
            "schedule": "schedule", "sched": "schedule",
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
    parser.add_argument("--verbose", action="store_true",
                        help="Print engine logs to stderr in addition to the log file.")
    parser.add_argument("--live", action="store_true", default=True,
                        help="Use the live-dashboard UI (rich.live.Live) — default.")
    parser.add_argument("--no-live", action="store_false", dest="live",
                        help="Disable live-dashboard mode; use the static render loop instead.")
    parser.add_argument("--fps", type=float, default=8.0,
                        help="Live-mode refresh rate in frames per second (default 8).")
    parser.add_argument("--sim-rate", type=float, default=0.25,
                        help="Live-mode simulation tick interval in seconds (default 0.25).")
    return parser.parse_args(argv)


def _configure_quiet_logging(log_file: Optional[Path], verbose: bool) -> None:
    """Configure logging so the console stays clean for the rich UI.

    By default, engine logs go only to the log file. With --verbose, they
    also go to stderr.
    """
    import logging
    from engine.core.logging import configure_logging
    level = logging.DEBUG if verbose else logging.INFO
    configure_logging(
        level=logging.WARNING if not verbose else level,
        log_file=log_file,
    )
    # The Engine's __init__ will call configure_logging() again, which would
    # re-add a console INFO handler. Monkey-patch the module-level
    # `configure_logging` so subsequent calls from the Engine preserve our
    # quiet console setting.
    import engine.core.logging as _elog
    _orig_configure = _elog.configure_logging

    def _quiet_configure(*args: Any, **kwargs: Any) -> Any:
        # Force the console level to WARNING unless verbose was requested.
        if not verbose:
            kwargs["level"] = logging.WARNING
        return _orig_configure(*args, **kwargs)

    _elog.configure_logging = _quiet_configure


def main(argv: Optional[list[str]] = None) -> int:
    """Single entry point for Aeon Engine."""
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # Configure logging BEFORE any engine imports so get_logger() doesn't
    # auto-configure at INFO level behind our back. We'll re-apply after
    # we know the log file path from config.
    _configure_quiet_logging(None, args.verbose)

    from engine.core.config import EngineConfig, load_config, set_config
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

    # Configure logging: keep console clean unless --verbose.
    log_file = Path(config.log_file) if config.log_file else None
    if log_file is not None and not log_file.is_absolute():
        log_file = project_root / log_file
    _configure_quiet_logging(log_file, args.verbose)

    log.info("Starting Aeon Engine v%s", config.version)

    engine = Engine(config, headless=True)
    if args.no_plugins:
        engine.config.plugins.autoload_enabled = False

    # Re-apply quiet logging in case the Engine's __init__ reset it.
    _configure_quiet_logging(log_file, args.verbose)

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
        # Configure live-dashboard mode. Live mode auto-disables when stdin
        # isn't a TTY (piped input, CI) because rich.live.Live with
        # screen=True would corrupt non-interactive output.
        if args.live and repl._is_tty():
            repl.live_mode = True
            repl._live_fps = max(1.0, min(30.0, args.fps))
            repl._sim_dt = max(0.05, min(5.0, args.sim_rate))
        else:
            repl.live_mode = False
        repl.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        engine.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
