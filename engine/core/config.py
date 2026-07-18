"""Engine configuration loaded from TOML files with environment overrides.

Configuration is layered: defaults < TOML file < environment variables.
The merged configuration is exposed as a singleton via `get_config()`.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from engine.core.logging import get_logger


log = get_logger("config")


@dataclass
class WorldConfig:
    """World generation parameters."""

    world_seed: int = 0xBEEF
    region_size: int = 64            # tiles per region edge
    world_tiles_x: int = 256
    world_tiles_y: int = 256
    sea_level: float = 0.42
    mountain_level: float = 0.78
    temperature_noise_scale: float = 4.0
    moisture_noise_scale: float = 3.5
    enable_rivers: bool = True
    enable_roads: bool = True
    initial_npc_density: float = 0.012


@dataclass
class SimulationConfig:
    """Simulation tick parameters."""

    ticks_per_second: int = 20
    ticks_per_game_minute: int = 10
    minutes_per_game_hour: int = 60
    hours_per_day: int = 24
    days_per_season: int = 30
    seasons_per_year: int = 4
    npc_simulation_chunk_size: int = 64
    async_npc_simulation: bool = False


@dataclass
class PluginConfig:
    """Plugin system parameters."""

    plugin_dirs: list[str] = field(
        default_factory=lambda: ["plugins", "engine/builtins"]
    )
    hot_reload: bool = True
    sandbox_enabled: bool = False
    autoload_enabled: bool = True


@dataclass
class SaveConfig:
    """Save system parameters."""

    save_dir: str = "saves"
    autosave_interval_ticks: int = 1200  # once per game-hour at 20 tps
    max_autosaves: int = 5
    compression: str = "zlib"
    integrity_check: bool = True


@dataclass
class UIConfig:
    """Terminal UI parameters."""

    theme: str = "dark"
    color_enabled: bool = True
    unicode_enabled: bool = True
    message_log_size: int = 200
    viewport_width: int = 80
    viewport_height: int = 24


@dataclass
class EngineConfig:
    """Top-level engine configuration."""

    engine_name: str = "Aeon"
    version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    log_file: Optional[str] = "aeon.log"
    world: WorldConfig = field(default_factory=WorldConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    plugins: PluginConfig = field(default_factory=PluginConfig)
    save: SaveConfig = field(default_factory=SaveConfig)
    ui: UIConfig = field(default_factory=UIConfig)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_config: Optional[EngineConfig] = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` into `base`."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _apply_env_overrides(cfg: EngineConfig) -> EngineConfig:
    """Apply `AEON_*` environment variable overrides to the config."""
    env_map = {
        "AEON_DEBUG": ("debug", lambda v: v.lower() in {"1", "true", "yes"}),
        "AEON_LOG_LEVEL": ("log_level", str),
        "AEON_LOG_FILE": ("log_file", lambda v: v or None),
        "AEON_WORLD_SEED": ("world.world_seed", int),
        "AEON_TICKS_PER_SECOND": ("simulation.ticks_per_second", int),
        "AEON_UI_THEME": ("ui.theme", str),
        "AEON_SAVE_DIR": ("save.save_dir", str),
    }
    for env_key, (path, conv) in env_map.items():
        if env_key in os.environ:
            value = conv(os.environ[env_key])
            obj: Any = cfg
            parts = path.split(".")
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], value)
    return cfg


def load_config(path: Optional[Path] = None) -> EngineConfig:
    """Load configuration from a TOML file, falling back to defaults."""
    global _config
    cfg = EngineConfig()

    if path is None:
        path = Path("engine.toml")
    path = Path(path)

    if path.exists():
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
            # Map TOML sections onto dataclass fields.
            for section, values in data.items():
                if section == "engine":
                    for k, v in values.items():
                        if hasattr(cfg, k):
                            setattr(cfg, k, v)
                elif hasattr(cfg, section):
                    sub = getattr(cfg, section)
                    for k, v in values.items():
                        if hasattr(sub, k):
                            setattr(sub, k, v)
            log.info("Loaded config from %s", path)
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load config %s: %s", path, exc)
    else:
        log.debug("No config file at %s — using defaults", path)

    cfg = _apply_env_overrides(cfg)
    _config = cfg
    return cfg


def get_config() -> EngineConfig:
    """Return the current engine configuration, loading defaults if needed."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(cfg: EngineConfig) -> None:
    """Replace the global configuration (used by tests)."""
    global _config
    _config = cfg
