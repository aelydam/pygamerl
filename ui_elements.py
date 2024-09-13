from __future__ import annotations
import pygame as pg
import numpy as np

import consts
import entities
import map_renderer

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game_logic import GameLogic
    import actions


class MapHPBar(pg.sprite.Sprite):
    def __init__(self, group: map_renderer.MapRenderer,
                 parent: map_renderer.EntitySprite):
        self._layer = map_renderer.UI_LAYER
        super().__init__(group)
        self.parent = parent
        self.fill = None
        self.is_in_fov = None
        self.rect: pg.Rect

    def update(self):
        x, y = self.parent.rect.x, self.parent.rect.bottom
        w, h = self.parent.rect.width, 4
        self.rect = pg.Rect(x, y, w, h)
        entity = self.parent.entity
        if entity.hp < 1:
            self.kill()
        fill = int(self.rect.width * entity.hp / entity.max_hp)
        is_in_fov = self.parent.is_in_fov
        if fill == self.fill and self.is_in_fov == is_in_fov:
            return
        if self.fill is None:
            self.fill = fill
        elif fill > self.fill:
            self.fill += 1
        elif fill < self.fill:
            self.fill -= 1
        self.parent.is_in_fov = is_in_fov
        self.image = pg.Surface(self.rect.size).convert_alpha()
        if not is_in_fov:
            self.image.fill("#00000000")
            return
        self.image.fill(consts.HPBAR_BG_COLOR)
        if self.fill >= self.rect.width // 2:
            color = consts.HPBAR_GOOD_COLOR
        else:
            color = consts.HPBAR_BAD_COLOR
        pg.draw.rect(self.image, color,
                     pg.Rect(0, 0, self.fill, self.rect.height))


class HPBar(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group,
                 game_logic: GameLogic, font: pg.Font):
        super().__init__(group)
        self.game_logic = game_logic
        self.font: pg.font.Font = font
        self.rect = pg.Rect(16, 16, 200, 20)
        self.fill = None

    def update(self):
        player = self.game_logic.player
        fill = int(self.rect.width * player.hp / player.max_hp)
        if fill == self.fill:
            return
        if self.fill is None:
            self.fill = fill
        if fill > self.fill:
            self.fill += 1
        elif fill < self.fill:
            self.fill -= 1
        if self.fill >= self.rect.width // 2:
            color = consts.HPBAR_GOOD_COLOR
        else:
            color = consts.HPBAR_BAD_COLOR
        self.image = pg.Surface(self.rect.size)
        self.image.fill(consts.HPBAR_BG_COLOR)
        pg.draw.rect(self.image, color,
                     pg.Rect(0, 0, self.fill, self.rect.height))
        surf = self.font.render(f"{player.hp}/{player.max_hp}", False,
                                consts.HPBAR_TEXT_COLOR)
        self.image.blit(surf,
                        surf.get_rect(center=(self.rect.width//2,
                                              self.rect.height//2)))


class MessageLog(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group,
                 game_logic: GameLogic,
                 font: pg.Font):
        super().__init__(group)
        self.rect = pg.Rect(16, 16+24, consts.SCREEN_SHAPE[0]//2, 24*10)
        self.image = pg.Surface(self.rect.size).convert_alpha()
        self.image.fill("#00000000")
        self.game_logic = game_logic
        self.last_text = None
        self.log_len = 0
        self.font = font

    def update(self):
        log_len = len(self.game_logic.message_log)
        if log_len < 1:
            return
        last_text = self.game_logic.message_log[-1]
        if last_text == self.last_text and log_len == self.log_len:
            return
        self.image.fill("#00000000")
        for i in range(1, min(11, log_len+1)):
            text = self.game_logic.message_log[-i]
            surf = self.font.render(text, False, consts.LOG_TEXT_COLOR, None)
            self.image.blit(surf, (0, (i - 1)*20))


class Popup(pg.sprite.Sprite):
    def __init__(self, group: map_renderer.MapRenderer,
                 action: actions.AttackAction,
                 font: pg.Font):
        self._layer = map_renderer.UI_LAYER
        super().__init__(group)
        self.action = action
        self.group = group
        self.counter = 0
        self.x, self.y = self.action.target.x, self.action.target.y
        text = str(self.action.damage)
        if text == '0':
            text = 'MISS'
        self.image: pg.Surface = \
            font.render(text, False, consts.POPUP_TEXT_COLOR, None)

    def update(self):
        if self.counter > consts.TILE_SIZE:
            self.kill()
            return
        x, y = self.group.grid_to_screen(self.x, self.y)
        x += consts.TILE_SIZE // 2
        y -= self.counter // 2
        self.rect = self.image.get_rect(center=(x, y))
        self.counter += 1


class Minimap(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group, game_logic: GameLogic):
        super().__init__(group)
        self.game_logic = game_logic
        self.scale = 4
        w = consts.MAP_SHAPE[0] * self.scale
        h = consts.MAP_SHAPE[1] * self.scale
        x, y = consts.SCREEN_SHAPE[0] - w - 16, 16
        self.rect = pg.Rect(x, y, w, h)

    def update(self):
        player = self.game_logic.player
        walkable = self.game_logic.map.walkable
        explored = self.game_logic.map.explored
        shape = self.game_logic.map.shape
        fov = player.fov
        grid = np.ones((shape[0], shape[1], 3))
        for k in range(3):
            grid[:, :, k] += 120 * explored * walkable
            grid[:, :, k] += 120 * explored * walkable * fov
            grid[:, :, k] += 40 * explored * (~walkable)
            grid[:, :, k] += 40 * explored * (~walkable) * fov
        for e in self.game_logic.entities:
            if fov[e.x, e.y]:
                if isinstance(e, entities.Player):
                    grid[e.x, e.y, :] = [0, 0, 255]
                else:
                    grid[e.x, e.y, :] = [255, 0, 0]
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
        text = self.entity.name
        self.image: pg.Surface = \
            font.render(text, False, consts.TOOLTIP_TEXT_COLOR, None)
        self.rect = self.image.get_rect(topleft=parent.hpbar.rect.bottomleft)

    def update(self):
        if self.parent is None or not self.parent.alive():
            return self.kill()
        self.rect = self.image.get_rect(
            topleft=self.parent.hpbar.rect.bottomleft)
        super().update()


class StatsHUD(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group,
                 logic: GameLogic,
                 font: pg.Font):
        super().__init__(group)
        self.group = group
        self.logic = logic
        self.font = font
        self.text = ''

    def update(self):
        turns = self.logic.turn_count
        player = self.logic.player
        explored = self.logic.map.explored
        walkable = self.logic.map.walkable
        explored_ratio = 100 * np.sum(explored & walkable) // np.sum(walkable)

        text = f'Turns: {turns:.0f}  Steps: {player.steps:.0f}  ' + \
            f'Explored: {explored_ratio:.0f}%  ' + \
            f'Hits: {player.hits:.0f}  Misses: {player.misses:.0f}  ' + \
            f'Kills: {player.kills:.0f}'
        if self.text == text:
            return
        self.image = self.font.render(text, False, "#FFFFFF")

        self.rect = self.image.get_rect(topleft=(16, 0))


class MapCursor(pg.sprite.Sprite):
    def __init__(self, group: map_renderer.MapRenderer):
        self._layer = map_renderer.TILE_UI_LAYER
        super().__init__(group)
        self.group = group
        self.default_image = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE)) \
            .convert_alpha()
        self.default_image.fill("#FFFFFF40")
        pg.draw.rect(
            self.default_image, "#FFFFFF",
            self.default_image.get_rect(topleft=(0, 0)), 2)
        self.image: pg.Surface = self.default_image
        self.blank_image = self.default_image.copy()
        self.blank_image.fill("#00000000")
        self.red_image = self.default_image.copy()
        self.red_image.fill(
            consts.CURSOR_IMPOSSIBLE_COLOR, special_flags=pg.BLEND_MULT)
        self.default_image.fill(
            consts.CURSOR_DEFAULT_COLOR, special_flags=pg.BLEND_MULT)

    def update(self, *args, **kwargs) -> None:
        mouse_x, mouse_y = pg.mouse.get_pos()
        grid_x, grid_y = self.group.screen_to_grid(mouse_x, mouse_y)
        x, y = self.group.grid_to_screen(grid_x, grid_y)
        self.rect = self.image.get_rect(topleft=(x, y))
        map_ = self.group.logic.map
        in_bounds = map_.is_in_bounds(grid_x, grid_y)
        is_explored = in_bounds and map_.explored[grid_x, grid_y]
        is_walkable = in_bounds and map_.walkable[grid_x, grid_y]
        if not is_explored:
            self.image = self.blank_image
        elif not is_walkable:
            self.image = self.red_image
        else:
            self.image = self.default_image
