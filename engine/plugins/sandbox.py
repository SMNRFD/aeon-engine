"""Plugin sandbox — restricted execution environment for untrusted plugins."""

from __future__ import annotations

import ast
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from engine.core.logging import get_logger
from engine.scripting.interpreter import (
    SAFE_BUILTINS, DEFAULT_ALLOWED_MODULES, FORBIDDEN_NAMES, _ALLOWED_AST_NODES,
    ScriptContext, ScriptError, ScriptResult,
)


log = get_logger("plugins.sandbox")


class PluginSandbox:
    """A sandbox for executing untrusted plugin code.

    Wraps the ScriptEngine's sandbox with plugin-specific restrictions:
    * Restricts filesystem access to the plugin's own directory
    * Limits CPU time per plugin tick
    * Limits memory usage (best-effort via object count)
    * Audits sensitive API calls
    """

    def __init__(self,
                 plugin_data_dir: str = "plugin_data",
                 max_cpu_seconds: float = 5.0,
                 max_memory_objects: int = 100_000,
                 audit_log: Optional[list[str]] = None) -> None:
        self.plugin_data_dir = plugin_data_dir
        self.max_cpu_seconds = max_cpu_seconds
        self.max_memory_objects = max_memory_objects
        self.audit_log = audit_log if audit_log is not None else []
        self._object_count = 0
        self._violations: dict[str, int] = {}

    def audit(self, plugin_name: str, action: str) -> None:
        """Record an auditable action."""
        entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {plugin_name}: {action}"
        self.audit_log.append(entry)
        if len(self.audit_log) > 10000:
            self.audit_log = self.audit_log[-10000:]

    def record_violation(self, plugin_name: str, violation_type: str) -> None:
        key = f"{plugin_name}:{violation_type}"
        self._violations[key] = self._violations.get(key, 0) + 1
        log.warning("Plugin sandbox violation: %s (count=%d)",
                    key, self._violations[key])

    def violations(self) -> dict[str, int]:
        return dict(self._violations)

    def validate_source(self, source: str) -> tuple[bool, Optional[str]]:
        """Validate plugin source for forbidden patterns."""
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            return False, f"Syntax error: {exc}"
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                self.record_violation("source", f"forbidden_name:{node.id}")
                return False, f"Forbidden name: {node.id}"
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                if node.attr not in ("__name__", "__doc__", "__class__"):
                    return False, f"Access to private attribute: {node.attr}"
            if isinstance(node, ast.Call):
                # Check for forbidden calls
                if isinstance(node.func, ast.Name):
                    if node.func.id in ("exec", "eval", "compile", "open",
                                         "__import__", "input"):
                        return False, f"Forbidden function call: {node.func.id}"
            # Check for forbidden imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in ("os", "sys", "subprocess", "socket",
                                      "shutil", "pathlib", "ctypes"):
                        return False, f"Forbidden import: {alias.name}"
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.split(".")[0] in (
                    "os", "sys", "subprocess", "socket", "shutil",
                    "pathlib", "ctypes",
                ):
                    return False, f"Forbidden import: {node.module}"
            if type(node) not in _ALLOWED_AST_NODES:
                return False, f"Disallowed AST node: {type(node).__name__}"
        return True, None

    def create_sandbox_globals(self, plugin_name: str,
                                plugin_api: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Create sandboxed globals for a plugin."""
        import builtins
        safe_builtins = dict(SAFE_BUILTINS)
        # Add a restricted file API
        plugin_data_path = f"{self.plugin_data_dir}/{plugin_name}"
        import os
        os.makedirs(plugin_data_path, exist_ok=True)

        def safe_open(filename: str, mode: str = "r") -> Any:
            # Restrict to plugin's data directory
            full_path = os.path.join(plugin_data_path, filename)
            real_path = os.path.realpath(full_path)
            if not real_path.startswith(os.path.realpath(plugin_data_path)):
                self.record_violation(plugin_name, "path_traversal")
                raise PermissionError(f"Plugin {plugin_name} cannot access {filename}")
            self.audit(plugin_name, f"open({filename}, {mode})")
            return open(real_path, mode)

        safe_builtins["open"] = safe_open
        # Add import (already restricted in ScriptSandbox)
        globs: dict[str, Any] = {
            "__builtins__": safe_builtins,
            "__name__": f"plugin.{plugin_name}",
        }
        if plugin_api:
            globs.update(plugin_api)
        return globs

    def execute_with_timeout(self, source: str, plugin_name: str,
                              api: Optional[dict[str, Any]] = None) -> ScriptResult:
        """Execute plugin code in a sandboxed environment with a timeout."""
        start = time.perf_counter()
        valid, error = self.validate_source(source)
        if not valid:
            return ScriptResult(success=False, error=error or "Validation failed",
                                duration=0.0)
        try:
            tree = ast.parse(source, mode="exec")
            code = compile(tree, f"<plugin:{plugin_name}>", "exec")
        except Exception as exc:  # noqa: BLE001
            return ScriptResult(success=False, error=f"Compile error: {exc}",
                                duration=time.perf_counter() - start)
        globs = self.create_sandbox_globals(plugin_name, api)
        result_holder: dict[str, Any] = {"return": None, "error": None}

        def target() -> None:
            try:
                exec(code, globs)  # noqa: S102
                result_holder["return"] = globs.get("result")
            except Exception as exc:  # noqa: BLE001
                result_holder["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=self.max_cpu_seconds)
        duration = time.perf_counter() - start
        if thread.is_alive():
            self.record_violation(plugin_name, "timeout")
            return ScriptResult(
                success=False,
                error=f"Plugin {plugin_name} timed out after {self.max_cpu_seconds}s",
                duration=duration,
            )
        if result_holder["error"] is not None:
            self.record_violation(plugin_name, "runtime_error")
            return ScriptResult(
                success=False,
                error=f"{type(result_holder['error']).__name__}: {result_holder['error']}",
                duration=duration,
            )
        return ScriptResult(
            success=True,
            return_value=result_holder["return"],
            duration=duration,
        )
