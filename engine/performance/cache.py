"""Caches — LRU and TTL-based."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Generic, Hashable, Optional, TypeVar

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """A thread-safe LRU cache."""

    def __init__(self, capacity: int = 128) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._data: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, key: K, default: Any = None) -> Any:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._hits += 1
                return self._data[key]
            self._misses += 1
            return default

    def put(self, key: K, value: V) -> None:
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self._data[key] = value
            else:
                self._data[key] = value
                if len(self._data) > self.capacity:
                    self._data.popitem(last=False)

    def remove(self, key: K) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __contains__(self, key: K) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "size": len(self._data),
                "capacity": self.capacity,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": (self._hits / (self._hits + self._misses))
                if (self._hits + self._misses) > 0
                else 0.0,
            }


class TTLCache(Generic[K, V]):
    """A thread-safe cache with time-to-live expiry."""

    def __init__(self, ttl_seconds: float = 60.0,
                 capacity: int = 256) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.ttl = ttl_seconds
        self.capacity = capacity
        self._data: OrderedDict[K, tuple[V, float]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._expirations = 0

    def get(self, key: K, default: Any = None) -> Any:
        now = time.monotonic()
        with self._lock:
            if key in self._data:
                value, expires = self._data[key]
                if expires > now:
                    self._data.move_to_end(key)
                    self._hits += 1
                    return value
                else:
                    del self._data[key]
                    self._expirations += 1
            self._misses += 1
            return default

    def put(self, key: K, value: V,
            ttl: Optional[float] = None) -> None:
        expires = time.monotonic() + (ttl if ttl is not None else self.ttl)
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
            self._data[key] = (value, expires)
            if len(self._data) > self.capacity:
                self._data.popitem(last=False)

    def remove(self, key: K) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns the count removed."""
        now = time.monotonic()
        removed = 0
        with self._lock:
            keys_to_remove = [k for k, (_, exp) in self._data.items() if exp <= now]
            for k in keys_to_remove:
                del self._data[k]
                removed += 1
            self._expirations += removed
        return removed

    def __contains__(self, key: K) -> bool:
        return self.get(key, _SENTINEL) is not _SENTINEL

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._data),
                "capacity": self.capacity,
                "ttl": self.ttl,
                "hits": self._hits,
                "misses": self._misses,
                "expirations": self._expirations,
                "hit_rate": self._hits / total if total > 0 else 0.0,
            }


_SENTINEL: Any = object()
