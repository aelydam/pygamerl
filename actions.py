from __future__ import annotations
import random

import entities


class Action:
    def can(self) -> bool:
        return True

    def perform(self) -> Action | None:
        return self


class WaitAction(Action):
    pass


class MoveAction(Action):
    def __init__(self, dx: int, dy: int, actor: entities.Entity):
        self.dx, self.dy, self.actor = dx, dy, actor

    def can(self) -> bool:
        dist = (self.dx**2 + self.dy**2)**0.5
        if dist > 1.5:
            return False
        new_x = self.actor.x + self.dx
        new_y = self.actor.y + self.dy
        if not self.actor.map.is_in_bounds(new_x, new_y):
            return False
        return self.actor.map.is_walkable(new_x, new_y)

    def perform(self) -> Action | None:
        if not self.can():
            return None
        self.actor.x += self.dx
        self.actor.y += self.dy
        self.actor.dx, self.actor.dy = self.dx, self.dy
        self.actor.steps += (self.dx**2 + self.dy**2)**0.5
        return self

    @classmethod
    def random(cls, actor: entities.Entity) -> MoveAction:
        dx, dy = random.randint(-1, 1), random.randint(-1, 1)
        return cls(dx, dy, actor)

    @classmethod
    def to(cls, target: tuple[int, int],
           actor: entities.Entity) -> MoveAction | None:
        dx, dy = target[0] - actor.x, target[1] - actor.y
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist <= 1.5:
            return cls(dx, dy, actor)
        path = actor.map.astar_path((actor.x, actor.y), target)
        if len(path) < 2:
            return None
        dx = path[1][0] - path[0][0]
        dy = path[1][1] - path[0][1]
        return cls(dx, dy, actor)


class AttackAction(Action):
    def __init__(self, target: entities.Entity, actor: entities.Entity):
        self.target = target
        self.actor = actor

    def can(self) -> bool:
        dist = (
            (self.target.x - self.actor.x) ** 2 +
            (self.target.y - self.actor.y) ** 2
        ) ** 0.5
        if dist > 1.5:
            return False
        if self.target.hp < 1:
            return False
        return True

    def perform(self) -> Action | None:
        if not self.can():
            return None
        roll = random.randint(1, 20) + self.actor.tohit
        text = f"{self.actor.name} attacks {self.target.name}: "
        if roll >= self.target.ac:
            self.damage = random.randint(1, self.actor.damage)
            self.target.hp = max(0, self.target.hp - self.damage)
            text += f"{self.damage} points of damage!"
            self.actor.hits += 1
        else:
            self.actor.misses += 1
            self.damage = 0
            text += "Miss!"
        self.actor.map.logic.log(text)
        if self.target.hp < 1:
            self.actor.kills += 1
            self.actor.map.logic.log(f"{self.target.name} dies!")
        self.actor.dx = self.target.x - self.actor.x
        self.actor.dy = self.target.y - self.actor.y
        return self


class BumpAction(MoveAction):
    def get_entity(self) -> entities.Entity | None:
        new_x = self.actor.x + self.dx
        new_y = self.actor.y + self.dy
        for e in self.actor.map.entities:
            if e.x == new_x and e.y == new_y and e != self.actor:
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
            return AttackAction(entity, self.actor).perform()
        else:
            return super().perform()
