
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


def spawn_enemies(map_: maps.Map, radius: int, max_count: int = 0):
    xgrid, ygrid = np.indices(map_.shape)
    counter = 0
    # Initialize available array from walkable points
    available = map_.walkable.copy()
    # While there are available spots and still below max_count
    while (counter < max_count or max_count < 1) and np.sum(available) > 0:
        # Pick a random available point
        all_x, all_y = np.where(available)
        i = random.randint(0, len(all_x) - 1)
        x, y = all_x[i], all_y[i]
        # Spawn enemy and increase counter
        enemy = entities.Enemy(map_, x, y)
        map_.entities.append(enemy)
        counter += 1
        # Make all points within radius unavailable
        dist2 = (xgrid - x) ** 2 + (ygrid - y) ** 2
        available[dist2 <= radius ** 2] = False


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
    return map_


def generate(map_: maps.Map):
    random_walk(map_)
    add_walls(map_)
    spawn_enemies(map_, consts.ENEMY_RADIUS, consts.N_ENEMIES)
    return map_
