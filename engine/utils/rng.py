"""Seeded random number generator with deterministic, savable state."""

from __future__ import annotations

import random
from typing import Any, Optional, Sequence, TypeVar

T = TypeVar("T")


class RNG:
    """A seeded RNG wrapper that supports sub-streams and state save/restore."""

    __slots__ = ("_rng", "seed")

    def __init__(self, seed: Optional[int] = None) -> None:
        self.seed = seed if seed is not None else random.randrange(1 << 32)
        self._rng = random.Random(self.seed)

    # ---------- core API ----------

    def random(self) -> float:
        return self._rng.random()

    def uniform(self, lo: float, hi: float) -> float:
        return self._rng.uniform(lo, hi)

    def randint(self, lo: int, hi: int) -> int:
        return self._rng.randint(lo, hi)

    def randrange(self, start: int, stop: Optional[int] = None, step: int = 1) -> int:
        if stop is None:
            return self._rng.randrange(0, start, step)
        return self._rng.randrange(start, stop, step)

    def choice(self, seq: Sequence[T]) -> T:
        return self._rng.choice(seq)

    def weighted_choice(self, seq: Sequence[T], weights: Sequence[float]) -> T:
        return self._rng.choices(seq, weights=weights, k=1)[0]

    def sample(self, seq: Sequence[T], k: int) -> list[T]:
        return self._rng.sample(seq, k)

    def shuffle(self, seq: list[T]) -> list[T]:
        self._rng.shuffle(seq)
        return seq

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return self._rng.gauss(mu, sigma)

    def chance(self, p: float) -> bool:
        """Return True with probability `p` (0..1)."""
        return self._rng.random() < p

    def dice(self, count: int, sides: int, modifier: int = 0) -> int:
        """Roll `count`d`sides` + `modifier` and return the total."""
        return sum(self._rng.randint(1, sides) for _ in range(count)) + modifier

    def sign(self) -> int:
        return self._rng.choice((-1, 1))

    def unit_vector2d(self) -> tuple[float, float]:
        import math
        a = self._rng.uniform(0.0, 2.0 * math.pi)
        return math.cos(a), math.sin(a)

    # ---------- sub-streams ----------

    def substream(self, salt: int = 0) -> "RNG":
        """Derive a deterministic sub-stream from this RNG."""
        return RNG(self._rng.randint(0, 1 << 32) ^ salt)

    # ---------- state ----------

    def get_state(self) -> tuple[Any, ...]:
        return self._rng.getstate()

    def set_state(self, state: tuple[Any, ...]) -> None:
        self._rng.setstate(state)

    def __repr__(self) -> str:
        return f"RNG(seed={self.seed})"


_global_rng: Optional[RNG] = None


def get_global_rng() -> RNG:
    global _global_rng
    if _global_rng is None:
        _global_rng = RNG()
    return _global_rng


def set_global_rng(rng: RNG) -> None:
    global _global_rng
    _global_rng = rng
