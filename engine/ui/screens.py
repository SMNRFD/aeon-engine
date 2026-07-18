"""UI screens — main game view, side panels, character sheet, etc."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from engine.core.ecs import Entity, World
from engine.entities.components import Health, Identity, Needs, Position, Stats
from engine.localization.i18n import I18n
from engine.render.terminal import Color, TerminalRenderer, ANSI, Style
from engine.world.map import WorldMap


@dataclass
class MessageLog:
    """A rolling log of recent messages."""

    max_size: int = 200
    messages: list[tuple[str, int]] = field(default_factory=list)  # (text, color)

    def add(self, text: str, color: int = Color.WHITE) -> None:
        self.messages.append((text, color))
        if len(self.messages) > self.max_size:
            self.messages = self.messages[-self.max_size:]

    def recent(self, n: int = 10) -> list[tuple[str, int]]:
        return self.messages[-n:]


class Screen(ABC):
    """Base class for UI screens."""

    name: str = "screen"

    def __init__(self, renderer: TerminalRenderer, i18n: I18n) -> None:
        self.renderer = renderer
        self.i18n = i18n

    @abstractmethod
    def render(self, engine: Any) -> None: ...


from typing import Any  # noqa: E402


class MainScreen(Screen):
    """The primary game view — map, stats, message log, prompt."""

    name = "main"

    def __init__(self, renderer: TerminalRenderer, i18n: I18n,
                 viewport_w: int = 50, viewport_h: int = 17,
                 log_h: int = 5) -> None:
        super().__init__(renderer, i18n)
        self.viewport_w = viewport_w
        self.viewport_h = viewport_h
        self.log_h = log_h

    def render(self, engine: Any) -> None:
        r = self.renderer
        r.clear()
        # Header
        title = f" {self.i18n.t('ui.title')} — {self.i18n.t('ui.subtitle')} "
        r.write_centered(0, title, fg=Color.GOLD, style=Style.BOLD)
        # Time & weather
        time_str = engine.clock.time.display()
        weather_str = engine.weather.current.description() if engine.weather else ""
        header = f" {time_str} | {weather_str} "
        r.write_text(self.renderer.width - len(header) - 1, 0, header,
                     fg=Color.CYAN)

        player = engine.player
        if player is not None:
            self._render_map(engine)
            self._render_sidebar(engine, player)
        self._render_message_log(engine)
        self._render_prompt(engine)
        r.render()

    def _render_map(self, engine: Any) -> None:
        r = self.renderer
        player = engine.player
        pos = engine.world.get_component(player, Position)
        if pos is None:
            return
        world_map = engine.world_map
        ox = pos.x - self.viewport_w // 2
        oy = pos.y - self.viewport_h // 2
        # Box around the map
        map_x, map_y = 1, 2
        r.draw_box(map_x - 1, map_y - 1, self.viewport_w + 2, self.viewport_h + 2,
                   title="Map", fg=Color.GRAY)
        for j in range(self.viewport_h):
            for i in range(self.viewport_w):
                wx = ox + i
                wy = oy + j
                tile = world_map.get_tile(wx, wy)
                if tile is None:
                    r.set_cell(map_x + i, map_y + j, " ", fg=Color.BLACK)
                    continue
                if not tile.is_explored and not engine.cheat_mode:
                    r.set_cell(map_x + i, map_y + j, " ", fg=Color.BLACK)
                    continue
                if tile.is_visible or engine.cheat_mode:
                    r.set_cell(map_x + i, map_y + j, tile.terrain.glyph,
                               fg=tile.terrain.color)
                else:
                    r.set_cell(map_x + i, map_y + j, tile.terrain.glyph,
                               fg=Color.DARK_GRAY)
        # Render entities
        for ent, (p,) in engine.world.view(Position):
            if ent.id == player.id:
                continue
            rx = p.x - ox
            ry = p.y - oy
            if 0 <= rx < self.viewport_w and 0 <= ry < self.viewport_h:
                tile = world_map.get_tile(p.x, p.y)
                if tile is None or (not tile.is_visible and not engine.cheat_mode):
                    continue
                identity = engine.world.get_component(ent, Identity)
                glyph = identity.glyph if identity else "?"
                color = identity.color if identity else Color.WHITE
                if engine.world.has_tag(ent, "hostile"):
                    color = Color.RED
                elif engine.world.has_tag(ent, "npc"):
                    color = Color.YELLOW
                r.set_cell(map_x + rx, map_y + ry, glyph, fg=color)
        # Player
        rx = pos.x - ox
        ry = pos.y - oy
        if 0 <= rx < self.viewport_w and 0 <= ry < self.viewport_h:
            r.set_cell(map_x + rx, map_y + ry, "@", fg=Color.WHITE,
                       style=Style.BOLD)

    def _render_sidebar(self, engine: Any, player: Entity) -> None:
        r = self.renderer
        sidebar_x = self.viewport_w + 3
        sidebar_w = r.width - sidebar_x - 1
        r.draw_box(sidebar_x, 1, sidebar_w, self.viewport_h + 1,
                   title="Status", fg=Color.GRAY)
        y = 2
        identity = engine.world.get_component(player, Identity)
        if identity:
            r.write_text(sidebar_x + 1, y, identity.display_name[:sidebar_w - 2],
                         fg=Color.WHITE, style=Style.BOLD)
            y += 1
        # Health bar
        health = engine.world.get_component(player, Health)
        if health:
            label = f"HP: {health.current}/{health.maximum}"
            r.write_text(sidebar_x + 1, y, label, fg=Color.HEALTH)
            y += 1
            bar_w = sidebar_w - 4
            filled = int(bar_w * health.current / max(1, health.maximum))
            r.write_text(sidebar_x + 1, y, "[" + "█" * filled + "·" * (bar_w - filled) + "]",
                         fg=Color.HEALTH)
            y += 2
        stats = engine.world.get_component(player, Stats)
        if stats:
            r.write_text(sidebar_x + 1, y,
                         f"Str {stats.strength}  Agi {stats.agility}", fg=Color.GRAY)
            y += 1
            r.write_text(sidebar_x + 1, y,
                         f"End {stats.endurance}  Int {stats.intelligence}",
                         fg=Color.GRAY)
            y += 1
            r.write_text(sidebar_x + 1, y,
                         f"Wil {stats.willpower}  Cha {stats.charisma}",
                         fg=Color.GRAY)
            y += 2
        needs = engine.world.get_component(player, Needs)
        if needs:
            self._render_need_bar(sidebar_x + 1, y, sidebar_w - 2,
                                  "Hunger", needs.hunger, Color.YELLOW)
            y += 1
            self._render_need_bar(sidebar_x + 1, y, sidebar_w - 2,
                                  "Thirst", needs.thirst, Color.CYAN)
            y += 1
            self._render_need_bar(sidebar_x + 1, y, sidebar_w - 2,
                                  "Fatigue", needs.fatigue, Color.MUTED)
            y += 1
            self._render_need_bar(sidebar_x + 1, y, sidebar_w - 2,
                                  "Sleep", needs.sleep, Color.PURPLE)
            y += 1
            r.write_text(sidebar_x + 1, y,
                         f"Morale: {needs.morale:.0f}  Sanity: {needs.sanity:.0f}",
                         fg=Color.GRAY)
            y += 2
        # Wealth
        from engine.entities.components import Wealth
        wealth = engine.world.get_component(player, Wealth)
        if wealth:
            r.write_text(sidebar_x + 1, y,
                         f"Gold: {wealth.gold}  Silver: {wealth.silver}",
                         fg=Color.GOLD)
            y += 1
            r.write_text(sidebar_x + 1, y,
                         f"Copper: {wealth.copper}",
                         fg=Color.GOLD)
            y += 1
        # Location
        pos = engine.world.get_component(player, Position)
        if pos:
            y += 1
            r.write_text(sidebar_x + 1, y,
                         f"Pos: ({pos.x}, {pos.y})", fg=Color.GRAY)

    def _render_need_bar(self, x: int, y: int, w: int, label: str,
                         value: float, color: int) -> None:
        r = self.renderer
        r.write_text(x, y, f"{label:8s}", fg=Color.GRAY)
        bar_w = w - 12
        filled = int(bar_w * value / 100.0)
        r.write_text(x + 9, y, "[" + "█" * filled + "·" * (bar_w - filled) + "]",
                     fg=color)

    def _render_message_log(self, engine: Any) -> None:
        r = self.renderer
        log_y = self.viewport_h + 3
        log_h = self.log_h
        r.draw_box(1, log_y, r.width - 2, log_h + 1,
                   title="Messages", fg=Color.GRAY)
        msgs = engine.message_log.recent(log_h - 1)
        for i, (text, color) in enumerate(msgs):
            r.write_text(2, log_y + 1 + i, text[:r.width - 4], fg=color)

    def _render_prompt(self, engine: Any) -> None:
        r = self.renderer
        prompt_y = r.height - 1
        r.write_text(1, prompt_y, self.i18n.t("ui.prompt"), fg=Color.GOLD,
                     style=Style.BOLD)
        if engine.current_input:
            r.write_text(3, prompt_y, engine.current_input, fg=Color.WHITE)


class InventoryScreen(Screen):
    """Inventory display."""

    name = "inventory"

    def render(self, engine: Any) -> None:
        r = self.renderer
        r.clear()
        r.draw_box(0, 0, r.width, r.height, title="Inventory",
                   fg=Color.GOLD, style=Style.BOLD)
        player = engine.player
        if player is None:
            r.render()
            return
        inv = engine.inventories.get(player.id)
        if inv is None:
            r.write_text(2, 2, "No inventory.", fg=Color.GRAY)
            r.render()
            return
        y = 2
        for slot_idx, item, count in inv.iter_items(engine.items):
            color = item.rarity.color
            line = f"[{slot_idx:2d}] {item.display_name}"
            if count > 1:
                line += f" x{count}"
            line += f"  ({item.weight:.1f}kg, {item.total_value}cp)"
            r.write_text(2, y, line[:r.width - 4], fg=color)
            y += 1
            if y >= r.height - 3:
                break
        r.write_text(2, r.height - 2,
                     f"Weight: {inv.total_weight(engine.items):.1f}/{inv.max_weight:.1f} kg",
                     fg=Color.GRAY)
        r.write_text(2, r.height - 1, "[Esc] Close", fg=Color.MUTED)
        r.render()


class CharacterScreen(Screen):
    """Character sheet — detailed stats and skills."""

    name = "character"

    def render(self, engine: Any) -> None:
        r = self.renderer
        r.clear()
        r.draw_box(0, 0, r.width, r.height, title="Character",
                   fg=Color.GOLD, style=Style.BOLD)
        player = engine.player
        if player is None:
            r.render()
            return
        identity = engine.world.get_component(player, Identity)
        health = engine.world.get_component(player, Health)
        stats = engine.world.get_component(player, Stats)
        y = 2
        if identity:
            r.write_text(2, y, identity.display_name, fg=Color.WHITE, style=Style.BOLD)
            y += 1
            r.write_text(2, y, identity.description, fg=Color.GRAY)
            y += 2
        if health:
            r.write_text(2, y, f"HP: {health.current}/{health.maximum}", fg=Color.HEALTH)
            y += 2
        if stats:
            derived = stats.derived()
            r.write_text(2, y, "Attributes:", fg=Color.GOLD, style=Style.BOLD)
            y += 1
            for attr in ("strength", "agility", "endurance", "intelligence",
                         "willpower", "charisma", "perception", "luck"):
                val = getattr(stats, attr)
                r.write_text(4, y, f"{attr:14s}: {val}", fg=Color.WHITE)
                y += 1
            y += 1
            r.write_text(2, y, "Derived:", fg=Color.GOLD, style=Style.BOLD)
            y += 1
            for k, v in derived.items():
                r.write_text(4, y, f"{k:18s}: {v}", fg=Color.WHITE)
                y += 1
        r.write_text(2, r.height - 1, "[Esc] Close", fg=Color.MUTED)
        r.render()


class MapScreen(Screen):
    """Full-screen world map."""

    name = "world_map"

    def render(self, engine: Any) -> None:
        r = self.renderer
        r.clear()
        r.draw_box(0, 0, r.width, r.height, title="World Map",
                   fg=Color.GOLD, style=Style.BOLD)
        world_map = engine.world_map
        player = engine.player
        pos = engine.world.get_component(player, Position) if player else None
        # Fit world map to screen
        sx = max(1, (r.width - 2) // world_map.width)
        sy = max(1, (r.height - 2) // world_map.height)
        s = min(sx, sy)
        offset_x = (r.width - world_map.width * s) // 2
        offset_y = (r.height - world_map.height * s) // 2
        for tile in world_map.iter_tiles():
            if not tile.is_explored and not engine.cheat_mode:
                continue
            x = offset_x + tile.x * s
            y = offset_y + tile.y * s
            if 0 <= x < r.width and 0 <= y < r.height:
                r.set_cell(x, y, tile.terrain.glyph, fg=tile.terrain.color)
        if pos:
            x = offset_x + pos.x * s
            y = offset_y + pos.y * s
            r.set_cell(x, y, "@", fg=Color.WHITE, style=Style.BOLD)
        r.write_text(2, r.height - 1, "[Esc] Close", fg=Color.MUTED)
        r.render()


class HelpScreen(Screen):
    """Help screen with key bindings."""

    name = "help"

    def render(self, engine: Any) -> None:
        r = self.renderer
        r.clear()
        r.draw_box(0, 0, r.width, r.height, title="Help",
                   fg=Color.GOLD, style=Style.BOLD)
        y = 2
        helps = [
            ("Movement", "h/j/k/l or arrow keys to move"),
            ("Look", "type 'look' to examine surroundings"),
            ("Inventory", "type 'inventory' or 'i'"),
            ("Character", "type 'character' or 'c'"),
            ("Map", "type 'map' or 'm'"),
            ("Save", "type 'save [name]'"),
            ("Load", "type 'load <name>'"),
            ("Time", "type 'time' to see game time"),
            ("Wait", "type 'wait [minutes]'"),
            ("Help", "type 'help' to list all commands"),
            ("Quit", "type 'quit' to exit"),
        ]
        for label, desc in helps:
            r.write_text(2, y, f"{label:12s}", fg=Color.GOLD, style=Style.BOLD)
            r.write_text(16, y, desc, fg=Color.WHITE)
            y += 1
            if y >= r.height - 2:
                break
        r.write_text(2, r.height - 1, "[Esc] Close", fg=Color.MUTED)
        r.render()


class ScreenManager:
    """Manages the active screen stack."""

    def __init__(self, renderer: TerminalRenderer, i18n: I18n) -> None:
        self.renderer = renderer
        self.i18n = i18n
        self._stack: list[Screen] = []
        self._screens: dict[str, Screen] = {}

    def register_screen(self, screen: Screen) -> None:
        self._screens[screen.name] = screen

    def push(self, name: str) -> None:
        if name in self._screens:
            self._stack.append(self._screens[name])

    def pop(self) -> Optional[Screen]:
        if not self._stack:
            return None
        return self._stack.pop()

    def set(self, name: str) -> None:
        self._stack.clear()
        if name in self._screens:
            self._stack.append(self._screens[name])

    def current(self) -> Optional[Screen]:
        if not self._stack:
            return None
        return self._stack[-1]

    def render(self, engine: Any) -> None:
        screen = self.current()
        if screen:
            screen.render(engine)
