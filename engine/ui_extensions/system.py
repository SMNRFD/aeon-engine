"""UI extensions — search, filtering, mouse support, sortable lists."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Optional

from engine.core.logging import get_logger


log = get_logger("ui.extensions")


class SortOrder(IntEnum):
    ASCENDING = 0
    DESCENDING = 1


@dataclass
class FilterCriteria:
    """A filter criterion for a list."""

    field_name: str
    value: Any
    operator: str = "=="  # ==, !=, >, <, >=, <=, contains, starts_with, ends_with

    def matches(self, item: Any) -> bool:
        if not hasattr(item, self.field_name):
            # Try dict-like access
            if isinstance(item, dict):
                item_value = item.get(self.field_name)
            else:
                return False
        else:
            item_value = getattr(item, self.field_name)
        if self.operator == "==":
            return item_value == self.value
        if self.operator == "!=":
            return item_value != self.value
        if self.operator == ">":
            return item_value > self.value
        if self.operator == "<":
            return item_value < self.value
        if self.operator == ">=":
            return item_value >= self.value
        if self.operator == "<=":
            return item_value <= self.value
        if self.operator == "contains":
            return self.value in item_value if hasattr(item_value, "__contains__") else False
        if self.operator == "starts_with":
            return str(item_value).startswith(str(self.value))
        if self.operator == "ends_with":
            return str(item_value).endswith(str(self.value))
        return False


@dataclass
class SearchFilter:
    """A combined search and filter for lists."""

    query: str = ""
    criteria: list[FilterCriteria] = field(default_factory=list)
    sort_field: Optional[str] = None
    sort_order: SortOrder = SortOrder.ASCENDING
    case_sensitive: bool = False

    def matches(self, item: Any) -> bool:
        # Check text query
        if self.query:
            item_str = str(item).lower() if not self.case_sensitive else str(item)
            query = self.query if self.case_sensitive else self.query.lower()
            if query not in item_str:
                return False
        # Check all criteria
        for criterion in self.criteria:
            if not criterion.matches(item):
                return False
        return True

    def filter(self, items: list[Any]) -> list[Any]:
        result = [item for item in items if self.matches(item)]
        if self.sort_field:
            result.sort(
                key=lambda x: getattr(x, self.sort_field, 0)
                              if not isinstance(x, dict)
                              else x.get(self.sort_field, 0),
                reverse=(self.sort_order == SortOrder.DESCENDING),
            )
        return result


class SortableList:
    """A list that can be sorted by various fields."""

    def __init__(self, items: Optional[list[Any]] = None) -> None:
        self._items: list[Any] = list(items or [])
        self._sort_field: Optional[str] = None
        self._sort_order: SortOrder = SortOrder.ASCENDING

    def add(self, item: Any) -> None:
        self._items.append(item)
        if self._sort_field:
            self.sort(self._sort_field, self._sort_order)

    def remove(self, item: Any) -> bool:
        try:
            self._items.remove(item)
            return True
        except ValueError:
            return False

    def sort(self, field_name: str, order: SortOrder = SortOrder.ASCENDING) -> None:
        self._sort_field = field_name
        self._sort_order = order
        self._items.sort(
            key=lambda x: getattr(x, field_name, 0)
                          if not isinstance(x, dict)
                          else x.get(field_name, 0),
            reverse=(order == SortOrder.DESCENDING),
        )

    def filter(self, criteria: list[FilterCriteria]) -> list[Any]:
        return [item for item in self._items
                if all(c.matches(item) for c in criteria)]

    def search(self, query: str) -> list[Any]:
        query_lower = query.lower()
        return [item for item in self._items
                if query_lower in str(item).lower()]

    @property
    def items(self) -> list[Any]:
        return list(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)


@dataclass
class MouseClick:
    """A mouse click event."""

    x: int
    y: int
    button: str = "left"  # left, right, middle
    is_double: bool = False
    is_drag: bool = False
    modifiers: list[str] = field(default_factory=list)  # ctrl, shift, alt


class MouseInput:
    """Mouse input handler.

    In a terminal environment, mouse support is provided via:
    * ANSI escape sequences for SGR mouse mode
    * Click position is reported in (row, col)
    * Button events: press, release, drag
    """

    def __init__(self) -> None:
        self._enabled: bool = False
        self._click_handlers: list[Callable[[MouseClick], None]] = []
        self._drag_handlers: list[Callable[[MouseClick], None]] = []
        self._last_click: Optional[MouseClick] = None
        self._drag_start: Optional[MouseClick] = None

    def enable(self) -> None:
        """Enable mouse tracking in the terminal."""
        import sys
        # SGR mouse mode: \033[?1000h \033[?1006h
        sys.stdout.write("\033[?1000h\033[?1006h")
        sys.stdout.flush()
        self._enabled = True
        log.debug("Mouse tracking enabled")

    def disable(self) -> None:
        """Disable mouse tracking."""
        import sys
        sys.stdout.write("\033[?1000l\033[?1006l")
        sys.stdout.flush()
        self._enabled = False
        log.debug("Mouse tracking disabled")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def on_click(self, handler: Callable[[MouseClick], None]) -> None:
        self._click_handlers.append(handler)

    def on_drag(self, handler: Callable[[MouseClick], None]) -> None:
        self._drag_handlers.append(handler)

    def parse_sgr_event(self, data: str) -> Optional[MouseClick]:
        """Parse an SGR mouse mode escape sequence.

        Format: \033[<button;x;ym for press, M for release
        """
        if not data.startswith("\033[<"):
            return None
        try:
            body = data[3:]  # skip \033[<
            # Find the trailing M or m
            if body.endswith("M"):
                action = "press"
                body = body[:-1]
            elif body.endswith("m"):
                action = "release"
                body = body[:-1]
            else:
                return None
            parts = body.split(";")
            if len(parts) != 3:
                return None
            button_code = int(parts[0])
            x = int(parts[1]) - 1  # 0-indexed
            y = int(parts[2]) - 1
            # Decode button
            button = "left"
            if button_code == 0:
                button = "left"
            elif button_code == 1:
                button = "middle"
            elif button_code == 2:
                button = "right"
            elif button_code == 32:
                button = "left"  # drag
            elif button_code == 33:
                button = "middle"  # drag
            elif button_code == 34:
                button = "right"  # drag
            is_drag = 32 <= button_code <= 34
            click = MouseClick(x=x, y=y, button=button, is_drag=is_drag)
            if action == "press":
                if self._last_click and self._is_double(self._last_click, click):
                    click.is_double = True
                self._last_click = click
                if not is_drag:
                    self._drag_start = click
                for handler in self._click_handlers:
                    handler(click)
            elif action == "release":
                if is_drag and self._drag_start:
                    for handler in self._drag_handlers:
                        handler(click)
                self._drag_start = None
            return click
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _is_double(click1: MouseClick, click2: MouseClick) -> bool:
        import time
        # In real use, we'd track timestamps
        return (click1.x == click2.x and click1.y == click2.y
                and click1.button == click2.button)


class UIStateManager:
    """Manages UI state — focus, selection, scroll position."""

    def __init__(self) -> None:
        self._focus: Optional[str] = None  # focused widget name
        self._selection: dict[str, Any] = {}  # widget_name -> selected index
        self._scroll: dict[str, int] = {}  # widget_name -> scroll position
        self._expanded: dict[str, bool] = {}  # widget_name -> expanded state

    def set_focus(self, widget_name: str) -> None:
        self._focus = widget_name

    @property
    def focus(self) -> Optional[str]:
        return self._focus

    def set_selection(self, widget_name: str, index: Any) -> None:
        self._selection[widget_name] = index

    def get_selection(self, widget_name: str) -> Any:
        return self._selection.get(widget_name)

    def scroll_up(self, widget_name: str, amount: int = 1) -> None:
        current = self._scroll.get(widget_name, 0)
        self._scroll[widget_name] = max(0, current - amount)

    def scroll_down(self, widget_name: str, amount: int = 1,
                    max_scroll: int = 100) -> None:
        current = self._scroll.get(widget_name, 0)
        self._scroll[widget_name] = min(max_scroll, current + amount)

    def get_scroll(self, widget_name: str) -> int:
        return self._scroll.get(widget_name, 0)

    def set_scroll(self, widget_name: str, position: int) -> None:
        self._scroll[widget_name] = max(0, position)

    def toggle_expanded(self, widget_name: str) -> bool:
        current = self._expanded.get(widget_name, False)
        self._expanded[widget_name] = not current
        return self._expanded[widget_name]

    def is_expanded(self, widget_name: str) -> bool:
        return self._expanded.get(widget_name, False)

    def reset(self) -> None:
        self._focus = None
        self._selection.clear()
        self._scroll.clear()
        self._expanded.clear()
