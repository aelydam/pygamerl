from __future__ import annotations

import datetime
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


def push_action(reg: ecs.Registry, action: actions.Action):
    reg[None].components[comp.ActionQueue].appendleft(action)


class GameLogic:
    def __init__(self) -> None:
        self.continuous_action: actions.Action | None
        self.input_action: actions.Action | None
        self.last_action: actions.Action | None
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

    def new_world(self) -> None:
        self.reg = ecs.Registry()
        self.frame_count = 0
        self.input_action = None
        self.last_action = None
        self.continuous_action = None
        self.reg[None].components[comp.MessageLog] = []
        self.reg[None].components[comp.InitiativeTracker] = deque([])
        self.reg[None].components[comp.ActionQueue] = deque([])
        self.reg[None].components[comp.TurnCount] = 0
        self.reg[None].components[comp.LastPlayed] = datetime.datetime.now()
        self.reg[None].components[comp.PlayedTime] = 0
        maps.get_map(self.reg, 0)

    def new_game(self) -> None:
        self.new_world()
        self.init_player()
        self.next_turn()

    def init_player(self):
        map_entity = maps.get_map(self.reg, 0)
        player = self.player
        player.clear()
        player.components[comp.Name] = "Player"
        player.components[comp.Position] = procgen.player_spawn(map_entity)
        player.components[comp.Sprite] = comp.Sprite("Characters/Player0", (1, 3))
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
    def turn_count(self) -> int:
        return self.reg[None].components[comp.TurnCount]

    @property
    def played_time(self) -> float:
        return self.reg[None].components[comp.PlayedTime]

    @property
    def initiative(self) -> deque[ecs.Entity]:
        return self.reg[None].components[comp.InitiativeTracker]

    @property
    def current_entity(self) -> ecs.Entity:
        return self.initiative[0]

    @property
    def action_queue(self) -> deque[actions.Action]:
        return self.reg[None].components[comp.ActionQueue]

    def push_action(self, action: actions.Action):
        self.action_queue.appendleft(action)

    def next_turn(self):
        self.reg[None].components[comp.TurnCount] += 1
        initiative = self.initiative
        initiative.clear()
        procgen.respawn(self.map)
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
        if entity is None or not entities.can_act(entity):
            return self.next_entity()
        if comp.Player in entity.tags:
            if self.input_action is not None:
                self.continuous_action = None
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
            self.push_action(action)
        self.input_action = None
        if not entities.can_act(entity):
            self.next_entity()
        return not in_fov

    def act(self) -> bool:
        actions = self.action_queue
        if len(actions) < 1:
            return self.update_entity()
        action = actions.popleft()
        result = action.perform()
        self.last_action = result
        if result is None:
            return True
        if result.message != "":
            self.log(result.message)
        if hasattr(result, "actor"):
            actor: ecs.Entity = result.actor  # type: ignore
            entities.update_fov(actor)
            if comp.Initiative in actor.components:
                actor.components[comp.Initiative] -= result.cost
            in_fov = entities.is_in_fov(self.player, actor)
        else:
            in_fov = False
        return not in_fov

    def tick(self):
        self.frame_count += 1
        last_played = self.reg[None].components[comp.LastPlayed]
        now = datetime.datetime.now(last_played.tzinfo)
        elapsed = (now - last_played).total_seconds()
        if elapsed > 0:
            self.reg[None].components[comp.PlayedTime] += elapsed
            self.reg[None].components[comp.LastPlayed] = now

    def update(self):
        self.tick()
        for _ in range(100):
            if not self.act():
                break
