"""Dungeon generation — caves, ruins, catacombs, vaults, mines.

Procedurally generates multi-level dungeons using room-and-corridor,
cave-cellular-automata, and BSP-tree algorithms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.utils.rng import RNG


class DungeonType(IntEnum):
    CAVE = 0
    RUINS = 1
    CATACOMBS = 2
    VAULT = 3
    MINE = 4
    TEMPLE = 5
    TOMB = 6
    LAIR = 7
    STRONGHOLD = 8
    ABYSS = 9


class RoomType(IntEnum):
    ENTRANCE = 0
    CORRIDOR = 1
    ROOM = 2
    HALL = 3
    SHRINE = 4
    TREASURE = 5
    BOSS = 6
    TRAP = 7
    PUZZLE = 8
    STAIRS_DOWN = 9
    STAIRS_UP = 10
    ALTAR = 11
    POOL = 12
    LIBRARY = 13
    KITCHEN = 14
    BARRACKS = 15
    PRISON = 16


@dataclass
class DungeonRoom:
    """A single room in a dungeon."""

    room_id: int
    room_type: RoomType
    x: int
    y: int
    width: int
    height: int
    description: str = ""
    is_lit: bool = False
    is_secret: bool = False
    encounter_rate: float = 0.0
    treasure_value: int = 0
    connections: list[int] = field(default_factory=list)  # connected room_ids
    features: list[str] = field(default_factory=list)  # "fountain", "altar", "throne", etc.

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id, "room_type": int(self.room_type),
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "description": self.description, "is_lit": self.is_lit,
            "is_secret": self.is_secret, "encounter_rate": self.encounter_rate,
            "treasure_value": self.treasure_value,
            "connections": list(self.connections),
            "features": list(self.features),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DungeonRoom":
        return cls(
            room_id=data["room_id"], room_type=RoomType(data["room_type"]),
            x=data["x"], y=data["y"], width=data["width"], height=data["height"],
            description=data.get("description", ""),
            is_lit=data.get("is_lit", False),
            is_secret=data.get("is_secret", False),
            encounter_rate=data.get("encounter_rate", 0.0),
            treasure_value=data.get("treasure_value", 0),
            connections=list(data.get("connections", [])),
            features=list(data.get("features", [])),
        )


@dataclass
class DungeonLevel:
    """A single level of a dungeon."""

    level_id: int
    depth: int  # 0 = top
    width: int
    height: int
    rooms: list[DungeonRoom] = field(default_factory=list)
    tiles: list[list[str]] = field(default_factory=list)  # char grid
    stairs_up: Optional[tuple[int, int]] = None
    stairs_down: Optional[tuple[int, int]] = None
    ambient_light: float = 0.1  # 0..1
    danger_level: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "level_id": self.level_id, "depth": self.depth,
            "width": self.width, "height": self.height,
            "rooms": [r.to_dict() for r in self.rooms],
            "tiles": [list(row) for row in self.tiles],
            "stairs_up": self.stairs_up, "stairs_down": self.stairs_down,
            "ambient_light": self.ambient_light,
            "danger_level": self.danger_level,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DungeonLevel":
        return cls(
            level_id=data["level_id"], depth=data["depth"],
            width=data["width"], height=data["height"],
            rooms=[DungeonRoom.from_dict(r) for r in data.get("rooms", [])],
            tiles=[list(row) for row in data.get("tiles", [])],
            stairs_up=tuple(data["stairs_up"]) if data.get("stairs_up") else None,
            stairs_down=tuple(data["stairs_down"]) if data.get("stairs_down") else None,
            ambient_light=data.get("ambient_light", 0.1),
            danger_level=data.get("danger_level", 1),
        )


@dataclass
class Dungeon:
    """A complete dungeon instance."""

    dungeon_id: int
    name: str
    dungeon_type: DungeonType
    location: tuple[int, int]  # world position of entrance
    levels: list[DungeonLevel] = field(default_factory=list)
    min_level: int = 1
    max_level: int = 50
    cleared: bool = False
    boss_defeated: bool = False
    total_treasure: int = 0
    description: str = ""
    history: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dungeon_id": self.dungeon_id, "name": self.name,
            "dungeon_type": int(self.dungeon_type),
            "location": self.location,
            "levels": [l.to_dict() for l in self.levels],
            "min_level": self.min_level, "max_level": self.max_level,
            "cleared": self.cleared, "boss_defeated": self.boss_defeated,
            "total_treasure": self.total_treasure,
            "description": self.description,
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Dungeon":
        return cls(
            dungeon_id=data["dungeon_id"], name=data["name"],
            dungeon_type=DungeonType(data["dungeon_type"]),
            location=tuple(data["location"]),
            levels=[DungeonLevel.from_dict(l) for l in data.get("levels", [])],
            min_level=data.get("min_level", 1),
            max_level=data.get("max_level", 50),
            cleared=data.get("cleared", False),
            boss_defeated=data.get("boss_defeated", False),
            total_treasure=data.get("total_treasure", 0),
            description=data.get("description", ""),
            history=list(data.get("history", [])),
        )


class DungeonGenerator:
    """Procedural dungeon generator with multiple algorithms."""

    def __init__(self, rng: Optional[RNG] = None) -> None:
        self.rng = rng or RNG()

    def generate(self, name: str, dungeon_type: DungeonType,
                 location: tuple[int, int], depth: int = 5,
                 dungeon_id: int = 0,
                 danger_base: int = 1) -> Dungeon:
        """Generate a complete dungeon."""
        dungeon = Dungeon(
            dungeon_id=dungeon_id, name=name, dungeon_type=dungeon_type,
            location=location, min_level=danger_base,
            max_level=danger_base + depth * 5,
            description=self._describe(dungeon_type),
        )
        for d in range(depth):
            level = self._generate_level(d, dungeon_type, danger_base + d * 5)
            dungeon.levels.append(level)
            dungeon.total_treasure += sum(r.treasure_value for r in level.rooms)
        dungeon.history.append(f"Dungeon discovered at {location}.")
        return dungeon

    def _describe(self, dungeon_type: DungeonType) -> str:
        return {
            DungeonType.CAVE: "A natural cave system, dark and twisting.",
            DungeonType.RUINS: "Crumbling remnants of a forgotten age.",
            DungeonType.CATACOMBS: "A maze of bone-lined tunnels beneath a holy site.",
            DungeonType.VAULT: "A secure underground treasury.",
            DungeonType.MINE: "An abandoned mine, ore veins still glittering.",
            DungeonType.TEMPLE: "A buried temple to a long-forgotten god.",
            DungeonType.TOMB: "A great tomb of an ancient ruler.",
            DungeonType.LAIR: "A creature's lair, strewn with bones.",
            DungeonType.STRONGHOLD: "A fortified underground bastion.",
            DungeonType.ABYSS: "A yawning chasm descending into nightmare.",
        }.get(dungeon_type, "A mysterious dungeon.")

    def _generate_level(self, depth: int, dungeon_type: DungeonType,
                        danger_level: int) -> DungeonLevel:
        """Generate a single level using the appropriate algorithm."""
        width = 60 + depth * 4
        height = 40 + depth * 3
        level = DungeonLevel(
            level_id=depth, depth=depth, width=width, height=height,
            danger_level=danger_level,
            ambient_light=max(0.0, 0.2 - depth * 0.02),
        )
        # Choose algorithm based on dungeon type
        if dungeon_type in (DungeonType.CAVE, DungeonType.LAIR, DungeonType.ABYSS):
            self._generate_cave(level)
        elif dungeon_type in (DungeonType.CATACOMBS, DungeonType.TOMB):
            self._generate_catacombs(level)
        elif dungeon_type in (DungeonType.RUINS, DungeonType.TEMPLE):
            self._generate_ruins(level)
        else:
            self._generate_rooms(level)
        # Place stairs
        if depth > 0:
            entry = level.rooms[0] if level.rooms else None
            if entry:
                cx, cy = entry.center
                level.stairs_up = (cx, cy)
                level.tiles[cy][cx] = "<"
        if depth < 20:  # max depth cap
            last_room = level.rooms[-1] if level.rooms else None
            if last_room:
                cx, cy = last_room.center
                level.stairs_down = (cx, cy)
                level.tiles[cy][cx] = ">"
        return level

    # ----- algorithms -----

    def _init_tiles(self, width: int, height: int, fill: str = "#") -> list[list[str]]:
        return [[fill for _ in range(width)] for _ in range(height)]

    def _generate_rooms(self, level: DungeonLevel) -> None:
        """Room-and-corridor BSP generation."""
        level.tiles = self._init_tiles(level.width, level.height)
        # Place random non-overlapping rooms
        attempts = 30
        rooms: list[DungeonRoom] = []
        room_id = 0
        for _ in range(attempts):
            if len(rooms) >= 8:
                break
            rw = self.rng.randint(5, 12)
            rh = self.rng.randint(4, 8)
            rx = self.rng.randint(1, level.width - rw - 1)
            ry = self.rng.randint(1, level.height - rh - 1)
            # Check overlap
            overlap = False
            for r in rooms:
                if (rx < r.x + r.width + 1 and rx + rw + 1 > r.x and
                        ry < r.y + r.height + 1 and ry + rh + 1 > r.y):
                    overlap = True
                    break
            if overlap:
                continue
            room_type = RoomType.ENTRANCE if not rooms else RoomType.ROOM
            room = DungeonRoom(
                room_id=room_id, room_type=room_type,
                x=rx, y=ry, width=rw, height=rh,
                description=self._room_description(),
                encounter_rate=self.rng.uniform(0.05, 0.3),
                treasure_value=self.rng.randint(0, 100 * level.danger_level),
            )
            room_id += 1
            # Carve floor
            for y in range(ry, ry + rh):
                for x in range(rx, rx + rw):
                    level.tiles[y][x] = "."
            rooms.append(room)
        # Connect rooms with corridors
        for i in range(len(rooms) - 1):
            self._carve_corridor(level, rooms[i], rooms[i + 1])
            rooms[i].connections.append(rooms[i + 1].room_id)
            rooms[i + 1].connections.append(rooms[i].room_id)
        # Mark last room as treasure/boss
        if rooms:
            last = rooms[-1]
            last.room_type = RoomType.BOSS
            last.treasure_value *= 3
            last.encounter_rate = 0.6
            last.features.append("boss_throne")
            level.rooms = rooms

    def _generate_cave(self, level: DungeonLevel) -> None:
        """Cellular automata cave generation."""
        width, height = level.width, level.height
        # Start with random wall/floor mix
        grid = [["#" for _ in range(width)] for _ in range(height)]
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                grid[y][x] = "." if self.rng.chance(0.45) else "#"
        # Cellular automata: floor if neighbours mostly floor
        for _ in range(5):
            new_grid = [row[:] for row in grid]
            for y in range(1, height - 1):
                for x in range(1, width - 1):
                    walls = 0
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if dy == 0 and dx == 0:
                                continue
                            ny, nx = y + dy, x + dx
                            if grid[ny][nx] == "#":
                                walls += 1
                    new_grid[y][x] = "#" if walls >= 5 else "."
            grid = new_grid
        level.tiles = grid
        # Find open areas and designate as rooms
        room_id = 0
        visited = [[False] * width for _ in range(height)]
        rooms: list[DungeonRoom] = []
        for y in range(1, height - 1):
            for x in range(1, width - 1):
                if grid[y][x] == "." and not visited[y][x]:
                    # Flood-fill
                    area: list[tuple[int, int]] = []
                    stack = [(x, y)]
                    while stack:
                        cx, cy = stack.pop()
                        if visited[cy][cx] or grid[cy][cx] != ".":
                            continue
                        visited[cy][cx] = True
                        area.append((cx, cy))
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < width and 0 <= ny < height:
                                if not visited[ny][nx] and grid[ny][nx] == ".":
                                    stack.append((nx, ny))
                    if len(area) > 12:
                        xs = [a[0] for a in area]
                        ys = [a[1] for a in area]
                        room = DungeonRoom(
                            room_id=room_id,
                            room_type=RoomType.ENTRANCE if not rooms else RoomType.ROOM,
                            x=min(xs), y=min(ys),
                            width=max(xs) - min(xs) + 1,
                            height=max(ys) - min(ys) + 1,
                            description="A natural cavern.",
                            encounter_rate=self.rng.uniform(0.1, 0.4),
                            treasure_value=self.rng.randint(0, 80 * level.danger_level),
                        )
                        rooms.append(room)
                        room_id += 1
        level.rooms = rooms

    def _generate_catacombs(self, level: DungeonLevel) -> None:
        """Tight grid of small rooms with corridors — catacomb-style."""
        level.tiles = self._init_tiles(level.width, level.height)
        rooms: list[DungeonRoom] = []
        room_id = 0
        # Grid layout
        cols = 4
        rows = 3
        cell_w = level.width // cols
        cell_h = level.height // rows
        for r in range(rows):
            for c in range(cols):
                rw = cell_w - 4
                rh = cell_h - 4
                rx = c * cell_w + 2
                ry = r * cell_h + 2
                room = DungeonRoom(
                    room_id=room_id, room_type=RoomType.ROOM,
                    x=rx, y=ry, width=rw, height=rh,
                    description="A narrow bone-lined chamber.",
                    encounter_rate=self.rng.uniform(0.15, 0.35),
                    treasure_value=self.rng.randint(10, 80 * level.danger_level),
                )
                room_id += 1
                for y in range(ry, ry + rh):
                    for x in range(rx, rx + rw):
                        level.tiles[y][x] = "."
                rooms.append(room)
                # Sometimes add features
                if self.rng.chance(0.3):
                    room.features.append(self.rng.choice(["sarcophagus", "bone_pile", "altar"]))
        # Connect adjacent rooms
        for i, room in enumerate(rooms):
            for j in (i + 1, i + cols):
                if j < len(rooms):
                    self._carve_corridor(level, room, rooms[j])
                    room.connections.append(rooms[j].room_id)
                    rooms[j].connections.append(room.room_id)
        # Mark some rooms as shrines
        for room in rooms:
            if self.rng.chance(0.2):
                room.room_type = RoomType.SHRINE
                room.features.append("shrine")
        level.rooms = rooms

    def _generate_ruins(self, level: DungeonLevel) -> None:
        """Large irregular rooms with rubble."""
        self._generate_rooms(level)
        # Add rubble and partial walls
        for room in level.rooms:
            for _ in range(self.rng.randint(2, 5)):
                rx = self.rng.randint(room.x, room.x + room.width - 1)
                ry = self.rng.randint(room.y, room.y + room.height - 1)
                if 0 <= rx < level.width and 0 <= ry < level.height:
                    if level.tiles[ry][rx] == ".":
                        level.tiles[ry][rx] = self.rng.choice(["*", "°", ","])
            # Add columns
            if self.rng.chance(0.4):
                cx = room.x + room.width // 2
                cy = room.y + room.height // 2
                if 0 <= cx < level.width and 0 <= cy < level.height:
                    level.tiles[cy][cx] = "o"

    def _carve_corridor(self, level: DungeonLevel, room_a: DungeonRoom,
                        room_b: DungeonLevel | DungeonRoom) -> None:
        ax, ay = room_a.center
        bx, by = room_b.center  # type: ignore[attr-defined]
        # L-shaped corridor
        if self.rng.chance(0.5):
            self._carve_h_line(level, ax, bx, ay)
            self._carve_v_line(level, ay, by, bx)
        else:
            self._carve_v_line(level, ay, by, ax)
            self._carve_h_line(level, ax, bx, by)

    def _carve_h_line(self, level: DungeonLevel, x1: int, x2: int, y: int) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            if 0 <= y < level.height and 0 <= x < level.width:
                if level.tiles[y][x] == "#":
                    level.tiles[y][x] = "."

    def _carve_v_line(self, level: DungeonLevel, y1: int, y2: int, x: int) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            if 0 <= y < level.height and 0 <= x < level.width:
                if level.tiles[y][x] == "#":
                    level.tiles[y][x] = "."

    def _room_description(self) -> str:
        return self.rng.choice([
            "A small, musty chamber.",
            "A wide, vaulted hall.",
            "A cramped stone cell.",
            "An ornate antechamber.",
            "A natural cavern.",
            "A rubble-strewn passage.",
            "A damp, mouldy room.",
            "A torch-lit corridor.",
            "A dark, foreboding chamber.",
            "A small alcove.",
        ])


# Default dungeon templates
DEFAULT_DUNGEON_TEMPLATES: dict[str, dict[str, Any]] = {
    "goblin_cave": {
        "name": "Goblin Cave", "dungeon_type": DungeonType.CAVE,
        "depth": 3, "danger_base": 1,
        "description": "A stinking goblin warren.",
    },
    "ancient_tomb": {
        "name": "Ancient Tomb", "dungeon_type": DungeonType.TOMB,
        "depth": 5, "danger_base": 10,
        "description": "A great ruler's burial place, cursed for eternity.",
    },
    "abandoned_mine": {
        "name": "Abandoned Mine", "dungeon_type": DungeonType.MINE,
        "depth": 6, "danger_base": 5,
        "description": "A played-out mine shaft,rumoured to hide deeper secrets.",
    },
    "catacombs": {
        "name": "Catacombs", "dungeon_type": DungeonType.CATACOMBS,
        "depth": 8, "danger_base": 8,
        "description": "Bone-lined tunnels beneath the old temple.",
    },
    "dragon_lair": {
        "name": "Dragon's Lair", "dungeon_type": DungeonType.LAIR,
        "depth": 4, "danger_base": 30,
        "description": "A vast cavern deep within the mountains, reeking of sulphur.",
    },
    "forgotten_temple": {
        "name": "Forgotten Temple", "dungeon_type": DungeonType.TEMPLE,
        "depth": 5, "danger_base": 15,
        "description": "A buried temple to a god long forgotten.",
    },
}
