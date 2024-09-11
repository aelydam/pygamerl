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
        self.sprite_group = pg.sprite.Group()
        self.ui_group = pg.sprite.Group()
        self.tilesheet = pg.image.load('32rogues/tiles.png').convert_alpha()
        self.hpbar = ui_elements.HPBar(self.ui_group, self.logic, self)
        self.log = ui_elements.MessageLog(self.ui_group, self.logic, self)
        self.minimap = ui_elements.Minimap(self.ui_group, self.logic)
        self.init_sprites()

    def init_sprites(self):
        for x in range(consts.MAP_SHAPE[0]):
            for y in range(consts.MAP_SHAPE[1]):
                map_renderer.TileSprite(self.sprite_group, self, self.logic,
                                        x, y)
        for e in self.logic.entities:
            map_renderer.EntitySprite(self.sprite_group, self, self.logic, e)

    def grid_to_screen(self, i: int, j: int) -> tuple[int, int]:
        pi, pj = self.logic.player.x, self.logic.player.y
        x = consts.SCREEN_SHAPE[0]//2 + (i-pi) * consts.TILE_SIZE
        y = consts.SCREEN_SHAPE[1]//2 + (j-pj) * consts.TILE_SIZE
        return (x, y)

    def screen_to_grid(self, x: int, y, int) -> tuple[int, int]:
        pi, pj = self.logic.player.x, self.logic.player.y
        i = (x - consts.SCREEN_SHAPE[0]//2) // consts.TILE_SIZE + pi
        j = (y - consts.SCREEN_SHAPE[1]//2) // consts.TILE_SIZE + pj
        return (i, j)

    def handle_events(self):
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

    def update(self):
        self.logic.update()

    def render(self):
        if isinstance(self.logic.last_action, actions.AttackAction):
            ui_elements.Popup(self.ui_group, self.logic.last_action, self)
            self.logic.last_action = None
        self.sprite_group.update()
        self.ui_group.update()
        self.screen.fill("#000000")
        self.sprite_group.draw(self.screen)
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
