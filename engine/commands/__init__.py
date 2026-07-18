"""Command system — parser, aliases, macros, permissions, history."""

from engine.commands.system import (
    Command, CommandResult, CommandContext, CommandRegistry, CommandProcessor,
    Permission, DEFAULT_COMMANDS,
)
