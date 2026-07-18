"""Identifier generation utilities."""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any


def generate_entity_uuid() -> str:
    """Generate a fresh UUID4 as a string."""
    return str(uuid.uuid4())


def stable_hash(*parts: Any) -> int:
    """Deterministic hash from arbitrary parts — used for seed derivation."""
    h = hashlib.blake2b(digest_size=8)
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"|")
    return int.from_bytes(h.digest(), "big", signed=False)


def timestamp_id() -> str:
    """A short, sortable ID based on the current time."""
    return f"{int(time.time() * 1000):x}"
