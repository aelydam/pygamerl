from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np
import tcod
import tcod.ecs as ecs

import comp
import consts
import entities
import funcs
import game_logic
import maps


@dataclass
class Action:
    message: str = field(init=False, default="")
    cost: float = field(init=False, default=0)

    def can(self) -> bool:
        return True

    def perform(self) -> Action | None:
        return self


@dataclass
class ActorAction(Action):
    actor: ecs.Entity


@dataclass
class WaitAction(ActorAction):
    def perform(self) -> Action | None:
        if comp.Initiative in self.actor.components:
            self.cost = self.actor.components[comp.Initiative]
        return super().perform()


@dataclass
class MoveAction(ActorAction):
    direction: tuple[int, int]

    def __post_init__(self, *args, **kwargs):
        self.cost = sum([self.direction[i] ** 2 for i in range(2)]) ** 0.5

    def can(self) -> bool:
        dist = sum([self.direction[i] ** 2 for i in range(2)]) ** 0.5
        if dist > 1.5:
            return False
        if (
            comp.Position not in self.actor.components
            or comp.Map not in self.actor.relation_tag
        ):
            return False
        map_entity = self.actor.relation_tag[comp.Map]
        new_pos = self.actor.components[comp.Position] + self.direction
        if not maps.is_in_bounds(map_entity, new_pos):
            return False
        return maps.is_walkable(map_entity, new_pos)

    def perform(self) -> Action | None:
        if not self.can():
            return None
        self.actor.components[comp.Position] += self.direction
        self.actor.components[comp.Direction] = self.direction
        self.cost = sum([self.direction[i] ** 2 for i in range(2)]) ** 0.5
        return self

    @classmethod
    def random(cls, actor: ecs.Entity) -> MoveAction:
        dx, dy = random.randint(-1, 1), random.randint(-1, 1)
        return cls(actor, (dx, dy))

    @classmethod
    def to(cls, actor: ecs.Entity, target: tuple[int, int]) -> MoveAction | None:
        path = maps.astar_path(actor, target)
        if len(path) < 2:
            return None
        dx = path[1][0] - path[0][0]
        dy = path[1][1] - path[0][1]
        return cls(actor, (dx, dy))


@dataclass
class MoveToAction(ActorAction):
    target: tuple[int, int]
    cost: int = field(init=False, default=1)

    def can(self) -> bool:
        action = MoveAction.to(self.actor, self.target)
        return action is not None and action.can()

    def perform(self) -> Action | None:
        action = MoveAction.to(self.actor, self.target)
        if action is not None:
            return action.perform()
        return None


@dataclass
class ExploreAction(ActorAction):
    cost: int = field(init=False, default=1)

    def can(self) -> bool:
        if (
            comp.Position not in self.actor.components
            or comp.Map not in self.actor.relation_tag
        ):
            return False
        map_entity = self.actor.relation_tag[comp.Map]
        explored = map_entity.components[comp.Explored]
        tiles = map_entity.components[comp.Tiles]
        walkable = ~consts.TILE_ARRAY["obstacle"][tiles]
        explorable = walkable | (funcs.moore(walkable) > 0)
        if np.sum(explorable & ~explored) > 0:
            return True
        query = self.actor.registry.Q.all_of(
            components=[comp.Position, comp.Interaction],
            tags=[comp.Downstairs],
            relations=[(comp.Map, map_entity)],
        )
        for _ in query:
            return True
        return False

    def perform(self) -> Action | None:
        if not self.can():
            return None
        map_entity = self.actor.relation_tag[comp.Map]
        pos = self.actor.components[comp.Position].xy
        cost = maps.cost_matrix(map_entity)
        # Remove cost of unexplored tiles
        explored = map_entity.components[comp.Explored]
        cost[~explored] = 1
        dijkstra = tcod.path.maxarray(cost.shape, dtype=np.int32)
        # Set unexplored tiles as the objective
        dijkstra[~explored] = 0
        # Set downstairs as objective
        query = self.actor.registry.Q.all_of(
            components=[comp.Position, comp.Interaction],
            tags=[comp.Downstairs],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            xy = e.components[comp.Position].xy
            dijkstra[xy] = 0
            cost[xy] = 0
            if xy == pos:
                return Descend(self.actor, e, False).perform()
        #
        tcod.path.dijkstra2d(dijkstra, cost, 2, 3, out=dijkstra)
        cost[pos] = 1
        path = tcod.path.hillclimb2d(dijkstra, pos, True, True).tolist()
        if len(path) < 2:
            return None
        dx, dy = path[1][0] - path[0][0], path[1][1] - path[0][1]
        return BumpAction(self.actor, (dx, dy)).perform()


@dataclass
class AttackAction(ActorAction):
    target: ecs.Entity
    cost: int = field(init=False, default=1)
    damage: int = field(init=False, default=0)
    xy: tuple[int, int] = field(init=False, default=(0, 0))

    def can(self) -> bool:
        if self.actor == self.target:
            return False
        dist = entities.dist(self.actor, self.target)
        if dist > 1.5:
            return False
        if not entities.is_alive(self.target):
            return False
        return True

    def perform(self) -> Action | None:
        if not self.can():
            return None
        roll = random.randint(1, 20)
        roll += self.actor.components.get(comp.AttackBonus, 2)
        aname = self.actor.components.get(comp.Name, "Something")
        tname = self.target.components.get(comp.Name, "Something")
        text = f"{aname} attacks {tname}: "
        if roll >= self.target.components.get(comp.ArmorClass, 12):
            dice = self.actor.components.get(comp.DamageDice, 4)
            self.damage = random.randint(1, dice)
            self.target.components[comp.HP] = max(
                0, self.target.components[comp.HP] - self.damage
            )
            text += f"{self.damage} points of damage!"
        else:
            self.damage = 0
            text += "Miss!"
        apos = self.actor.components[comp.Position].xy
        tpos = self.target.components[comp.Position].xy
        self.actor.components[comp.Direction] = (tpos[0] - apos[0], tpos[1] - apos[1])
        if not entities.is_alive(self.target):
            text += f" {tname} dies!"
            if comp.Player not in self.target.tags:
                self.target.clear()
        self.xy = tpos
        self.message = text
        self.cost = 1
        return self


class BumpAction(MoveAction):
    def get_entity(self) -> ecs.Entity | None:
        map_entity = self.actor.relation_tag[comp.Map]
        new_pos = self.actor.components[comp.Position] + self.direction
        query = self.actor.registry.Q.all_of(
            [comp.Position, comp.HP],
            tags=[new_pos],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            if e != self.actor:
                return e
        query = self.actor.registry.Q.all_of(
            [comp.Position, comp.Interaction],
            tags=[new_pos],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            if e != self.actor:
                return e
        return None

    def can(self) -> bool:
        self.actor.components[comp.Direction] = self.direction
        if super().can():
            return True
        return self.get_entity() is not None

    def perform(self) -> Action | None:
        if not self.can():
            return None
        entity = self.get_entity()
        if entity is not None:
            if comp.HP in entity.components:
                return AttackAction(self.actor, entity).perform()
            elif comp.Interaction in entity.components:
                action_class = entity.components[comp.Interaction]
                action = action_class(self.actor, entity, bump=True)
                if action.can():
                    return action.perform()
        return super().perform()


@dataclass
class Interact(ActorAction):
    def get_entity(self) -> ecs.Entity | None:
        map_entity = self.actor.relation_tag[comp.Map]
        pos = self.actor.components[comp.Position]
        query = self.actor.registry.Q.all_of(
            [comp.Position, comp.Interaction],
            tags=[pos],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            if e != self.actor:
                return e
        if comp.Direction in self.actor.components:
            newpos = pos + self.actor.components[comp.Direction]
            query = self.actor.registry.Q.all_of(
                [comp.Position, comp.Interaction],
                tags=[newpos],
                relations=[(comp.Map, map_entity)],
            )
            for e in query:
                if e != self.actor:
                    return e
        return None

    def get_action(self) -> Interaction | None:
        entity = self.get_entity()
        if entity is not None:
            action_class = entity.components[comp.Interaction]
            return action_class(self.actor, entity, bump=False)
        return None

    def can(self) -> bool:
        action = self.get_action()
        return action is not None and action.can()

    def perform(self) -> Action | None:
        action = self.get_action()
        if action is not None:
            return action.perform()
        return None


@dataclass
class MagicMap(ActorAction):
    def can(self) -> bool:
        map_ = self.actor.relation_tag[comp.Map]
        tiles = map_.components[comp.Tiles]
        explored = map_.components[comp.Explored]
        walkable = ~consts.TILE_ARRAY["obstacle"][tiles]
        explorable = walkable | (funcs.moore(walkable) > 0)
        remaining = np.sum(explorable & ~explored)
        return bool(remaining > 0)

    def perform(self) -> Action | None:
        map_ = self.actor.relation_tag[comp.Map]
        tiles = map_.components[comp.Tiles]
        explored = map_.components[comp.Explored]
        walkable = ~consts.TILE_ARRAY["obstacle"][tiles]
        explorable = walkable | (funcs.moore(walkable) > 0)
        remaining = np.sum(explorable & ~explored)
        if remaining < 1:
            return None
        rand = np.random.random(explorable.shape)
        reveal = explorable & (funcs.moore(explored, False) > 0) & (rand < 0.2)
        map_.components[comp.Explored] |= reveal
        if self.can():
            game_logic.push_action(self.actor.registry, self)
        return self


@dataclass
class Interaction(ActorAction):
    target: ecs.Entity | None = None
    bump: bool = False

    def can(self) -> bool:
        return self.target is not None and entities.dist(self.target, self.actor) < 1.5


class ToggleDoor(Interaction):
    def can(self) -> bool:
        if (
            self.target is not None
            and self.bump
            and (comp.Obstacle not in self.target.tags)
        ):
            return False
        return super().can()

    def perform(self) -> Action | None:
        if self.target is None:
            return None
        if comp.Obstacle in self.target.tags:
            verb = "opens"
            self.target.tags -= {comp.Obstacle, comp.Opaque}
            self.target.tags.discard(comp.Obstacle)
            if comp.Opaque in self.target.tags:
                self.target.tags.discard(comp.Opaque)
            self.target.tags |= {comp.HideSprite}
        else:
            verb = "closes"
            self.target.tags |= {comp.Obstacle, comp.Opaque}
            if comp.HideSprite in self.target.tags:
                self.target.tags.discard(comp.HideSprite)
        entities.update_fov(self.actor)
        self.cost = 1
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} {verb} a door"
        self.cost = 1
        return self


class ToggleTorch(Interaction):
    def can(self):
        return self.target is None or super().can()

    def perform(self) -> Action | None:
        if not self.can():
            return None
        if self.target is None:
            self.target = self.actor
        if comp.Lit in self.target.tags:
            self.target.tags.discard(comp.Lit)
            verb = "extinguish"
        else:
            self.target.tags |= {comp.Lit}
            entities.update_entity_light(self.target)
            verb = "lits"
        self.cost = 1
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} {verb} a torch"
        return self


class Descend(Interaction):
    def can(self) -> bool:
        return not self.bump and super().can()

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        pos = self.target.components[comp.Position]
        new_depth = pos.depth + 1
        maps.get_map(self.actor.registry, new_depth)
        new_pos = comp.Position(pos.xy, new_depth)
        self.actor.components[comp.Position] = new_pos
        self.cost = 1
        if new_depth > self.actor.registry[None].components.get(comp.MaxDepth, 0):
            self.actor.registry[None].components[comp.MaxDepth] = new_depth
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} descends the stairs"
        return self


class Ascend(Interaction):
    def can(self) -> bool:
        if self.target is None:
            return False
        depth = self.target.components[comp.Position].depth
        return depth > 0 and not self.bump and super().can()

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        pos = self.target.components[comp.Position]
        new_depth = pos.depth - 1
        maps.get_map(self.actor.registry, new_depth)
        new_pos = comp.Position(pos.xy, new_depth)
        self.actor.components[comp.Position] = new_pos
        self.cost = 1
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} ascends the stairs"
        return self
