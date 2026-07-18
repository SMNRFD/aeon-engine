"""Accessibility system — screen reader, colorblindness, large text, reduced motion."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Optional

from engine.core.logging import get_logger


log = get_logger("accessibility")


class ColorBlindnessType(IntEnum):
    NONE = 0
    PROTANOPIA = 1      # red-blind
    DEUTERANOPIA = 2    # green-blind
    TRITANOPIA = 3      # blue-blind
    ACHROMATOPSIA = 4   # total colorblindness


@dataclass
class ScreenReaderMode:
    """Configuration for screen-reader-friendly output."""

    enabled: bool = False
    describe_position: bool = True
    describe_visuals: bool = True
    verbose_combat: bool = True
    announce_status_changes: bool = True
    speak_threshold_hp: int = 25  # announce HP when below this percent

    def describe(self, text: str) -> str:
        """Wrap a visual text in a screen-reader description."""
        if not self.enabled:
            return text
        return f"[{text}]"


@dataclass
class AccessibilityConfig:
    """User accessibility preferences."""

    screen_reader = ScreenReaderMode()
    color_blindness: ColorBlindnessType = ColorBlindnessType.NONE
    large_text: bool = False
    high_contrast: bool = False
    reduced_motion: bool = False
    audio_cues: bool = True
    text_to_speech: bool = False
    caption_sounds: bool = False  # show sound descriptions as text
    slow_text_speed: bool = False
    disable_flashing: bool = False
    keyboard_only: bool = False  # disable mouse

    def to_dict(self) -> dict[str, Any]:
        return {
            "color_blindness": int(self.color_blindness),
            "large_text": self.large_text,
            "high_contrast": self.high_contrast,
            "reduced_motion": self.reduced_motion,
            "audio_cues": self.audio_cues,
            "text_to_speech": self.text_to_speech,
            "caption_sounds": self.caption_sounds,
            "slow_text_speed": self.slow_text_speed,
            "disable_flashing": self.disable_flashing,
            "keyboard_only": self.keyboard_only,
            "screen_reader": {
                "enabled": self.screen_reader.enabled,
                "describe_position": self.screen_reader.describe_position,
                "describe_visuals": self.screen_reader.describe_visuals,
                "verbose_combat": self.screen_reader.verbose_combat,
                "announce_status_changes": self.screen_reader.announce_status_changes,
                "speak_threshold_hp": self.screen_reader.speak_threshold_hp,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccessibilityConfig":
        cfg = cls()
        cfg.color_blindness = ColorBlindnessType(data.get("color_blindness", 0))
        cfg.large_text = data.get("large_text", False)
        cfg.high_contrast = data.get("high_contrast", False)
        cfg.reduced_motion = data.get("reduced_motion", False)
        cfg.audio_cues = data.get("audio_cues", True)
        cfg.text_to_speech = data.get("text_to_speech", False)
        cfg.caption_sounds = data.get("caption_sounds", False)
        cfg.slow_text_speed = data.get("slow_text_speed", False)
        cfg.disable_flashing = data.get("disable_flashing", False)
        cfg.keyboard_only = data.get("keyboard_only", False)
        sr = data.get("screen_reader", {})
        cfg.screen_reader.enabled = sr.get("enabled", False)
        cfg.screen_reader.describe_position = sr.get("describe_position", True)
        cfg.screen_reader.describe_visuals = sr.get("describe_visuals", True)
        cfg.screen_reader.verbose_combat = sr.get("verbose_combat", True)
        cfg.screen_reader.announce_status_changes = sr.get("announce_status_changes", True)
        cfg.screen_reader.speak_threshold_hp = sr.get("speak_threshold_hp", 25)
        return cfg


class AccessibilitySystem:
    """Applies accessibility transforms to output."""

    # Color remapping tables for colorblindness
    _PROTANOPIA_MAP: dict[int, int] = {
        196: 208,  # red -> orange
        124: 130,
        160: 166,
        9: 208,
        1: 130,
    }
    _DEUTERANOPIA_MAP: dict[int, int] = {
        41: 51,   # green -> cyan
        22: 30,
        34: 36,
        10: 51,
        2: 30,
    }
    _TRITANOPIA_MAP: dict[int, int] = {
        33: 165,  # blue -> magenta
        21: 57,
        27: 63,
        12: 165,
        4: 57,
    }
    _ACHROMATOPSIA_MAP: dict[int, int] = {
        # Map all colors to grayscale equivalents (simplified)
        196: 124, 41: 71, 33: 75, 215: 179, 165: 138,
        130: 130, 220: 220, 250: 250, 244: 244, 240: 240,
    }

    def __init__(self, config: Optional[AccessibilityConfig] = None) -> None:
        self.config = config or AccessibilityConfig()

    def adjust_color(self, color: int) -> int:
        """Apply colorblindness remapping."""
        cb = self.config.color_blindness
        if cb == ColorBlindnessType.NONE:
            return color
        if cb == ColorBlindnessType.PROTANOPIA:
            return self._PROTANOPIA_MAP.get(color, color)
        if cb == ColorBlindnessType.DEUTERANOPIA:
            return self._DEUTERANOPIA_MAP.get(color, color)
        if cb == ColorBlindnessType.TRITANOPIA:
            return self._TRITANOPIA_MAP.get(color, color)
        if cb == ColorBlindnessType.ACHROMATOPSIA:
            return self._ACHROMATOPSIA_MAP.get(color, color)
        return color

    def describe_visual(self, text: str) -> str:
        """Wrap visual output for screen readers."""
        if self.config.screen_reader.enabled and self.config.screen_reader.describe_visuals:
            return self.config.screen_reader.describe(text)
        return text

    def should_announce(self, hp_percent: int) -> bool:
        """Should we announce HP change?"""
        if not self.config.screen_reader.enabled:
            return False
        if not self.config.screen_reader.announce_status_changes:
            return False
        return hp_percent <= self.config.screen_reader.speak_threshold_hp

    def filter_text(self, text: str) -> str:
        """Filter flashing/animated text if reduced motion is enabled."""
        if self.config.disable_flashing:
            # Remove ANSI blink codes
            text = text.replace("\033[5m", "")
        if self.config.slow_text_speed:
            # In a real impl, we'd add delays between characters
            pass
        return text

    def caption_sound(self, sound_id: str, description: str) -> Optional[str]:
        """Return a text caption for a sound, if captioning is enabled."""
        if self.config.caption_sounds:
            return f"♪ {sound_id}: {description}"
        return None
