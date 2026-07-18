"""Command system — parser, aliases, macros, permissions."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, ClassVar, Optional

from engine.core.ecs import Entity, World
from engine.core.logging import get_logger


log = get_logger("commands")


class Permission(IntEnum):
    PLAYER = 0
    MODERATOR = 1
    ADMIN = 2
    OWNER = 3
    DEBUG = 4


@dataclass
class CommandContext:
    """Context passed to a command handler."""

    world: World
    player: Optional[Entity] = None
    args: list[str] = field(default_factory=list)
    raw_input: str = ""
    engine: Any = None  # back-reference to the engine
    caller_id: Optional[int] = None
    permission: Permission = Permission.PLAYER


@dataclass
class CommandResult:
    success: bool
    output: str = ""
    error: str = ""
    data: dict[str, Any] = field(default_factory=dict)


CommandHandler = Callable[[CommandContext], CommandResult]


@dataclass
class Command:
    """A command definition."""

    name: str
    handler: CommandHandler
    description: str = ""
    usage: str = ""
    aliases: list[str] = field(default_factory=list)
    permission: Permission = Permission.PLAYER
    plugin: Optional[str] = None
    debug_only: bool = False
    autocomplete: Optional[Callable[[CommandContext, str], list[str]]] = None


class CommandRegistry:
    """Registry of commands and aliases."""

    def __init__(self) -> None:
        self._commands: dict[str, Command] = {}
        self._aliases: dict[str, str] = {}
        self._macros: dict[str, str] = {}
        self._history: list[str] = []

    def register(self, command: Command) -> None:
        self._commands[command.name] = command
        for alias in command.aliases:
            self._aliases[alias] = command.name

    def unregister(self, name: str) -> None:
        cmd = self._commands.pop(name, None)
        if cmd:
            for alias in cmd.aliases:
                self._aliases.pop(alias, None)

    def get(self, name: str) -> Optional[Command]:
        if name in self._commands:
            return self._commands[name]
        if name in self._aliases:
            return self._commands.get(self._aliases[name])
        return None

    def all(self) -> list[Command]:
        return list(self._commands.values())

    def names(self) -> list[str]:
        return sorted(self._commands.keys())

    def add_macro(self, name: str, expansion: str) -> None:
        self._macros[name] = expansion

    def remove_macro(self, name: str) -> None:
        self._macros.pop(name, None)

    def get_macro(self, name: str) -> Optional[str]:
        return self._macros.get(name)

    def all_macros(self) -> dict[str, str]:
        return dict(self._macros)

    def add_history(self, raw: str) -> None:
        self._history.append(raw)
        if len(self._history) > 1000:
            self._history = self._history[-1000:]

    def history(self, limit: int = 50) -> list[str]:
        return self._history[-limit:]

    def autocomplete(self, partial: str) -> list[str]:
        """Return command names starting with `partial`."""
        return sorted(name for name in self._commands if name.startswith(partial))


class CommandProcessor:
    """Parses and executes commands."""

    def __init__(self, registry: CommandRegistry) -> None:
        self.registry = registry

    def execute(self, raw_input: str, ctx: CommandContext) -> CommandResult:
        raw_input = raw_input.strip()
        if not raw_input:
            return CommandResult(success=False, error="Empty command.")
        self.registry.add_history(raw_input)
        # Expand macros
        try:
            tokens = shlex.split(raw_input)
        except ValueError as exc:
            return CommandResult(success=False, error=f"Parse error: {exc}")
        if not tokens:
            return CommandResult(success=False, error="Empty command.")
        cmd_name = tokens[0]
        # Macro expansion
        if cmd_name in self.registry._macros:
            expansion = self.registry._macros[cmd_name]
            try:
                tokens = shlex.split(expansion) + tokens[1:]
                cmd_name = tokens[0]
            except ValueError as exc:
                return CommandResult(success=False, error=f"Macro expansion error: {exc}")
        command = self.registry.get(cmd_name)
        if command is None:
            return CommandResult(success=False, error=f"Unknown command: {cmd_name}")
        # Permission check
        if command.permission.value > ctx.permission.value:
            return CommandResult(success=False,
                                  error=f"Permission denied: requires {command.permission.name}")
        if command.debug_only and ctx.permission < Permission.DEBUG:
            return CommandResult(success=False, error="Debug-only command.")
        ctx.args = tokens[1:]
        try:
            result = command.handler(ctx)
            return result
        except Exception as exc:  # noqa: BLE001
            log.exception("Command %s failed", cmd_name)
            return CommandResult(success=False, error=str(exc))


# ---------- Default commands ----------

def _cmd_help(ctx: CommandContext) -> CommandResult:
    """List available commands."""
    if not ctx.engine:
        return CommandResult(success=False, error="No engine reference.")
    cmds = ctx.engine.commands.all()
    lines = [f"  {c.name:20s} {c.description}" for c in cmds
             if c.permission.value <= ctx.permission.value]
    return CommandResult(success=True, output="Available commands:\n" + "\n".join(lines))


def _cmd_look(ctx: CommandContext) -> CommandResult:
    """Look around the current location."""
    from engine.entities.components import Position, Identity
    if ctx.player is None:
        return CommandResult(success=False, error="No player.")
    pos = ctx.world.get_component(ctx.player, Position)
    if pos is None:
        return CommandResult(success=False, error="No position.")
    # Find nearby entities
    lines = [f"You are at ({pos.x}, {pos.y})."]
    for ent, (p,) in ctx.world.view(Position):
        if ent.id == ctx.player.id:
            continue
        if abs(p.x - pos.x) <= 8 and abs(p.y - pos.y) <= 8:
            identity = ctx.world.get_component(ent, Identity)
            name = identity.display_name if identity else f"entity#{ent.id}"
            glyph = identity.glyph if identity else "?"
            lines.append(f"  {glyph} {name} at ({p.x}, {p.y})")
    return CommandResult(success=True, output="\n".join(lines))


def _cmd_inventory(ctx: CommandContext) -> CommandResult:
    """Show inventory."""
    if ctx.player is None or ctx.engine is None:
        return CommandResult(success=False, error="No player or engine.")
    inv = ctx.engine.inventories.get(ctx.player.id)
    if inv is None:
        return CommandResult(success=False, error="No inventory.")
    lines = ["Inventory:"]
    for slot_idx, item, count in inv.iter_items(ctx.engine.items):
        lines.append(f"  [{slot_idx}] {item.display_name} x{count}")
    return CommandResult(success=True, output="\n".join(lines))


def _cmd_status(ctx: CommandContext) -> CommandResult:
    """Show player status."""
    if ctx.player is None:
        return CommandResult(success=False, error="No player.")
    from engine.entities.components import Health, Stats, Needs, Identity
    identity = ctx.world.get_component(ctx.player, Identity)
    health = ctx.world.get_component(ctx.player, Health)
    stats = ctx.world.get_component(ctx.player, Stats)
    needs = ctx.world.get_component(ctx.player, Needs)
    lines = []
    if identity:
        lines.append(f"Name: {identity.display_name}")
    if health:
        lines.append(f"HP: {health.current}/{health.maximum}")
    if stats:
        lines.append(f"Str: {stats.strength} Agi: {stats.agility} End: {stats.endurance}")
        lines.append(f"Int: {stats.intelligence} Wil: {stats.willpower} Cha: {stats.charisma}")
    if needs:
        lines.append(f"Hunger: {needs.hunger:.0f}/100  Thirst: {needs.thirst:.0f}/100")
        lines.append(f"Fatigue: {needs.fatigue:.0f}/100  Morale: {needs.morale:.0f}")
    return CommandResult(success=True, output="\n".join(lines))


def _cmd_save(ctx: CommandContext) -> CommandResult:
    """Save the game."""
    if ctx.engine is None:
        return CommandResult(success=False, error="No engine.")
    name = ctx.args[0] if ctx.args else "quicksave"
    ctx.engine.save_game(name)
    return CommandResult(success=True, output=f"Saved as {name}.")


def _cmd_load(ctx: CommandContext) -> CommandResult:
    """Load a save."""
    if ctx.engine is None:
        return CommandResult(success=False, error="No engine.")
    if not ctx.args:
        return CommandResult(success=False, error="Usage: load <name>")
    ctx.engine.load_game(ctx.args[0])
    return CommandResult(success=True, output=f"Loaded {ctx.args[0]}.")


def _cmd_time(ctx: CommandContext) -> CommandResult:
    """Show current game time."""
    if ctx.engine is None:
        return CommandResult(success=False, error="No engine.")
    return CommandResult(success=True, output=ctx.engine.clock.time.display())


def _cmd_wait(ctx: CommandContext) -> CommandResult:
    """Wait for some time."""
    if ctx.engine is None:
        return CommandResult(success=False, error="No engine.")
    minutes = int(ctx.args[0]) if ctx.args else 60
    ticks = minutes * ctx.engine.clock.ticks_per_game_minute
    ctx.engine.clock.advance_ticks(ticks)
    return CommandResult(success=True, output=f"Waited {minutes} minutes.")


def _cmd_spawn(ctx: CommandContext) -> CommandResult:
    """[DEBUG] Spawn a creature."""
    if not ctx.args:
        return CommandResult(success=False, error="Usage: spawn <creature> [count]")
    creature = ctx.args[0]
    count = int(ctx.args[1]) if len(ctx.args) > 1 else 1
    if ctx.engine is None:
        return CommandResult(success=False, error="No engine.")
    from engine.entities.components import Position
    pos = ctx.world.get_component(ctx.player, Position) if ctx.player else None
    if pos is None:
        return CommandResult(success=False, error="No position.")
    spawned = []
    for i in range(count):
        e = ctx.engine.factory.create_creature(
            creature, creature[0] if creature else "?",
            ctx.engine.rng.randint(50, 250),
            x=pos.x + ctx.engine.rng.randint(-3, 3),
            y=pos.y + ctx.engine.rng.randint(-3, 3),
            aggressive=True, race_id="beast",
        )
        spawned.append(e.id)
    return CommandResult(success=True, output=f"Spawned: {spawned}")


def _cmd_weather(ctx: CommandContext) -> CommandResult:
    """Show current weather."""
    if ctx.engine is None or ctx.engine.weather is None:
        return CommandResult(success=False, error="No weather system.")
    return CommandResult(success=True, output=ctx.engine.weather.current.description())


def _cmd_plugins(ctx: CommandContext) -> CommandResult:
    """List plugins."""
    if ctx.engine is None:
        return CommandResult(success=False, error="No engine.")
    status = ctx.engine.plugins.status()
    lines = ["Plugins:"]
    for s in status:
        lines.append(f"  {s['name']:30s} v{s['version']:8s} [{s['state']}]")
    return CommandResult(success=True, output="\n".join(lines))


def _cmd_reload(ctx: CommandContext) -> CommandResult:
    """[ADMIN] Reload a plugin."""
    if not ctx.args or ctx.engine is None:
        return CommandResult(success=False, error="Usage: reload <plugin>")
    ctx.engine.plugins.reload(ctx.args[0])
    return CommandResult(success=True, output=f"Reloaded {ctx.args[0]}.")


def _cmd_quit(ctx: CommandContext) -> CommandResult:
    """Quit the game."""
    if ctx.engine is not None:
        ctx.engine.shutdown()
    return CommandResult(success=True, output="Goodbye!")


DEFAULT_COMMANDS: list[Command] = [
    Command("help", _cmd_help, "Show this help.", "help [command]"),
    Command("look", _cmd_look, "Look around.", "look", aliases=["l"]),
    Command("inventory", _cmd_inventory, "Show inventory.", "inventory",
            aliases=["i", "inv"]),
    Command("status", _cmd_status, "Show player status.", "status",
            aliases=["st", "stat"]),
    Command("save", _cmd_save, "Save the game.", "save [name]"),
    Command("load", _cmd_load, "Load a save.", "load <name>"),
    Command("time", _cmd_time, "Show current game time.", "time"),
    Command("wait", _cmd_wait, "Wait for some time.", "wait [minutes]",
            aliases=["w"]),
    Command("weather", _cmd_weather, "Show weather.", "weather"),
    Command("plugins", _cmd_plugins, "List plugins.", "plugins"),
    Command("reload", _cmd_reload, "Reload a plugin.", "reload <plugin>",
            permission=Permission.ADMIN),
    Command("spawn", _cmd_spawn, "Spawn a creature (debug).", "spawn <creature> [count]",
            permission=Permission.DEBUG, debug_only=True),
    Command("quit", _cmd_quit, "Quit the game.", "quit", aliases=["exit", "q"]),
]
