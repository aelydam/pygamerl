from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import tcod
import tcod.constants
import tcod.ecs as ecs
from numpy.typing import NDArray

import comp
import db
import entities
import procgen


def get_map(reg: ecs.Registry, depth: int, generate: bool = True) -> ecs.Entity:
    map_entity = reg[(comp.Map, depth)]
    if generate and comp.Depth not in map_entity.components:
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


def is_walkable(
    map_entity: ecs.Entity, pos: comp.Position | tuple[int, int], entities: bool = True
) -> bool:
    if not is_in_bounds(map_entity, pos):
        return False
    depth = map_entity.components[comp.Depth]
    if isinstance(pos, comp.Position):
        if pos.depth != depth:
            return False
    else:
        pos = comp.Position(pos, depth)
    grid = map_entity.components[comp.Tiles]
    if db.obstacle[grid[pos.xy]]:
        return False
    if not entities:
        return True
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        tags=[comp.Obstacle, pos],
        relations=[(comp.Map, map_entity)],
    )
    for e in query:
        return False
    return True


def lightlevel(map_entity: ecs.Entity, pos: comp.Position | tuple[int, int]) -> int:
    if not is_in_bounds(map_entity, pos):
        return 0
    depth = map_entity.components[comp.Depth]
    if isinstance(pos, comp.Position):
        if pos.depth != depth:
            return 0
        pos = pos.xy
    else:
        pos = comp.Position(pos, depth).xy
    if comp.Lightsource not in map_entity.components:
        update_map_light(map_entity)
    light = map_entity.components[comp.Lightsource]
    return int(light[pos[0], pos[1]])


def cost_matrix(
    map_entity: ecs.Entity,
    entity_cost: int = 10,
    door_cost: int = 1,
    explored_only: bool = False,
) -> NDArray[np.int8]:
    grid = map_entity.components[comp.Tiles]
    cost = 1 - db.obstacle[grid]
    if entity_cost != 0:
        query = map_entity.registry.Q.all_of(
            components=[comp.Position],
            tags=[comp.Obstacle],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            xy = e.components[comp.Position].xy
            if comp.Door in e.tags:
                cost[xy] += door_cost
            elif comp.Initiative in e.tags:
                cost[xy] += entity_cost
            else:
                cost[xy] = 0
    if explored_only:
        explored = map_entity.components[comp.Explored]
        cost[~explored] = 0
    return cost.astype(np.int8)


def transparency_matrix(
    map_entity: ecs.Entity, entities: bool = True
) -> NDArray[np.bool_]:
    grid = map_entity.components[comp.Tiles]
    transparency = db.transparency[grid]
    # Find opaque entities
    if entities:
        query = map_entity.registry.Q.all_of(
            components=[comp.Position],
            tags=[comp.Opaque],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            xy = e.components[comp.Position].xy
            transparency[xy] = False
    return transparency


def astar_path(
    actor: ecs.Entity,
    target: tuple[int, int] | comp.Position | ecs.Entity,
    entity_cost: int = 10,
    cardinal: int = 5,
    diagonal: int = 7,
    explored_only: bool = False,
) -> list[tuple[int, int]]:
    map_entity = actor.relation_tag[comp.Map]
    origin = actor.components[comp.Position].xy
    if isinstance(target, ecs.Entity):
        if target.relation_tag[comp.Map] != map_entity:
            return []
        target = target.components[comp.Position]
    if isinstance(target, comp.Position):
        target = target.xy
    cost = cost_matrix(map_entity, entity_cost=entity_cost, explored_only=explored_only)
    cost[origin] = 1
    cost[target] = 1
    # Use tcod pathfinding stuff
    graph = tcod.path.SimpleGraph(cost=cost, cardinal=cardinal, diagonal=diagonal)
    pathfinder = tcod.path.Pathfinder(graph)
    pathfinder.add_root(origin)
    return pathfinder.path_to(target).tolist()


def update_map_light(map_entity: ecs.Entity, update_entities: bool = False):
    grid = map_entity.components[comp.Tiles]
    light = np.zeros(grid.shape, np.int8)
    #
    query = map_entity.registry.Q.all_of(
        components=[comp.LightRadius, comp.Position],
        tags={comp.Lit},
        relations=[(comp.Map, map_entity)],
        traverse=[slot for slot in comp.EquipSlot] + [ecs.IsA, comp.ConditionTurns],
    )
    for e in query:
        if update_entities or comp.Lightsource not in e.components:
            entities.update_entity_light(e)
        if comp.Lightsource in e.components:
            elight = e.components[comp.Lightsource]
            light[elight > light] = elight[elight > light]
    map_entity.components[comp.Lightsource] = light
