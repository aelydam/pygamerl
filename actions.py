from __future__ import annotations

import random
from dataclasses import dataclass, field

import tcod.ecs as ecs

import comp
import entities
import maps


@dataclass
class Action:
    message: str = field(init=False, default="")
    cost: float = field(init=False, default=0)

    def can(self) -> bool:
        return True

    def perform(self) -> Action | None:
        return self


class WaitAction(Action):
    pass


@dataclass
class MoveAction(Action):
    actor: ecs.Entity
    direction: tuple[int, int]

    def can(self) -> bool:
        dist = sum([self.direction[i]**2 for i in range(2)])**0.5
        if dist > 1.5:
            return False
        if comp.Position not in self.actor.components or comp.Map not in self.actor.relation_tag:
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
        self.cost = sum([self.direction[i]**2 for i in range(2)])**0.5
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
class AttackAction(Action):
    actor: ecs.Entity
    target: ecs.Entity
    damage: int = field(init = False, default=0)
    xy: tuple[int, int] = field(init = False, default=(0,0))

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
            self.target.components[comp.HP] = max(0, self.target.components[comp.HP] - self.damage)
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
            relations=[(comp.Map, map_entity)]
        )
        for e in query:
            if e != self.actor:
                return e
        return None

    def can(self) -> bool:
        if super().can():
            return True
        return self.get_entity() is not None

    def perform(self) -> Action | None:
        if not self.can():
            return None
        entity = self.get_entity()
        if entity is not None:
            return AttackAction(self.actor, entity).perform()
        else:
            return super().perform()
