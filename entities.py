from __future__ import annotations
import random
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
        super().__init__(map_, x, y, '32rogues/rogues.png', 1, 1)
        self.max_hp = 40
        self.hp = 40
        self.name = 'Player'

    def update_fov(self):
        super().update_fov()
        self.map.explored |= self.fov


class Enemy(Entity):
    def __init__(self, map_: maps.Map, x: int, y: int):
        super().__init__(map_, x, y, '32rogues/monsters.png', 0, 0)
        self.name = 'Enemy'

    def next_action(self) -> actions.Action:
        player = self.map.logic.player
        px, py = player.x, player.y
        dist = ((px-self.x)**2 + (py-self.y)**2)**0.5
        if player.hp < 1 or not self.fov[px, py]:
            dx, dy = random.randint(-1, 1), random.randint(-1, 1)
            return actions.MoveAction(dx, dy, self)
        if dist < 1.5:
            return actions.AttackAction(player, self)
        path = self.map.astar_path(
            (self.x, self.y), (player.x, player.y))
        if len(path) < 2:
            return actions.WaitAction()
        dx = path[1][0] - path[0][0]
        dy = path[1][1] - path[0][1]
        return actions.MoveAction(dx, dy, self)
