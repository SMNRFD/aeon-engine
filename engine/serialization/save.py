"""Save system — versioned, compressed, integrity-checked."""

from __future__ import annotations

import hashlib
import json
import os
import pickle
import shutil
import time
import zlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from engine.core.logging import get_logger


log = get_logger("save")

SAVE_FORMAT_VERSION = 1


@dataclass
class SaveSlot:
    """Metadata for a save slot."""

    name: str
    path: Path
    timestamp: float
    size_bytes: int
    version: int
    game_time_display: str = ""
    character_name: str = ""
    character_level: int = 1

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "timestamp": self.timestamp,
            "size_bytes": self.size_bytes,
            "version": self.version,
            "game_time_display": self.game_time_display,
            "character_name": self.character_name,
            "character_level": self.character_level,
        }


@dataclass
class SaveData:
    """The full save state."""

    format_version: int = SAVE_FORMAT_VERSION
    engine_version: str = "0.1.0"
    timestamp: float = field(default_factory=time.time)
    game_time: dict = field(default_factory=dict)
    world: dict = field(default_factory=dict)
    entities: dict = field(default_factory=dict)
    items: dict = field(default_factory=dict)
    inventories: dict = field(default_factory=dict)
    factions: dict = field(default_factory=dict)
    markets: dict = field(default_factory=dict)
    quests: dict = field(default_factory=dict)
    weather: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SaveData":
        return cls(**{k: data.get(k, {}) if k != "format_version" and k != "engine_version" and k != "timestamp" else data.get(k)
                      for k in cls.__dataclass_fields__})


_MIGRATIONS: dict[int, Any] = {}


def migration(from_version: int):
    """Decorator to register a migration from `from_version` to `from_version + 1`."""
    def decorator(fn):
        _MIGRATIONS[from_version] = fn
        return fn
    return decorator


def migrate(data: dict) -> dict:
    """Apply migrations to bring `data` up to the current save version."""
    version = data.get("format_version", 1)
    while version < SAVE_FORMAT_VERSION:
        migrator = _MIGRATIONS.get(version)
        if migrator is None:
            log.warning("No migration from save version %d — attempting to load anyway", version)
            break
        data = migrator(data)
        version = data.get("format_version", version + 1)
    data["format_version"] = SAVE_FORMAT_VERSION
    return data


# Example migration: from v1 to v2 (placeholder for future use)
@migration(1)
def _migrate_v1_to_v2(data: dict) -> dict:
    # Future: add new fields, rename keys, etc.
    data["format_version"] = 2
    return data


class SaveManager:
    """Manages saving and loading the game."""

    def __init__(self, save_dir: str = "saves",
                 compression: str = "zlib",
                 integrity_check: bool = True) -> None:
        self.save_dir = Path(save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.compression = compression
        self.integrity_check = integrity_check

    # ---------- listing ----------

    def list_slots(self) -> list[SaveSlot]:
        slots: list[SaveSlot] = []
        for entry in sorted(self.save_dir.iterdir()):
            if entry.suffix == ".sav":
                try:
                    slot = self._read_metadata(entry)
                    slots.append(slot)
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed to read save slot %s: %s", entry, exc)
        return slots

    def _read_metadata(self, path: Path) -> SaveSlot:
        raw = path.read_bytes()
        if self.compression == "zlib":
            raw = zlib.decompress(raw)
        payload, _, metadata_bytes = raw.partition(b"\n---META---\n")
        if not metadata_bytes:
            metadata_bytes = b"{}"
        metadata = json.loads(metadata_bytes.decode("utf-8"))
        return SaveSlot(
            name=path.stem,
            path=path,
            timestamp=metadata.get("timestamp", 0.0),
            size_bytes=path.stat().st_size,
            version=metadata.get("format_version", 1),
            game_time_display=metadata.get("game_time_display", ""),
            character_name=metadata.get("character_name", ""),
            character_level=metadata.get("character_level", 1),
        )

    # ---------- save ----------

    def save(self, name: str, data: SaveData, *,
             character_name: str = "", character_level: int = 1,
             game_time_display: str = "") -> Path:
        """Save the game to `<save_dir>/<name>.sav`. Returns the path."""
        path = self.save_dir / f"{name}.sav"
        payload_dict = data.to_dict()
        payload_bytes = pickle.dumps(payload_dict)
        if self.compression == "zlib":
            payload_bytes = zlib.compress(payload_bytes, level=6)
        # Integrity hash
        if self.integrity_check:
            checksum = hashlib.sha256(payload_bytes).hexdigest()
        else:
            checksum = ""
        metadata = {
            "format_version": SAVE_FORMAT_VERSION,
            "engine_version": data.engine_version,
            "timestamp": data.timestamp,
            "checksum": checksum,
            "character_name": character_name,
            "character_level": character_level,
            "game_time_display": game_time_display,
        }
        metadata_bytes = json.dumps(metadata).encode("utf-8")
        full = payload_bytes + b"\n---META---\n" + metadata_bytes
        path.write_bytes(full)
        log.info("Saved game to %s (%.2f KB)", path, len(full) / 1024)
        return path

    # ---------- load ----------

    def load(self, name: str) -> SaveData:
        """Load a save by name. Raises FileNotFoundError if not present."""
        path = self.save_dir / f"{name}.sav"
        if not path.exists():
            raise FileNotFoundError(f"No save slot: {name}")
        return self.load_path(path)

    def load_path(self, path: Path) -> SaveData:
        raw = path.read_bytes()
        if self.compression == "zlib":
            raw = zlib.decompress(raw)
        payload_bytes, _, metadata_bytes = raw.partition(b"\n---META---\n")
        metadata = json.loads(metadata_bytes.decode("utf-8")) if metadata_bytes else {}
        # Integrity check
        if self.integrity_check and metadata.get("checksum"):
            actual = hashlib.sha256(payload_bytes).hexdigest()
            if actual != metadata["checksum"]:
                raise ValueError(f"Save file {path} failed integrity check")
        data_dict = pickle.loads(payload_bytes)
        # Migrate
        data_dict = migrate(data_dict)
        return SaveData.from_dict(data_dict)

    # ---------- management ----------

    def delete(self, name: str) -> bool:
        path = self.save_dir / f"{name}.sav"
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, name: str) -> bool:
        return (self.save_dir / f"{name}.sav").exists()

    def autosave(self, data: SaveData, max_autosaves: int = 5, **kwargs) -> Path:
        """Save to a rotating set of autosave slots."""
        # Find next autosave slot
        existing = sorted(self.save_dir.glob("autosave_*.sav"))
        if len(existing) >= max_autosaves:
            # Remove oldest
            oldest = min(existing, key=lambda p: p.stat().st_mtime)
            oldest.unlink()
        # Find next index
        indices = []
        for p in existing:
            try:
                idx = int(p.stem.split("_")[1])
                indices.append(idx)
            except (IndexError, ValueError):
                continue
        next_idx = max(indices) + 1 if indices else 1
        name = f"autosave_{next_idx}"
        return self.save(name, data, **kwargs)
