#!/usr/bin/env python3

import os

import pygame as pg

import comp
import consts
import entities
import game_interface
import items
import keybinds
import map_renderer
import maps
import ui_elements


class DungeonViewerState(game_interface.State):
    def __init__(self, parent: game_interface.GameInterface | game_interface.State):
        super().__init__(parent)
        self.logic = self.interface.logic
        self.new_world()
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        self.minimap = ui_elements.Minimap(self.ui_group, self.logic)
        self.map_renderer = map_renderer.MapRenderer(self.interface)
        self.map_renderer.center = self.logic.player.components[comp.Position].xy

        self.hud = ui_elements.StatsHUD(
            self.ui_group,
            self.interface,
            {
                "Depth": lambda: self.map_renderer.depth,
                "Pos": lambda: ",".join(str(i) for i in self.map_renderer.center),
                "FPS": lambda: int(self.interface.clock.get_fps()),
                "Global Seed": lambda: self.logic.reg[None].components[comp.Seed],
                "Map Seed": lambda: self.logic.map.components[comp.Seed],
            },
        )

    def new_world(self):
        self.logic.new_game()
        self.logic.map.components[comp.Explored] |= True
        self.logic.map.components[comp.Lightsource] += 10
        self.logic.player.components[comp.FOV] |= True

    def set_depth(self, depth: int):
        if depth < 0:
            return
        if depth != self.map_renderer.depth:
            self.logic.player.components[comp.Position] = comp.Position(
                self.map_renderer.center, depth
            )
            map_entity = maps.get_map(self.logic.reg, depth)
            # Show hidden entities
            query = map_entity.registry.Q.all_of(
                components=[comp.Position, comp.Sprite],
                tags=[comp.HideSprite],
                relations=[(comp.Map, map_entity)],
            )
            for e in query:
                e.tags.discard(comp.HideSprite)
            # Identify entities
            query = map_entity.registry.Q.all_of(
                components=[comp.Position, comp.Sprite, comp.UnidentifiedName],
                relations=[(comp.Map, map_entity)],
            )
            for e in query:
                items.identify(e)
        # Display everything at full light
        entities.update_fov(self.logic.player)
        self.logic.map.components[comp.Explored] |= True
        self.logic.map.components[comp.Lightsource] += 10
        self.logic.player.components[comp.FOV] |= True

    def update(self):
        super().update()
        self.map_renderer.update()
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        screen.fill(consts.BACKGROUND_COLOR)
        self.map_renderer.draw(screen)
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key == pg.K_ESCAPE:
                self.interface.pop()
            elif event.key in keybinds.MOVE_KEYS:
                dx, dy = keybinds.MOVE_KEYS[event.key]
                self.map_renderer.move_center((dx, dy))
                self.map_renderer.cursor = self.map_renderer.center
            elif event.key == pg.K_PAGEDOWN:
                self.set_depth(self.map_renderer.depth + 1)
            elif event.key == pg.K_PAGEUP:
                self.set_depth(self.map_renderer.depth - 1)
            elif event.key == pg.K_F5:
                self.new_world()

        elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
            self.map_renderer.center = self.map_renderer.screen_to_grid(*event.pos)
            self.map_renderer.cursor = self.map_renderer.center

        elif event.type == pg.MOUSEMOTION:
            self.map_renderer.cursor = self.map_renderer.screen_to_grid(*event.pos)


if __name__ == "__main__":
    os.chdir(consts.GAME_PATH)
    interface = game_interface.GameInterface()
    interface.push(DungeonViewerState(interface))
    interface.run()
