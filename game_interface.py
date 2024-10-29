from __future__ import annotations

import pygame as pg

import assets
import consts
import db
import game_logic


class State:
    def __init__(self, parent: GameInterface | State):
        if isinstance(parent, GameInterface):
            self.interface = parent
        else:
            self.parent = parent
            self.interface = parent.interface

    def update(self):
        pass

    def handle_event(self, event: pg.Event):
        pass

    def render(self, screen: pg.Surface):
        pass


class GameInterface:
    def __init__(self) -> None:
        pg.init()
        db.load_tiles()
        self.screen = pg.display.set_mode(consts.SCREEN_SHAPE, pg.SCALED)
        pg.display.set_caption(consts.GAME_TITLE)
        self.clock = pg.time.Clock()
        self.font = assets.font(consts.FONTNAME, consts.FONTSIZE)
        self.logic = game_logic.GameLogic()
        self.state_stack: list[State] = []
        self.sfx_volume = 60
        self.master_volume = 60

    def push(self, state: State):
        self.state_stack.append(state)

    def pop(self):
        self.state_stack.pop()

    def clear(self):
        self.state_stack.clear()

    def reset(self, state: State):
        self.clear()
        self.push(state)

    @property
    def state(self) -> State | None:
        if len(self.state_stack) < 1:
            return None
        return self.state_stack[-1]

    def handle_events(self) -> None:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
                if self.logic.active:
                    self.logic.save_game()
            elif self.state is not None:
                self.state.handle_event(event)

    def update(self):
        if self.state is None:
            self.running = False
            return
        self.state.update()

    def render(self):
        if self.state is not None:
            self.state.render(self.screen)
        pg.display.flip()

    def run(self):
        self.running = True
        while self.running:
            self.delta_time = self.clock.tick(consts.FPS) / 1000
            self.handle_events()
            self.update()
            self.render()
        pg.quit()

    def play_sfx(self, sfx: str):
        obj = assets.sfx(sfx)
        obj.set_volume(self.sfx_volume * self.master_volume / 10000)
        obj.play()
