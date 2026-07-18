#!/usr/bin/env python3
"""Aeon Engine — main entry point.

Usage:
    python main.py [options]

Options:
    --seed N        World generation seed.
    --width N       World width.
    --height N      World height.
    --headless      Run without UI (for testing).
    --load NAME     Load a save slot instead of starting a new game.
    --no-plugins    Skip plugin loading.
    --debug         Enable debug/cheat mode.
    --help          Show this help.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

from engine.core.config import EngineConfig, load_config, set_config
from engine.core.logging import configure_logging, get_logger
from engine.engine import Engine
from engine.world.generator import WorldGenParams


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aeon Engine — text-based open-world RPG")
    parser.add_argument("--seed", type=int, default=None, help="World generation seed.")
    parser.add_argument("--width", type=int, default=None, help="World width.")
    parser.add_argument("--height", type=int, default=None, help="World height.")
    parser.add_argument("--headless", action="store_true", help="Run without UI.")
    parser.add_argument("--load", type=str, default=None, help="Load a save slot.")
    parser.add_argument("--no-plugins", action="store_true", help="Skip plugin loading.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode.")
    parser.add_argument("--name", type=str, default="Hero", help="Player character name.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    # Load configuration
    config = load_config(Path("engine.toml"))
    if args.debug:
        config.debug = True
    if args.seed is not None:
        config.world.world_seed = args.seed
    set_config(config)
    import logging
    configure_logging(level=logging.DEBUG if config.debug else logging.INFO,
                      log_file=Path(config.log_file) if config.log_file else None)

    log = get_logger("main")
    log.info("Starting Aeon Engine v%s", config.version)

    engine = Engine(config, headless=args.headless)
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
        # Run a single tick to verify
        engine.tick_simulation(0.05)
        log.info("Headless tick complete. Player id: %s",
                 engine.player.id if engine.player else None)
        return 0

    try:
        engine.start()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    finally:
        engine.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
