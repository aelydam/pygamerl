from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pygame as pg
import tcod.ecs as ecs

import comp
import consts
import entities
import maps
import ui_elements

if TYPE_CHECKING:
    from game_interface import GameInterface


TILE_LAYER = 0
TILE_UI_LAYER = 1
ENTITY_LAYER = 2
UI_LAYER = 3


class EntitySprite(pg.sprite.Sprite):
    def __init__(self, group: MapRenderer, entity: ecs.Entity):
        self._layer = ENTITY_LAYER
        super().__init__(group)
        self.group = group
        self.entity = entity
        self.is_in_fov: bool | None = None
        self.flip: bool | None = None
        spr = entity.components[comp.Sprite]
        tilesheet = pg.image.load(spr.sheet+".png").convert_alpha()
        self.tile = tilesheet.subsurface(
            pg.Rect(spr.tile[0]*consts.TILE_SIZE,
                    spr.tile[1]*consts.TILE_SIZE,
                    consts.TILE_SIZE, consts.TILE_SIZE))
        self.flip_tile = pg.transform.flip(self.tile, True, False)
        self.image = self.tile
        self.hpbar = ui_elements.MapHPBar(group, self)
        self.tooltip: ui_elements.EntityTooltip | None = None

    def update(self) -> None:
        if  not entities.is_alive(self.entity):
            self.kill()
            return
        pos = self.entity.components[comp.Position]
        x, y = self.group.grid_to_screen(*pos.xy)
        y -= consts.ENTITY_YOFFSET
        self.rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)
        is_in_fov = entities.is_in_fov(self.group.logic.player, pos)
        self.update_tooltip()
        dx, dy = self.entity.components.get(comp.Direction, (0, 0))
        flip = (dx > 0) or (dx >= 0 and dy > 0)
        if is_in_fov == self.is_in_fov and flip == self.flip:
            return
        self.is_in_fov = is_in_fov
        self.flip = flip
        if is_in_fov:
            if flip:
                self.image = self.flip_tile
            else:
                self.image = self.tile
        else:
            self.image = pg.Surface((1, 1)).convert_alpha()
            self.image.fill("#00000000")

    def update_tooltip(self):
        x, y = pg.mouse.get_pos()
        pressed = pg.key.get_pressed()
        self.hovered = self.rect.collidepoint(x, y)
        show_tooltip = self.hovered or pressed[pg.K_RALT] or pressed[pg.K_LALT]
        show_tooltip = show_tooltip and self.is_in_fov
        show_tooltip = show_tooltip and entities.is_alive(self.entity)
        if show_tooltip and self.tooltip is None:
            self.tooltip = \
                ui_elements.EntityTooltip(self, self.group.interface.font)
        elif not show_tooltip and self.tooltip is not None:
            self.tooltip.kill()
            self.tooltip = None


class TileSprite(pg.sprite.Sprite):
    def __init__(self, group: MapRenderer, x: int, y: int):
        self._layer = TILE_LAYER
        super().__init__(group)
        self.group = group
        self.x, self.y = x, y
        self.is_explored = False
        self.is_in_fov = False
        self.tile_id: int | None = None
        self.image = group.void_surface

    def update(self) -> None:
        x, y = self.group.grid_to_screen(self.x, self.y)
        map_ = self.group.logic.map
        tiles = map_.components[comp.Tiles]
        player = self.group.logic.player
        self.rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)
        tile_id = int(tiles[self.x, self.y])
        is_explored = maps.is_explored(map_, (self.x, self.y))
        is_in_fov = entities.is_in_fov(player, (self.x, self.y))
        if is_explored == self.is_explored and is_in_fov == self.is_in_fov \
                and tile_id == self.tile_id:
            return
        self.tile_id = tile_id
        self.is_explored = is_explored
        self.is_in_fov = is_in_fov
        if not is_explored:
            self.group.void_surface
        elif not is_in_fov:
            self.image = self.group.dark_surfaces[tile_id]
        else:
            self.image = self.group.tile_surfaces[tile_id]


class MapRenderer(pg.sprite.LayeredUpdates):
    def __init__(self, interface: GameInterface):
        super().__init__()
        self.interface = interface
        self.logic = interface.logic
        self.shape = pg.display.get_window_size()
        self.tile_sprite_map: dict[tuple[int, int], TileSprite] = {}
        self.tile_surfaces: dict[int, pg.Surface] = {}
        self.dark_surfaces: dict[int, pg.Surface] = {}
        self.dark_tint = consts.UNEXPLORED_TINT
        self.tilesheet = pg.image.load('tiles-dcss/brick_gray_0.png').convert_alpha()
        self.tile_sprites: dict[tuple[int, int], TileSprite] = {}
        self.entity_sprites: dict[ecs.Entity, EntitySprite] = {}
        self.create_surfaces()
        self.create_tile_sprites()
        self.create_entity_sprites()

    def create_surfaces(self) -> None:
        self.void_surface = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE))
        self.void_surface.fill(consts.BACKGROUND_COLOR)
        for i, tile in enumerate(consts.TILE_ARRAY):
            color = tile[2]
            sprite = tile[3]
            self.tile_surfaces[i] = \
                pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE))
            self.tile_surfaces[i].fill(color)
            if sprite[0] > 0 and sprite[1] > 0:
                src = self.tilesheet.subsurface(
                    (consts.TILE_SIZE * (sprite[0] - 1),
                     consts.TILE_SIZE * (sprite[1] - 1),
                     consts.TILE_SIZE, consts.TILE_SIZE))
                self.tile_surfaces[i].blit(src, (0, 0))
            # Dark tile
            self.dark_surfaces[i] = \
                pg.transform.grayscale(self.tile_surfaces[i])
            self.dark_surfaces[i].fill(
                self.dark_tint, special_flags=pg.BLEND_MULT)

    def create_tile_sprites(self) -> None:
        shape = self.logic.map.components[comp.Tiles].shape
        for x in range(shape[0]):
            for y in range(shape[1]):
                if (x, y) not in self.tile_sprites:
                    self.tile_sprites[(x,y)] = TileSprite(self, x, y)

    def create_entity_sprites(self) -> None:
        query = self.logic.reg.Q.all_of(
            components=[comp.Position, comp.Sprite],
            relations=[(comp.Map, self.logic.map)],
        )
        for e in query:
            if e not in self.entity_sprites:
                self.entity_sprites[e] = EntitySprite(self, e)
        self.cursor_sprite = ui_elements.MapCursor(self)

    def grid_to_screen(self, i: int, j: int) -> tuple[int, int]:
        pi, pj = self.logic.player.components[comp.Position].xy
        x = self.shape[0]//2 + (i-pi) * consts.TILE_SIZE
        y = self.shape[1]//2 + (j-pj) * consts.TILE_SIZE
        return (x, y)

    def screen_to_grid(self, x: int, y: int) -> tuple[int, int]:
        pi, pj = self.logic.player.components[comp.Position].xy
        i = (x - self.shape[0]//2) // consts.TILE_SIZE + pi
        j = (y - self.shape[1]//2) // consts.TILE_SIZE + pj
        return (i, j)

    def update(self, *args, **kwargs):
        self.create_entity_sprites()
        super().update(*args, **kwargs)
