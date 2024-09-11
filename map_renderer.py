from __future__ import annotations
import pygame as pg

import consts
import ui_elements

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game_logic import GameLogic
    from game_interface import GameInterface
    import entities


class EntitySprite(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group,
                 interface: GameInterface,
                 game_logic: GameLogic,
                 entity: entities.Entity):
        super().__init__(group)
        self.group = group
        self.entity = entity
        self.game_logic = game_logic
        self.interface = interface
        self.is_in_fov = None
        tilesheet = pg.image.load(self.entity.sprite).convert_alpha()
        self.tile = tilesheet.subsurface(
            pg.Rect(self.entity.row*consts.TILE_SIZE,
                    self.entity.col*consts.TILE_SIZE,
                    consts.TILE_SIZE, consts.TILE_SIZE))
        self.image = self.tile
        self.hpbar = ui_elements.MapHPBar(group, self)

    def update(self):
        if self.entity.hp < 1:
            self.kill()
            return
        x, y = self.interface.grid_to_screen(self.entity.x, self.entity.y)
        self.rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)
        is_in_fov = self.game_logic.player.fov[self.entity.x, self.entity.y]
        if is_in_fov == self.is_in_fov:
            return
        self.is_in_fov = is_in_fov
        if is_in_fov:
            self.image = self.tile
        else:
            self.image = pg.Surface((1, 1)).convert_alpha()
            self.image.fill("#00000000")


class TileSprite(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group,
                 interface: GameInterface,
                 game_logic: GameLogic,
                 x: int, y: int):
        super().__init__(group)
        self.group = group
        self.x, self.y = x, y
        self.game_logic = game_logic
        self.interface = interface
        self.is_explored = False
        self.is_in_fov = False
        self.is_walkable = None
        self.image = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE)) \
            .convert_alpha()
        self.image.fill("#00000000")
        self.wall = interface.tilesheet.subsurface(
            (consts.TILE_SIZE, consts.TILE_SIZE,
             consts.TILE_SIZE, consts.TILE_SIZE))
        self.wall2 = interface.tilesheet.subsurface(
            (0, consts.TILE_SIZE, consts.TILE_SIZE, consts.TILE_SIZE))

    def update(self):
        x, y = self.interface.grid_to_screen(self.x, self.y)
        self.rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)

        is_walkable = self.game_logic.map[self.x, self.y] == 1
        is_explored = self.game_logic.explored[self.x, self.y]
        is_in_fov = self.game_logic.player.fov[self.x, self.y]
        if is_explored == self.is_explored and is_in_fov == self.is_in_fov \
                and is_walkable == self.is_walkable:
            return
        self.is_walkable = is_walkable
        self.is_explored = is_explored
        self.is_in_fov = is_in_fov
        k = 255
        if not is_in_fov:
            k //= 2
        if not is_explored:
            k *= 0
        if not is_walkable:
            walkable_below = (self.y < consts.MAP_SHAPE[1] - 1) and \
                (self.game_logic.map[self.x, self.y+1] == 1)
            if walkable_below:
                self.image.blit(self.wall, (0, 0))
            else:
                self.image.blit(self.wall2, (0, 0))
        else:
            self.image.fill("#404040")
        self.image.set_alpha(k)
