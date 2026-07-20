"""End-to-end gameplay simulation — verify the REPL works for a full play session."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.engine import Engine
from engine.core.config import EngineConfig
from engine.world.generator import WorldGenParams
from engine.repl.repl import GameREPL
from engine.magic.spells import Mana


def run_cmd(repl: GameREPL, cmd: str) -> tuple[bool, str]:
    """Run a command, returning (success, error_message)."""
    try:
        repl._execute_command(cmd)
        return True, ""
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"


def main() -> int:
    config = EngineConfig()
    config.ui.color_enabled = False
    e = Engine(config, headless=True)
    e.generate_world(WorldGenParams(seed=42, width=30, height=20))
    e.create_player("Hero")
    e.world.add_component(e.player, Mana(current=200, maximum=200))

    repl = GameREPL(e)

    # Simulate a full play session
    session = [
        # Wake up, look around
        "look",
        "time", "weather", "map",
        # Check character
        "character", "inventory", "spells", "skills", "status",
        # Move around
        "go north", "k", "l", "h", "j",
        # Combat
        "look", "attack goblin",
        # Magic
        "cast fireball", "schools", "meditate 1",
        # Items
        "use health potion", "equip dagger", "unequip weapon",
        # Crafting
        "recipes", "craft torch", "train smithing 1",
        # Economy
        "market", "buy food 5", "sell food 5",
        "bank balance", "bank deposit 100", "bank withdraw 50",
        "loan take 1000 12",
        # Companies & guilds
        "companies", "company 1", "company 1 join", "company 1 leave",
        "guilds", "guild 1",
        # Structures
        "structures",
        # Quests
        "quests", "quest list", "quest_chains", "quest_chain 1",
        # Factions
        "factions", "faction 1", "kingdoms", "kingdom 1",
        # Reputation
        "reputation", "hero saved a cat",
        # Stealth
        "stealth on", "stealth off",
        # Themes
        "theme list",
        # Dimensions
        "dimensions",
        # Body parts
        "bodyparts", "heal_part HEAD 10",
        # Audio
        "audio list", "audio play sword_hit", "audio cues",
        # Accessibility
        "accessibility", "accessibility reader on", "accessibility reader off",
        # Keybindings
        "keybindings",
        # Locale
        "locale", "locale en_US",
        # Mods
        "mods list", "mods discover",
        # Script
        "script list", "script exec print(2 + 2)",
        # World
        "simulate 1", "contentpacks",
        # Bookmarks
        "bookmark list", "bookmark add Home", "pin 10 10 my_pin",
        # Animals
        "hunt wolf", "tame wolf", "livestock", "animals",
        # Artifacts
        "artifacts",
        # Diseases
        "diseases", "cure",
        # Family
        "family", "job",
        # Schedule & memory
        "schedule", "memory",
        # Plugins & banner
        "plugins", "banner",
        # Help
        "help",
        # Save
        "save test_session",
        # Quit
        "quit",
    ]

    failures = []
    for cmd in session:
        ok, err = run_cmd(repl, cmd)
        if not ok:
            failures.append((cmd, err))
            print(f"FAIL: {cmd!r}")
            print(f"  {err.splitlines()[0] if err else ''}")
        else:
            print(f"OK:   {cmd!r}")
        if not repl.running and cmd != "quit":
            print(f"  WARNING: REPL stopped after {cmd!r}")

    print()
    print(f"Total: {len(session)}, Failures: {len(failures)}")
    if failures:
        print("\n=== Failures ===")
        for cmd, err in failures:
            print(f"\nCommand: {cmd!r}")
            print(err)
        return 1
    print("\nAll commands executed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
