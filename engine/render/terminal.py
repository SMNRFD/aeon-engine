"""Terminal rendering primitives — ANSI colours, styles, cursor control."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional


# ANSI escape sequences
class ANSI:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    REVERSE = "\033[7m"
    HIDDEN = "\033[8m"

    # Cursor
    CURSOR_HIDE = "\033[?25l"
    CURSOR_SHOW = "\033[?25h"
    CURSOR_SAVE = "\0337"
    CURSOR_RESTORE = "\0338"
    CLEAR_SCREEN = "\033[2J"
    CLEAR_LINE = "\033[2K"
    CLEAR_TO_END = "\033[0K"

    @staticmethod
    def move(x: int, y: int) -> str:
        return f"\033[{y + 1};{x + 1}H"

    @staticmethod
    def move_up(n: int = 1) -> str:
        return f"\033[{n}A"

    @staticmethod
    def move_down(n: int = 1) -> str:
        return f"\033[{n}B"

    @staticmethod
    def move_right(n: int = 1) -> str:
        return f"\033[{n}C"

    @staticmethod
    def move_left(n: int = 1) -> str:
        return f"\033[{n}D"

    @staticmethod
    def fg(color: int) -> str:
        """Set foreground colour (256-colour)."""
        return f"\033[38;5;{color}m"

    @staticmethod
    def bg(color: int) -> str:
        """Set background colour (256-colour)."""
        return f"\033[48;5;{color}m"

    @staticmethod
    def fg_rgb(r: int, g: int, b: int) -> str:
        return f"\033[38;2;{r};{g};{b}m"

    @staticmethod
    def bg_rgb(r: int, g: int, b: int) -> str:
        return f"\033[48;2;{r};{g};{b}m"


class Color:
    """Common colours (256-colour codes)."""
    BLACK = 0
    RED = 196
    GREEN = 41
    YELLOW = 215
    BLUE = 33
    MAGENTA = 165
    CYAN = 51
    WHITE = 255
    GRAY = 244
    DARK_GRAY = 240
    LIGHT_GRAY = 248

    BROWN = 130
    ORANGE = 208
    PINK = 211
    PURPLE = 99
    TEAL = 37
    LIME = 154
    GOLD = 220
    SILVER = 250

    # UI semantic
    HEALTH = 196
    MANA = 33
    STAMINA = 41
    EXPERIENCE = 215
    DANGER = 196
    WARNING = 215
    SUCCESS = 41
    INFO = 33
    MUTED = 240


class Style:
    BOLD = ANSI.BOLD
    DIM = ANSI.DIM
    ITALIC = ANSI.ITALIC
    UNDERLINE = ANSI.UNDERLINE
    REVERSE = ANSI.REVERSE


class Cursor:
    HIDE = ANSI.CURSOR_HIDE
    SHOW = ANSI.CURSOR_SHOW
    SAVE = ANSI.CURSOR_SAVE
    RESTORE = ANSI.CURSOR_RESTORE


@dataclass
class Cell:
    """A single terminal cell."""

    char: str = " "
    fg: int = Color.WHITE
    bg: int = -1
    style: str = ""


class TerminalRenderer:
    """A double-buffered terminal renderer.

    Renders to stdout using ANSI escape codes. Supports:
    * 256-colour foreground and background
    * Bold/italic/underline styles
    * Cursor movement
    * Double-buffered rendering (only diffs are flushed)
    """

    def __init__(self, width: int = 80, height: int = 24,
                 use_color: bool = True) -> None:
        self.width = width
        self.height = height
        self.use_color = use_color and self._color_supported()
        self._front: list[list[Cell]] = self._new_buffer()
        self._back: list[list[Cell]] = self._new_buffer()
        self._initialized = False

    def _color_supported(self) -> bool:
        return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"

    def _new_buffer(self) -> list[list[Cell]]:
        return [[Cell() for _ in range(self.width)] for _ in range(self.height)]

    def clear(self) -> None:
        self._back = self._new_buffer()

    def set_cell(self, x: int, y: int, char: str, fg: int = Color.WHITE,
                 bg: int = -1, style: str = "") -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        if len(char) > 1:
            char = char[0]
        self._back[y][x] = Cell(char=char or " ", fg=fg, bg=bg, style=style)

    def write_text(self, x: int, y: int, text: str, fg: int = Color.WHITE,
                   bg: int = -1, style: str = "",
                   truncate: bool = True) -> None:
        for i, ch in enumerate(text):
            if truncate and x + i >= self.width:
                break
            self.set_cell(x + i, y, ch, fg=fg, bg=bg, style=style)

    def write_centered(self, y: int, text: str, fg: int = Color.WHITE,
                       bg: int = -1, style: str = "") -> None:
        x = max(0, (self.width - len(text)) // 2)
        self.write_text(x, y, text, fg=fg, bg=bg, style=style)

    def fill_rect(self, x: int, y: int, w: int, h: int, char: str = " ",
                  fg: int = Color.WHITE, bg: int = -1) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set_cell(xx, yy, char, fg=fg, bg=bg)

    def draw_box(self, x: int, y: int, w: int, h: int,
                 title: Optional[str] = None, fg: int = Color.WHITE,
                 bg: int = -1) -> None:
        if w < 2 or h < 2:
            return
        self.set_cell(x, y, "┌", fg=fg, bg=bg)
        self.set_cell(x + w - 1, y, "┐", fg=fg, bg=bg)
        self.set_cell(x, y + h - 1, "└", fg=fg, bg=bg)
        self.set_cell(x + w - 1, y + h - 1, "┘", fg=fg, bg=bg)
        for i in range(1, w - 1):
            self.set_cell(x + i, y, "─", fg=fg, bg=bg)
            self.set_cell(x + i, y + h - 1, "─", fg=fg, bg=bg)
        for j in range(1, h - 1):
            self.set_cell(x, y + j, "│", fg=fg, bg=bg)
            self.set_cell(x + w - 1, y + j, "│", fg=fg, bg=bg)
        if title:
            tx = x + 2
            self.write_text(tx, y, f" {title} ", fg=fg, bg=bg, style=Style.BOLD)

    def render(self) -> None:
        """Flush differences to stdout."""
        out: list[str] = []
        if not self._initialized:
            out.append(ANSI.CLEAR_SCREEN)
            out.append(ANSI.CURSOR_HIDE)
            self._initialized = True
        for y in range(self.height):
            for x in range(self.width):
                front = self._front[y][x]
                back = self._back[y][x]
                if (front.char != back.char or front.fg != back.fg
                        or front.bg != back.bg or front.style != back.style):
                    out.append(ANSI.move(x, y))
                    if self.use_color:
                        out.append(ANSI.fg(back.fg))
                        if back.bg >= 0:
                            out.append(ANSI.bg(back.bg))
                        if back.style:
                            out.append(back.style)
                    out.append(back.char)
                    if self.use_color:
                        out.append(ANSI.RESET)
                    self._front[y][x] = Cell(
                        char=back.char, fg=back.fg, bg=back.bg, style=back.style,
                    )
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    def shutdown(self) -> None:
        sys.stdout.write(ANSI.CURSOR_SHOW + ANSI.RESET + ANSI.CLEAR_SCREEN)
        sys.stdout.flush()

    def get_input(self) -> Optional[str]:
        """Read a single line of input from the user."""
        sys.stdout.write(ANSI.CURSOR_SHOW)
        sys.stdout.flush()
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            return None
        finally:
            sys.stdout.write(ANSI.CURSOR_HIDE)
            sys.stdout.flush()
        return line
