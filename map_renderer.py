from __future__ import annotations
import pygame as pg

import consts
import ui_elements

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game_logic import GameLogic
    from game_interface import GameInterface
    import entities


TILE_LAYER = 0
ENTITY_LAYER = 1
UI_LAYER = 2


class EntitySprite(pg.sprite.Sprite):
    def __init__(self, group: MapRenderer,
                 interface: GameInterface,
                 game_logic: GameLogic,
                 entity: entities.Entity):
        self._layer = ENTITY_LAYER
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
    def __init__(self, group: MapRenderer,
                 interface: GameInterface,
                 game_logic: GameLogic,
                 x: int, y: int):
        self._layer = TILE_LAYER
        super().__init__(group)
        self.group = group
        self.x, self.y = x, y
        self.game_logic = game_logic
        self.interface = interface
        self.is_explored = False
        self.is_in_fov = False
        self.tile_id = None
        self.image = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE)) \
            .convert_alpha()

    def update(self):
        x, y = self.interface.grid_to_screen(self.x, self.y)
        self.rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)
        tile_id = self.game_logic.map[self.x, self.y]
        is_explored = self.game_logic.explored[self.x, self.y]
        is_in_fov = self.game_logic.player.fov[self.x, self.y]
        if is_explored == self.is_explored and is_in_fov == self.is_in_fov \
                and tile_id == self.tile_id:
            return
        self.tile_id = tile_id
        self.is_explored = is_explored
        self.is_in_fov = is_in_fov
        if not is_explored:
            self.group.void_surdace
        elif not is_in_fov:
            self.image = self.group.dark_surfaces[tile_id]
        else:
            self.image = self.group.tile_surfaces[tile_id]


class MapRenderer(pg.sprite.LayeredUpdates):
    def __init__(self, logic: GameLogic):
        super().__init__()
        self.logic = logic
        self.map = logic.map
        self.shape = pg.display.get_window_size()
        self.tile_sprite_map: dict[tuple[int, int], TileSprite] = {}
        self.tile_surfaces: dict[int, pg.Surface] = {}
        self.dark_surfaces: dict[int, pg.Surface] = {}
        self.dark_tint = "#303030"
        self.tilesheet = pg.image.load('32rogues/tiles.png').convert_alpha()
        self.create_surfaces()
        self.create_sprites()

    def create_surfaces(self):
        self.void_surdace = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE))
        self.void_surdace.fill("#000000")
        self.tile_surfaces[0] = self.tilesheet.subsurface(
            (0, consts.TILE_SIZE,
             consts.TILE_SIZE, consts.TILE_SIZE))
        self.tile_surfaces[1] = self.void_surdace.copy()
        self.tile_surfaces[1].fill("#222034")
        self.tile_surfaces[2] = self.tilesheet.subsurface(
            (consts.TILE_SIZE, consts.TILE_SIZE,
             consts.TILE_SIZE, consts.TILE_SIZE))
        for k, v in self.tile_surfaces.items():
            self.dark_surfaces[k] = pg.transform.grayscale(v)
            self.dark_surfaces[k].fill(
                self.dark_tint, special_flags=pg.BLEND_MULT)

    def create_sprites(self):
        shape = self.map.shape
        for x in range(shape[0]):
            for y in range(shape[1]):
                TileSprite(self, self, self.logic, x, y)
        for e in self.logic.entities:
            EntitySprite(self, self, self.logic, e)

    def grid_to_screen(self, i: int, j: int) -> tuple[int, int]:
        pi, pj = self.logic.player.x, self.logic.player.y
        x = self.shape[0]//2 + (i-pi) * consts.TILE_SIZE
        y = self.shape[1]//2 + (j-pj) * consts.TILE_SIZE
        return (x, y)

    def screen_to_grid(self, x: int, y: int) -> tuple[int, int]:
        pi, pj = self.logic.player.x, self.logic.player.y
        i = (x - self.shape[0]//2) // consts.TILE_SIZE + pi
        j = (y - self.shape[1]//2) // consts.TILE_SIZE + pj
        return (i, j)
