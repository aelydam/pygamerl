from __future__ import annotations

import pygame as pg

import consts
import game_logic


class State:
    def __init__(self, interface: GameInterface):
        self.interface = interface

    def update(self):
        pass

    def handle_event(self, event: pg.Event):
        pass

    def render(self, screen: pg.Surface):
        pass


class GameInterface:
    def __init__(self) -> None:
        pg.init()
        self.screen = pg.display.set_mode(consts.SCREEN_SHAPE)
        self.clock = pg.time.Clock()
        self.font = pg.font.Font(consts.FONTNAME, consts.FONTSIZE)
        self.logic = game_logic.GameLogic()
        self.state_stack: list[State] = []

    def push(self, state: State):
        self.state_stack.append(state)

    def pop(self):
        self.state_stack.pop()

    @property
    def state(self) -> State | None:
        if len(self.state_stack) < 1:
            return None
        return self.state_stack[-1]

    def handle_events(self) -> None:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
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
