from __future__ import annotations
import random
import tcod

import actions

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from game_logic import GameLogic


class Entity:
    def __init__(self, game_logic: GameLogic,
                 x: int, y: int,
                 sprite: str, row: int, col: int):
        self.game_logic = game_logic
        self.x, self.y = x, y
        self.sprite, self.row, self.col = sprite, row, col
        self.max_hp = 10
        self.hp = 10
        self.tohit = 4
        self.damage = 6
        self.ac = 12
        self.fov_radius = 5
        self.update_fov()

    def update_fov(self):
        transparency = self.game_logic.map.transparent
        self.fov = tcod.map.compute_fov(
            transparency, (self.x, self.y), self.fov_radius,
            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)


class Player(Entity):
    def __init__(self, game_logic: GameLogic, x: int, y: int):
        super().__init__(game_logic, x, y, '32rogues/rogues.png', 1, 1)
        self.max_hp = 40
        self.hp = 40

    def update_fov(self):
        super().update_fov()
        self.game_logic.map.explored |= self.fov


class Enemy(Entity):
    def __init__(self, game_logic: GameLogic, x: int, y: int):
        super().__init__(game_logic, x, y, '32rogues/monsters.png', 0, 0)

    def next_action(self) -> actions.Action:
        player = self.game_logic.player
        px, py = player.x, player.y
        dist = ((px-self.x)**2 + (py-self.y)**2)**0.5
        if player.hp < 1 or not self.fov[px, py]:
            dx, dy = random.randint(-1, 1), random.randint(-1, 1)
            return actions.MoveAction(dx, dy, self)
        if dist < 1.5:
            return actions.AttackAction(player, self)
        path = self.game_logic.map.astar_path(
            (self.x, self.y), (player.x, player.y))
        if len(path) < 2:
            return actions.WaitAction()
        dx = path[1][0] - path[0][0]
        dy = path[1][1] - path[0][1]
        return actions.MoveAction(dx, dy, self)
