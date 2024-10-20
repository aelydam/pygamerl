from __future__ import annotations

import numpy as np
import tcod
import tcod.ecs as ecs

import actions
import comp
import consts
import funcs
import maps


def dist(
    origin: ecs.Entity | comp.Position | tuple[int, int],
    target: ecs.Entity | comp.Position | tuple[int, int],
) -> float:
    if isinstance(origin, ecs.Entity):
        origin = origin.components[comp.Position]
    if isinstance(target, ecs.Entity):
        target = target.components[comp.Position]
    if isinstance(origin, comp.Position):
        if isinstance(target, comp.Position) and origin.depth != target.depth:
            return 255
        origin = origin.xy
    if isinstance(target, comp.Position):
        target = target.xy
    return sum([(origin[i] - target[i]) ** 2 for i in range(2)]) ** 0.5


def update_fov(actor: ecs.Entity):
    if (
        comp.Map not in actor.relation_tag
        or comp.Position not in actor.components
        or comp.FOVRadius not in actor.components
    ):
        return
    map_entity = actor.relation_tag[comp.Map]
    update_entity_light(actor)
    maps.update_map_light(map_entity)
    light = map_entity.components[comp.Lightsource]
    #
    transparency = maps.transparency_matrix(map_entity)
    # Actor can see its own position
    xy = actor.components[comp.Position].xy
    transparency[xy] = True
    # Update player FOV
    radius = actor.components[comp.FOVRadius]
    fov = tcod.map.compute_fov(
        transparency, xy, radius, algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST
    )
    fov &= light > 0
    for dx in {-1, 0, 1}:
        for dy in {-1, 0, 1}:
            if maps.is_in_bounds(fov, (xy[0] + dx, xy[1] + dy)):
                fov[xy[0] + dx, xy[1] + dy] = True
    actor.components[comp.FOV] = fov
    # Set map as explored if this is a player
    if comp.Player in actor.tags:
        if comp.Explored not in map_entity.components:
            map_entity.components[comp.Explored] = fov.copy()
        else:
            map_entity.components[comp.Explored] |= fov


def is_in_fov(
    actor: ecs.Entity, pos: comp.Position | ecs.Entity | tuple[int, int]
) -> bool:
    if not is_alive(actor) or not comp.Position in actor.components:
        return False
    apos = actor.components[comp.Position]
    if isinstance(pos, ecs.Entity):
        if actor == pos:
            return True
        if comp.Position not in pos.components:
            return False
        pos = pos.components[comp.Position]
    if isinstance(pos, comp.Position):
        if apos.depth != pos.depth:
            return False
        pos = pos.xy
    d = dist(apos, pos)
    if d <= 1.5:
        return True
    if comp.FOVRadius not in actor.components:
        return False
    radius = actor.components[comp.FOVRadius]
    if d > radius:
        return False
    if comp.FOV not in actor.components:
        return False
    return actor.components[comp.FOV][pos]


def update_entity_light(entity: ecs.Entity):
    if (
        comp.LightRadius not in entity.components
        or comp.Position not in entity.components
        or comp.Lit not in entity.tags
    ):
        if comp.Lightsource in entity.components:
            entity.components.pop(comp.Lightsource)
        return
    map_entity = entity.relation_tag[comp.Map]
    grid = map_entity.components[comp.Tiles]
    transparency = maps.transparency_matrix(map_entity)
    x, y = entity.components[comp.Position].xy
    radius = entity.components[comp.LightRadius]
    fov1 = tcod.map.compute_fov(transparency, (x, y), radius, light_walls=False)
    fov2 = tcod.map.compute_fov(transparency, (x, y), radius, light_walls=True)
    fov = fov1 | (fov2 & (funcs.moore(fov1 & transparency) > 0))
    grid_x, grid_y = np.indices(grid.shape)
    dist = ((grid_x - x) ** 2 + (grid_y - y) ** 2) ** 0.5
    light = np.astype(
        fov * (1 + radius - dist) / (1 + radius) * consts.MAX_LIGHT_RADIUS, np.int8
    )
    entity.components[comp.Lightsource] = light


def enemies_in_fov(actor: ecs.Entity) -> set[ecs.Entity]:
    map_ = actor.relation_tag[comp.Map]
    if comp.Player not in actor.tags:
        query = actor.registry.Q.all_of(
            components=[comp.Position, comp.HP],
            tags=[comp.Player],
            relations=[(comp.Map, map_)],
        )
    else:
        query = actor.registry.Q.all_of(
            components=[comp.Position, comp.HP],
            relations=[(comp.Map, map_)],
        ).none_of(tags=[comp.Player])
    return {e for e in query if is_in_fov(actor, e)}


def has_enemy_in_fov(actor: ecs.Entity) -> bool:
    return len(enemies_in_fov(actor)) > 0


def is_alive(actor: ecs.Entity) -> bool:
    if comp.MaxHP in actor.components:
        return actor.components.get(comp.HP, 0) > 0
    return True


def can_act(actor: ecs.Entity) -> bool:
    return (
        is_alive(actor)
        and comp.Initiative in actor.components
        and actor.components[comp.Initiative] > 0
    )


def enemy_action(actor: ecs.Entity) -> actions.Action:
    player = actor.registry[comp.Player]
    player_infov = is_alive(player) and is_in_fov(actor, player)
    if player_infov:
        actor.components[comp.AITarget] = player.components[comp.Position]

    target = actor.components.get(comp.AITarget)
    if target is not None:
        d = dist(actor, target)
        # Attack player if in reach
        if d < 1.5 and player_infov:
            return actions.AttackAction(actor, player)
        elif d == 0:
            actor.components.pop(comp.AITarget)
            dir = actor.components.get(comp.Direction)
            if dir is not None:
                move = actions.MoveAction(actor, dir)
                if move.can():
                    return move
        elif d >= 1.5:
            # Move towards target
            move_to = actions.MoveAction.to(actor, target.xy)
            if move_to is not None and move_to.can():
                return move_to

    return actions.MoveAction.random(actor)


def spawn_creature(
    map_entity: ecs.Entity, pos: tuple[int, int], kind: str | ecs.Entity
) -> ecs.Entity:
    if isinstance(kind, str):
        kind = map_entity.registry[("creatures", kind)]
    entity = kind.instantiate()
    if comp.MaxHP in entity.components:
        entity.components[comp.HP] = entity.components[comp.MaxHP]
    depth = map_entity.components[comp.Depth]
    entity.components[comp.Position] = comp.Position(pos, depth)
    entity.components[comp.Initiative] = 0
    return entity
