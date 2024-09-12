from __future__ import annotations

import random
import numpy as np

import consts
import entities
import maps

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import actions
    import game_interface


class GameLogic:
    def __init__(self, interface: game_interface.GameInterface):
        self.current_turn = -1
        self.interface = interface
        self.input_action: actions.Action | None = None
        self.message_log: list[str] = []
        self.last_action: actions.Action | None = None
        self.map = maps.Map.random_walk(consts.MAP_SHAPE, self)
        self.map.spawn_enemies(consts.N_ENEMIES)
        self.init_player()

    def log(self, text: str):
        self.message_log.append(text)

    @property
    def entities(self):
        return self.map.entities

    def init_player(self):
        x, y = np.where(self.map.walkable)
        i = random.randint(0, len(x) - 1)
        self.player = entities.Player(self, x[i], y[i])
        self.entities.append(self.player)

    def update(self):
        if self.current_turn >= len(self.entities):
            self.current_turn = 0
        entity = self.entities[self.current_turn]
        action = None
        if entity.hp < 1:
            self.entities.remove(entity)
            return
        if isinstance(entity, entities.Player):
            if self.input_action is not None and self.input_action.can():
                action = self.input_action
            else:
                return
        else:
            action = entity.next_action()
        if action is not None:
            self.last_action = action.perform()
        self.input_action = None
        self.current_turn += 1
        if self.current_turn >= len(self.entities):
            self.current_turn = 0
        self.entities[self.current_turn].update_fov()
