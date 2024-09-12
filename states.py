import pygame as pg

import game_interface
import ui_elements
import map_renderer
import consts
import actions


class InGameState(game_interface.State):
    def __init__(self, interface: game_interface.GameInterface):
        self.interface = interface
        self.logic = interface.logic
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        self.hpbar = ui_elements.HPBar(self.ui_group, self.logic, interface)
        self.log = ui_elements.MessageLog(self.ui_group, self.logic, interface)
        self.minimap = ui_elements.Minimap(self.ui_group, self.logic)
        self.map_renderer = map_renderer.MapRenderer(interface)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYDOWN:
            if event.key in consts.MOVE_KEYS.keys():
                dx, dy = consts.MOVE_KEYS[event.key]
                self.logic.input_action = \
                    actions.BumpAction(dx, dy, self.logic.player)
            elif event.key in consts.WAIT_KEYS:
                self.logic.input_action = actions.WaitAction()
        elif event.type == pg.MOUSEBUTTONUP:
            if event.button != 1:
                return
            x, y = self.map_renderer.screen_to_grid(event.pos[0],
                                                    event.pos[1])
            if not self.logic.map.explored[x, y]:
                return
            player = self.logic.player
            if x == player.x and y == player.y:
                self.logic.input_action = actions.WaitAction()
                return
            dx, dy = x - player.x, y - player.y
            dist = (dx ** 2 + dy ** 2) ** 0.5
            if dist <= 1.5:
                self.logic.input_action = \
                    actions.BumpAction(dx, dy, player)
                return
            path = self.logic.map.astar_path((player.x, player.y), (x, y))
            if len(path) < 2:
                return
            dx = path[1][0] - path[0][0]
            dy = path[1][1] - path[0][1]
            self.logic.input_action = actions.BumpAction(dx, dy, player)

    def update(self):
        self.logic.update()
        if self.logic.player.hp < 1:
            self.interface.push(GameOverState(self))
            return
        if isinstance(self.logic.last_action, actions.AttackAction):
            ui_elements.Popup(self.map_renderer, self.logic.last_action,
                              self.interface)
            self.logic.last_action = None
        self.map_renderer.update()
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        screen.fill(consts.BACKGROUND_COLOR)
        self.map_renderer.draw(screen)
        self.ui_group.draw(screen)


class GameOverState(game_interface.State):
    def __init__(self, parent: InGameState):
        self.parent = parent
        self.interface = parent.interface
        font = pg.Font(size=48)
        self.text_surface = \
            font.render("GAME OVER", False, consts.GAMEOVER_TEXT_COLOR, None)
        self.text_surface = pg.transform.scale_by(self.text_surface, 3)

    def render(self, screen: pg.Surface):
        self.parent.render(screen)
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
