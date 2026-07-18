"""Plugin validation — checks plugin metadata, structure, and dependencies."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

from engine.core.logging import get_logger
from engine.plugins.base import PluginMetadata, parse_version, version_satisfies


log = get_logger("plugins.validation")


class ValidationLevel(IntEnum):
    OK = 0
    WARNING = 1
    ERROR = 2


@dataclass
class ValidationResult:
    """Result of plugin validation."""

    plugin_name: str
    level: ValidationLevel = ValidationLevel.OK
    messages: list[tuple[ValidationLevel, str]] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.level < ValidationLevel.ERROR

    @property
    def has_warnings(self) -> bool:
        return any(lvl == ValidationLevel.WARNING for lvl, _ in self.messages)

    def add(self, level: ValidationLevel, message: str) -> None:
        self.messages.append((level, message))
        if level.value > self.level.value:
            self.level = level

    def __str__(self) -> str:
        lines = [f"Plugin {self.plugin_name}:"]
        for level, msg in self.messages:
            prefix = {ValidationLevel.OK: "OK", ValidationLevel.WARNING: "WARN",
                      ValidationLevel.ERROR: "ERROR"}[level]
            lines.append(f"  [{prefix}] {msg}")
        return "\n".join(lines)


class PluginValidator:
    """Validates plugin metadata and source code."""

    # Required metadata fields
    REQUIRED_METADATA_FIELDS = ("name", "version", "description")

    # Valid name pattern
    NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

    def validate_metadata(self, metadata: PluginMetadata) -> ValidationResult:
        """Validate a plugin's metadata."""
        result = ValidationResult(plugin_name=metadata.name)
        # Check required fields
        for field_name in self.REQUIRED_METADATA_FIELDS:
            value = getattr(metadata, field_name, "")
            if not value:
                result.add(ValidationLevel.ERROR, f"Missing required field: {field_name}")
        # Check name format
        if metadata.name and not self.NAME_PATTERN.match(metadata.name):
            result.add(ValidationLevel.WARNING,
                       f"Plugin name '{metadata.name}' should match {self.NAME_PATTERN.pattern}")
        # Check version format
        try:
            parse_version(metadata.version)
        except ValueError as exc:
            result.add(ValidationLevel.ERROR, f"Invalid version: {exc}")
        # Check API version
        try:
            parse_version(metadata.api_version)
        except ValueError as exc:
            result.add(ValidationLevel.ERROR, f"Invalid api_version: {exc}")
        # Check dependencies format
        for dep in metadata.dependencies:
            if not self._is_valid_dependency_string(dep):
                result.add(ValidationLevel.ERROR,
                           f"Invalid dependency format: {dep!r}")
        # Check conflicts format
        for conflict in metadata.conflicts:
            if not self._is_valid_dependency_string(conflict):
                result.add(ValidationLevel.WARNING,
                           f"Invalid conflict format: {conflict!r}")
        # Check permissions
        valid_permissions = {
            "filesystem.read", "filesystem.write", "network", "process",
            "memory", "audio", "video", "input", "save", "config",
        }
        for perm in metadata.permissions:
            if perm not in valid_permissions and "*" not in perm:
                result.add(ValidationLevel.WARNING,
                           f"Unknown permission: {perm!r}")
        # Check load_order
        if not (0 <= metadata.load_order <= 10000):
            result.add(ValidationLevel.WARNING,
                       f"load_order {metadata.load_order} is outside recommended range 0-10000")
        return result

    def _is_valid_dependency_string(self, dep: str) -> bool:
        """Check if a dependency string like 'core>=1.0' is valid."""
        # Must have a name, optionally followed by operator and version
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*?)(\s*(>=|<=|==|!=|>|<)\s*(.+))?$", dep)
        if not m:
            return False
        if m.group(3):
            try:
                parse_version(m.group(4))
            except ValueError:
                return False
        return True

    def validate_source(self, source: str,
                         plugin_name: str = "<unknown>") -> ValidationResult:
        """Validate plugin source code."""
        result = ValidationResult(plugin_name=plugin_name)
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            result.add(ValidationLevel.ERROR, f"Syntax error: {exc}")
            return result
        # Find Plugin subclass
        has_plugin_class = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "Plugin":
                        has_plugin_class = True
                        break
                    if isinstance(base, ast.Attribute) and base.attr == "Plugin":
                        has_plugin_class = True
                        break
        if not has_plugin_class:
            result.add(ValidationLevel.ERROR, "No Plugin subclass found")
        # Check for forbidden patterns
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "eval":
                result.add(ValidationLevel.WARNING, "Use of eval() is discouraged")
            if isinstance(node, ast.Name) and node.id == "exec":
                result.add(ValidationLevel.WARNING, "Use of exec() is discouraged")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("os", "sys", "subprocess", "socket"):
                        result.add(ValidationLevel.WARNING,
                                   f"Import of {alias.name} may be unsafe")
        return result

    def validate_file(self, path: Path) -> ValidationResult:
        """Validate a plugin file."""
        path = Path(path)
        if not path.exists():
            result = ValidationResult(plugin_name=path.name)
            result.add(ValidationLevel.ERROR, f"File not found: {path}")
            return result
        try:
            source = path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            result = ValidationResult(plugin_name=path.name)
            result.add(ValidationLevel.ERROR, f"Could not read file: {exc}")
            return result
        return self.validate_source(source, path.stem)

    def validate_plugin_directory(self, dir_path: Path) -> ValidationResult:
        """Validate a plugin directory."""
        dir_path = Path(dir_path)
        result = ValidationResult(plugin_name=dir_path.name)
        if not dir_path.exists() or not dir_path.is_dir():
            result.add(ValidationLevel.ERROR, f"Directory not found: {dir_path}")
            return result
        plugin_file = dir_path / "plugin.py"
        if not plugin_file.exists():
            result.add(ValidationLevel.ERROR, "No plugin.py file found")
            return result
        # Validate source
        source_result = self.validate_file(plugin_file)
        result.messages.extend(source_result.messages)
        if source_result.level.value > result.level.value:
            result.level = source_result.level
        return result
