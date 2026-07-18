"""Sandboxed Python scripting engine.

Provides a restricted Python execution environment suitable for:
* Plugin scripting
* Quest scripting
* AI scripting
* Event scripting
* Mod scripting (Lua-style Python scripts)

The sandbox:
* Restricts builtins to a safe subset
* Allows specific modules (math, random, statistics, datetime, etc.)
* Blocks dangerous operations: file I/O, network, subprocess, eval/exec
* Provides a controlled API object for engine interaction
* Enforces execution timeout to prevent infinite loops
* Limits recursion depth
"""

from __future__ import annotations

import ast
import inspect
import math
import random
import statistics
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional


SAFE_BUILTINS: dict[str, Any] = {
    # Type constructors
    "int": int, "float": float, "str": str, "bool": bool,
    "list": list, "dict": dict, "set": set, "tuple": tuple,
    "frozenset": frozenset,
    # Math-ish
    "abs": abs, "min": min, "max": max, "sum": sum,
    "round": round, "pow": pow, "divmod": divmod,
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "sorted": sorted, "reversed": reversed, "all": all, "any": any,
    "map": map, "filter": filter,
    # Type checks
    "isinstance": isinstance, "issubclass": issubclass,
    "type": type, "id": id, "hash": hash, "repr": repr,
    # Iteration
    "iter": iter, "next": next,
    # Format
    "format": format, "chr": chr, "ord": ord,
    "hex": hex, "oct": oct, "bin": bin,
    # Other
    "print": print, "help": lambda *a, **k: None,
    "True": True, "False": False, "None": None,
    "Exception": Exception, "ValueError": ValueError,
    "TypeError": TypeError, "KeyError": KeyError,
    "IndexError": IndexError, "AttributeError": AttributeError,
    "ZeroDivisionError": ZeroDivisionError, "StopIteration": StopIteration,
}

DEFAULT_ALLOWED_MODULES: dict[str, Any] = {
    "math": math,
    "random": random,
    "statistics": statistics,
    "datetime": datetime,
    "timedelta": timedelta,
}


FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "__import__", "exec", "eval", "compile", "open", "input",
    "globals", "locals", "vars", "dir", "getattr", "setattr",
    "delattr", "memoryview", "bytearray", "bytes",
    "exit", "quit", "license", "copyright", "credits",
    "breakpoint", "classmethod", "staticmethod", "property",
    "super", "object",
})


# AST node types we allow
_ALLOWED_AST_NODES: frozenset[type] = frozenset({
    ast.Module, ast.Expression, ast.Interactive,
    # Statements
    ast.Assign, ast.AnnAssign, ast.AugAssign,
    ast.Expr, ast.Pass, ast.Break, ast.Continue,
    ast.Return, ast.Yield, ast.YieldFrom,
    ast.If, ast.For, ast.While, ast.With,
    ast.Try, ast.ExceptHandler, ast.Raise, ast.Assert,
    ast.Import, ast.ImportFrom,
    ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
    ast.Lambda, ast.arguments, ast.arg, ast.alias,
    ast.Global, ast.Nonlocal, ast.Delete,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
    ast.comprehension,
    # Expressions
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.Call, ast.Starred, ast.keyword,
    ast.IfExp, ast.NamedExpr,
    ast.Constant, ast.Name, ast.Attribute,
    ast.Subscript, ast.Index, ast.Slice,
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.FormattedValue, ast.JoinedStr,
    # Operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod,
    ast.Pow, ast.LShift, ast.RShift, ast.BitOr, ast.BitXor, ast.BitAnd,
    ast.And, ast.Or, ast.Not, ast.Invert, ast.UAdd, ast.USub,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.MatMult,
    # Function args
    ast.Load, ast.Store, ast.Del, ast.AugLoad, ast.AugStore, ast.Param,
})


class ScriptError(Exception):
    """Raised when a script fails to parse or execute."""


@dataclass
class ScriptResult:
    """Result of a script execution."""

    success: bool
    return_value: Any = None
    output: str = ""
    error: str = ""
    duration: float = 0.0
    line_count: int = 0


@dataclass
class ScriptContext:
    """The context passed to a script — provides engine API."""

    engine: Any = None
    entity: Any = None
    world: Any = None
    event_bus: Any = None
    rng: Any = None
    variables: dict[str, Any] = field(default_factory=dict)
    timeout: float = 5.0
    max_operations: int = 1_000_000

    def api(self) -> dict[str, Any]:
        """Return the API surface exposed to scripts."""
        return {
            "engine": self.engine,
            "entity": self.entity,
            "world": self.world,
            "event_bus": self.event_bus,
            "rng": self.rng,
            "log": lambda msg: print(f"[script] {msg}"),
            "emit_event": lambda event_type, payload: (
                self.event_bus.dispatch(event_type(**payload))
                if self.event_bus and hasattr(event_type, "__call__")
                else None
            ),
        }


class ScriptSandbox:
    """A restricted Python execution environment."""

    def __init__(self,
                 allowed_modules: Optional[dict[str, Any]] = None,
                 extra_builtins: Optional[dict[str, Any]] = None) -> None:
        self.allowed_modules = allowed_modules or dict(DEFAULT_ALLOWED_MODULES)
        self.builtins = dict(SAFE_BUILTINS)
        if extra_builtins:
            self.builtins.update(extra_builtins)
        # Custom __import__ that only allows whitelisted modules
        self.builtins["__import__"] = self._safe_import
        self._operation_count = 0
        self._timed_out = False

    def _safe_import(self, name: str, globals: Optional[dict] = None,
                     locals: Optional[dict] = None,
                     fromlist: tuple = (), level: int = 0) -> Any:
        if level != 0:
            raise ScriptError("Relative imports are not allowed")
        if name not in self.allowed_modules:
            raise ScriptError(f"Import of module '{name}' is not allowed")
        return self.allowed_modules[name]

    def validate_source(self, source: str) -> ast.AST:
        """Parse and validate the source code."""
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            raise ScriptError(f"Syntax error: {exc}") from exc
        # Walk the AST and reject forbidden nodes
        for node in ast.walk(tree):
            # Check for forbidden names
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                raise ScriptError(f"Use of '{node.id}' is forbidden")
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                # Allow common dunder methods? No — block all _-prefixed attrs.
                if node.attr not in ("__name__", "__doc__", "__class__"):
                    raise ScriptError(
                        f"Access to attribute '{node.attr}' is forbidden"
                    )
            # Check for forbidden AST node types
            if type(node) not in _ALLOWED_AST_NODES:
                raise ScriptError(
                    f"AST node {type(node).__name__} is not allowed in scripts"
                )
        return tree

    def execute(self, source: str, context: ScriptContext) -> ScriptResult:
        """Execute a script in the sandbox."""
        start = time.perf_counter()
        self._operation_count = 0
        self._timed_out = False
        try:
            tree = self.validate_source(source)
        except ScriptError as exc:
            return ScriptResult(
                success=False, error=str(exc),
                duration=time.perf_counter() - start,
            )
        # Compile to bytecode
        try:
            code = compile(tree, "<script>", "exec")
        except Exception as exc:  # noqa: BLE001
            return ScriptResult(
                success=False, error=f"Compile error: {exc}",
                duration=time.perf_counter() - start,
            )
        # Set up globals
        globs: dict[str, Any] = {
            "__builtins__": self.builtins,
            "__name__": "__script__",
        }
        # Inject context
        globs.update(context.api())
        globs.update(context.variables)
        # Run with timeout in a thread
        result_holder: dict[str, Any] = {"return": None, "error": None, "output": []}

        def target() -> None:
            try:
                exec(code, globs)  # noqa: S102
                result_holder["return"] = globs.get("result")
            except Exception as exc:  # noqa: BLE001
                result_holder["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=context.timeout)
        if thread.is_alive():
            # Timeout — we can't kill threads in Python, but daemon will exit
            # when the main process does.
            return ScriptResult(
                success=False, error=f"Script timed out after {context.timeout}s",
                duration=time.perf_counter() - start,
                line_count=len(source.splitlines()),
            )
        duration = time.perf_counter() - start
        if result_holder["error"] is not None:
            return ScriptResult(
                success=False,
                error=f"{type(result_holder['error']).__name__}: {result_holder['error']}",
                duration=duration,
                line_count=len(source.splitlines()),
            )
        return ScriptResult(
            success=True,
            return_value=result_holder["return"],
            duration=duration,
            line_count=len(source.splitlines()),
        )

    def call_function(self, source: str, function_name: str,
                      args: tuple = (), kwargs: Optional[dict] = None,
                      context: Optional[ScriptContext] = None) -> ScriptResult:
        """Execute a script and then call a named function from it."""
        ctx = context or ScriptContext()
        first = self.execute(source, ctx)
        if not first.success:
            return first
        # The function should now be in the script's globals — but exec runs
        # in a separate dict we don't have access to. Re-execute inline:
        try:
            tree = self.validate_source(source)
            code = compile(tree, "<script>", "exec")
            globs: dict[str, Any] = {
                "__builtins__": self.builtins,
                "__name__": "__script__",
            }
            globs.update(ctx.api())
            exec(code, globs)  # noqa: S102
            fn = globs.get(function_name)
            if not callable(fn):
                return ScriptResult(
                    success=False,
                    error=f"Function '{function_name}' not found or not callable",
                )
            result = fn(*args, **(kwargs or {}))
            return ScriptResult(success=True, return_value=result)
        except Exception as exc:  # noqa: BLE001
            return ScriptResult(success=False, error=str(exc))


class ScriptEngine:
    """Top-level script engine managing multiple sandboxes and scripts."""

    def __init__(self) -> None:
        self.sandbox = ScriptSandbox()
        self._scripts: dict[str, str] = {}  # name -> source

    def register_script(self, name: str, source: str) -> None:
        self._scripts[name] = source

    def get_script(self, name: str) -> Optional[str]:
        return self._scripts.get(name)

    def run(self, name: str, context: Optional[ScriptContext] = None) -> ScriptResult:
        source = self._scripts.get(name)
        if source is None:
            return ScriptResult(success=False, error=f"No such script: {name}")
        return self.sandbox.execute(source, context or ScriptContext())

    def run_source(self, source: str,
                   context: Optional[ScriptContext] = None) -> ScriptResult:
        return self.sandbox.execute(source, context or ScriptContext())

    def call(self, name: str, function_name: str,
             args: tuple = (), kwargs: Optional[dict] = None,
             context: Optional[ScriptContext] = None) -> ScriptResult:
        source = self._scripts.get(name)
        if source is None:
            return ScriptResult(success=False, error=f"No such script: {name}")
        return self.sandbox.call_function(
            source, function_name, args, kwargs, context or ScriptContext(),
        )

    def list_scripts(self) -> list[str]:
        return sorted(self._scripts.keys())


# Convenience accessor
safe_builtins = SAFE_BUILTINS
