from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np
import pygame as pg
import tcod.ecs as ecs

import assets
import comp
import consts
import entities
import ui_elements

if TYPE_CHECKING:
    from game_interface import GameInterface


TILE_LAYER = 0
TILE_UI_LAYER = 1
ENTITY_LAYER = 2
ACTOR_LAYER = 3
UI_LAYER = 4


class EntitySprite(pg.sprite.Sprite):
    def __init__(self, group: MapRenderer, entity: ecs.Entity):
        super().__init__()
        if comp.HP in entity.components:
            layer = ACTOR_LAYER
        else:
            layer = ENTITY_LAYER
        group.add(self, layer=layer)
        self.group = group
        self.entity = entity
        self.is_in_fov: bool | None = None
        self.flip: bool | None = None
        self.visible: bool | None = None
        self.spr: comp.Sprite | None = None
        self.hpbar: ui_elements.MapHPBar | None = None
        self.tooltip: ui_elements.MapHPBar | None = None
        self.tiles: list[pg.Surface] = []
        self.blank_surface = pg.Surface((1, 1)).convert_alpha()
        self.blank_surface.fill("#00000000")
        self.rect: pg.Rect
        self.frame = 0
        self.frame_offset = random.randint(0, consts.FPS)
        self.prepare_surfaces()

    def prepare_surfaces(self) -> None:
        spr = self.entity.components[comp.Sprite]
        if spr == self.spr and self.tiles is not None and len(self.tiles) > 0:
            return
        self.spr = spr
        if comp.HP in self.entity.components:
            max_frames = 2
        else:
            max_frames = 1
        self.tiles = assets.frames(spr.sheet, spr.tile, max_frames)
        self.dark_tiles = [pg.transform.grayscale(t) for t in self.tiles]
        for t in self.dark_tiles:
            t.fill(consts.UNEXPLORED_TINT, special_flags=pg.BLEND_MULT)
        self.flip_tiles = [pg.transform.flip(t, True, False) for t in self.tiles]

    def update(self) -> None:
        if (
            not comp.Position in self.entity.components
            or not comp.Sprite in self.entity.components
            or self.entity.components[comp.Position].depth != self.group.depth
        ):
            self.kill()
            self.group.entity_sprites.pop(self.entity)
            return
        self.prepare_surfaces()
        pos = self.entity.components[comp.Position]
        x, y = self.group.grid_to_screen(*pos.xy)
        if comp.HP in self.entity.components:
            y -= consts.ENTITY_YOFFSET
        rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)
        is_in_fov = self.group.fov[pos.xy]
        visible = (
            self.group.explored[pos.xy]
            and (is_in_fov or comp.HP not in self.entity.components)
            and not comp.HideSprite in self.entity.tags
        )
        dx, dy = self.entity.components.get(comp.Direction, (0, 0))
        flip = (dx > 0) or (dx >= 0 and dy > 0)
        frame = ((self.group.frame_counter + self.frame_offset) // 30) % len(self.tiles)
        self.update_tooltip()
        if (
            is_in_fov == self.is_in_fov
            and flip == self.flip
            and rect == self.rect
            and visible == self.visible
            and frame == self.frame
        ):
            return
        if is_in_fov and self.hpbar is None and comp.HP in self.entity.components:
            self.hpbar = ui_elements.MapHPBar(self.group, self)
        self.rect = rect
        self.is_in_fov = is_in_fov
        self.flip = flip
        self.visible = visible
        self.frame = frame
        if visible:
            if not is_in_fov:
                self.image = self.dark_tiles[self.frame]
            elif flip:
                self.image = self.flip_tiles[self.frame]
            else:
                self.image = self.tiles[self.frame]
        else:
            self.image = self.blank_surface

    def update_tooltip(self):
        if self.rect is None or not self.is_in_fov or not self.alive():
            if self.tooltip is not None:
                self.tooltip.kill()
                self.tooltip = None
            return
        x, y = pg.mouse.get_pos()
        pressed = pg.key.get_pressed()
        self.hovered = self.rect.collidepoint(x, y)
        show_tooltip = self.hovered or pressed[pg.K_RALT] or pressed[pg.K_LALT]
        show_tooltip = show_tooltip and self.is_in_fov
        show_tooltip = show_tooltip and entities.is_alive(self.entity)
        show_tooltip = show_tooltip and comp.Name in self.entity.components
        if show_tooltip and self.tooltip is None:
            self.tooltip = ui_elements.EntityTooltip(self, self.group.interface.font)
        elif not show_tooltip and self.tooltip is not None:
            self.tooltip.kill()
            self.tooltip = None


class TileSprite(pg.sprite.Sprite):
    def __init__(self, group: MapRenderer, x: int, y: int):
        super().__init__()
        group.add(self, layer=TILE_LAYER)
        self.group = group
        self.x, self.y = x, y
        self.depth = 0
        self.is_explored = False
        self.is_in_fov = False
        self.light = -1
        self.tile_id: int | None = None
        self.image = group.void_surface
        x, y = self.group.grid_to_screen(self.x, self.y)
        self.rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)

    def update(self) -> None:
        x, y = self.group.grid_to_screen(self.x, self.y)
        rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)
        tile_id = int(self.group.tiles[self.x, self.y])
        is_explored = self.group.explored[self.x, self.y]
        is_in_fov = self.group.fov[self.x, self.y]
        light = max(0, min(consts.MAX_LIGHT_RADIUS, self.group.light[self.x, self.y]))
        if self.depth != self.group.depth:
            is_explored = False
            self.image = self.group.void_surface
        if (
            is_explored == self.is_explored
            and is_in_fov == self.is_in_fov
            and tile_id == self.tile_id
            and rect == self.rect
            and self.depth == self.group.depth
            and light == self.light
        ):
            return
        self.light = light
        self.depth = self.group.depth
        self.tile_id = tile_id
        self.is_explored = is_explored
        self.is_in_fov = is_in_fov
        self.rect = rect
        if not is_explored:
            self.group.void_surface
        elif not is_in_fov:
            self.image = self.group.tile_surfaces[tile_id][-1]
        else:
            id = max(0, len(self.group.tile_surfaces[tile_id]) - light - 1)
            self.image = self.group.tile_surfaces[tile_id][id]


class MapRenderer(pg.sprite.LayeredUpdates):
    def __init__(self, interface: GameInterface):
        super().__init__()
        self.interface = interface
        self.logic = interface.logic
        self.frame_counter = 0
        self.shape = pg.display.get_surface().size
        self.tile_sprite_map: dict[tuple[int, int], TileSprite] = {}
        self.tile_surfaces: dict[int, list[pg.Surface]] = {}
        self.dark_surfaces: dict[int, pg.Surface] = {}
        self.dark_tint = consts.UNEXPLORED_TINT
        self.tile_sprites: dict[tuple[int, int], TileSprite] = {}
        self.entity_sprites: dict[ecs.Entity, EntitySprite] = {}
        self.create_surfaces()
        self.create_tile_sprites()
        self.create_entity_sprites()
        self.cursor_sprite = ui_elements.MapCursor(self)

    def create_surfaces(self) -> None:
        self.void_surface = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE))
        self.void_surface.fill(consts.BACKGROUND_COLOR)
        for i, tile in enumerate(consts.TILE_ARRAY):
            color = tile[2]
            sprite = tuple(tile[3])
            sheet = tile[4]
            surf = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE)).convert_alpha()
            surf.fill(color)
            if sheet != "":
                src = assets.tile(sheet, (int(sprite[0]), int(sprite[1])))
                surf.blit(src, (0, 0))
            self.tile_surfaces[i] = [surf]
            for j in range(consts.MAX_LIGHT_RADIUS + 1):
                alpha = int(
                    255
                    * (1 + consts.MAX_LIGHT_RADIUS - j)
                    / (1 + consts.MAX_LIGHT_RADIUS)
                )
                darksurf = surf.copy()
                darksurf.fill((alpha, alpha, alpha), special_flags=pg.BLEND_MULT)
                self.tile_surfaces[i].append(darksurf)

    def create_tile_sprites(self) -> None:
        shape = self.logic.map.components[comp.Tiles].shape
        for x in range(shape[0]):
            for y in range(shape[1]):
                if (x, y) not in self.tile_sprites:
                    self.tile_sprites[(x, y)] = TileSprite(self, x, y)

    def create_entity_sprites(self) -> None:
        query = self.logic.reg.Q.all_of(
            components=[comp.Position, comp.Sprite],
            relations=[(comp.Map, self.logic.map)],
        )
        for e in query:
            if e not in self.entity_sprites:
                self.entity_sprites[e] = EntitySprite(self, e)

    def grid_to_screen(self, i: int, j: int) -> tuple[int, int]:
        pi, pj = self.logic.player.components[comp.Position].xy
        x = self.shape[0] // 2 + (i - pi) * consts.TILE_SIZE
        y = self.shape[1] // 2 + (j - pj) * consts.TILE_SIZE
        return (x, y)

    def screen_to_grid(self, x: int, y: int) -> tuple[int, int]:
        pi, pj = self.logic.player.components[comp.Position].xy
        i = (x - self.shape[0] // 2) // consts.TILE_SIZE + pi
        j = (y - self.shape[1] // 2) // consts.TILE_SIZE + pj
        return (i, j)

    def update(self, *args, **kwargs):
        self.create_entity_sprites()
        self.frame_counter += 1
        player = self.logic.player
        map_ = self.logic.map
        self.depth = map_.components[comp.Depth]
        self.tiles = map_.components[comp.Tiles]
        self.fov = player.components[comp.FOV]
        self.explored = map_.components[comp.Explored]
        self.light = map_.components[comp.Lightsource]
        self.walkable = ~consts.TILE_ARRAY["obstacle"][self.tiles]
        super().update(*args, **kwargs)
