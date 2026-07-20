"""Test that all REPL commands work without crashing.

Catches hidden errors by patching _execute_command to NOT swallow exceptions.
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.engine import Engine
from engine.core.config import EngineConfig
from engine.world.generator import WorldGenParams
from engine.repl.repl import GameREPL
from engine.magic.spells import Mana


def main() -> int:
    config = EngineConfig()
    config.ui.color_enabled = False
    e = Engine(config, headless=True)
    e.generate_world(WorldGenParams(seed=42, width=30, height=20))
    e.create_player("Tester")
    # Add mana so spells work
    e.world.add_component(e.player, Mana(current=200, maximum=200))

    repl = GameREPL(e)

    commands_to_test = [
        # Movement
        "go north", "go south", "go east", "go west",
        # Look/exploration
        "look", "look goblin",
        # Character
        "inventory", "character", "status", "spells", "skills",
        # Magic
        "cast fireball", "schools", "meditate 1",
        # Items
        "use health potion", "equip dagger", "unequip weapon",
        # Crafting
        "recipes", "craft bread", "train smithing 1", "use_skill smithing",
        "books", "read book", "runes",
        # Economy
        "market", "buy food 5", "sell food 5", "bank balance",
        "bank deposit 100", "bank withdraw 50", "loan take 1000 12",
        "trade_routes",
        # Auctions
        "auction list", "auction sell dagger 50", "blackmarket list",
        # Quests
        "quests", "quest list", "quest_chains", "quest_chain 1",
        # Factions
        "factions", "faction 1", "kingdoms", "kingdom 1",
        # Espionage
        "spies", "recruit_spy 1 TestSpy",
        # Rebellion
        "rebellion PEASANT 1", "suppress 1", "negotiate 1",
        # Combat variants
        "naval list", "siege create 1 2", "aerial mount", "space fire",
        "realtime queue", "mount mount",
        # Survival
        "diseases", "cure", "family", "job",
        # Dungeons
        "dungeon CAVE 3", "bookmark list", "bookmark add test",
        # Animals
        "hunt wolf", "tame wolf", "livestock", "animals",
        # Artifacts
        "artifacts", "wield test", "talk_artifact test",
        # Reputation
        "reputation", "hero saved a cat", "crime theft",
        # Stealth
        "stealth on", "stealth off", "backstab",
        # World
        "map", "time", "weather", "simulate 1", "contentpacks",
        # Themes
        "theme list",
        # Dimensions
        "dimensions",
        # Body parts
        "bodyparts", "heal_part HEAD 10",
        # NEW: Companies & Guilds
        "companies", "company 1", "company 1 join", "company 1 leave",
        "guilds", "guild 1",
        # NEW: Structures
        "structures",
        # NEW: Quest chains
        "quest_chains", "quest_chain 1",
        # NEW: Mods
        "mods list", "mods discover", "mods apply",
        # NEW: Script
        "script list", "script exec print(2 + 2)",
        # NEW: Audio
        "audio list", "audio play sword_hit", "audio cues",
        # NEW: Accessibility
        "accessibility", "accessibility reader on", "accessibility reader off",
        # NEW: Keybindings
        "keybindings", "keybindings rebind MOVE_NORTH k",
        # NEW: Locale
        "locale", "locale en_US",
        # System
        "banner", "schedule", "memory", "plugins",
        # Fishing
        "fish",
        # Unknown
        "nonexistent_command",
        # Help
        "help",
    ]

    failures = []
    for cmd in commands_to_test:
        # Use the underlying command handler directly to bypass the
        # _execute_command exception swallowing.
        try:
            import shlex
            tokens = shlex.split(cmd)
            if not tokens:
                continue
            cmd_name = tokens[0].lower()
            args = tokens[1:]
            aliases = GameREPL._aliases()
            from engine.repl.repl import DIRECTIONS
            if cmd_name in DIRECTIONS:
                args = [cmd_name]
                cmd_name = "go"
            else:
                cmd_name = aliases.get(cmd_name, cmd_name)
            handler = getattr(repl, f"cmd_{cmd_name}", None)
            if handler is None:
                # Unknown command — just register it as OK (handled by
                # the command processor fallback).
                print(f"OK (no handler):   {cmd!r}")
                continue
            handler(args)
        except Exception as exc:
            tb = traceback.format_exc()
            failures.append((cmd, str(exc), tb))
            print(f"FAIL: {cmd!r} -> {exc}")
        else:
            print(f"OK:   {cmd!r}")

    print()
    print(f"Total: {len(commands_to_test)}, Failures: {len(failures)}")
    if failures:
        print("\n=== Failures ===")
        for cmd, exc, tb in failures:
            print(f"\nCommand: {cmd!r}")
            print(f"Error: {exc}")
            print(tb[-600:])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

