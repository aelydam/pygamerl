from typing import Iterable

import tcod.ecs as ecs

import comp


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
    actor = item.relation_tag[comp.Inventory]
    pos = actor.components[comp.Position]
    kind = item.relation_tag[ecs.IsA]
    query = item.registry.Q.all_of(tags=[pos], relations=[(ecs.IsA, kind)])
    item.relation_tag.pop(comp.Inventory)
    item.components[comp.Position] = pos
    stack_item(item, query)


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


def inventory(actor: ecs.Entity) -> Iterable[ecs.Entity]:
    return actor.registry.Q.all_of(tags={"items"}, relations=[(comp.Inventory, actor)])
