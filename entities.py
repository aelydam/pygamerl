from __future__ import annotations

import random
from typing import Any, Never

import numpy as np
import tcod
import tcod.ecs as ecs

import actions
import comp
import consts
import dice
import funcs
import game_logic
import items
import maps


def dist(
    origin: ecs.Entity | comp.Position | tuple[int, int],
    target: ecs.Entity | comp.Position | tuple[int, int],
) -> float:
    if isinstance(origin, ecs.Entity):
        if not comp.Position in origin.components:
            return 255
        origin = origin.components[comp.Position]
    if isinstance(target, ecs.Entity):
        if not comp.Position in target.components:
            return 255
        target = target.components[comp.Position]
    if isinstance(origin, comp.Position):
        if isinstance(target, comp.Position) and origin.depth != target.depth:
            return 255
        origin = origin.xy
    if isinstance(target, comp.Position):
        target = target.xy
    return sum([(origin[i] - target[i]) ** 2 for i in range(2)]) ** 0.5


def get_combined_component(
    actor: ecs.Entity, component: tuple[str, type[int]], default: int = 0, func=sum
) -> int:
    res = actor.components.get(component, default)
    for e in items.equipment(actor).values():
        if e is not None and component in e.components:
            res = func([res, e.components[component]])
    return res


def armor_class(actor: ecs.Entity, default: int = 10) -> int:
    return get_combined_component(actor, comp.ArmorClass, default)


def attack_bonus(actor: ecs.Entity, default: int = 2) -> int:
    return get_combined_component(actor, comp.AttackBonus, default)


def damage_dice(actor: ecs.Entity, default: str = "1") -> str:
    mainhand = items.equipment_at_slot(actor, comp.EquipSlot.Main_Hand)
    dice = str(actor.components.get(comp.DamageDice, default))
    if mainhand is not None and comp.DamageDice in mainhand.components:
        dice = mainhand.components[comp.DamageDice]
    bonus = get_combined_component(actor, comp.DamageBonus, 0)
    if bonus > 0:
        return f"{dice}+{bonus}"
    elif bonus < 0:
        return f"{dice}-{abs(bonus)}"
    return dice


def speed(actor: ecs.Entity, default: int = consts.BASE_SPEED) -> int:
    return get_combined_component(actor, comp.Speed, default)


def fov_radius(actor: ecs.Entity, default: int = consts.DEFAULT_FOV_RADIUS) -> int:
    return get_combined_component(actor, comp.FOVRadius, default)


def light_radius(actor: ecs.Entity, default: int = 0) -> int:
    return get_combined_component(actor, comp.LightRadius, default, func=max)


def update_fov(actor: ecs.Entity):
    radius = fov_radius(actor)
    if (
        radius < 1
        or comp.Map not in actor.relation_tag
        or comp.Position not in actor.components
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
    radius = light_radius(entity)
    if radius < 1 or comp.Lit not in entity.tags:
        if comp.Lightsource in entity.components:
            entity.components.pop(comp.Lightsource)
        return
    map_entity = entity.relation_tag[comp.Map]
    grid = map_entity.components[comp.Tiles]
    transparency = maps.transparency_matrix(map_entity)
    x, y = entity.components[comp.Position].xy
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
    if comp.Trap in actor.tags:
        query = actor.registry.Q.all_of(
            components=[comp.Position, comp.HP],
            relations=[(comp.Map, map_)],
        )
    elif comp.Player not in actor.tags:
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
    return {e for e in query if is_in_fov(actor, e) and is_alive(e)}


def has_enemy_in_fov(actor: ecs.Entity) -> bool:
    return len(enemies_in_fov(actor)) > 0


def is_alive(actor: ecs.Entity) -> bool:
    if comp.MaxHP in actor.components:
        return actor.components.get(comp.HP, 0) > 0
    return comp.Position in actor.components and comp.Map in actor.relation_tag


def can_act(actor: ecs.Entity) -> bool:
    return (
        is_alive(actor)
        and comp.Initiative in actor.components
        and actor.components[comp.Initiative] > 0
    )


def enemy_action(actor: ecs.Entity) -> actions.Action:
    if not is_alive(actor):
        return actions.WaitAction(actor)
    visible_enemies = enemies_in_fov(actor)
    enemy_infov = len(visible_enemies) > 0
    if enemy_infov:
        enemy = next(iter(visible_enemies))
        actor.components[comp.AITarget] = enemy.components[comp.Position]

    target = actor.components.get(comp.AITarget)
    if target is not None:
        d = dist(actor, target)
        # Attack player if in reach
        reach = actor.components.get(comp.Reach, 1.5)
        if d <= reach and enemy_infov:
            return actions.AttackAction(actor, enemy)
        elif d == 0:
            actor.components.pop(comp.AITarget)
            dir = actor.components.get(comp.Direction)
            if dir is not None:
                move = actions.MoveAction(actor, dir)
                if move.can():
                    return move
        elif d > reach:
            # Move towards target
            move_to = actions.MoveAction.to(actor, target.xy)
            if move_to is not None and move_to.can():
                return move_to
    # Rest on low HP
    if actor.components.get(comp.HP, 0) < actor.components.get(comp.MaxHP, 0):
        return actions.WaitAction(actor)

    move = actions.MoveAction.random(actor)
    if move.can():
        return move
    return actions.WaitAction(actor)


def spawn_creature(
    map_entity: ecs.Entity, pos: tuple[int, int], kind: str | ecs.Entity
) -> ecs.Entity:
    if isinstance(kind, str):
        kind = map_entity.registry[("creatures", kind)]
    entity = kind.instantiate()
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    if comp.HPDice in kind.components:
        maxhp = dice.dice_roll(kind.components[comp.HPDice], seed)  # type: ignore
        entity.components[comp.MaxHP] = int(maxhp)
    if comp.MaxHP in entity.components:
        entity.components[comp.HP] = entity.components[comp.MaxHP]
    entity.components[comp.Position] = comp.Position(pos, depth)
    entity.components[comp.Initiative] = 0
    if comp.TempInventory in kind.components:
        for k, v in kind.components[comp.TempInventory].items():
            q = max(0, int(dice.dice_roll(v, seed)))
            if q > 0:
                items.add_item(entity, k, q)
    if comp.TempEquipment in kind.components:
        for k in kind.components[comp.TempEquipment]:
            items.equip(entity, items.add_item(entity, k, 1))
    return entity


def hunger(actor: ecs.Entity) -> int:
    return actor.components.get(comp.Hunger, 0)


def is_hungry(actor: ecs.Entity) -> bool:
    return hunger(actor) >= consts.MAX_HUNGER


def update_hunger(map_entity: ecs.Entity):
    actors = map_entity.registry.Q.all_of(
        components=[comp.Hunger],
        relations=[(comp.Map, map_entity)],
    )
    seed = map_entity.registry[None].components[random.Random]
    for e in actors:
        roll = dice.dice_roll("d20", seed)
        was_hungry = is_hungry(e)
        if roll < 2:
            if was_hungry:
                dmg = actions.Damage(e, "min(1d4,1d4)")
                game_logic.push_action(e.registry, dmg)
            else:
                e.components[comp.Hunger] += 1
                if (
                    (not was_hungry or roll > 1)
                    and comp.Player in e.tags
                    and is_hungry(e)
                ):
                    name = e.components.get(comp.Name, "Player")
                    game_logic.log(e.registry, f"{name} feels quite hungry")
