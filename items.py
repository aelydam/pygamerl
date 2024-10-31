from __future__ import annotations

from typing import Iterable

import tcod.ecs as ecs

import actions
import comp
import entities


def is_identified(item: ecs.Entity) -> bool:
    return comp.Identified in item.tags or comp.UnidentifiedName not in item.components


def display_name(item: ecs.Entity) -> str:
    if not is_identified(item):
        return item.components[comp.UnidentifiedName]
    return item.components[comp.Name]


def slot_name(slot: comp.EquipSlot | ecs.Entity) -> str:
    if isinstance(slot, ecs.Entity):
        if is_ready(slot):
            slot = comp.EquipSlot.Ready
        elif comp.EquipSlot in slot.components:
            slot = slot.components[comp.EquipSlot]
        else:
            return ""
    return slot.name.replace("_", " ")


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


def stack_item(item: ecs.Entity, stack: Iterable[ecs.Entity]) -> int:
    count = item.components.get(comp.Count, 1)
    max_stack = item.components.get(comp.MaxStack, 1)
    if max_stack > 1:
        stack = sorted(stack, key=lambda e: max_stack - e.components.get(comp.Count, 1))
        for e in stack:
            if e == item or not is_same_kind(item, e):
                continue
            count_e = e.components.get(comp.Count, 1)
            available = max(0, max_stack - count_e)
            count_i = min(count, available)
            if count_e >= max_stack or available < 1 or count_i < 1:
                continue
            e.components[comp.Count] = count_e + count_i
            count -= count_i
            item.components[comp.Count] = count
            if count < 1:
                if comp.Inventory in item.relation_tag:
                    item.relation_tag.pop(comp.Inventory)
                item.clear()
                return 0
        item.components[comp.Count] = count
    return count


def pickup(actor: ecs.Entity, item: ecs.Entity):
    kind = item.relation_tag[ecs.IsA]
    query = actor.registry.Q.all_of(
        relations=[(comp.Inventory, actor), (ecs.IsA, kind)], traverse=[]
    )
    count = stack_item(item, query)
    if count > 0:
        item.relation_tag[comp.Inventory] = actor
        item.components.pop(comp.Position)


def drop(item: ecs.Entity):
    if is_equipped(item):
        unequip_item(item)
    actor = item.relation_tag[comp.Inventory]
    pos = actor.components[comp.Position]
    kind = item.relation_tag[ecs.IsA]
    map_entity = actor.relation_tag[comp.Map]
    query = item.registry.Q.all_of(
        components=[comp.Position],
        tags=[pos],
        relations=[(ecs.IsA, kind), (comp.Map, map_entity)],
        traverse=[],
    )
    item.relation_tag.pop(comp.Inventory)
    count = stack_item(item, query)
    if count > 0:
        item.components[comp.Position] = pos


def drop_all(actor: ecs.Entity):
    items = set(inventory(actor))
    for e in items:
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


def is_ready(item: ecs.Entity) -> bool:
    if comp.EquipSlot not in item.components or comp.Inventory not in item.relation_tag:
        return False
    actor = item.relation_tag[comp.Inventory]
    ready = equipment_at_slot(actor, comp.EquipSlot.Ready)
    return ready == item


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
    prev_in_slot = equipment_at_slot(actor, slot)
    if prev_in_slot is not None:
        unequip_slot(actor, slot)
        if slot == comp.EquipSlot.Main_Hand:
            actor.relation_tag[comp.EquipSlot.Ready] = prev_in_slot
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
    actions.apply_effects(target, item.components[comp.Effects])
    if comp.Consumable in item.tags:
        count = item.components.get(comp.Count, 1) - 1
        if count < 1:
            item.clear()
        else:
            item.components[comp.Count] = count
    return True
