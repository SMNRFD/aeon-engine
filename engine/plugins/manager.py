"""Plugin manager — discovery, dependency resolution, lifecycle, hot reload."""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import sys
import threading
from pathlib import Path
from typing import Any, Optional

from engine.core.logging import get_logger
from engine.plugins.base import (
    Plugin,
    PluginMetadata,
    PluginState,
    parse_version,
    version_satisfies,
)
from engine.plugins.registry import PluginRegistry, PluginRecord


log = get_logger("plugins.manager")


class PluginError(Exception):
    """Raised when a plugin fails to load or satisfies a constraint."""


class PluginManager:
    """Manages plugin discovery, loading, hot reload, and lifecycle."""

    def __init__(self, engine: Any, plugin_dirs: Optional[list[str]] = None) -> None:
        self.engine = engine
        self.event_bus = getattr(engine, "event_bus", None)
        self.registry = PluginRegistry()
        self.plugin_dirs: list[Path] = [
            Path(p).resolve() for p in (plugin_dirs or ["plugins"])
        ]
        self._lock = threading.RLock()
        self._loaded_modules: dict[str, Any] = {}

    # ---------- discovery ----------

    def discover(self) -> int:
        """Scan plugin directories for `plugin.py` modules and `plugin.toml`
        metadata files. Returns the number of discovered plugins."""
        count = 0
        for d in self.plugin_dirs:
            if not d.exists():
                continue
            for entry in sorted(d.iterdir()):
                if entry.is_dir() and (entry / "plugin.py").exists():
                    if self._discover_module(entry):
                        count += 1
                elif entry.is_file() and entry.suffix == ".py":
                    if self._discover_module(entry.parent, entry.stem):
                        count += 1
        log.info("Discovered %d plugins", count)
        return count

    def _discover_module(self, dir_path: Path, module_name: Optional[str] = None) -> bool:
        if module_name is None:
            module_name = dir_path.name
        plugin_file = dir_path / "plugin.py" if dir_path.is_dir() else dir_path
        if not plugin_file.exists():
            return False
        # Defer actual import — we just record the path.
        record_key = f"{dir_path.name}:{plugin_file}"
        try:
            spec = importlib.util.spec_from_file_location(
                f"plugins.{module_name}", plugin_file
            )
            if spec is None or spec.loader is None:
                return False
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            plugin_class = self._find_plugin_class(module)
            if plugin_class is None:
                log.warning("No Plugin subclass found in %s", plugin_file)
                return False
            instance = plugin_class()
            metadata = instance.metadata
            record = PluginRecord(
                metadata=metadata,
                plugin=instance,
                module_path=spec.name,
                file_path=str(plugin_file),
            )
            self.registry.register(record)
            self._loaded_modules[metadata.name] = module
            log.debug("Discovered plugin %s v%s at %s",
                      metadata.name, metadata.version, plugin_file)
            return True
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to discover plugin at %s: %s", plugin_file, exc)
            return False

    def _find_plugin_class(self, module: Any) -> Optional[type[Plugin]]:
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, Plugin) and obj is not Plugin:
                # Skip imported classes from other modules
                if obj.__module__ == module.__name__:
                    return obj
        return None

    # ---------- dependency resolution ----------

    @staticmethod
    def _parse_dependency(dep: str) -> tuple[str, str]:
        """Parse 'name>=1.0' -> ('name', '>=1.0'). Returns (name, requirement)."""
        import re
        # Find the first operator and split there
        m = re.search(r"\s*(>=|<=|==|!=|>|<)\s*", dep)
        if m:
            name = dep[:m.start()].strip()
            op = m.group(1)
            version = dep[m.end():].strip()
            return name, f"{op}{version}"
        return dep.strip(), ""

    def resolve_load_order(self) -> list[PluginRecord]:
        """Topologically sort plugins by their declared dependencies."""
        records = self.registry.all()
        name_to_record = {r.metadata.name: r for r in records}
        visited: dict[str, int] = {}  # 0=visiting, 1=visited
        order: list[PluginRecord] = []

        def visit(rec: PluginRecord, path: list[str]) -> None:
            state = visited.get(rec.metadata.name)
            if state == 1:
                return
            if state == 0:
                raise PluginError(
                    f"Circular dependency detected: {' -> '.join(path + [rec.metadata.name])}"
                )
            visited[rec.metadata.name] = 0
            for dep in rec.metadata.dependencies:
                dep_name, version_req = self._parse_dependency(dep)
                if dep_name not in name_to_record:
                    raise PluginError(
                        f"Plugin {rec.metadata.name} requires missing dependency {dep_name}"
                    )
                dep_rec = name_to_record[dep_name]
                if version_req and not version_satisfies(dep_rec.metadata.version, version_req):
                    raise PluginError(
                        f"Plugin {rec.metadata.name} requires {dep} "
                        f"but {dep_name} is {dep_rec.metadata.version}"
                    )
                visit(dep_rec, path + [rec.metadata.name])
            visited[rec.metadata.name] = 1
            order.append(rec)

        # Sort by load_order first for deterministic output.
        for rec in sorted(records, key=lambda r: r.metadata.load_order):
            visit(rec, [])

        return order

    # ---------- lifecycle ----------

    def load_all(self) -> tuple[int, int]:
        """Discover, resolve, and load all plugins. Returns (success, failure)."""
        self.discover()
        try:
            order = self.resolve_load_order()
        except PluginError as exc:
            log.error("Dependency resolution failed: %s", exc)
            return 0, self.registry.__len__()
        success = 0
        failure = 0
        for rec in order:
            try:
                self._load_plugin(rec)
                success += 1
            except Exception as exc:  # noqa: BLE001
                log.exception("Failed to load %s: %s", rec.metadata.name, exc)
                rec.state = PluginState.ERROR
                rec.error = str(exc)
                failure += 1
        return success, failure

    def _load_plugin(self, record: PluginRecord) -> None:
        if record.state == PluginState.LOADED:
            return
        record.state = PluginState.LOADING
        plugin = record.plugin
        plugin.engine = self.engine
        plugin.event_bus = self.event_bus
        try:
            plugin.on_load(self.engine)
            record.state = PluginState.LOADED
            log.info("Loaded plugin %s v%s",
                     record.metadata.name, record.metadata.version)
        except Exception as exc:  # noqa: BLE001
            record.state = PluginState.ERROR
            record.error = str(exc)
            raise

    def enable(self, name: str) -> None:
        record = self.registry.get(name)
        if record is None:
            raise PluginError(f"No such plugin: {name}")
        if record.state == PluginState.ERROR:
            raise PluginError(f"Plugin {name} is in error state: {record.error}")
        if record.state == PluginState.UNLOADED:
            self._load_plugin(record)
        record.plugin.on_enable(self.engine)
        record.state = PluginState.ENABLED
        record.enabled = True
        log.info("Enabled plugin %s", name)

    def disable(self, name: str) -> None:
        record = self.registry.get(name)
        if record is None:
            raise PluginError(f"No such plugin: {name}")
        if record.state != PluginState.ENABLED:
            return
        record.plugin.on_disable(self.engine)
        record.state = PluginState.DISABLED
        record.enabled = False
        # Unsubscribe all event handlers from this plugin.
        if self.event_bus:
            self.event_bus.unsubscribe_plugin(name)
        log.info("Disabled plugin %s", name)

    def unload(self, name: str) -> None:
        record = self.registry.get(name)
        if record is None:
            return
        if record.state == PluginState.ENABLED:
            self.disable(name)
        record.plugin.on_unload(self.engine)
        record.state = PluginState.UNLOADED
        # Remove from sys.modules to allow fresh re-import.
        sys.modules.pop(record.module_path, None)
        log.info("Unloaded plugin %s", name)

    def reload(self, name: str) -> None:
        """Hot-reload a plugin: disable, reload module, re-enable."""
        record = self.registry.get(name)
        if record is None:
            raise PluginError(f"No such plugin: {name}")
        was_enabled = record.enabled
        if was_enabled:
            self.disable(name)
        try:
            module = self._loaded_modules.get(name)
            if module is not None:
                importlib.reload(module)
                plugin_class = self._find_plugin_class(module)
                if plugin_class is None:
                    raise PluginError("No Plugin class after reload")
                record.plugin = plugin_class()
                record.plugin.engine = self.engine
                record.plugin.event_bus = self.event_bus
                record.plugin.on_reload(self.engine)
            if was_enabled:
                self.enable(name)
            log.info("Hot-reloaded plugin %s", name)
        except Exception as exc:  # noqa: BLE001
            record.state = PluginState.ERROR
            record.error = str(exc)
            log.exception("Failed to reload %s: %s", name, exc)
            raise

    def enable_all(self) -> None:
        for rec in self.registry.all():
            if rec.state != PluginState.ENABLED:
                try:
                    self.enable(rec.metadata.name)
                except PluginError as exc:
                    log.error("Could not enable %s: %s", rec.metadata.name, exc)

    def disable_all(self) -> None:
        for rec in self.registry.all():
            if rec.enabled:
                try:
                    self.disable(rec.metadata.name)
                except PluginError as exc:
                    log.error("Could not disable %s: %s", rec.metadata.name, exc)

    def status(self) -> list[dict[str, Any]]:
        return [
            {
                "name": r.metadata.name,
                "version": r.metadata.version,
                "state": r.state,
                "enabled": r.enabled,
                "error": r.error,
                "file": r.file_path,
            }
            for r in self.registry.all()
        ]
