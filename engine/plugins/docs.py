"""Plugin documentation generator."""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from engine.core.logging import get_logger
from engine.plugins.base import PluginMetadata


log = get_logger("plugins.docs")


@dataclass
class PluginDoc:
    """Generated plugin documentation."""

    plugin_name: str
    version: str
    description: str = ""
    author: str = ""
    license: str = ""
    api_version: str = ""
    dependencies: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    classes: list[dict[str, Any]] = field(default_factory=list)
    functions: list[dict[str, Any]] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render the documentation as Markdown."""
        lines = [
            f"# {self.plugin_name}",
            "",
            f"**Version:** {self.version}",
            f"**Description:** {self.description}",
            "",
        ]
        if self.author:
            lines.append(f"**Author:** {self.author}")
        if self.license:
            lines.append(f"**License:** {self.license}")
        if self.api_version:
            lines.append(f"**API Version:** {self.api_version}")
        lines.append("")
        if self.dependencies:
            lines.append("## Dependencies")
            for dep in self.dependencies:
                lines.append(f"- {dep}")
            lines.append("")
        if self.conflicts:
            lines.append("## Conflicts")
            for c in self.conflicts:
                lines.append(f"- {c}")
            lines.append("")
        if self.permissions:
            lines.append("## Permissions")
            for perm in self.permissions:
                lines.append(f"- `{perm}`")
            lines.append("")
        if self.commands:
            lines.append("## Commands")
            lines.append("| Command | Description | Usage |")
            lines.append("|---------|-------------|-------|")
            for cmd in self.commands:
                lines.append(f"| `{cmd.get('name', '')}` | {cmd.get('description', '')} | `{cmd.get('usage', '')}` |")
            lines.append("")
        if self.events:
            lines.append("## Events")
            for ev in self.events:
                lines.append(f"- **{ev.get('name', '')}**: {ev.get('description', '')}")
            lines.append("")
        if self.hooks:
            lines.append("## Lifecycle Hooks")
            for hook in self.hooks:
                lines.append(f"- `{hook}`")
            lines.append("")
        if self.classes:
            lines.append("## Classes")
            for cls in self.classes:
                lines.append(f"### {cls.get('name', '')}")
                if cls.get("docstring"):
                    lines.append(cls["docstring"])
                    lines.append("")
                if cls.get("methods"):
                    lines.append("**Methods:**")
                    for m in cls["methods"]:
                        sig = m.get("signature", "")
                        doc = m.get("docstring", "")
                        lines.append(f"- `{sig}` — {doc}")
                    lines.append("")
        if self.functions:
            lines.append("## Functions")
            for fn in self.functions:
                sig = fn.get("signature", "")
                doc = fn.get("docstring", "")
                lines.append(f"- `{sig}` — {doc}")
            lines.append("")
        if self.examples:
            lines.append("## Examples")
            for ex in self.examples:
                lines.append(f"```python\n{ex}\n```")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name, "version": self.version,
            "description": self.description, "author": self.author,
            "license": self.license, "api_version": self.api_version,
            "dependencies": list(self.dependencies),
            "conflicts": list(self.conflicts),
            "permissions": list(self.permissions),
            "commands": list(self.commands),
            "events": list(self.events),
            "hooks": list(self.hooks),
            "classes": list(self.classes),
            "functions": list(self.functions),
            "examples": list(self.examples),
        }


class PluginDocGenerator:
    """Generates documentation for plugins."""

    def generate(self, plugin_path: Path,
                 metadata: Optional[PluginMetadata] = None) -> PluginDoc:
        """Generate documentation for a plugin."""
        plugin_path = Path(plugin_path)
        if plugin_path.is_dir():
            plugin_file = plugin_path / "plugin.py"
        else:
            plugin_file = plugin_path
        if not plugin_file.exists():
            return PluginDoc(plugin_name=plugin_path.stem, version="0.0.0",
                             description="Plugin file not found")
        source = plugin_file.read_text(encoding="utf-8")
        # Parse AST
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError:
            return PluginDoc(plugin_name=plugin_path.stem, version="0.0.0",
                             description="Could not parse plugin source")
        # Extract docstrings and signatures
        classes: list[dict[str, Any]] = []
        functions: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cls_info: dict[str, Any] = {
                    "name": node.name,
                    "docstring": ast.get_docstring(node) or "",
                    "methods": [],
                }
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [a.arg for a in item.args.args]
                        cls_info["methods"].append({
                            "name": item.name,
                            "signature": f"{item.name}({', '.join(args)})",
                            "docstring": ast.get_docstring(item) or "",
                        })
                classes.append(cls_info)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Module-level function
                args = [a.arg for a in node.args.args]
                functions.append({
                    "name": node.name,
                    "signature": f"{node.name}({', '.join(args)})",
                    "docstring": ast.get_docstring(node) or "",
                })
        # Build doc
        doc = PluginDoc(
            plugin_name=metadata.name if metadata else plugin_path.stem,
            version=metadata.version if metadata else "0.0.0",
            description=metadata.description if metadata else "",
            author=metadata.author if metadata else "",
            license=metadata.license if metadata else "",
            api_version=metadata.api_version if metadata else "",
            dependencies=list(metadata.dependencies) if metadata else [],
            conflicts=list(metadata.conflicts) if metadata else [],
            permissions=list(metadata.permissions) if metadata else [],
            classes=classes,
            functions=functions,
            hooks=["on_load", "on_enable", "on_disable",
                   "on_unload", "on_reload"],
        )
        return doc

    def save_markdown(self, doc: PluginDoc, output_path: Path) -> None:
        """Save documentation as Markdown."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(doc.to_markdown(), encoding="utf-8")

    def save_json(self, doc: PluginDoc, output_path: Path) -> None:
        """Save documentation as JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(doc.to_dict(), indent=2),
            encoding="utf-8",
        )
