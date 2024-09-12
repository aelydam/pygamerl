from __future__ import annotations

import random
import numpy as np

import consts
import entities
import maps
import procgen

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import actions
    import game_interface


class GameLogic:
    def __init__(self, interface: game_interface.GameInterface):
        self.interface = interface
        self.input_action: actions.Action | None
        self.message_log: list[str]
        self.last_action: actions.Action | None
        self.map: maps.Map
        self.new_game()

    def new_game(self) -> None:
        self.current_turn = -1
        self.input_action = None
        self.message_log = []
        self.last_action = None
        self.map = maps.Map(consts.MAP_SHAPE, self)
        procgen.generate(self.map)
        self.init_player()

    def init_player(self):
        x, y = np.where(self.map.walkable)
        i = random.randint(0, len(x) - 1)
        self.player = entities.Player(self.map, x[i], y[i])
        self.entities.append(self.player)

    def log(self, text: str):
        self.message_log.append(text)

    @property
    def entities(self) -> list[entities.Entity]:
        return self.map.entities

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
