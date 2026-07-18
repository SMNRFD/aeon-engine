"""Item registry — central store for all items in the world."""

from __future__ import annotations

import threading
from typing import Iterator, Optional

from engine.core.logging import get_logger
from engine.items.item import Item


log = get_logger("items.registry")


class ItemRegistry:
    """A thread-safe registry of all instantiated items."""

    def __init__(self) -> None:
        self._items: dict[int, Item] = {}
        self._next_id: int = 1
        self._lock = threading.RLock()

    def register(self, item: Item) -> Item:
        """Assign a new id to `item` if needed and store it."""
        with self._lock:
            if item.id == 0:
                item.id = self._next_id
                self._next_id += 1
            else:
                self._next_id = max(self._next_id, item.id + 1)
            self._items[item.id] = item
            return item

    def get(self, item_id: int) -> Optional[Item]:
        with self._lock:
            return self._items.get(item_id)

    def remove(self, item_id: int) -> Optional[Item]:
        with self._lock:
            return self._items.pop(item_id, None)

    def all(self) -> list[Item]:
        with self._lock:
            return list(self._items.values())

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    def __contains__(self, item_id: int) -> bool:
        with self._lock:
            return item_id in self._items

    def __iter__(self) -> Iterator[Item]:
        with self._lock:
            return iter(list(self._items.values()))

    def next_id(self) -> int:
        with self._lock:
            return self._next_id

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._next_id = 1

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "next_id": self._next_id,
                "items": {item.id: item.to_dict() for item in self._items.values()},
            }

    def load_from_dict(self, data: dict) -> None:
        with self._lock:
            self._items.clear()
            self._next_id = data.get("next_id", 1)
            for item_id_str, item_data in data.get("items", {}).items():
                item = Item.from_dict(item_data)
                self._items[item.id] = item
