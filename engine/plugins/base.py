"""Plugin base class and metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from engine.core.events import EventBus
from engine.core.logging import get_logger


log = get_logger("plugins.base")


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].+)?$")


def parse_version(v: str) -> tuple[int, int, int]:
    m = _VERSION_RE.match(v.strip())
    if not m:
        raise ValueError(f"Invalid version string: {v!r}")
    major, minor, patch = m.group(1), m.group(2), m.group(3)
    return int(major), int(minor), int(patch or 0)


def version_satisfies(version: str, requirement: str) -> bool:
    """Check whether `version` satisfies a `requirement` like `>=1.0`, `==2.3.1`."""
    op_match = re.match(r"^(>=|<=|>|<|==|!=)?\s*(.+)$", requirement.strip())
    if not op_match:
        return False
    op = op_match.group(1) or "=="
    want = parse_version(op_match.group(2))
    have = parse_version(version)
    if op == "==":
        return have == want
    if op == "!=":
        return have != want
    if op == ">=":
        return have >= want
    if op == "<=":
        return have <= want
    if op == ">":
        return have > want
    if op == "<":
        return have < want
    return False


@dataclass
class PluginMetadata:
    """Static metadata about a plugin."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = "MIT"
    homepage: str = ""
    dependencies: list[str] = field(default_factory=list)  # e.g. ["core>=1.0"]
    conflicts: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    api_version: str = "0.1"
    tags: list[str] = field(default_factory=list)
    load_order: int = 1000  # lower loads first

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "license": self.license,
            "homepage": self.homepage,
            "dependencies": list(self.dependencies),
            "conflicts": list(self.conflicts),
            "permissions": list(self.permissions),
            "api_version": self.api_version,
            "tags": list(self.tags),
            "load_order": self.load_order,
        }


class PluginState:
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class Plugin:
    """Base class for all plugins.

    Subclasses override the lifecycle hooks:

        on_load(engine)       — called once after the module is imported
        on_enable(engine)     — called when the plugin is enabled
        on_disable(engine)    — called when the plugin is disabled
        on_unload(engine)     — called when the module is being unloaded
        on_reload(engine)     — called on hot reload (after on_disable / before on_enable)
    """

    metadata: PluginMetadata  # subclasses must override

    def __init__(self) -> None:
        self.engine: Any = None
        self.event_bus: Optional[EventBus] = None
        self.state: str = PluginState.UNLOADED
        self.logger = get_logger(f"plugin.{self.__class__.__name__}")

    # ---------- lifecycle hooks ----------

    def on_load(self, engine: Any) -> None:
        """Called once after the module is imported."""

    def on_enable(self, engine: Any) -> None:
        """Called when the plugin is enabled."""

    def on_disable(self, engine: Any) -> None:
        """Called when the plugin is disabled."""

    def on_unload(self, engine: Any) -> None:
        """Called when the module is being unloaded."""

    def on_reload(self, engine: Any) -> None:
        """Called on hot reload."""

    # ---------- helper API ----------

    def register_command(self, engine: Any, name: str, handler: Any, **kwargs: Any) -> None:
        if hasattr(engine, "commands"):
            engine.commands.register(name, handler, plugin=self.metadata.name, **kwargs)

    def subscribe(self, event_bus: EventBus, event_type: type, handler: Any,
                  priority: int = 50) -> None:
        from engine.core.events import Priority
        # Allow int priorities for convenience.
        prio = priority if isinstance(priority, Priority) else Priority(priority)
        event_bus.subscribe(event_type, handler, priority=prio, plugin=self.metadata.name)

    def __repr__(self) -> str:
        return f"<Plugin {self.metadata.name} v{self.metadata.version} [{self.state}]>"
