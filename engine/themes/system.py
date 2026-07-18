"""UI themes — colour palettes and visual styles.

A theme defines colour codes for various UI elements (background, foreground,
health, mana, etc.). Themes can be switched at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Optional


@dataclass
class ThemeColor:
    """A colour role and its ANSI code."""

    role: str  # background, foreground, accent, health, mana, etc.
    code: int  # ANSI 256-colour code


@dataclass
class Theme:
    """A complete UI theme."""

    name: str
    description: str
    colors: dict[str, int] = field(default_factory=dict)
    is_dark: bool = True
    font_recommendation: str = "monospace"

    def get(self, role: str, default: int = 244) -> int:
        return self.colors.get(role, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "description": self.description,
            "colors": dict(self.colors), "is_dark": self.is_dark,
            "font_recommendation": self.font_recommendation,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        return cls(
            name=data["name"], description=data.get("description", ""),
            colors=dict(data.get("colors", {})),
            is_dark=data.get("is_dark", True),
            font_recommendation=data.get("font_recommendation", "monospace"),
        )


class ThemeLibrary:
    """Registry of themes."""

    _themes: ClassVar[dict[str, Theme]] = {}
    _defaults_loaded: ClassVar[bool] = False

    @classmethod
    def register(cls, theme: Theme) -> None:
        if not cls._defaults_loaded:
            cls._init_defaults()
        cls._themes[theme.name] = theme

    @classmethod
    def get(cls, name: str) -> Optional[Theme]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return cls._themes.get(name)

    @classmethod
    def all(cls) -> list[Theme]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return list(cls._themes.values())

    @classmethod
    def names(cls) -> list[str]:
        if not cls._defaults_loaded:
            cls._init_defaults()
        return sorted(cls._themes.keys())

    @classmethod
    def _init_defaults(cls) -> None:
        if cls._defaults_loaded:
            return
        for t in DEFAULT_THEMES:
            cls._themes[t.name] = t
        cls._defaults_loaded = True


DEFAULT_THEMES: list[Theme] = [
    Theme(
        name="dark", description="Classic dark theme.",
        is_dark=True,
        colors={
            "background": 232, "foreground": 244,
            "accent": 75, "border": 240, "title": 220,
            "health": 196, "mana": 33, "stamina": 41,
            "experience": 215, "danger": 196, "warning": 215,
            "success": 41, "info": 33, "muted": 240,
            "highlight": 255, "selected": 165, "player": 255,
            "npc": 215, "hostile": 196, "creature": 130,
            "water": 33, "fire": 196, "earth": 130,
            "air": 255, "magic": 165, "holy": 255,
            "shadow": 90, "gold": 220, "silver": 250,
        },
    ),
    Theme(
        name="light", description="Light background theme.",
        is_dark=False,
        colors={
            "background": 255, "foreground": 232,
            "accent": 21, "border": 248, "title": 124,
            "health": 124, "mana": 21, "stamina": 22,
            "experience": 130, "danger": 124, "warning": 130,
            "success": 22, "info": 21, "muted": 248,
            "highlight": 232, "selected": 165, "player": 232,
            "npc": 130, "hostile": 124, "creature": 94,
            "water": 21, "fire": 124, "earth": 94,
            "air": 232, "magic": 91, "holy": 232,
            "shadow": 91, "gold": 130, "silver": 248,
        },
    ),
    Theme(
        name="solarized_dark", description="Solarized dark palette.",
        is_dark=True,
        colors={
            "background": 234, "foreground": 187,
            "accent": 38, "border": 240, "title": 136,
            "health": 160, "mana": 33, "stamina": 71,
            "experience": 136, "danger": 160, "warning": 166,
            "success": 71, "info": 33, "muted": 241,
            "highlight": 230, "selected": 162, "player": 230,
            "npc": 136, "hostile": 160, "creature": 100,
            "water": 33, "fire": 160, "earth": 100,
            "air": 244, "magic": 162, "holy": 230,
            "shadow": 96, "gold": 136, "silver": 248,
        },
    ),
    Theme(
        name="monokai", description="Monokai-inspired theme.",
        is_dark=True,
        colors={
            "background": 235, "foreground": 231,
            "accent": 81, "border": 238, "title": 186,
            "health": 197, "mana": 81, "stamina": 154,
            "experience": 208, "danger": 197, "warning": 208,
            "success": 154, "info": 81, "muted": 242,
            "highlight": 231, "selected": 141, "player": 231,
            "npc": 186, "hostile": 197, "creature": 173,
            "water": 81, "fire": 197, "earth": 173,
            "air": 231, "magic": 141, "holy": 230,
            "shadow": 95, "gold": 186, "silver": 250,
        },
    ),
    Theme(
        name="dracula", description="Dracula-inspired theme.",
        is_dark=True,
        colors={
            "background": 234, "foreground": 231,
            "accent": 141, "border": 238, "title": 213,
            "health": 203, "mana": 117, "stamina": 120,
            "experience": 215, "danger": 203, "warning": 215,
            "success": 120, "info": 117, "muted": 245,
            "highlight": 231, "selected": 141, "player": 231,
            "npc": 215, "hostile": 203, "creature": 137,
            "water": 117, "fire": 203, "earth": 137,
            "air": 231, "magic": 141, "holy": 231,
            "shadow": 97, "gold": 215, "silver": 250,
        },
    ),
    Theme(
        name="nord", description="Nord-inspired theme.",
        is_dark=True,
        colors={
            "background": 235, "foreground": 188,
            "accent": 110, "border": 239, "title": 179,
            "health": 174, "mana": 110, "stamina": 150,
            "experience": 179, "danger": 174, "warning": 179,
            "success": 150, "info": 110, "muted": 240,
            "highlight": 231, "selected": 140, "player": 231,
            "npc": 179, "hostile": 174, "creature": 137,
            "water": 110, "fire": 174, "earth": 137,
            "air": 188, "magic": 140, "holy": 231,
            "shadow": 97, "gold": 179, "silver": 245,
        },
    ),
    Theme(
        name="gruvbox", description="Gruvbox-inspired theme.",
        is_dark=True,
        colors={
            "background": 235, "foreground": 223,
            "accent": 109, "border": 239, "title": 214,
            "health": 167, "mana": 109, "stamina": 142,
            "experience": 214, "danger": 167, "warning": 214,
            "success": 142, "info": 109, "muted": 245,
            "highlight": 230, "selected": 132, "player": 230,
            "npc": 214, "hostile": 167, "creature": 137,
            "water": 109, "fire": 167, "earth": 137,
            "air": 223, "magic": 132, "holy": 230,
            "shadow": 95, "gold": 214, "silver": 245,
        },
    ),
    Theme(
        name="high_contrast", description="Maximum-contrast theme for accessibility.",
        is_dark=True,
        colors={
            "background": 0, "foreground": 15,
            "accent": 14, "border": 7, "title": 11,
            "health": 12, "mana": 9, "stamina": 10,
            "experience": 11, "danger": 12, "warning": 11,
            "success": 10, "info": 14, "muted": 8,
            "highlight": 15, "selected": 13, "player": 15,
            "npc": 11, "hostile": 12, "creature": 6,
            "water": 9, "fire": 12, "earth": 6,
            "air": 15, "magic": 13, "holy": 15,
            "shadow": 5, "gold": 11, "silver": 7,
        },
    ),
]
