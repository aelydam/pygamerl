from __future__ import annotations

import random
from typing import TYPE_CHECKING

import numpy as np

import consts
import entities
import maps
import procgen

if TYPE_CHECKING:
    import actions
    from entities import Entity


class GameLogic:
    def __init__(self) -> None:
        self.input_action: actions.Action | None
        self.message_log: list[str]
        self.last_action: actions.Action | None
        self.map: maps.Map
        self.turn_count = 0
        self.frame_count = 0
        self.new_game()

    def new_game(self) -> None:
        self.current_turn = -1
        self.input_action = None
        self.message_log = []
        self.last_action = None
        self.turn_count = 0
        self.frame_count = 0
        self.map = maps.Map(consts.MAP_SHAPE, self)
        procgen.generate(self.map)
        self.init_player()
        self.next_turn()

    def init_player(self):
        x, y = np.where(self.map.walkable)
        i = random.randint(0, len(x) - 1)
        self.player = entities.Player(self.map, x[i], y[i])
        self.entities.append(self.player)

    def log(self, text: str):
        self.message_log.append(text)

    @property
    def entities(self) -> list[Entity]:
        return self.map.entities

    @property
    def current_entity(self) -> Entity:
        return self.entities[self.current_turn]

    def next_turn(self):
        self.turn_count += 1
        self.current_turn = 0

    def next_entity(self):
        self.current_turn += 1
        if self.current_turn >= len(self.entities):
            self.current_turn = 0
            self.next_turn()
        self.current_entity.update_fov()

    def update_entity(self) -> bool:
        entity = self.current_entity
        in_fov = self.player.fov[self.current_entity.x, self.current_entity.y]
        action = None
        if entity is None:
            self.next_entity()
            return True
        if entity.hp < 1:
            self.entities.remove(entity)
            self.next_entity()
            return True
        if isinstance(entity, entities.Player):
            if self.input_action is not None and self.input_action.can():
                action = self.input_action
            else:
                return False  # Waiting for player input
        elif isinstance(entity, entities.Enemy):
            if in_fov and (self.frame_count + self.current_turn) % 5 != 0:
                return False
            action = entity.next_action()
        if action is not None:
            self.last_action = action.perform()
            entity.update_fov()
        self.input_action = None
        self.next_entity()
        return not in_fov

    def update(self):
        self.frame_count += 1
        for e in self.entities:
            if not self.update_entity():
                break
