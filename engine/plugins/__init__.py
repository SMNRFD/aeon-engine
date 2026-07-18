"""Plugin system — dynamic loading, hot reload, lifecycle, dependencies.

Each plugin is a Python module (or package) that exports a `Plugin` subclass.
The `PluginManager` handles discovery, dependency resolution, versioning
checks, lifecycle hooks, and sandboxed execution.
"""

from engine.plugins.base import Plugin, PluginMetadata
from engine.plugins.registry import PluginRegistry
from engine.plugins.manager import PluginManager

__all__ = ["Plugin", "PluginMetadata", "PluginRegistry", "PluginManager"]
