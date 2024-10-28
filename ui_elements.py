from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import numpy as np
import pygame as pg

import actions
import comp
import consts
import db
import entities
import items
import map_renderer
import maps
from game_interface import GameInterface

if TYPE_CHECKING:
    from game_logic import GameLogic


class MapHPBar(pg.sprite.Sprite):
    def __init__(
        self, group: map_renderer.MapRenderer, parent: map_renderer.EntitySprite
    ):
        self._layer = map_renderer.UI_LAYER
        super().__init__(group)
        self.parent = parent
        self.fill = None
        self.is_in_fov = None
        self.light = -1
        self.rect: pg.Rect = pg.Rect(0, -4, consts.TILE_SIZE, consts.FONTSIZE // 4)
        self.image = pg.Surface(self.rect.size).convert_alpha()

    def update(self):
        x, y = self.parent.rect.x, self.parent.rect.bottom
        w, h = self.parent.rect.width, 4
        self.rect = pg.Rect(x, y, w, h)
        if not self.parent.alive() or not self.parent.is_in_fov:
            self.kill()
            self.parent.hpbar = None
            return
        entity = self.parent.entity
        hp = entity.components.get(comp.HP)
        max_hp = entity.components.get(comp.MaxHP)
        fill = int(self.rect.width * hp / max_hp)
        light = self.parent.light
        if fill == self.fill and light == self.light:
            return
        self.fill = fill
        self.light = self.parent.light
        self.image.fill(consts.HPBAR_BG_COLOR)
        if self.fill >= self.rect.width // 2:
            color = consts.HPBAR_GOOD_COLOR
        else:
            color = consts.HPBAR_BAD_COLOR
        tint = map_renderer.light_tint(light)
        pg.draw.rect(self.image, color, pg.Rect(0, 0, self.fill, self.rect.height))
        self.image.fill(tint, special_flags=pg.BLEND_MULT)


class Bar(pg.sprite.Sprite):
    def __init__(
        self,
        group: pg.sprite.Group,
        font: pg.Font,
        current_fun: Callable[[], int],
        max_fun: Callable[[], int],
        text_fun: Callable[[], str] | None = None,
        width: int = 200,
        height: int = 12,
        x: int = 16,
        y: int = 16,
        bg_color: str = consts.HPBAR_BG_COLOR,
        good_color: str = consts.HPBAR_GOOD_COLOR,
        bad_color: str = consts.HPBAR_BAD_COLOR,
        text_color: str = consts.HPBAR_TEXT_COLOR,
        bad_ratio: float = 0.5,
        label: str = "",
    ):
        super().__init__(group)
        self.font: pg.font.Font = font
        self.rect: pg.Rect = pg.Rect(x, y, width, height)
        self.fill = None
        self.image = pg.Surface(self.rect.size).convert_alpha()
        self.current_fun = current_fun
        self.max_fun = max_fun
        self.text_fun = text_fun
        self.bg_color = bg_color
        self.good_color = good_color
        self.bad_color = bad_color
        self.text_color = text_color
        self.bad_ratio = bad_ratio
        self.label = label

    def update(self):
        current = self.current_fun()
        maximum = self.max_fun()
        fill = int(self.rect.width * current / maximum)
        if self.text_fun is None:
            text = f"{current}/{maximum}"
        else:
            text = self.text_fun()
        if fill == self.fill and text == self.text:
            return
        self.fill = fill
        self.text = text
        if self.fill >= self.rect.width * self.bad_ratio:
            color = self.good_color
        else:
            color = self.bad_color
        self.image.fill(self.bg_color)
        pg.draw.rect(self.image, color, pg.Rect(0, 0, self.fill, self.rect.height))
        surf = self.font.render(" " + self.label, False, self.text_color)
        self.image.blit(surf, surf.get_rect(midleft=(0, self.rect.height // 2)))
        surf = self.font.render(text + " ", False, self.text_color)
        self.image.blit(
            surf, surf.get_rect(midright=(self.rect.width, self.rect.height // 2))
        )


class MessageLog(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group, game_logic: GameLogic, font: pg.Font):
        super().__init__(group)
        self.rect: pg.Rect = pg.Rect(
            16, 16 + 24, consts.SCREEN_SHAPE[0] * 3 // 4, 24 * 10
        )
        self.image = pg.Surface(self.rect.size).convert_alpha()
        self.image.fill("#00000000")
        self.game_logic = game_logic
        self.last_text = None
        self.log_len = 0
        self.font = font

    def update(self):
        log = self.game_logic.message_log
        log_len = len(log)
        if log_len < 1:
            return
        last_text = log[-1]
        if last_text == self.last_text and log_len == self.log_len:
            return
        text = "\n".join(log[-min(11, log_len + 1) :])
        self.image = self.font.render(
            text, False, consts.LOG_TEXT_COLOR, None
        ).convert_alpha()
        self.rect.size = self.image.size


class Popup(pg.sprite.Sprite):
    def __init__(
        self,
        group: map_renderer.MapRenderer,
        action: actions.Damage | actions.Heal,
        font: pg.Font,
    ):
        self._layer = map_renderer.UI_LAYER
        super().__init__(group)
        self.action = action
        self.group = group
        self.counter = 0
        self.x, self.y = self.action.xy
        text = str(self.action.amount)
        if text == "0":
            text = "MISS"
        elif isinstance(action, actions.Heal):
            text = f"+{text}"
        if action.critical:
            text += "!"
        self.image: pg.Surface = font.render(text, False, consts.POPUP_TEXT_COLOR, None)

    def update(self):
        if self.counter > consts.TILE_SIZE:
            self.kill()
            return
        x, y = self.group.grid_to_screen(self.x, self.y)
        x += consts.TILE_SIZE // 2
        y -= self.counter
        self.rect = self.image.get_rect(center=(x, y))
        self.counter += 1


class Minimap(pg.sprite.Sprite):
    def __init__(
        self,
        group: pg.sprite.Group,
        logic: GameLogic,
        scale: int = consts.FONTSIZE // 4,
        follow_player: bool = True,
        x: int = -16,
        y: int = 16,
    ):
        super().__init__(group)
        self.logic = logic
        self.depth = logic.map.components[comp.Depth]
        self.scale = scale
        self.follow_player = follow_player
        w = consts.MAP_SHAPE[0] * self.scale
        h = consts.MAP_SHAPE[1] * self.scale
        self.x, self.y = x, y
        if x < 0:
            x = consts.SCREEN_SHAPE[0] - w + x
        if y < 0:
            y = consts.SCREEN_SHAPE[1] - h + y
        self.rect: pg.Rect = pg.Rect(x, y, w, h)

    def inc_depth(self, delta: int):
        depth = self.depth + delta
        map_ = maps.get_map(self.logic.reg, depth, generate=False)
        if comp.Tiles in map_.components:
            self.depth = depth

    def update(self):
        player = self.logic.player
        pdepth = player.components[comp.Position].depth
        if self.follow_player:
            map_ = player.relation_tag[comp.Map]
            self.depth = map_.components[comp.Depth]
        else:
            map_ = maps.get_map(self.logic.reg, self.depth, generate=False)
            screen = pg.display.get_surface().size
            self.rect.center = ((self.x + screen[0]) // 2, (self.y + screen[1]) // 2)
        grid = map_.components[comp.Tiles]
        walkable = db.walkable[grid]
        explored = map_.components[comp.Explored]
        shape = grid.shape
        if comp.FOV in player.components and self.depth == pdepth:
            fov = player.components[comp.FOV]
        else:
            fov = np.full(shape, False)
        grid = np.ones((shape[0], shape[1], 3))
        for k in range(3):
            grid[:, :, k] += 120 * explored * walkable
            grid[:, :, k] += 120 * explored * walkable * fov
            grid[:, :, k] += 40 * explored * (~walkable)
            grid[:, :, k] += 40 * explored * (~walkable) * fov
        #
        query = (
            map_.registry.Q.all_of(
                components=[comp.Position, comp.HP],
                relations=[(comp.Map, map_)],
            ).get_entities()
            | map_.registry.Q.all_of(
                components=[comp.Position, comp.Interaction],
                relations=[(comp.Map, map_)],
            )
            .none_of(tags=[comp.Trap])
            .get_entities()
        )
        for e in query:
            ex, ey = e.components[comp.Position].xy
            if explored[ex, ey]:
                if comp.Player in e.tags:
                    grid[ex, ey, :] = [0, 0, 255]
                elif comp.Interaction in e.components and not comp.HP in e.components:
                    grid[ex, ey, :] = [255, 255, 0]
                elif fov[ex, ey] and comp.HP in e.components:
                    grid[ex, ey, :] = [255, 0, 0]
        self.image = pg.surfarray.make_surface(grid.astype(np.uint8))
        self.image.set_colorkey((1, 1, 1))
        self.image = pg.transform.scale_by(self.image, self.scale)


class EntityTooltip(pg.sprite.Sprite):
    def __init__(self, parent: map_renderer.EntitySprite, font: pg.Font):
        self._layer = map_renderer.UI_LAYER
        super().__init__(parent.group)
        self.parent = parent
        self.group = parent.group
        self.entity = parent.entity
        text = items.display_name(self.entity)
        self.image: pg.Surface = font.render(
            text, False, consts.TOOLTIP_TEXT_COLOR, None
        )
        self.rect = self.image.get_rect(topleft=parent.rect.bottomleft)

    def update(self):
        if (
            self.parent is None
            or not self.parent.alive()
            or not comp.Name in self.entity.components
        ):
            return self.kill()
        self.rect = self.image.get_rect(topleft=self.parent.rect.bottomleft)
        super().update()


class StatsHUD(pg.sprite.Sprite):
    def __init__(
        self,
        group: pg.sprite.Group,
        interface: GameInterface,
        elements: dict[str, Callable[[], str | int]],
    ):
        super().__init__(group)
        self.group = group
        self.interface = interface
        self.logic = interface.logic
        self.font = interface.font
        self.elements = elements
        self.text = ""

    def update(self):
        text = " ".join([f"{k}:{v()}" for k, v in self.elements.items()])
        if self.text == text:
            return
        self.image = self.font.render(text, False, "#FFFFFF")

        self.rect = self.image.get_rect(topleft=(16, 0))


class MapCursor(pg.sprite.Sprite):
    def __init__(self, group: map_renderer.MapRenderer):
        self._layer = map_renderer.TILE_UI_LAYER
        super().__init__(group)
        self.group = group
        self.default_image = pg.Surface(
            (consts.TILE_SIZE, consts.TILE_SIZE)
        ).convert_alpha()
        self.default_image.fill("#80808040")
        pg.draw.rect(
            self.default_image,
            "#FFFFFF",
            self.default_image.get_rect(topleft=(0, 0)),
            2,
        )
        self.image: pg.Surface = self.default_image
        self.blank_image = self.default_image.copy()
        self.blank_image.fill("#00000000")
        self.red_image = self.default_image.copy()
        self.red_image.fill(consts.CURSOR_IMPOSSIBLE_COLOR, special_flags=pg.BLEND_MULT)
        self.default_image.fill(
            consts.CURSOR_DEFAULT_COLOR, special_flags=pg.BLEND_MULT
        )

    def update(self, *args, **kwargs) -> None:
        cursor_pos = self.group.cursor
        if cursor_pos is None:
            self.image = self.blank_image
            self.rect = self.image.get_rect(bottomright=(-1, -1))
            return
        x, y = self.group.grid_to_screen(*cursor_pos)
        self.rect = self.image.get_rect(topleft=(x, y))
        map_ = self.group.logic.map
        in_bounds = maps.is_in_bounds(map_, cursor_pos)
        is_explored = in_bounds and self.group.explored[cursor_pos]
        is_walkable = is_explored and maps.is_walkable(map_, cursor_pos)
        if not is_explored:
            self.image = self.blank_image
        elif not is_walkable:
            self.image = self.red_image
        else:
            self.image = self.default_image
