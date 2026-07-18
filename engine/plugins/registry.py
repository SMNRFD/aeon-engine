"""Plugin registry — tracks discovered plugins and their states."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional

from engine.plugins.base import Plugin, PluginMetadata, PluginState


@dataclass
class PluginRecord:
    """A discovered plugin entry."""

    metadata: PluginMetadata
    plugin: Plugin
    module_path: str
    file_path: str
    state: str = PluginState.UNLOADED
    error: Optional[str] = None
    enabled: bool = False


class PluginRegistry:
    """Thread-safe registry of discovered plugins."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginRecord] = {}
        self._lock = threading.RLock()

    def register(self, record: PluginRecord) -> None:
        with self._lock:
            self._plugins[record.metadata.name] = record

    def unregister(self, name: str) -> Optional[PluginRecord]:
        with self._lock:
            return self._plugins.pop(name, None)

    def get(self, name: str) -> Optional[PluginRecord]:
        with self._lock:
            return self._plugins.get(name)

    def all(self) -> list[PluginRecord]:
        with self._lock:
            return list(self._plugins.values())

    def names(self) -> list[str]:
        with self._lock:
            return list(self._plugins.keys())

    def by_tag(self, tag: str) -> list[PluginRecord]:
        with self._lock:
            return [
                r for r in self._plugins.values()
                if tag in r.metadata.tags
            ]

    def clear(self) -> None:
        with self._lock:
            self._plugins.clear()

    def __contains__(self, name: str) -> bool:
        with self._lock:
            return name in self._plugins

    def __len__(self) -> int:
        with self._lock:
            return len(self._plugins)
