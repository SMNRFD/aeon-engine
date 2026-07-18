"""Tests for the plugin system."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from engine.plugins.base import Plugin, PluginMetadata, parse_version, version_satisfies
from engine.plugins.manager import PluginManager, PluginError


class DummyPlugin(Plugin):
    metadata = PluginMetadata(
        name="dummy", version="0.2.0", description="A test plugin.",
    )
    def __init__(self):
        super().__init__()
        self.loaded = False
        self.enabled = False
    def on_load(self, engine):
        self.loaded = True
    def on_enable(self, engine):
        self.enabled = True
    def on_disable(self, engine):
        self.enabled = False


def test_version_parsing():
    assert parse_version("1.0") == (1, 0, 0)
    assert parse_version("2.3.1") == (2, 3, 1)
    assert parse_version("1.0-rc1") == (1, 0, 0)


def test_version_satisfies():
    assert version_satisfies("1.0.0", ">=1.0")
    assert version_satisfies("1.5.0", ">=1.0")
    assert not version_satisfies("0.9.0", ">=1.0")
    assert version_satisfies("2.0.0", "==2.0.0")
    assert not version_satisfies("2.0.1", "==2.0.0")
    assert version_satisfies("1.5.0", "!=1.0.0")


def test_plugin_lifecycle():
    plugin = DummyPlugin()
    # Simulate lifecycle
    class FakeEngine: pass
    engine = FakeEngine()
    plugin.on_load(engine)
    assert plugin.loaded
    plugin.on_enable(engine)
    assert plugin.enabled
    plugin.on_disable(engine)
    assert not plugin.enabled


def test_dependency_resolution():
    # Create two plugins where one depends on the other
    class CorePlugin(Plugin):
        metadata = PluginMetadata(name="core_dep", version="1.0.0",
                                   description="core", load_order=10)

    class DependentPlugin(Plugin):
        metadata = PluginMetadata(name="dependent", version="0.1.0",
                                   description="dependent",
                                   dependencies=["core_dep>=1.0"],
                                   load_order=20)

    from engine.plugins.registry import PluginRegistry, PluginRecord
    registry = PluginRegistry()
    registry.register(PluginRecord(
        metadata=CorePlugin.metadata, plugin=CorePlugin(),
        module_path="core_dep", file_path="/tmp/core_dep.py",
    ))
    registry.register(PluginRecord(
        metadata=DependentPlugin.metadata, plugin=DependentPlugin(),
        module_path="dependent", file_path="/tmp/dependent.py",
    ))

    # Topological sort
    manager = PluginManager(engine=None, plugin_dirs=[])
    manager.registry = registry
    order = manager.resolve_load_order()
    names = [r.metadata.name for r in order]
    assert names.index("core_dep") < names.index("dependent")


def test_circular_dependency_detected():
    from engine.plugins.registry import PluginRegistry, PluginRecord

    class A(Plugin):
        metadata = PluginMetadata(name="a", version="1.0", dependencies=["b"])
    class B(Plugin):
        metadata = PluginMetadata(name="b", version="1.0", dependencies=["a"])

    registry = PluginRegistry()
    registry.register(PluginRecord(metadata=A.metadata, plugin=A(),
                                    module_path="a", file_path="a"))
    registry.register(PluginRecord(metadata=B.metadata, plugin=B(),
                                    module_path="b", file_path="b"))
    manager = PluginManager(engine=None, plugin_dirs=[])
    manager.registry = registry
    with pytest.raises(PluginError, match="Circular"):
        manager.resolve_load_order()
