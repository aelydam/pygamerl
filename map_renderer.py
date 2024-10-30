from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np
import pygame as pg
import tcod.ecs as ecs

import assets
import comp
import consts
import db
import entities
import ui_elements

if TYPE_CHECKING:
    from game_interface import GameInterface


TILE_LAYER = 0
TILE_UI_LAYER = 1
ENTITY_LAYER = 2
ITEM_LAYER = 3
INTERACTION_LAYER = 4
ACTOR_LAYER = 5
UI_LAYER = 6


def light_tint(light_level: int) -> tuple[int, int, int]:
    i = int(
        254
        * (1 + max(0, min(consts.MAX_LIGHT_RADIUS, int(light_level))))
        / (1 + consts.MAX_LIGHT_RADIUS)
    )
    return (i, i, i)


class EntitySprite(pg.sprite.Sprite):
    def __init__(self, group: MapRenderer, entity: ecs.Entity):
        super().__init__()
        if comp.HP in entity.components:
            layer = ACTOR_LAYER
        elif comp.Interaction in entity.components:
            layer = INTERACTION_LAYER
        elif "items" in entity.tags:
            layer = ITEM_LAYER
        else:
            layer = ENTITY_LAYER
        group.add(self, layer=layer)
        self.group = group
        self.entity = entity
        self.is_in_fov: bool | None = None
        self.flip: bool | None = None
        self.light = -1
        self.x, self.y = -1, -1
        self.visible: bool | None = None
        self.spr: comp.Sprite | None = None
        self.hpbar: ui_elements.MapHPBar | None = None
        self.tooltip: ui_elements.MapHPBar | None = None
        self.tiles: list[list[pg.Surface]] = []
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
        frames = assets.frames(spr.sheet, tuple(spr.tile), max_frames)
        self.tiles = [frames]
        for j in range(consts.MAX_LIGHT_RADIUS + 1):
            tint = light_tint(consts.MAX_LIGHT_RADIUS - j)
            darkframes: list[pg.Surface] = []
            for k, surf in enumerate(frames):
                darksurf = surf.copy()
                darksurf.fill(tint, special_flags=pg.BLEND_MULT)
                darkframes.append(darksurf)
            self.tiles.append(darkframes)
        self.flip_tiles = [
            [pg.transform.flip(a, True, False) for a in b] for b in self.tiles
        ]

    def update(self) -> None:
        if (
            not comp.Position in self.entity.components
            or not comp.Sprite in self.entity.components
            or self.entity.components[comp.Position].depth != self.group.depth
            or self.entity.registry != self.group.logic.reg
        ):
            self.kill()
            self.group.entity_sprites.pop(self.entity)
            return
        self.prepare_surfaces()
        pos = self.entity.components[comp.Position]
        self.x, self.y = pos.xy
        x, y = self.group.grid_to_screen(*pos.xy)
        if comp.HP in self.entity.components:
            y -= consts.ENTITY_YOFFSET
        rect = pg.Rect(x, y, consts.TILE_SIZE, consts.TILE_SIZE)
        is_in_fov = self.group.fov[pos.xy]
        light = self.group.light[pos.xy]
        visible = (
            self.group.explored[pos.xy]
            and (is_in_fov or comp.HP not in self.entity.components)
            and not comp.HideSprite in self.entity.tags
            and not comp.Hidden in self.entity.tags
        )
        dx, dy = self.entity.components.get(comp.Direction, (0, 0))
        flip = (dx > 0) or (dx >= 0 and dy > 0)
        frame = ((self.group.frame_counter + self.frame_offset) // 30) % len(
            self.tiles[0]
        )
        self.update_tooltip()
        if (
            is_in_fov == self.is_in_fov
            and flip == self.flip
            and rect == self.rect
            and visible == self.visible
            and frame == self.frame
            and light == self.light
        ):
            return
        if is_in_fov and self.hpbar is None and comp.HP in self.entity.components:
            self.hpbar = ui_elements.MapHPBar(self.group, self)
        self.rect = rect
        self.is_in_fov = is_in_fov
        self.flip = flip
        self.visible = visible
        self.frame = frame
        self.light = light
        if visible:
            if not is_in_fov:
                self.image = self.tiles[-1][0]
            else:
                id = max(0, len(self.tiles) - light - 1)
                if flip:
                    self.image = self.flip_tiles[id][self.frame]
                else:
                    self.image = self.tiles[id][self.frame]
        else:
            self.image = self.blank_surface

    def update_tooltip(self):
        if self.rect is None or not self.is_in_fov or not self.alive():
            if self.tooltip is not None:
                self.tooltip.kill()
                self.tooltip = None
            return
        pressed = pg.key.get_pressed()
        self.hovered = self.group.cursor == (self.x, self.y)
        show_tooltip = self.hovered or pressed[pg.K_RALT] or pressed[pg.K_LALT]
        show_tooltip = show_tooltip and self.visible
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
        self.center: tuple[int, int] = (0, 0)
        self.cursor: tuple[int, int] | None = None
        self.create_surfaces()
        self.create_tile_sprites()
        self.create_entity_sprites()
        self.cursor_sprite = ui_elements.MapCursor(self)

    def create_surfaces(self) -> None:
        self.void_surface = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE))
        self.void_surface.fill(consts.BACKGROUND_COLOR)
        for i, tile in enumerate(db.tiles):
            color = tile[2]
            sprite = tuple(tile[3])
            sheet = tile[4]
            surf = pg.Surface((consts.TILE_SIZE, consts.TILE_SIZE)).convert_alpha()
            surf.fill(color)
            if tile[5] > 0:
                bgtile = tile[5]
                surf.blit(self.tile_surfaces[bgtile][0], (0, 0))
            if sheet != "":
                src = assets.tile(sheet, (int(sprite[0]), int(sprite[1])))
                surf.blit(src, (0, 0))
            self.tile_surfaces[i] = [surf]
            for j in range(consts.MAX_LIGHT_RADIUS + 1):
                tint = light_tint(consts.MAX_LIGHT_RADIUS - j)
                darksurf = surf.copy()
                darksurf.fill(tint, special_flags=pg.BLEND_MULT)
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
        pi, pj = self.center
        x = self.shape[0] // 2 + (i - pi) * consts.TILE_SIZE
        y = self.shape[1] // 2 + (j - pj) * consts.TILE_SIZE
        return (int(x), int(y))

    def screen_to_grid(self, x: int, y: int) -> tuple[int, int]:
        pi, pj = self.center
        i = (x - self.shape[0] // 2) // consts.TILE_SIZE + pi
        j = (y - self.shape[1] // 2) // consts.TILE_SIZE + pj
        return (int(i), int(j))

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
        self.walkable = db.walkable[self.tiles]
        super().update(*args, **kwargs)

    def move_center(self, direction: tuple[int, int]):
        x = min(max(0, self.center[0] + direction[0]), consts.MAP_SHAPE[0])
        y = min(max(0, self.center[1] + direction[1]), consts.MAP_SHAPE[1])
        self.center = (x, y)
