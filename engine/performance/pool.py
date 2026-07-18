"""Object pool — reuse expensive-to-create objects."""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class PooledFactory(Generic[T]):
    """A factory that creates and resets pooled objects."""

    def __init__(self, create_fn: Callable[[], T],
                 reset_fn: Callable[[T], None] | None = None) -> None:
        self.create_fn = create_fn
        self.reset_fn = reset_fn

    def create(self) -> T:
        return self.create_fn()

    def reset(self, obj: T) -> T:
        if self.reset_fn is not None:
            self.reset_fn(obj)
        return obj


class ObjectPool(Generic[T]):
    """A thread-safe object pool.

    Objects are created on demand up to `max_size`. When the pool is empty,
    `acquire()` either creates a new object (if below max) or blocks (if at max
    and `block` is True) or returns None (if `block` is False).
    """

    def __init__(self, factory: PooledFactory[T],
                 initial_size: int = 0,
                 max_size: int = 100,
                 block: bool = True,
                 timeout: float = 1.0) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be positive")
        self.factory = factory
        self.max_size = max_size
        self.block = block
        self.timeout = timeout
        self._pool: deque[T] = deque()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)
        self._created_count = 0
        self._in_use = 0
        # Pre-populate
        for _ in range(min(initial_size, max_size)):
            self._pool.append(self.factory.create())
            self._created_count += 1

    def acquire(self) -> T | None:
        with self._not_empty:
            while True:
                if self._pool:
                    obj = self._pool.popleft()
                    self._in_use += 1
                    return self.factory.reset(obj)
                if self._created_count < self.max_size:
                    obj = self.factory.create()
                    self._created_count += 1
                    self._in_use += 1
                    return obj
                if not self.block:
                    return None
                self._not_empty.wait(timeout=self.timeout)
                if not self._pool and self._created_count >= self.max_size:
                    # Still nothing available — give up
                    return None

    def release(self, obj: T) -> None:
        with self._not_empty:
            self._factory_reset_for_release(obj)
            self._pool.append(obj)
            self._in_use = max(0, self._in_use - 1)
            self._not_empty.notify()

    def _factory_reset_for_release(self, obj: T) -> None:
        if self.factory.reset_fn is not None:
            self.factory.reset_fn(obj)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "pool_size": len(self._pool),
                "in_use": self._in_use,
                "created": self._created_count,
                "max_size": self.max_size,
            }

    def clear(self) -> None:
        with self._lock:
            self._pool.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._pool)

    def __enter__(self) -> "ObjectPool[T]":
        return self

    def __exit__(self, *args: Any) -> None:
        self.clear()
