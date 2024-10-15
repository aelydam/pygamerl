from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING

import numpy as np
import tcod.ecs as ecs

import comp
import consts
import entities
import maps
import procgen

if TYPE_CHECKING:
    import actions


class GameLogic:
    def __init__(self) -> None:
        self.continuous_action: actions.Action | None
        self.input_action: actions.Action | None
        self.last_action: actions.Action | None
        self.turn_count = 0
        self.frame_count = 0
        self.new_game()

    @property
    def map(self) -> ecs.Entity:
        return self.reg[comp.Player].relation_tag[comp.Map]

    @property
    def message_log(self) -> list[str]:
        return self.reg[None].components[comp.MessageLog]

    @property
    def player(self) -> ecs.Entity:
        return self.reg[comp.Player]

    def new_game(self) -> None:
        self.reg = ecs.Registry()

        self.current_turn = -1
        self.input_action = None
        self.continuous_action = None
        self.reg[None].components[comp.MessageLog] = []
        self.reg[None].components[comp.InitiativeTracker] = deque([])

        self.last_action = None
        self.turn_count = 0
        self.frame_count = 0
        maps.get_map(self.reg, 0)
        self.init_player()
        self.next_turn()

    def init_player(self):
        map_entity = maps.get_map(self.reg, 0)
        grid = map_entity.components[comp.Tiles]
        walkable = ~consts.TILE_ARRAY["obstacle"][grid]
        x, y = np.where(walkable)
        i = random.randint(0, len(x) - 1)
        player = self.player
        player.clear()
        player.components[comp.Name] = "Player"
        player.components[comp.Position] = comp.Position((x[i], y[i]), 0)
        player.components[comp.Sprite] = comp.Sprite("human_male", (0, 0))
        player.components[comp.MaxHP] = 48
        player.components[comp.HP] = 48
        player.components[comp.AttackBonus] = 4
        player.components[comp.ArmorClass] = 14
        player.components[comp.DamageDice] = 6
        player.components[comp.FOVRadius] = 8
        player.components[comp.Initiative] = 1
        player.tags |= {comp.Player, comp.Obstacle}
        player.relation_tag[comp.Map] = map_entity
        entities.update_fov(player)

    def log(self, text: str):
        self.message_log.append(text)

    @property
    def initiative(self) -> deque[ecs.Entity]:
        return self.reg[None].components[comp.InitiativeTracker]

    @property
    def current_entity(self) -> ecs.Entity:
        return self.initiative[0]

    def next_turn(self):
        self.turn_count += 1
        initiative = self.initiative
        initiative.clear()
        query = self.reg.Q.all_of(
            components=[comp.Position, comp.Initiative],
            relations=[(comp.Map, self.map)],
        )
        for e in query:
            e.components[comp.Initiative] += 1
            if e.components[comp.Initiative] > 0:
                initiative.append(e)

    def next_entity(self):
        initiative = self.initiative
        initiative.popleft()
        if len(initiative) < 1:
            self.next_turn()
            return False
        entities.update_fov(self.current_entity)
        return True

    def update_entity(self) -> bool:
        if len(self.initiative) < 1:
            self.next_turn()
            return False
        entity = self.current_entity
        in_fov = entities.is_in_fov(entity, self.player)
        action = None
        if entity is None:
            return self.next_entity()
        if not entities.is_alive(entity):
            return self.next_entity()
        if comp.Player in entity.tags:
            if self.continuous_action is not None and self.continuous_action.can():
                action = self.continuous_action
                if entities.has_enemy_in_fov(entity) and action.cost > 0:
                    self.continuous_action = None
            elif self.input_action is not None and self.input_action.can():
                self.continuous_action = None
                action = self.input_action
            else:
                self.continuous_action = None
                return False  # Waiting for player input
        else:
            action = entities.enemy_action(entity)
        if action is not None:
            result = action.perform()
            self.last_action = result
            entities.update_fov(entity)
            if result is not None:
                if result.message != "":
                    self.log(result.message)
                if comp.Initiative in entity.components:
                    entity.components[comp.Initiative] -= result.cost
        self.input_action = None
        if entity.components.get(comp.Initiative, 0) < 1:
            self.next_entity()
        return not in_fov

    def update(self):
        self.frame_count += 1
        for _ in range(100):
            if not self.update_entity():
                break
