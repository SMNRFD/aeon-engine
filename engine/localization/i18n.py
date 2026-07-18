"""Internationalization — locale management, pluralization, RTL."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Optional


@dataclass(frozen=True)
class Locale:
    """A locale identifier."""

    code: str           # e.g. "en_US"
    language: str       # e.g. "en"
    region: str = ""    # e.g. "US"
    rtl: bool = False   # right-to-left?
    display_name: str = ""

    @classmethod
    def parse(cls, code: str) -> "Locale":
        parts = code.replace("-", "_").split("_")
        lang = parts[0]
        region = parts[1] if len(parts) > 1 else ""
        rtl = lang in {"ar", "he", "fa", "ur"}
        display = code
        return cls(code=code, language=lang, region=region, rtl=rtl, display_name=display)


class PluralRule:
    """Simple plural-rule implementation (English-style by default)."""

    @staticmethod
    def category(n: int, locale: str = "en") -> str:
        """Return the plural category: 'one', 'few', 'many', 'other'."""
        lang = locale.split("_")[0].lower()
        if lang in {"en", "de", "es", "it", "nl", "sv", "da", "no", "pt"}:
            return "one" if n == 1 else "other"
        if lang in {"fr", "tl"}:
            return "one" if n in (0, 1) else "other"
        if lang == "ru":
            if n % 10 == 1 and n % 100 != 11:
                return "one"
            if 2 <= n % 10 <= 4 and not (10 <= n % 100 <= 20):
                return "few"
            return "many"
        if lang == "ar":
            if n == 0:
                return "zero"
            if n == 1:
                return "one"
            if n == 2:
                return "two"
            if 3 <= n % 100 <= 10:
                return "few"
            if 11 <= n % 100 <= 99:
                return "many"
            return "other"
        if lang in {"zh", "ja", "ko", "vi", "th"}:
            return "other"
        return "one" if n == 1 else "other"


class I18n:
    """Internationalization manager."""

    DEFAULT_LOCALE = "en_US"

    def __init__(self, locale: str = DEFAULT_LOCALE) -> None:
        self.locale = Locale.parse(locale)
        self._strings: dict[str, dict[str, str]] = {self.DEFAULT_LOCALE: dict(DEFAULT_STRINGS)}
        self._fallback: str = self.DEFAULT_LOCALE
        self._loaded_locales: set[str] = {self.DEFAULT_LOCALE}

    def set_locale(self, code: str) -> None:
        self.locale = Locale.parse(code)
        if code not in self._loaded_locales:
            self._load_locale(code)

    def add_strings(self, locale: str, strings: dict[str, str]) -> None:
        self._strings.setdefault(locale, {}).update(strings)
        self._loaded_locales.add(locale)

    def t(self, key: str, **kwargs: Any) -> str:
        """Translate `key` with optional format arguments."""
        template = self._lookup(key)
        if template is None:
            return key
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template

    def tn(self, key: str, n: int, **kwargs: Any) -> str:
        """Translate with plural form selection. Looks up `<key>.one`, `<key>.few`,
        `<key>.many`, `<key>.other` based on the locale's plural rule."""
        category = PluralRule.category(n, self.locale.code)
        full_key = f"{key}.{category}"
        template = self._lookup(full_key)
        if template is None:
            # Fall back to base key
            template = self._lookup(key)
            if template is None:
                return f"{key}.{category}"
        kwargs["n"] = n
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template

    def _lookup(self, key: str) -> Optional[str]:
        # Try current locale, then fallback, then default
        for locale in [self.locale.code, self._fallback, self.DEFAULT_LOCALE]:
            strings = self._strings.get(locale, {})
            if key in strings:
                return strings[key]
        return None

    def _load_locale(self, code: str) -> None:
        """Attempt to load a locale from `localization/<code>.json`."""
        path = Path("localization") / f"{code}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.add_strings(code, data)
            except Exception:
                pass
        self._loaded_locales.add(code)

    @property
    def rtl(self) -> bool:
        return self.locale.rtl

    def available_locales(self) -> list[str]:
        return sorted(self._loaded_locales)


# Default English strings
DEFAULT_STRINGS: dict[str, str] = {
    "ui.title": "Aeon Engine",
    "ui.subtitle": "A Text-Based Open-World RPG",
    "ui.prompt": "> ",
    "ui.unknown_command": "Unknown command: {cmd}",
    "ui.welcome": "Welcome to Aeon. Type 'help' for commands.",
    "ui.goodbye": "Farewell, traveller.",
    "ui.health": "Health: {current}/{maximum}",
    "ui.level": "Level {n}",
    "ui.gold": "Gold: {n}",
    "ui.time": "Time: {time}",
    "ui.weather": "Weather: {weather}",
    "ui.location": "Location: ({x}, {y})",
    "combat.hit": "{attacker} hits {target} for {damage} damage.",
    "combat.miss": "{attacker} misses {target}.",
    "combat.crit": "{attacker} scores a critical hit on {target} for {damage} damage!",
    "combat.kill": "{target} is slain!",
    "combat.flee": "You flee from combat.",
    "need.hunger": "You are hungry.",
    "need.thirst": "You are thirsty.",
    "need.fatigue": "You are tired.",
    "need.sleep": "You are exhausted.",
    "need.starving": "You are starving!",
    "need.dehydrated": "You are dehydrated!",
    "item.picked_up": "Picked up: {item}",
    "item.dropped": "Dropped: {item}",
    "item.broken": "{item} has broken!",
    "quest.started": "Quest started: {name}",
    "quest.completed": "Quest completed: {name}",
    "quest.failed": "Quest failed: {name}",
    "quest.objective_complete": "Objective complete: {description}",
    "spell.cast": "You cast {name}.",
    "spell.mana_low": "Not enough mana to cast {name}.",
    "dialogue.start": "{npc} says: {text}",
    "dialogue.choose": "Choose:",
    "faction.reputation_up": "Your reputation with {faction} has increased.",
    "faction.reputation_down": "Your reputation with {faction} has decreased.",
    "save.saved": "Game saved as {name}.",
    "save.loaded": "Game loaded: {name}.",
    "save.failed": "Save failed: {error}",
    "error.invalid": "Invalid input: {input}",
    "error.permission": "You don't have permission to do that.",
    # Plural examples
    "item.count.one": "{n} {item}",
    "item.count.other": "{n} {item}s",
    "enemy.killed.one": "Killed {n} enemy.",
    "enemy.killed.other": "Killed {n} enemies.",
}
