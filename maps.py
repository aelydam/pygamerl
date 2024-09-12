from __future__ import annotations
import numpy as np
import tcod

import consts
import entities

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
        # Create walking cost matrix
        cost = self.walkable * 1
        for e in self.entities:
            cost[e.x, e.y] = 0
        cost[origin[0], origin[1]] = 1
        cost[target[0], target[1]] = 1
        # Use tcod pathfinding stuff
        # diagonal uses 7 and cardinal 5 because 7/5=1.4 ~= sqrt(2)
        graph = tcod.path.SimpleGraph(cost=cost.astype(np.int8),
                                      cardinal=5, diagonal=7)
        pathfinder = tcod.path.Pathfinder(graph)
        pathfinder.add_root(origin)
        return pathfinder.path_to(target).tolist()
