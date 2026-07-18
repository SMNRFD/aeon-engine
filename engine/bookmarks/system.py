"""Map bookmarks, pins, and markers.

Players can bookmark locations for later reference:
* Bookmark — a saved location with a name and notes
* Pin — a temporary marker placed on the map
* Map Marker — a permanent marker for points of interest

Bookmarks persist across saves; pins are temporary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class BookmarkType(IntEnum):
    LOCATION = 0       # generic location
    CITY = 1
    DUNGEON = 2
    SHOP = 3
    QUEST = 4          # quest-related location
    TREASURE = 5
    DEATH = 6          # where player died
    FRIEND = 7         # friend's location
    ENEMY = 8          # enemy's location
    RESOURCE = 9       # mining/logging spot
    SAFEHOUSE = 10
    PORTAL = 11
    SHRINE = 12
    CUSTOM = 99


@dataclass
class Bookmark:
    """A saved location bookmark."""

    bookmark_id: int
    name: str
    bookmark_type: BookmarkType = BookmarkType.LOCATION
    x: int = 0
    y: int = 0
    z: int = 0  # dimension/level
    notes: str = ""
    icon: str = "★"
    color: int = 215  # gold
    created_tick: float = 0.0
    owner_id: Optional[int] = None
    is_shared: bool = False  # shared with party members
    category: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["bookmark_type"] = int(self.bookmark_type)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Bookmark":
        d = dict(data)
        d["bookmark_type"] = BookmarkType(d.get("bookmark_type", 0))
        return cls(**d)


@dataclass
class MapPin:
    """A temporary pin placed on the map."""

    pin_id: int
    x: int
    y: int
    label: str = ""
    color: int = 196
    icon: str = "!"
    expires_at: Optional[float] = None  # tick when pin expires
    created_by: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "MapPin":
        return cls(**data)


@dataclass
class MapMarker:
    """A permanent marker for a point of interest."""

    marker_id: int
    name: str
    x: int
    y: int
    marker_type: str = "poi"  # poi, city, dungeon, shrine, portal
    description: str = ""
    icon: str = "○"
    color: int = 244
    is_visible: bool = True  # visible on map when explored
    requires_discovery: bool = True
    discovered_by: list[int] = field(default_factory=list)
    faction_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "MapMarker":
        return cls(**data)


class BookmarkManager:
    """Manages bookmarks, pins, and markers."""

    def __init__(self) -> None:
        self._bookmarks: dict[int, Bookmark] = {}
        self._pins: dict[int, MapPin] = {}
        self._markers: dict[int, MapMarker] = {}
        self._next_bookmark_id: int = 1
        self._next_pin_id: int = 1
        self._next_marker_id: int = 1

    # ---------- bookmarks ----------

    def add_bookmark(self, name: str, x: int, y: int,
                     bookmark_type: BookmarkType = BookmarkType.LOCATION,
                     **kwargs: Any) -> Bookmark:
        bookmark = Bookmark(
            bookmark_id=self._next_bookmark_id,
            name=name, x=x, y=y,
            bookmark_type=bookmark_type,
            **kwargs,
        )
        self._next_bookmark_id += 1
        self._bookmarks[bookmark.bookmark_id] = bookmark
        return bookmark

    def remove_bookmark(self, bookmark_id: int) -> bool:
        return self._bookmarks.pop(bookmark_id, None) is not None

    def get_bookmark(self, bookmark_id: int) -> Optional[Bookmark]:
        return self._bookmarks.get(bookmark_id)

    def all_bookmarks(self) -> list[Bookmark]:
        return list(self._bookmarks.values())

    def bookmarks_of(self, owner_id: int) -> list[Bookmark]:
        return [b for b in self._bookmarks.values() if b.owner_id == owner_id]

    def bookmarks_near(self, x: int, y: int, radius: int = 5) -> list[Bookmark]:
        return [b for b in self._bookmarks.values()
                if abs(b.x - x) <= radius and abs(b.y - y) <= radius]

    def bookmarks_by_type(self, bookmark_type: BookmarkType) -> list[Bookmark]:
        return [b for b in self._bookmarks.values() if b.bookmark_type == bookmark_type]

    # ---------- pins ----------

    def add_pin(self, x: int, y: int, label: str = "",
                **kwargs: Any) -> MapPin:
        pin = MapPin(
            pin_id=self._next_pin_id,
            x=x, y=y, label=label, **kwargs,
        )
        self._next_pin_id += 1
        self._pins[pin.pin_id] = pin
        return pin

    def remove_pin(self, pin_id: int) -> bool:
        return self._pins.pop(pin_id, None) is not None

    def all_pins(self) -> list[MapPin]:
        return list(self._pins.values())

    def pins_at(self, x: int, y: int) -> list[MapPin]:
        return [p for p in self._pins.values() if p.x == x and p.y == y]

    def update_pins(self, current_tick: float) -> int:
        """Remove expired pins. Returns the count removed."""
        expired = [pid for pid, pin in self._pins.items()
                   if pin.expires_at is not None and pin.expires_at <= current_tick]
        for pid in expired:
            self._pins.pop(pid, None)
        return len(expired)

    # ---------- markers ----------

    def add_marker(self, name: str, x: int, y: int,
                   marker_type: str = "poi", **kwargs: Any) -> MapMarker:
        marker = MapMarker(
            marker_id=self._next_marker_id,
            name=name, x=x, y=y,
            marker_type=marker_type, **kwargs,
        )
        self._next_marker_id += 1
        self._markers[marker.marker_id] = marker
        return marker

    def get_marker(self, marker_id: int) -> Optional[MapMarker]:
        return self._markers.get(marker_id)

    def all_markers(self) -> list[MapMarker]:
        return list(self._markers.values())

    def markers_at(self, x: int, y: int) -> list[MapMarker]:
        return [m for m in self._markers.values() if m.x == x and m.y == y]

    def markers_visible_to(self, entity_id: int) -> list[MapMarker]:
        return [m for m in self._markers.values()
                if m.is_visible and (not m.requires_discovery or entity_id in m.discovered_by)]

    def discover_marker(self, marker_id: int, entity_id: int) -> bool:
        marker = self._markers.get(marker_id)
        if marker is None:
            return False
        if entity_id not in marker.discovered_by:
            marker.discovered_by.append(entity_id)
        return True

    # ---------- search ----------

    def search(self, query: str) -> dict[str, list]:
        """Search bookmarks, pins, and markers by name."""
        query_lower = query.lower()
        return {
            "bookmarks": [b for b in self._bookmarks.values()
                          if query_lower in b.name.lower() or query_lower in b.notes.lower()],
            "pins": [p for p in self._pins.values()
                     if query_lower in p.label.lower()],
            "markers": [m for m in self._markers.values()
                        if query_lower in m.name.lower() or query_lower in m.description.lower()],
        }

    # ---------- serialization ----------

    def to_dict(self) -> dict[str, Any]:
        return {
            "bookmarks": {str(bid): b.to_dict() for bid, b in self._bookmarks.items()},
            "pins": {str(pid): p.to_dict() for pid, p in self._pins.items()},
            "markers": {str(mid): m.to_dict() for mid, m in self._markers.items()},
            "next_bookmark_id": self._next_bookmark_id,
            "next_pin_id": self._next_pin_id,
            "next_marker_id": self._next_marker_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BookmarkManager":
        mgr = cls()
        mgr._bookmarks = {
            int(bid): Bookmark.from_dict(b)
            for bid, b in data.get("bookmarks", {}).items()
        }
        mgr._pins = {
            int(pid): MapPin.from_dict(p)
            for pid, p in data.get("pins", {}).items()
        }
        mgr._markers = {
            int(mid): MapMarker.from_dict(m)
            for mid, m in data.get("markers", {}).items()
        }
        mgr._next_bookmark_id = data.get("next_bookmark_id", 1)
        mgr._next_pin_id = data.get("next_pin_id", 1)
        mgr._next_marker_id = data.get("next_marker_id", 1)
        return mgr
