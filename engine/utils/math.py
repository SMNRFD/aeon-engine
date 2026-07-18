"""Math helpers used across the engine."""

from __future__ import annotations

import math
from typing import Iterable


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp `value` to the closed range [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation between `a` and `b`."""
    return a + (b - a) * t


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    """Hermite-smooth interpolation between two edges."""
    if edge1 == edge0:
        return 0.0 if x < edge0 else 1.0
    t = clamp((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def distance2d(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def distance3d(x1: float, y1: float, z1: float, x2: float, y2: float, z2: float) -> float:
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)


def manhattan(x1: int, y1: int, x2: int, y2: int) -> int:
    return abs(x2 - x1) + abs(y2 - y1)


def chebyshev(x1: int, y1: int, x2: int, y2: int) -> int:
    return max(abs(x2 - x1), abs(y2 - y1))


def hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """Distance between two axial hex coordinates."""
    return (abs(q1 - q2) + abs(q1 + r1 - q2 - r2) + abs(r1 - r2)) // 2


def normalize_angle(angle: float) -> float:
    """Wrap an angle in radians into [-π, π]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def angle_difference(a: float, b: float) -> float:
    """Smallest signed difference between two angles in radians."""
    return normalize_angle(b - a)


def moving_average(values: Iterable[float], window: int) -> list[float]:
    """Compute a simple moving average."""
    vals = list(values)
    if window <= 0:
        return vals
    out = []
    acc = 0.0
    queue: list[float] = []
    for v in vals:
        queue.append(v)
        acc += v
        if len(queue) > window:
            acc -= queue.pop(0)
        out.append(acc / len(queue))
    return out


def rolling_stddev(values: list[float], window: int) -> list[float]:
    """Compute rolling population standard deviation."""
    if window <= 0 or not values:
        return [0.0] * len(values)
    out = []
    for i in range(len(values)):
        s = values[max(0, i - window + 1): i + 1]
        if len(s) < 2:
            out.append(0.0)
            continue
        mu = sum(s) / len(s)
        var = sum((v - mu) ** 2 for v in s) / len(s)
        out.append(math.sqrt(var))
    return out


def ease_in_out_cubic(t: float) -> float:
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2
