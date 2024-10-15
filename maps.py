from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import tcod
import tcod.constants
import tcod.ecs as ecs
from numpy.typing import NDArray

import comp
import consts
import procgen

if TYPE_CHECKING:
    import game_logic


def get_map(reg: ecs.Registry, depth: int) -> ecs.Entity:
    map_entity = reg[(comp.Map, depth)]
    if comp.Depth not in map_entity.components:
        map_entity.components[comp.Depth] = depth
        procgen.generate(map_entity)
    return map_entity


def is_in_bounds(
    map_: NDArray | ecs.Entity, pos: comp.Position | tuple[int, int]
) -> bool:
    if isinstance(map_, ecs.Entity):
        map_ = map_.components[comp.Tiles]
    if isinstance(pos, comp.Position):
        pos = pos.xy
    return (
        (pos[0] >= 0)
        and (pos[0] < map_.shape[0])
        and (pos[1] >= 0)
        and (pos[1] < map_.shape[1])
    )


def is_explored(map_entity: ecs.Entity, pos: comp.Position | tuple[int, int]) -> bool:
    if not is_in_bounds(map_entity, pos):
        return False
    if comp.Explored not in map_entity.components:
        return False
    if isinstance(pos, comp.Position):
        pos = pos.xy
    return map_entity.components[comp.Explored][pos]


def is_walkable(map_entity: ecs.Entity, pos: comp.Position | tuple[int, int]) -> bool:
    if not is_in_bounds(map_entity, pos):
        return False
    depth = map_entity.components[comp.Depth]
    if isinstance(pos, comp.Position):
        if pos.depth != depth:
            return False
    else:
        pos = comp.Position(pos, depth)
    grid = map_entity.components[comp.Tiles]
    if consts.TILE_ARRAY["obstacle"][grid[pos.xy]]:
        return False
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        tags=[comp.Obstacle, pos],
        relations=[(comp.Map, map_entity)],
    )
    for e in query:
        return False
    return True


def cost_matrix(map_entity: ecs.Entity, entity_cost: int = 2) -> NDArray[np.int8]:
    grid = map_entity.components[comp.Tiles]
    cost = 1 - consts.TILE_ARRAY["obstacle"][grid]
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        tags=[comp.Obstacle],
        relations=[(comp.Map, map_entity)],
    )
    for e in query:
        xy = e.components[comp.Position].xy
        cost[xy] += entity_cost
    return cost.astype(np.int8)


def astar_path(
    actor: ecs.Entity,
    target: tuple[int, int] | comp.Position | ecs.Entity,
    entity_cost: int = 2,
    cardinal: int = 5,
    diagonal: int = 7,
) -> list[tuple[int, int]]:
    map_entity = actor.relation_tag[comp.Map]
    origin = actor.components[comp.Position].xy
    if isinstance(target, ecs.Entity):
        if target.relation_tag[comp.Map] != map_entity:
            return []
        target = target.components[comp.Position]
    if isinstance(target, comp.Position):
        target = target.xy
    cost = cost_matrix(map_entity, entity_cost=entity_cost)
    cost[origin] = 1
    cost[target] = 1
    # Use tcod pathfinding stuff
    graph = tcod.path.SimpleGraph(cost=cost, cardinal=cardinal, diagonal=diagonal)
    pathfinder = tcod.path.Pathfinder(graph)
    pathfinder.add_root(origin)
    return pathfinder.path_to(target).tolist()
