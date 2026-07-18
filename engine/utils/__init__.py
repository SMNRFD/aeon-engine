"""Utility modules: seeded RNG, math helpers, identifiers."""

from engine.utils.rng import RNG, get_global_rng, set_global_rng
from engine.utils.math import (
    clamp, lerp, smoothstep, distance2d, distance3d, manhattan,
    hex_distance, normalize_angle, angle_difference,
)
from engine.utils.identifiers import generate_entity_uuid

__all__ = [
    "RNG", "get_global_rng", "set_global_rng",
    "clamp", "lerp", "smoothstep", "distance2d", "distance3d",
    "manhattan", "hex_distance", "normalize_angle", "angle_difference",
    "generate_entity_uuid",
]
