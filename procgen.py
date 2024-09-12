
from __future__ import annotations

import random
import numpy as np

import maps
import funcs
import consts
import entities


def add_walls(map_: maps.Map):
    # Add walls
    walls = (funcs.moore(map_.tiles == consts.TILE_FLOOR) > 0) & \
        (map_.tiles == consts.TILE_VOID)
    map_.tiles[walls] = consts.TILE_WALL
    # Find wall tiles that are above floor tiles
    cond = (map_.tiles[:, 1:] == consts.TILE_FLOOR) & \
        (map_.tiles[:, :-1] == consts.TILE_WALL)
    map_.tiles[:, :-1] = \
        np.where(cond, consts.TILE_WALL2, map_.tiles[:, :-1])
    return map_


def spawn_enemies(map_: maps.Map, count: int):
    x, y = np.where(map_.walkable)
    i = list(range(len(x)))
    random.shuffle(i)
    for k in range(count):
        enemy = entities.Enemy(map_, x[i[k]], y[i[k]])
        map_.entities.append(enemy)


def random_walk(map_: maps.Map,
                walkers: int = 5, steps: int = 500):
    # Random walk algorithm
    for walkers in range(walkers):
        x, y = (consts.MAP_SHAPE[0] // 2, consts.MAP_SHAPE[1] // 2)
        map_.tiles[x, y] = consts.TILE_FLOOR
        for step in range(steps):
            dx, dy = random.choice([(0, 1), (1, 0), (0, -1), (-1, 0)])
            if x + dx > 0 and x + dx < consts.MAP_SHAPE[0] - 1 and \
                    y + dy > 0 and y + dy < consts.MAP_SHAPE[1] - 1:
                x += dx
                y += dy
                map_.tiles[x, y] = consts.TILE_FLOOR
            else:
                break
    add_walls(map_)
    spawn_enemies(map_, consts.N_ENEMIES)
    return map_
