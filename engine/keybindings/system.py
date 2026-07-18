"""Keyboard bindings — configurable key mappings.

Each key action (move_north, open_inventory, etc.) maps to one or more
keys. Bindings can be customised at runtime and saved to config.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, ClassVar, Optional


class KeyAction(IntEnum):
    # Movement
    MOVE_NORTH = 0
    MOVE_SOUTH = 1
    MOVE_EAST = 2
    MOVE_WEST = 3
    MOVE_NORTHEAST = 4
    MOVE_NORTHWEST = 5
    MOVE_SOUTHEAST = 6
    MOVE_SOUTHWEST = 7
    MOVE_UP = 8       # z-level
    MOVE_DOWN = 9
    # Wait / rest
    WAIT = 10
    REST = 11
    SLEEP = 12
    # UI panels
    OPEN_INVENTORY = 20
    OPEN_CHARACTER = 21
    OPEN_QUESTS = 22
    OPEN_MAP = 23
    OPEN_HELP = 24
    OPEN_SPELLS = 25
    OPEN_SKILLS = 26
    OPEN_MENU = 27
    CLOSE_PANEL = 28
    # Combat
    ATTACK = 30
    CAST_SPELL = 31
    USE_ITEM = 32
    INTERACT = 33
    # Communication
    TALK = 40
    SHOUT = 41
    WHISPER = 42
    # System
    SAVE = 50
    LOAD = 51
    QUIT = 52
    PAUSE = 53
    AUTO_RUN = 54
    SCREENSHOT = 55
    TOGGLE_FULLSCREEN = 56
    TOGGLE_DEBUG = 57
    TOGGLE_CHEAT = 58
    # Camera
    LOOK = 60
    CENTER_ON_PLAYER = 61
    ZOOM_IN = 62
    ZOOM_OUT = 63
    # Selection
    CURSOR_UP = 70
    CURSOR_DOWN = 71
    CURSOR_LEFT = 72
    CURSOR_RIGHT = 73
    CONFIRM = 74
    CANCEL = 75
    TAB = 76
    SHIFT_TAB = 77
    # Quick slots
    QUICK_SLOT_1 = 80
    QUICK_SLOT_2 = 81
    QUICK_SLOT_3 = 82
    QUICK_SLOT_4 = 83
    QUICK_SLOT_5 = 84
    QUICK_SLOT_6 = 85
    QUICK_SLOT_7 = 86
    QUICK_SLOT_8 = 87
    QUICK_SLOT_9 = 88
    QUICK_SLOT_0 = 89
    # Command history
    HISTORY_PREV = 90
    HISTORY_NEXT = 91
    AUTOCOMPLETE = 92
    # Macros
    MACRO_RECORD = 100
    MACRO_PLAY = 101


@dataclass
class KeyBinding:
    """A single key binding."""

    action: KeyAction
    keys: list[str]   # e.g. ["k", "up"]
    description: str = ""

    def matches(self, key: str) -> bool:
        return key.lower() in (k.lower() for k in self.keys)


class KeyBindings:
    """Manages key bindings."""

    def __init__(self) -> None:
        self._bindings: dict[KeyAction, KeyBinding] = {}
        self._key_to_action: dict[str, KeyAction] = {}
        for binding in DEFAULT_BINDINGS:
            self.add(binding)

    def add(self, binding: KeyBinding) -> None:
        self._bindings[binding.action] = binding
        for key in binding.keys:
            # Store with exact case for case-sensitive keys
            self._key_to_action[key] = binding.action
            # Only add lowercase fallback if not already taken
            lower = key.lower()
            if lower not in self._key_to_action:
                self._key_to_action[lower] = binding.action

    def remove(self, action: KeyAction) -> None:
        binding = self._bindings.pop(action, None)
        if binding:
            for key in binding.keys:
                # Only remove if it points to this action
                if self._key_to_action.get(key.lower()) == action:
                    del self._key_to_action[key.lower()]

    def get(self, action: KeyAction) -> Optional[KeyBinding]:
        return self._bindings.get(action)

    def action_for(self, key: str) -> Optional[KeyAction]:
        # Try exact match first, then lowercase
        if key in self._key_to_action:
            return self._key_to_action[key]
        return self._key_to_action.get(key.lower())

    def keys_for(self, action: KeyAction) -> list[str]:
        binding = self._bindings.get(action)
        return list(binding.keys) if binding else []

    def rebind(self, action: KeyAction, keys: list[str]) -> None:
        self.remove(action)
        self.add(KeyBinding(action=action, keys=keys))

    def all(self) -> list[KeyBinding]:
        return list(self._bindings.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            str(int(a)): {"keys": b.keys, "description": b.description}
            for a, b in self._bindings.items()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KeyBindings":
        kb = cls()
        for action_str, info in data.items():
            try:
                action = KeyAction(int(action_str))
                kb.rebind(action, info.get("keys", []))
            except (ValueError, KeyError):
                continue
        return kb


DEFAULT_BINDINGS: list[KeyBinding] = [
    # Movement (vi-keys + arrows + wasd)
    KeyBinding(KeyAction.MOVE_NORTH, ["k", "up", "w"], "Move north"),
    KeyBinding(KeyAction.MOVE_SOUTH, ["j", "down", "s"], "Move south"),
    KeyBinding(KeyAction.MOVE_EAST, ["l", "right", "d"], "Move east"),
    KeyBinding(KeyAction.MOVE_WEST, ["h", "left", "a"], "Move west"),
    KeyBinding(KeyAction.MOVE_NORTHEAST, ["u"], "Move northeast"),
    KeyBinding(KeyAction.MOVE_NORTHWEST, ["y"], "Move northwest"),
    KeyBinding(KeyAction.MOVE_SOUTHEAST, ["n"], "Move southeast"),
    KeyBinding(KeyAction.MOVE_SOUTHWEST, ["b"], "Move southwest"),
    KeyBinding(KeyAction.MOVE_UP, [">", "+"], "Ascend"),
    KeyBinding(KeyAction.MOVE_DOWN, ["<", "-"], "Descend"),
    # Wait / rest
    KeyBinding(KeyAction.WAIT, ["."], "Wait one tick"),
    KeyBinding(KeyAction.REST, ["r"], "Rest"),
    KeyBinding(KeyAction.SLEEP, ["R"], "Sleep"),
    # UI
    KeyBinding(KeyAction.OPEN_INVENTORY, ["i"], "Open inventory"),
    KeyBinding(KeyAction.OPEN_CHARACTER, ["c", "@"], "Open character sheet"),
    KeyBinding(KeyAction.OPEN_QUESTS, ["q"], "Open quest log"),
    KeyBinding(KeyAction.OPEN_MAP, ["m"], "Open world map"),
    KeyBinding(KeyAction.OPEN_HELP, ["?", "F1"], "Open help"),
    KeyBinding(KeyAction.OPEN_SPELLS, ["S"], "Open spell book"),
    KeyBinding(KeyAction.OPEN_SKILLS, ["K"], "Open skills list"),
    KeyBinding(KeyAction.OPEN_MENU, ["escape", "M"], "Open menu"),
    KeyBinding(KeyAction.CLOSE_PANEL, ["escape", "q"], "Close current panel"),
    # Combat
    KeyBinding(KeyAction.ATTACK, ["a"], "Attack"),
    KeyBinding(KeyAction.CAST_SPELL, ["z"], "Cast spell"),
    KeyBinding(KeyAction.USE_ITEM, ["u"], "Use item"),
    KeyBinding(KeyAction.INTERACT, ["e"], "Interact"),
    # Communication
    KeyBinding(KeyAction.TALK, ["t"], "Talk"),
    KeyBinding(KeyAction.SHOUT, ["T"], "Shout"),
    # System
    KeyBinding(KeyAction.SAVE, ["F5"], "Quicksave"),
    KeyBinding(KeyAction.LOAD, ["F9"], "Quickload"),
    KeyBinding(KeyAction.QUIT, ["Q"], "Quit"),
    KeyBinding(KeyAction.PAUSE, [" "], "Pause"),
    # Camera
    KeyBinding(KeyAction.LOOK, ["x"], "Look around"),
    KeyBinding(KeyAction.CENTER_ON_PLAYER, ["C"], "Center camera on player"),
    # Selection
    KeyBinding(KeyAction.CONFIRM, ["enter"], "Confirm"),
    KeyBinding(KeyAction.CANCEL, ["escape"], "Cancel"),
    KeyBinding(KeyAction.TAB, ["tab"], "Next"),
    KeyBinding(KeyAction.SHIFT_TAB, ["shift+tab"], "Previous"),
    # Quick slots
    KeyBinding(KeyAction.QUICK_SLOT_1, ["1"], "Quick slot 1"),
    KeyBinding(KeyAction.QUICK_SLOT_2, ["2"], "Quick slot 2"),
    KeyBinding(KeyAction.QUICK_SLOT_3, ["3"], "Quick slot 3"),
    KeyBinding(KeyAction.QUICK_SLOT_4, ["4"], "Quick slot 4"),
    KeyBinding(KeyAction.QUICK_SLOT_5, ["5"], "Quick slot 5"),
    KeyBinding(KeyAction.QUICK_SLOT_6, ["6"], "Quick slot 6"),
    KeyBinding(KeyAction.QUICK_SLOT_7, ["7"], "Quick slot 7"),
    KeyBinding(KeyAction.QUICK_SLOT_8, ["8"], "Quick slot 8"),
    KeyBinding(KeyAction.QUICK_SLOT_9, ["9"], "Quick slot 9"),
    KeyBinding(KeyAction.QUICK_SLOT_0, ["0"], "Quick slot 0"),
    # Command history
    KeyBinding(KeyAction.HISTORY_PREV, ["up"], "Previous command"),
    KeyBinding(KeyAction.HISTORY_NEXT, ["down"], "Next command"),
    KeyBinding(KeyAction.AUTOCOMPLETE, ["tab"], "Autocomplete"),
]
