import pygame as pg

import actions
import assets
import comp
import consts
import entities
import game_interface
import map_renderer
import maps
import ui_elements


class InGameState(game_interface.State):
    def __init__(self, interface: game_interface.GameInterface):
        self.interface = interface
        self.logic = interface.logic
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        font = interface.font
        self.hpbar = ui_elements.HPBar(self.ui_group, self.logic, font)
        self.log = ui_elements.MessageLog(self.ui_group, self.logic, font)
        self.minimap = ui_elements.Minimap(self.ui_group, self.logic)
        self.map_renderer = map_renderer.MapRenderer(interface)
        self.hud = ui_elements.StatsHUD(
            self.ui_group,
            self.interface,
            {
                "Depth": lambda: self.map_renderer.depth,
                "Turn": lambda: self.logic.turn_count,
                "Played": lambda: f"{self.logic.played_time // 3600:0.0f}:{self.logic.played_time // 60 % 60:0.0f}:{self.logic.played_time % 60:02.0f}",
                "FPS": lambda: int(self.interface.clock.get_fps()),
            },
        )

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key in consts.MOVE_KEYS.keys():
                dx, dy = consts.MOVE_KEYS[event.key]
                action = actions.BumpAction(self.logic.player, (dx, dy))
                if event.mod & pg.KMOD_SHIFT:
                    self.logic.continuous_action = action
                else:
                    self.logic.input_action = action
            elif event.key == pg.K_ESCAPE:
                self.logic.input_action = None
                self.logic.continuous_action = None
            elif event.key == pg.K_RETURN:
                self.logic.input_action = actions.Interact(self.logic.player)
            elif event.key in consts.WAIT_KEYS:
                self.logic.input_action = actions.WaitAction(self.logic.player)
            elif event.key == pg.K_m:
                self.interface.push(MapState(self.interface))
            elif event.key == pg.K_x:
                if event.mod & pg.KMOD_SHIFT:
                    self.logic.input_action = actions.MagicMap(self.logic.player)
                else:
                    self.logic.continuous_action = actions.ExploreAction(
                        self.logic.player
                    )
        elif event.type == pg.MOUSEBUTTONUP:
            if event.button == 3:
                self.logic.input_action = None
                self.logic.continuous_action = None
                return
            if event.button != 1:
                return
            if self.minimap.rect.collidepoint(*event.pos):
                return self.interface.push(MapState(self.interface))
            x, y = self.map_renderer.screen_to_grid(event.pos[0], event.pos[1])
            if not maps.is_explored(self.logic.map, (x, y)):
                return
            player = self.logic.player
            px, py = player.components[comp.Position].xy
            if x == px and y == py:
                self.logic.input_action = actions.WaitAction(player)
                return
            if (x - px) ** 2 + (y - py) ** 2 <= 2:
                self.logic.input_action = actions.BumpAction.to(player, (x, y))
            else:
                self.logic.continuous_action = actions.MoveToAction(player, (x, y))

    def update(self):
        self.logic.update()
        if not entities.is_alive(self.logic.player):
            self.interface.push(GameOverState(self))
            return
        if isinstance(self.logic.last_action, actions.AttackAction):
            ui_elements.Popup(
                self.map_renderer, self.logic.last_action, self.interface.font
            )
            self.logic.last_action = None

    def render(self, screen: pg.Surface):
        self.map_renderer.update()
        self.ui_group.update()
        screen.fill(consts.BACKGROUND_COLOR)
        self.map_renderer.draw(screen)
        self.ui_group.draw(screen)


class GameOverState(game_interface.State):
    def __init__(self, parent: InGameState):
        self.parent = parent
        self.interface = parent.interface
        font = assets.font(consts.FONTNAME, consts.FONTSIZE * 3)
        self.text_surface = font.render(
            "GAME OVER", False, consts.GAMEOVER_TEXT_COLOR, None
        )
        self.text_surface = pg.transform.scale_by(self.text_surface, 3)

    def render(self, screen: pg.Surface):
        self.parent.render(screen)
        screen.fill(consts.UNEXPLORED_TINT, special_flags=pg.BLEND_MULT)
        pos = (screen.width // 2, screen.height // 2)
        rect = self.text_surface.get_rect(center=pos)
        screen.blit(self.text_surface, rect)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE):
                self.pop()
        if event.type == pg.MOUSEBUTTONUP:
            self.pop()

    def pop(self):
        self.interface.logic.new_game()
        self.interface.pop()
        self.interface.pop()
        self.interface.push(InGameState(self.interface))


class MapState(game_interface.State):
    def __init__(self, interface: game_interface.GameInterface):
        self.interface = interface
        self.logic = interface.logic
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        scale = min(
            [
                (consts.SCREEN_SHAPE[i] - consts.TILE_SIZE) // consts.MAP_SHAPE[i]
                for i in range(2)
            ]
        )
        self.map = ui_elements.Minimap(
            self.ui_group, self.logic, scale, follow_player=False
        )
        self.hud = ui_elements.StatsHUD(
            self.ui_group,
            self.interface,
            {
                "Depth": lambda: self.map.depth,
            },
        )

    def update(self):
        super().update()
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        screen.fill(consts.BACKGROUND_COLOR)
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE, pg.K_m):
                self.interface.pop()
            elif event.key == pg.K_PAGEDOWN:
                self.map.inc_depth(1)
            elif event.key == pg.K_PAGEUP:
                self.map.inc_depth(-1)
        if event.type == pg.MOUSEBUTTONUP:
            if event.button == 1:
                self.interface.pop()
