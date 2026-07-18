"""Profiler — scoped timing and call statistics."""

from __future__ import annotations

import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional


@dataclass
class ProfileScope:
    """A single profiling scope."""

    name: str
    duration: float = 0.0
    calls: int = 0
    min_duration: float = float("inf")
    max_duration: float = 0.0
    children: dict[str, "ProfileScope"] = field(default_factory=dict)
    parent: Optional["ProfileScope"] = None

    def average(self) -> float:
        return self.duration / self.calls if self.calls > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration": self.duration,
            "calls": self.calls,
            "average": self.average(),
            "min": self.min_duration if self.min_duration != float("inf") else 0.0,
            "max": self.max_duration,
            "children": {k: v.to_dict() for k, v in self.children.items()},
        }


class Profiler:
    """A hierarchical profiler."""

    def __init__(self) -> None:
        self._root = ProfileScope(name="root")
        self._current: list[ProfileScope] = [self._root]
        self._lock = threading.RLock()
        self._enabled = True

    def enable(self) -> None:
        self._enabled = True

    def disable(self) -> None:
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @contextmanager
    def scope(self, name: str) -> Iterator[ProfileScope]:
        """Context manager that times a block of code."""
        if not self._enabled:
            # Return a no-op scope
            noop = ProfileScope(name=name)
            yield noop
            return
        with self._lock:
            parent = self._current[-1]
            if name not in parent.children:
                scope = ProfileScope(name=name, parent=parent)
                parent.children[name] = scope
            else:
                scope = parent.children[name]
            self._current.append(scope)
        start = time.perf_counter()
        try:
            yield scope
        finally:
            elapsed = time.perf_counter() - start
            with self._lock:
                scope.duration += elapsed
                scope.calls += 1
                if elapsed < scope.min_duration:
                    scope.min_duration = elapsed
                if elapsed > scope.max_duration:
                    scope.max_duration = elapsed
                self._current.pop()

    def reset(self) -> None:
        with self._lock:
            self._root = ProfileScope(name="root")
            self._current = [self._root]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return self._root.to_dict()

    def top_slowest(self, n: int = 10) -> list[tuple[str, float, int]]:
        """Return the top N slowest scopes by total duration."""
        flat: list[tuple[str, float, int]] = []

        def walk(scope: ProfileScope, path: str = "") -> None:
            for name, child in scope.children.items():
                full = f"{path}{name}" if path else name
                flat.append((full, child.duration, child.calls))
                walk(child, full + "/")

        with self._lock:
            walk(self._root)
        flat.sort(key=lambda x: x[1], reverse=True)
        return flat[:n]

    def print_report(self, n: int = 20) -> str:
        """Return a human-readable profiling report."""
        lines = ["Profiler Report:", "Name                              Duration    Calls   Average"]
        for name, dur, calls in self.top_slowest(n):
            avg = dur / calls if calls > 0 else 0.0
            lines.append(f"{name:35s} {dur*1000:8.2f}ms {calls:6d}  {avg*1000:8.2f}ms")
        return "\n".join(lines)


# Global profiler instance
profiler = Profiler()
