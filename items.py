from typing import Iterable

import tcod.ecs as ecs

import comp


def pickup(actor: ecs.Entity, item: ecs.Entity):
    item.components.pop(comp.Position)
    item.relation_tag[comp.Inventory] = actor


def drop(item: ecs.Entity):
    actor = item.relation_tag[comp.Inventory]
    pos = actor.components[comp.Position]
    item.relation_tag.pop(comp.Inventory)
    item.components[comp.Position] = pos


def spawn_item(
    map_entity: ecs.Entity, pos: tuple[int, int], kind: str | ecs.Entity
) -> ecs.Entity:
    if isinstance(kind, str):
        kind = map_entity.registry[("items", kind)]
    entity = kind.instantiate()
    depth = map_entity.components[comp.Depth]
    entity.components[comp.Position] = comp.Position(pos, depth)
    return entity


def inventory(actor: ecs.Entity) -> Iterable[ecs.Entity]:
    return actor.registry.Q.all_of(tags={"items"}, relations=[(comp.Inventory, actor)])
