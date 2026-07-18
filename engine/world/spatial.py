"""Spatial partitioning for fast neighbour queries.

Uses a uniform grid hash-map keyed by cell coordinates. Entities register
their position and can be queried by radius or cell.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Iterator, Optional, TypeVar

T = TypeVar("T")


class SpatialGrid:
    """A uniform-grid spatial hash for 2D entity positions."""

    def __init__(self, cell_size: int = 16) -> None:
        if cell_size <= 0:
            raise ValueError("cell_size must be positive")
        self.cell_size = cell_size
        self._cells: dict[tuple[int, int], set[T]] = defaultdict(set)
        self._positions: dict[T, tuple[int, int]] = {}

    def _key(self, x: float, y: float) -> tuple[int, int]:
        return int(math.floor(x / self.cell_size)), int(math.floor(y / self.cell_size))

    def insert(self, entity: T, x: float, y: float) -> None:
        # Remove old position if present.
        self.remove(entity)
        key = self._key(x, y)
        self._cells[key].add(entity)
        self._positions[entity] = (x, y)

    def remove(self, entity: T) -> None:
        pos = self._positions.pop(entity, None)
        if pos is None:
            return
        key = self._key(pos[0], pos[1])
        cell = self._cells.get(key)
        if cell is not None:
            cell.discard(entity)
            if not cell:
                del self._cells[key]

    def update(self, entity: T, x: float, y: float) -> None:
        self.insert(entity, x, y)

    def query_radius(self, x: float, y: float, radius: float) -> list[tuple[T, float]]:
        """Return [(entity, distance), ...] within `radius` of (x, y)."""
        out: list[tuple[T, float]] = []
        if radius < 0:
            return out
        cell_r = int(math.ceil(radius / self.cell_size))
        cx, cy = self._key(x, y)
        r2 = radius * radius
        for dx in range(-cell_r, cell_r + 1):
            for dy in range(-cell_r, cell_r + 1):
                cell = self._cells.get((cx + dx, cy + dy))
                if not cell:
                    continue
                for entity in cell:
                    ex, ey = self._positions[entity]
                    d2 = (ex - x) ** 2 + (ey - y) ** 2
                    if d2 <= r2:
                        out.append((entity, math.sqrt(d2)))
        out.sort(key=lambda t: t[1])
        return out

    def query_cell(self, x: float, y: float) -> set[T]:
        return set(self._cells.get(self._key(x, y), set()))

    def query_box(self, x1: float, y1: float, x2: float, y2: float) -> list[T]:
        """Return all entities within the axis-aligned box [x1..x2, y1..y2]."""
        out: list[T] = []
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        kx1, ky1 = self._key(x1, y1)
        kx2, ky2 = self._key(x2, y2)
        for cx in range(kx1, kx2 + 1):
            for cy in range(ky1, ky2 + 1):
                cell = self._cells.get((cx, cy))
                if not cell:
                    continue
                for entity in cell:
                    ex, ey = self._positions[entity]
                    if x1 <= ex <= x2 and y1 <= ey <= y2:
                        out.append(entity)
        return out

    def nearest(self, x: float, y: float, k: int = 1) -> list[tuple[T, float]]:
        """Return the k nearest entities to (x, y)."""
        out: list[tuple[T, float]] = []
        radius = self.cell_size
        while len(out) < k:
            out = self.query_radius(x, y, radius)
            radius *= 2
            if radius > self.cell_size * 64:
                break
        return out[:k]

    def __contains__(self, entity: T) -> bool:
        return entity in self._positions

    def __len__(self) -> int:
        return len(self._positions)

    def all_positions(self) -> dict[T, tuple[int, int]]:
        return dict(self._positions)

    def iter_entities(self) -> Iterator[T]:
        return iter(self._positions)
