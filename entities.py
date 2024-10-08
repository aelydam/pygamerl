from __future__ import annotations
import tcod

import actions
import maps
import consts


class Entity:
    def __init__(self, map_: maps.Map,
                 x: int, y: int,
                 sprite: str, row: int, col: int):
        self.map = map_
        self.x, self.y = x, y
        self.dx, self.dy = 0, 0
        self.sprite, self.row, self.col = sprite, row, col
        self.max_hp = 10
        self.hp = 10
        self.tohit = 4
        self.damage = 6
        self.ac = 12
        self.fov_radius = consts.FOV_RADIUS
        self.kills = 0
        self.hits = 0
        self.misses = 0
        self.steps = 0
        self.name = ''
        self.update_fov()

    def update_fov(self):
        transparency = self.map.transparent
        self.fov = tcod.map.compute_fov(
            transparency, (self.x, self.y), self.fov_radius,
            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)


class Player(Entity):
    def __init__(self, map_: maps.Map, x: int, y: int):
        super().__init__(map_, x, y, 'tiles-dcss/human_male.png', 0, 0)
        self.max_hp = 40
        self.hp = 40
        self.name = 'Player'

    def update_fov(self):
        super().update_fov()
        # Set visible tiles as explored
        self.map.explored |= self.fov


class Enemy(Entity):
    def __init__(self, map_: maps.Map, x: int, y: int):
        super().__init__(map_, x, y, 'tiles-dcss/skeleton_humanoid_small_new.png', 0, 0)
        self.name = 'Enemy'

    def next_action(self) -> actions.Action:
        player = self.map.logic.player
        px, py = player.x, player.y
        dist = ((px - self.x) ** 2 + (py - self.y) ** 2) ** 0.5
        # Move if player dead or not in FOV
        if player.hp < 1 or not self.fov[px, py]:
            return actions.MoveAction.random(self)
        # Attack player if in reach
        if dist < 1.5:
            return actions.AttackAction(player, self)
        # Move towards player
        move_to = actions.MoveAction.to((player.x, player.y), self)
        if move_to is None:
            return actions.WaitAction()
        else:
            return move_to
