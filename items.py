from __future__ import annotations

from typing import Iterable

import tcod.ecs as ecs

import comp
import entities
import game_logic


def is_identified(item: ecs.Entity) -> bool:
    return comp.Identified in item.tags or comp.UnidentifiedName not in item.components


def display_name(item: ecs.Entity) -> str:
    if not is_identified(item):
        return item.components[comp.UnidentifiedName]
    return item.components[comp.Name]


def identify(item: ecs.Entity):
    if is_identified(item):
        return
    if ecs.IsA in item.relation_tag:
        kind = item.relation_tag[ecs.IsA]
        if comp.UnidentifiedName in kind.components:
            kind.components.pop(comp.UnidentifiedName)
        kind.tags |= {comp.Identified}
    elif comp.UnidentifiedName in item.components:
        item.components.pop(comp.UnidentifiedName)
        item.tags |= {comp.Identified}


def is_same_kind(item1: ecs.Entity, item2: ecs.Entity) -> bool:
    return (
        item1.components.get(comp.Name) == item2.components.get(comp.Name)
        and item1.relation_tag[ecs.IsA] == item2.relation_tag[ecs.IsA]
    )


def stack_item(item: ecs.Entity, stack: Iterable[ecs.Entity]):
    count = item.components.get(comp.Count, 1)
    max_stack = item.components.get(comp.MaxStack, 1)
    if max_stack > 1:
        for e in stack:
            if e == item or not is_same_kind(item, e):
                continue
            count_i = min(count, max(0, max_stack - e.components.get(comp.Count, 1)))
            e.components[comp.Count] += count_i
            count -= count_i
            if count < 1:
                item.clear()
                return
        item.components[comp.Count] = count


def pickup(actor: ecs.Entity, item: ecs.Entity):
    kind = item.relation_tag[ecs.IsA]
    query = actor.registry.Q.all_of(
        relations=[(comp.Inventory, actor), (ecs.IsA, kind)]
    )
    item.relation_tag[comp.Inventory] = actor
    item.components.pop(comp.Position)
    stack_item(item, query)


def drop(item: ecs.Entity):
    if is_equipped(item):
        unequip_item(item)
    actor = item.relation_tag[comp.Inventory]
    pos = actor.components[comp.Position]
    kind = item.relation_tag[ecs.IsA]
    query = item.registry.Q.all_of(tags=[pos], relations=[(ecs.IsA, kind)])
    item.relation_tag.pop(comp.Inventory)
    item.components[comp.Position] = pos
    stack_item(item, query)


def drop_all(actor: ecs.Entity):
    for e in inventory(actor):
        drop(e)


def spawn_item(
    map_entity: ecs.Entity, pos: tuple[int, int], kind: str | ecs.Entity, count: int = 1
) -> ecs.Entity:
    if isinstance(kind, str):
        kind = map_entity.registry[("items", kind)]
    depth = map_entity.components[comp.Depth]
    max_stack = kind.components.get(comp.MaxStack, 1)
    while count > 0:
        stack_count = min(count, max_stack)
        entity = kind.instantiate()
        entity.components[comp.Position] = comp.Position(pos, depth)
        entity.components[comp.Count] = stack_count
        count -= stack_count
    return entity


def add_item(actor: ecs.Entity, kind: str | ecs.Entity, count: int = 1):
    if isinstance(kind, str):
        kind = actor.registry[("items", kind)]
    max_stack = kind.components.get(comp.MaxStack, 1)
    while count > 0:
        stack_count = min(count, max_stack)
        entity = kind.instantiate()
        entity.components[comp.Count] = stack_count
        entity.relation_tag[comp.Inventory] = actor
        count -= stack_count
    return entity


def inventory(actor: ecs.Entity) -> Iterable[ecs.Entity]:
    return actor.registry.Q.all_of(tags={"items"}, relations=[(comp.Inventory, actor)])


def is_equippable(item: ecs.Entity) -> bool:
    return comp.EquipSlot in item.components


def is_equipped(item: ecs.Entity) -> bool:
    if comp.EquipSlot not in item.components or comp.Inventory not in item.relation_tag:
        return False
    actor = item.relation_tag[comp.Inventory]
    slot = item.components[comp.EquipSlot]
    in_slot = equipment_at_slot(actor, slot)
    return in_slot == item


def equipment_at_slot(actor: ecs.Entity, slot: comp.EquipSlot) -> ecs.Entity | None:
    if slot in actor.relation_tag:
        return actor.relation_tag[slot]
    return None


def unequip_slot(actor: ecs.Entity, slot: comp.EquipSlot):
    if slot in actor.relation_tag:
        actor.relation_tag.pop(slot)


def unequip_item(item: ecs.Entity):
    if is_equipped(item):
        actor = item.relation_tag[comp.Inventory]
        slot = item.components[comp.EquipSlot]
        unequip_slot(actor, slot)


def equip(actor: ecs.Entity, item: ecs.Entity):
    if item.relation_tag[comp.Inventory] != actor:
        return
    slot = item.components[comp.EquipSlot]
    unequip_slot(actor, slot)
    actor.relation_tag[slot] = item
    if comp.LightRadius in item.components:
        actor.tags |= {comp.Lit}
        entities.update_entity_light(actor)


def equipment(actor: ecs.Entity) -> dict[comp.EquipSlot, ecs.Entity | None]:
    x = {slot: equipment_at_slot(actor, slot) for slot in comp.EquipSlot}
    return x


def money(actor: ecs.Entity) -> float:
    query = actor.registry.Q.all_of(
        components=[comp.Price],
        tags=[comp.Currency],
        relations=[(comp.Inventory, actor)],
    )
    return sum(
        e.components.get(comp.Count, 0) * e.components.get(comp.Price, 0) for e in query
    )


def apply_effects(item: ecs.Entity, target: ecs.Entity) -> bool:
    if comp.Effects not in item.components:
        return False
    effects = item.components[comp.Effects]
    for effect, args in effects.items():
        if isinstance(args, dict):
            action = effect(target, **args)
        elif isinstance(args, list):
            action = effect(target, *args)
        elif args is not None:
            action = effect(target, args)
        else:
            action = effect(target)
        game_logic.push_action(item.registry, action)
    if comp.Consumable in item.tags:
        count = item.components.get(comp.Count, 1) - 1
        if count < 1:
            item.clear()
        else:
            item.components[comp.Count] = count
    return True
