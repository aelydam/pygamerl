import random

import consts
import entities


class WaitAction:
    def can(self):
        return True

    def perform(self):
        return self


class MoveAction:
    def __init__(self, dx, dy, actor):
        self.dx, self.dy, self.actor = dx, dy, actor

    def can(self):
        dist = (self.dx**2 + self.dy**2)**0.5
        if dist > 1.5:
            return False
        new_x = self.actor.x + self.dx
        new_y = self.actor.y + self.dy
        if new_x < 0 or new_y < 0 or new_x >= consts.MAP_SHAPE[0] or new_y >= consts.MAP_SHAPE[1]:
            return False
        return self.actor.game_logic.is_walkable(new_x, new_y)

    def perform(self):
        if not self.can():
            return
        self.actor.x += self.dx
        self.actor.y += self.dy
        return self


class AttackAction:
    def __init__(self, target, actor):
        self.target = target
        self.actor = actor

    def can(self):
        dist = ((self.target.x-self.actor.x)**2+(self.target.y-self.actor.y)**2)**0.5
        if dist > 1.5:
            return False
        if self.target.hp < 1:
            return False
        return True

    def perform(self):
        if not self.can():
            return None
        roll = random.randint(1, 20) + self.actor.tohit
        if isinstance(self.actor, entities.Player):
            text = "You attack the enemy: "
        else:
            text = "The enemy attacks you: "
        if roll >= self.target.ac:
            self.damage = random.randint(1, self.actor.damage)
            self.target.hp = max(0, self.target.hp - self.damage)
            text += f"{self.damage} points of damage!"
        else:
            self.damage = 0
            text += "Miss!"
        self.actor.game_logic.log(text)
        if self.target.hp < 0:
            if isinstance(self.target, entities.Player):
                self.actor.game_logic.log("You die!")
            else:
                self.actor.game_logic.log("The enemy dies!")
        return self


class BumpAction:
    def __init__(self, dx, dy, actor):
        self.dx, self.dy, self.actor = dx, dy, actor

    def get_entity(self):
        new_x = self.actor.x + self.dx
        new_y = self.actor.y + self.dy
        for e in self.actor.game_logic.entities:
            if e.x == new_x and e.y == new_y and e != self.actor:
                return e
        return None

    def can(self):
        move = MoveAction(self.dx, self.dy, self.actor)
        if move.can():
            return True
        entity = self.get_entity()
        return entity is not None

    def perform(self):
        if not self.can():
            return None
        move = MoveAction(self.dx, self.dy, self.actor)
        if move.can():
            return move.perform()
        entity = self.get_entity()
        attack = AttackAction(entity, self.actor)
        return attack.perform()
