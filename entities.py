from __future__ import annotations

import tcod
import tcod.ecs as ecs

import actions
import comp
import consts
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
    transparency = maps.transparency_matrix(map_entity)
    # Actor can see its own position
    xy = actor.components[comp.Position].xy
    transparency[xy] = True
    # Update player FOV
    radius = actor.components[comp.FOVRadius]
    fov = tcod.map.compute_fov(
        transparency, xy, radius, algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST
    )
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
    # Move if player dead or not in FOV
    if not is_alive(player) or not is_in_fov(actor, player):
        return actions.MoveAction.random(actor)

    player_pos = player.components[comp.Position]
    # Attack player if in reach
    if dist(actor, player_pos) < 1.5:
        return actions.AttackAction(actor, player)
    # Move towards player
    move_to = actions.MoveAction.to(actor, player_pos.xy)
    if move_to is None or not move_to.can():
        return actions.WaitAction(actor)
    else:
        return move_to
