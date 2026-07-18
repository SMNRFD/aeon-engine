"""A* pathfinding over the world map with terrain-aware costs."""

from __future__ import annotations

import heapq
import math
from typing import Iterator, Optional

from engine.world.map import WorldMap


class AStarPathfinder:
    """Terrain-aware A* over a WorldMap."""

    def __init__(self, world: WorldMap) -> None:
        self.world = world

    def find_path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
        max_iterations: int = 50000,
        allow_diagonal: bool = True,
        allow_road_penalty: bool = True,
    ) -> Optional[list[tuple[int, int]]]:
        """Return a list of (x, y) tiles from start to goal, or None."""
        sx, sy = start
        gx, gy = goal
        if not self.world.in_bounds(sx, sy) or not self.world.in_bounds(gx, gy):
            return None
        start_tile = self.world.get_tile(sx, sy)
        goal_tile = self.world.get_tile(gx, gy)
        if start_tile is None or goal_tile is None:
            return None
        if not goal_tile.is_walkable:
            return None

        def heuristic(x: int, y: int) -> float:
            dx = abs(x - gx)
            dy = abs(y - gy)
            if allow_diagonal:
                return max(dx, dy) + 0.41 * min(dx, dy)
            return dx + dy

        def neighbors(x: int, y: int) -> Iterator[tuple[int, int, float]]:
            deltas = [(-1, 0), (1, 0), (0, -1), (0, 1)]
            if allow_diagonal:
                deltas += [(-1, -1), (-1, 1), (1, -1), (1, 1)]
            for dx, dy in deltas:
                nx, ny = x + dx, y + dy
                if not self.world.in_bounds(nx, ny):
                    continue
                t = self.world.get_tile(nx, ny)
                if t is None or not t.is_walkable:
                    continue
                if dx != 0 and dy != 0:
                    # Prevent diagonal cutting through walls
                    t1 = self.world.get_tile(x + dx, y)
                    t2 = self.world.get_tile(x, y + dy)
                    if (t1 and t1.blocks_sight) or (t2 and t2.blocks_sight):
                        continue
                    cost = t.movement_cost * 1.41
                else:
                    cost = t.movement_cost
                if allow_road_penalty and t.terrain_type.value == "road":
                    cost *= 0.7
                yield nx, ny, cost

        open_heap: list[tuple[float, int, int, int]] = []
        counter = 0
        heapq.heappush(open_heap, (heuristic(sx, sy), 0, sx, sy))
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], float] = {(sx, sy): 0.0}
        closed: set[tuple[int, int]] = set()
        it = 0

        while open_heap and it < max_iterations:
            it += 1
            _, _, cx, cy = heapq.heappop(open_heap)
            current = (cx, cy)
            if current == (gx, gy):
                # Reconstruct
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path
            if current in closed:
                continue
            closed.add(current)
            for nx, ny, cost in neighbors(cx, cy):
                if (nx, ny) in closed:
                    continue
                tentative = g_score[current] + cost
                if tentative < g_score.get((nx, ny), math.inf):
                    g_score[(nx, ny)] = tentative
                    came_from[(nx, ny)] = current
                    counter += 1
                    f = tentative + heuristic(nx, ny)
                    heapq.heappush(open_heap, (f, counter, nx, ny))
        return None

    def path_length(self, path: list[tuple[int, int]]) -> float:
        if len(path) < 2:
            return 0.0
        total = 0.0
        for (x1, y1), (x2, y2) in zip(path, path[1:]):
            t = self.world.get_tile(x2, y2)
            cost = t.movement_cost if t else 1.0
            if x1 != x2 and y1 != y2:
                cost *= 1.41
            total += cost
        return total
