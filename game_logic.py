from __future__ import annotations

import datetime
import glob
import os
import pickle
import random
from collections import deque
from typing import TYPE_CHECKING

import numpy as np
import tcod.ecs as ecs

import comp
import consts
import db
import entities
import items
import maps
import procgen

if TYPE_CHECKING:
    import actions


def push_action(reg: ecs.Registry, action: actions.Action):
    reg[None].components[comp.ActionQueue].appendleft(action)


def log(reg: ecs.Registry, message: str):
    reg[None].components[comp.MessageLog].append(message)


class GameLogic:
    def __init__(self) -> None:
        self.continuous_action: actions.Action | None
        self.input_action: actions.Action | None
        self.last_action: actions.Action | None
        self.clear()

    def clear(self) -> None:
        self.active = False
        self.continuous_action = None
        self.input_action = None
        self.last_action = None
        self.frame_count = 0
        self.visual_metadata: dict = {}

    @property
    def map(self) -> ecs.Entity:
        return self.reg[comp.Player].relation_tag[comp.Map]

    @property
    def message_log(self) -> list[str]:
        return self.reg[None].components[comp.MessageLog]

    @property
    def player(self) -> ecs.Entity:
        return self.reg[comp.Player]

    def new_world(self, seed: int | None = None) -> None:
        if seed is None:
            random.seed()
            seed = random.randint(1, 999999)
        print(f"World seed: {seed}")
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
        self.reg[None].components[comp.Seed] = seed
        self.reg[None].components[random.Random] = random.Random(seed)
        self.reg[None].components[np.random.RandomState] = np.random.RandomState(seed)
        db.load_unknowns(self.reg)
        db.load_data(self.reg, "items")
        db.load_data(self.reg, "creatures")
        maps.get_map(self.reg, 0)

    def new_game(self) -> None:
        self.new_world()
        self.init_player()
        self.next_turn()
        self.active = True

    def metadata(self) -> dict:
        return {
            "player_name": self.player.components[comp.Name],
            "player_sprite": self.player.components[comp.Sprite],
            "last_played": self.reg[None].components[comp.LastPlayed],
            "played_time": self.played_time,
            "turns": self.turn_count,
            "depth": self.player.components[comp.Position].depth,
        }

    def save_game(self, extra_metadata: dict | None = None):
        if comp.Filename in self.reg[None].components:
            filename = self.reg[None].components[comp.Filename]
        else:
            i = 1
            filename = f"game{i}"
            while os.path.exists(consts.SAVE_PATH / f"{filename}.pickle"):
                i += 1
                filename = f"game{i}"
            self.reg[None].components[comp.Filename] = filename
        path = consts.SAVE_PATH / f"{filename}.pickle"
        #
        metadata = self.metadata() | self.visual_metadata
        if extra_metadata is not None:
            metadata |= extra_metadata
        with open(path, "wb") as f:
            pickle.dump(metadata, f)
            pickle.dump(self.reg, f)
        print(f"Game saved at {path}")

    def file_metadata(self, filename: str) -> dict:
        path = consts.SAVE_PATH / f"{filename}.pickle"
        with open(path, "rb") as f:
            metadata = pickle.load(f)
        return metadata

    def load_game(self, filename: str):
        self.clear()
        path = consts.SAVE_PATH / f"{filename}.pickle"
        with open(path, "rb") as f:
            metadata = pickle.load(f)  # Discard header
            data = pickle.load(f)
        assert isinstance(data, ecs.Registry)
        self.reg = data
        self.reg[None].components[comp.Filename] = filename
        last_played = self.reg[None].components[comp.LastPlayed]
        now = datetime.datetime.now(last_played.tzinfo)
        self.reg[None].components[comp.LastPlayed] = now

        self.frame_count = 0
        self.input_action = None
        self.last_action = None
        self.continuous_action = None
        self.active = True

    @staticmethod
    def delete_game(filename: str):
        path = consts.SAVE_PATH / f"{filename}.pickle"
        os.remove(path)

    @staticmethod
    def list_savefiles() -> list[str]:
        files = glob.glob(str(consts.SAVE_PATH / "game*.pickle"))
        files = sorted(files, key=lambda f: -os.stat(f).st_mtime)
        return [os.path.splitext(os.path.basename(f))[0] for f in files]

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
        player.components[comp.ArmorClass] = 10
        player.components[comp.DamageDice] = 1
        player.components[comp.FOVRadius] = consts.DEFAULT_FOV_RADIUS
        player.components[comp.Speed] = consts.BASE_SPEED
        player.components[comp.Initiative] = 1
        player.components[comp.Hunger] = 0
        player.tags |= {comp.Player, comp.Obstacle, comp.Lit}
        player.relation_tag[comp.Map] = map_entity
        entities.update_fov(player)
        items.add_item(player, "Protection Ring")
        items.add_item(player, "Speed Ring")
        items.add_item(player, "Map")
        items.add_item(player, "Healing Potion", 6)
        items.add_item(player, "Rations", 2)
        items.add_item(player, "Bread", 2)
        items.add_item(player, "Apple", 2)
        items.equip(player, items.add_item(player, "Dagger"))
        items.equip(player, items.add_item(player, "Leather Armor"))
        items.equip(player, items.add_item(player, "Torch"))

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
        map_entity = self.map
        self.reg[None].components[comp.TurnCount] += 1
        initiative = self.initiative
        initiative.clear()
        procgen.respawn(map_entity)
        entities.update_hunger(map_entity)
        query = self.reg.Q.all_of(
            components=[comp.Position, comp.Initiative],
            relations=[(comp.Map, map_entity)],
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
        in_fov = False
        if hasattr(result, "xy"):
            xy: tuple[int, int] = result.xy
            in_fov = entities.is_in_fov(self.player, xy)
        if hasattr(result, "actor"):
            actor: ecs.Entity = result.actor  # type: ignore
            entities.update_fov(actor)
            if comp.Initiative in actor.components:
                actor.components[comp.Initiative] -= result.cost
            in_fov = in_fov or entities.is_in_fov(self.player, actor)
            if hasattr(result, "target") and result.target == self.player:
                self.continuous_action = None
        if in_fov and result.message != "":
            self.log(result.message)
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
