"""Plugin installer — install, uninstall, download, verify."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Optional

from engine.core.logging import get_logger
from engine.plugins.base import PluginMetadata
from engine.plugins.manager import PluginManager


log = get_logger("plugins.installer")


class PluginInstaller:
    """Installs and uninstalls plugins from local or remote sources."""

    def __init__(self, manager: PluginManager,
                 plugins_dir: str = "plugins") -> None:
        self.manager = manager
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)

    def install_from_directory(self, source_dir: Path,
                                overwrite: bool = False) -> Optional[str]:
        """Install a plugin from a local directory."""
        source_dir = Path(source_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            log.error("Source directory does not exist: %s", source_dir)
            return None
        plugin_file = source_dir / "plugin.py"
        if not plugin_file.exists():
            log.error("No plugin.py found in %s", source_dir)
            return None
        dest_dir = self.plugins_dir / source_dir.name
        if dest_dir.exists():
            if not overwrite:
                log.error("Plugin already installed: %s", dest_dir)
                return None
            shutil.rmtree(dest_dir)
        shutil.copytree(source_dir, dest_dir)
        log.info("Installed plugin from %s to %s", source_dir, dest_dir)
        return dest_dir.name

    def install_from_zip(self, zip_path: Path,
                         overwrite: bool = False) -> Optional[str]:
        """Install a plugin from a ZIP archive."""
        import zipfile
        zip_path = Path(zip_path)
        if not zip_path.exists():
            log.error("ZIP file does not exist: %s", zip_path)
            return None
        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)
            # Find the plugin directory (one containing plugin.py)
            for entry in Path(tmp_dir).iterdir():
                if entry.is_dir() and (entry / "plugin.py").exists():
                    return self.install_from_directory(entry, overwrite)
            log.error("No plugin.py found in ZIP archive")
            return None

    def install_from_url(self, url: str,
                         overwrite: bool = False,
                         expected_hash: Optional[str] = None) -> Optional[str]:
        """Download and install a plugin from a URL."""
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                log.info("Downloading plugin from %s", url)
                urllib.request.urlretrieve(url, tmp_path)
                # Verify hash if provided
                if expected_hash:
                    actual_hash = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
                    if actual_hash != expected_hash:
                        log.error("Hash mismatch: expected %s, got %s",
                                  expected_hash, actual_hash)
                        return None
                return self.install_from_zip(tmp_path, overwrite)
            except Exception as exc:  # noqa: BLE001
                log.error("Failed to download plugin: %s", exc)
                return None
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

    def uninstall(self, plugin_name: str,
                  remove_files: bool = True) -> bool:
        """Uninstall a plugin by name."""
        record = self.manager.registry.get(plugin_name)
        if record is None:
            log.error("Plugin not found: %s", plugin_name)
            return False
        # Disable and unload
        if record.enabled:
            try:
                self.manager.disable(plugin_name)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to disable %s: %s", plugin_name, exc)
        try:
            self.manager.unload(plugin_name)
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to unload %s: %s", plugin_name, exc)
        # Remove from registry
        self.manager.registry.unregister(plugin_name)
        # Remove files
        if remove_files:
            plugin_path = Path(record.file_path).parent
            if plugin_path.exists() and plugin_path.is_dir():
                try:
                    shutil.rmtree(plugin_path)
                    log.info("Removed plugin files: %s", plugin_path)
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed to remove plugin files: %s", exc)
                    return False
        log.info("Uninstalled plugin: %s", plugin_name)
        return True

    def list_installed(self) -> list[dict[str, Any]]:
        """List all installed plugins."""
        return [
            {
                "name": r.metadata.name,
                "version": r.metadata.version,
                "state": r.state,
                "path": r.file_path,
            }
            for r in self.manager.registry.all()
        ]

    def verify_plugin(self, plugin_name: str) -> dict[str, Any]:
        """Verify a plugin's integrity."""
        record = self.manager.registry.get(plugin_name)
        if record is None:
            return {"valid": False, "error": "Plugin not found"}
        plugin_path = Path(record.file_path)
        if not plugin_path.exists():
            return {"valid": False, "error": "Plugin file missing"}
        return {
            "valid": True,
            "name": record.metadata.name,
            "version": record.metadata.version,
            "path": str(plugin_path),
            "size_bytes": plugin_path.stat().st_size,
        }
