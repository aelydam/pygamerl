import tcod.ecs as ecs

import actions
import comp
import game_logic


def affecting(actor: ecs.Entity) -> dict[ecs.Entity, int]:
    if comp.ConditionTurns not in actor.relation_components:
        return {}
    return {k: v for k, v in actor.relation_components[comp.ConditionTurns].items()}


def add_condition(actor: ecs.Entity, condition: ecs.Entity | str, turns: int):
    if isinstance(condition, str):
        condition = actor.registry[("conditions", condition)]
    actor.relation_components[comp.ConditionTurns][condition] = turns


def remove_condition(actor: ecs.Entity, condition: ecs.Entity | str):
    if comp.ConditionTurns not in actor.relation_components:
        return
    if isinstance(condition, str):
        condition = actor.registry[("conditions", condition)]
    if condition not in actor.relation_components[comp.ConditionTurns]:
        return
    actor.relation_components[comp.ConditionTurns].pop(condition)


def remove_all_conditions(actor: ecs.Entity):
    for condition in affecting(actor).keys():
        remove_condition(actor, condition)


def apply_condition_effect(condition: ecs.Entity, actor: ecs.Entity):
    if comp.ConditionTurns not in actor.relation_components:
        return
    if condition not in actor.relation_components[comp.ConditionTurns]:
        return
    actor.relation_components[comp.ConditionTurns][condition] -= 1
    if actor.relation_components[comp.ConditionTurns][condition] < 1:
        remove_action = actions.RemoveCondition(actor, None, condition)
        game_logic.push_action(actor.registry, remove_action)
    if comp.Effects not in condition.components:
        return
    actions.apply_effects(actor, condition.components[comp.Effects])


def update_actor_conditions(actor: ecs.Entity):
    for condition in affecting(actor).keys():
        apply_condition_effect(condition, actor)


def update_conditions(map_entity: ecs.Entity):
    query = map_entity.registry.Q.all_of(
        relations=[(comp.Map, map_entity), (comp.ConditionTurns, ...)]
    )
    for e in query:
        update_actor_conditions(e)
