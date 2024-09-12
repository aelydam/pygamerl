from __future__ import annotations
import random
import numpy as np
import tcod

import consts
import entities
import funcs

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import game_logic


class Map:
    def __init__(self, shape: tuple[int, int], logic: game_logic.GameLogic):
        self.logic = logic
        self.tiles = np.full(shape, consts.TILE_VOID, dtype=np.int8)
        self.explored = np.full(shape, False)
        self.entities: list[entities.Entity] = []

    @property
    def shape(self):
        return self.tiles.shape

    @property
    def opaque(self):
        return consts.TILE_ARRAY['opaque'][self.tiles]

    @property
    def obstacle(self):
        return consts.TILE_ARRAY['obstacle'][self.tiles]

    @property
    def walkable(self):
        return ~self.obstacle

    @property
    def transparent(self):
        return ~self.opaque

    def is_walkable(self, x: int, y: int) -> bool:
        if not self.walkable[x, y]:
            return False
        for e in self.entities:
            if e.x == x and e.y == y:
                return False
        return True

    def astar_path(self,
                   origin: tuple[int, int],
                   target: tuple[int, int]) -> list[tuple[int, int]]:
        cost = self.walkable * 1
        for e in self.entities:
            cost[e.x, e.y] = 0
        cost[origin[0], origin[1]] = 1
        cost[target[0], target[1]] = 1
        graph = tcod.path.SimpleGraph(cost=cost.astype(np.int8),
                                      cardinal=5, diagonal=7)
        pathfinder = tcod.path.Pathfinder(graph)
        pathfinder.add_root(origin)
        return pathfinder.path_to(target).tolist()

    def spawn_enemies(self, count: int):
        x, y = np.where(self.walkable)
        i = list(range(len(x)))
        random.shuffle(i)
        for k in range(1, consts.N_ENEMIES+1):
            enemy = entities.Enemy(self.logic, x[i[k]], y[i[k]])
            self.entities.append(enemy)

    @classmethod
    def random_walk(cls, shape: tuple[int, int], logic: game_logic.GameLogic,
                    walkers: int = 5, steps: int = 500):
        res = cls(shape, logic)
        # Random walk algorithm
        for walkers in range(walkers):
            x, y = (consts.MAP_SHAPE[0] // 2, consts.MAP_SHAPE[1] // 2)
            res.tiles[x, y] = consts.TILE_FLOOR
            for step in range(steps):
                dx, dy = random.choice([(0, 1), (1, 0), (0, -1), (-1, 0)])
                if x + dx > 0 and x + dx < consts.MAP_SHAPE[0] - 1 and \
                        y + dy > 0 and y + dy < consts.MAP_SHAPE[1] - 1:
                    x += dx
                    y += dy
                    res.tiles[x, y] = consts.TILE_FLOOR
                else:
                    break
        # Add walls
        walls = (funcs.moore(res.tiles == consts.TILE_FLOOR) > 0) & \
            (res.tiles == consts.TILE_VOID)
        res.tiles[walls] = consts.TILE_WALL
        # Find wall tiles that are above floor tiles
        cond = (res.tiles[:, 1:] == consts.TILE_FLOOR) & \
            (res.tiles[:, :-1] == consts.TILE_WALL)
        res.tiles[:, :-1] = \
            np.where(cond, consts.TILE_WALL2, res.tiles[:, :-1])
        return res
