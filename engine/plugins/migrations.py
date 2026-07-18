"""Plugin migrations — versioned save data migration for plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from engine.core.logging import get_logger


log = get_logger("plugins.migrations")


@dataclass
class Migration:
    """A migration from one plugin version to the next."""

    from_version: str
    to_version: str
    migrate_fn: Callable[[dict], dict]
    description: str = ""


class PluginMigrator:
    """Manages plugin save data migrations."""

    def __init__(self) -> None:
        # plugin_name -> list of migrations
        self._migrations: dict[str, list[Migration]] = {}

    def register(self, plugin_name: str, migration: Migration) -> None:
        self._migrations.setdefault(plugin_name, []).append(migration)
        # Keep sorted by from_version
        self._migrations[plugin_name].sort(key=lambda m: m.from_version)

    def migration(self, plugin_name: str, from_version: str, to_version: str,
                  description: str = "") -> Callable[[Callable[[dict], dict]], Callable]:
        """Decorator to register a migration."""
        def decorator(fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
            self.register(plugin_name, Migration(
                from_version=from_version,
                to_version=to_version,
                migrate_fn=fn,
                description=description,
            ))
            return fn
        return decorator

    def migrate(self, plugin_name: str, data: dict,
                target_version: Optional[str] = None) -> dict:
        """Migrate plugin data to the target version (or latest)."""
        migrations = self._migrations.get(plugin_name, [])
        if not migrations:
            return data
        current_version = data.get("version", "0.0.0")
        if target_version is None:
            target_version = migrations[-1].to_version
        if current_version == target_version:
            return data
        log.info("Migrating %s save data from %s to %s",
                 plugin_name, current_version, target_version)
        for migration in migrations:
            if migration.from_version == current_version:
                try:
                    data = migration.migrate_fn(data)
                    data["version"] = migration.to_version
                    current_version = migration.to_version
                    log.debug("Migrated %s: %s -> %s (%s)",
                              plugin_name, migration.from_version,
                              migration.to_version, migration.description)
                except Exception as exc:  # noqa: BLE001
                    log.error("Migration failed for %s (%s -> %s): %s",
                              plugin_name, migration.from_version,
                              migration.to_version, exc)
                    return data
                if current_version == target_version:
                    break
        return data

    def migrations_for(self, plugin_name: str) -> list[Migration]:
        return list(self._migrations.get(plugin_name, []))

    def latest_version(self, plugin_name: str) -> Optional[str]:
        migrations = self._migrations.get(plugin_name, [])
        if not migrations:
            return None
        return migrations[-1].to_version
