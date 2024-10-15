from __future__ import annotations

import random

import numpy as np
import tcod.ecs as ecs
from numpy.typing import NDArray

import comp
import consts
import entities
import funcs
import maps


def add_walls(grid: NDArray[np.int8]):
    # Find tiles that are void but are neighbors to a floor
    walls = (funcs.moore(grid == consts.TILE_FLOOR) > 0) & (grid == consts.TILE_VOID)
    grid[walls] = consts.TILE_WALL
    return walls


def spawn_enemies(map_entity: ecs.Entity, radius: int, max_count: int = 0):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    xgrid, ygrid = np.indices(grid.shape)
    walkable = ~consts.TILE_ARRAY["obstacle"][grid]
    counter = 0
    # Initialize available array from walkable points
    available = walkable.copy()
    # While there are available spots and still below max_count
    while (counter < max_count or max_count < 1) and np.sum(available) > 0:
        # Pick a random available point
        all_x, all_y = np.where(available)
        i = random.randint(0, len(all_x) - 1)
        x, y = all_x[i], all_y[i]
        # Spawn enemy and increase counter
        enemy = map_entity.registry.new_entity(
            components={
                comp.Position: comp.Position((x, y), depth),
                comp.Name: "Skeleton",
                comp.Sprite: comp.Sprite("skeleton_humanoid_small_new", (0, 0)),
                comp.MaxHP: 6,
                comp.HP: 6,
                comp.Initiative: 0,
                comp.FOVRadius: 6,
            },
            tags=[comp.Obstacle],
        )
        enemy.relation_tag[comp.Map] = map_entity
        counter += 1
        # Make all points within radius unavailable
        dist2 = (xgrid - x) ** 2 + (ygrid - y) ** 2
        available[dist2 <= radius**2] = False


def random_walk(grid: NDArray[np.int8], walkers: int = 5, steps: int = 500):
    # Random walk algorithm
    # Repeat for each walker
    for walkers in range(walkers):
        x, y = (consts.MAP_SHAPE[0] // 2, consts.MAP_SHAPE[1] // 2)
        grid[x, y] = consts.TILE_FLOOR
        # Walk each step
        for step in range(steps):
            # Choose a random direction
            dx, dy = random.choice([(0, 1), (1, 0), (0, -1), (-1, 0)])
            # If next step is within map bounds
            if maps.is_in_bounds(grid, (x + dx * 2, y + dy * 2)):
                # Walk
                x += dx
                y += dy
                # Set as floor
                grid[x, y] = consts.TILE_FLOOR
            else:
                break
    return grid


def generate(map_entity: ecs.Entity):
    grid = np.zeros(consts.MAP_SHAPE, np.int8)
    random_walk(grid)
    add_walls(grid)
    map_entity.components[comp.Tiles] = grid
    map_entity.components[comp.Explored] = np.full(grid.shape, False)
    spawn_enemies(map_entity, consts.ENEMY_RADIUS, consts.N_ENEMIES)
