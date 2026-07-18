"""Lazy loading utilities — defer expensive computation until needed."""

from __future__ import annotations

import threading
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class LazyValue(Generic[T]):
    """A value computed on first access and cached thereafter."""

    __slots__ = ("_factory", "_value", "_lock", "_computed")

    def __init__(self, factory: Callable[[], T]) -> None:
        self._factory = factory
        self._value: Any = None
        self._lock = threading.Lock()
        self._computed = False

    def get(self) -> T:
        if self._computed:
            return self._value  # type: ignore
        with self._lock:
            if not self._computed:
                self._value = self._factory()
                self._computed = True
                # Drop the factory reference so it can be GC'd
                self._factory = None  # type: ignore
        return self._value  # type: ignore

    @property
    def is_computed(self) -> bool:
        return self._computed

    def reset(self) -> None:
        """Force recomputation on next access."""
        with self._lock:
            self._value = None
            self._computed = False

    def __repr__(self) -> str:
        if self._computed:
            return f"LazyValue({self._value!r})"
        return "LazyValue(<not computed>)"


class LazyLoader(Generic[T]):
    """A loader that defers loading of a resource until requested.

    Unlike LazyValue, the loader can be re-invoked to refresh the resource.
    """

    def __init__(self, loader: Callable[[], T]) -> None:
        self._loader = loader
        self._value: Any = None
        self._lock = threading.Lock()
        self._loaded = False

    def load(self) -> T:
        if self._loaded:
            return self._value  # type: ignore
        with self._lock:
            if not self._loaded:
                self._value = self._loader()
                self._loaded = True
        return self._value  # type: ignore

    def reload(self) -> T:
        """Force a reload."""
        with self._lock:
            self._value = self._loader()
            self._loaded = True
        return self._value  # type: ignore

    def unload(self) -> None:
        """Drop the loaded value."""
        with self._lock:
            self._value = None
            self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get(self) -> T:
        return self.load()

    def __repr__(self) -> str:
        if self._loaded:
            return f"LazyLoader({self._value!r})"
        return "LazyLoader(<not loaded>)"
