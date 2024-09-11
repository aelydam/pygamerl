import pygame as pg

import consts
import game_logic
import ui_elements
import map_renderer
import actions


class GameInterface:
    def __init__(self):
        pg.init()
        self.screen = pg.display.set_mode(consts.SCREEN_SHAPE)
        self.clock = pg.time.Clock()
        self.font = pg.font.Font()
        self.logic = game_logic.GameLogic(self)
        self.ui_group = pg.sprite.Group()
        self.hpbar = ui_elements.HPBar(self.ui_group, self.logic, self)
        self.log = ui_elements.MessageLog(self.ui_group, self.logic, self)
        self.minimap = ui_elements.Minimap(self.ui_group, self.logic)
        self.map_renderer = map_renderer.MapRenderer(self)

    def handle_events(self) -> None:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
            elif event.type == pg.KEYDOWN:
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
                if not self.logic.explored[x, y]:
                    return
                player = self.logic.player
                if x == player.x and y == player.y:
                    self.logic.input_action = actions.WaitAction()
                    return
                dx, dy = x - player.x, y - player.y
                dist = (dx**2 + dy**2) ** 0.5
                if dist <= 1.5:
                    self.logic.input_action = \
                        actions.BumpAction(dx, dy, player)
                    return
                path = self.logic.astar_path((player.x, player.y), (x, y))
                if len(path) < 2:
                    return
                dx = path[1][0] - path[0][0]
                dy = path[1][1] - path[0][1]
                self.logic.input_action = actions.BumpAction(dx, dy, player)

    def update(self):
        self.logic.update()

    def render(self):
        if isinstance(self.logic.last_action, actions.AttackAction):
            ui_elements.Popup(self.map_renderer, self.logic.last_action, self)
            self.logic.last_action = None
        self.map_renderer.update()
        self.ui_group.update()
        self.screen.fill(consts.BACKGROUND_COLOR)
        self.map_renderer.draw(self.screen)
        self.ui_group.draw(self.screen)
        pg.display.flip()

    def run(self):
        self.running = True
        while self.running:
            self.delta_time = self.clock.tick(consts.FPS) / 1000
            self.handle_events()
            self.update()
            self.render()
        pg.quit()
