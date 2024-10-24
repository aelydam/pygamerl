from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np
import tcod
import tcod.ecs as ecs

import comp
import consts
import db
import dice
import entities
import funcs
import game_logic
import items
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
        initiative = self.actor.components.get(comp.Initiative, 0)
        if (
            initiative >= 1
            and (
                self.actor.components.get(comp.HP, 0)
                < self.actor.components.get(comp.MaxHP, 0)
            )
            and not entities.is_hungry(self.actor)
        ):
            seed = self.actor.registry[None].components[random.Random]
            roll = dice.dice_roll("1d20", seed)
            if roll >= 15:
                heal = Heal(self.actor, "min(1d4,1d4)")
                game_logic.push_action(self.actor.registry, heal)
        self.cost = initiative
        return super().perform()


class Rest(WaitAction):
    def can(self):
        return (
            super().can()
            and (
                self.actor.components.get(comp.HP, 0)
                < self.actor.components.get(comp.MaxHP, 0)
            )
            and not entities.is_hungry(self.actor)
        )


@dataclass
class MoveAction(ActorAction):
    direction: tuple[int, int]

    def __post_init__(self, *args, **kwargs):
        self.cost = sum([self.direction[i] ** 2 for i in range(2)]) ** 0.5
        self.cost *= (1 + consts.BASE_SPEED) / (1 + entities.speed(self.actor))

    def can(self) -> bool:
        dist = sum([self.direction[i] ** 2 for i in range(2)]) ** 0.5
        if dist > 1.5:
            return False
        if (
            comp.Position not in self.actor.components
            or comp.Speed not in self.actor.components
            or self.actor.components[comp.Speed] < 1
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
        walkable = db.walkable[tiles]
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
        # Set currency as objective
        query = self.actor.registry.Q.all_of(
            components=[comp.Position],
            tags=[comp.Currency, "items"],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            xy = e.components[comp.Position].xy
            dijkstra[xy] = 0
            cost[xy] = 0
            if xy == pos:
                return Pickup(self.actor, e, False).perform()

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
    roll: int = field(init=False, default=0)
    hit: bool = field(init=False, default=False)
    crit: bool = field(init=False, default=False)
    xy: tuple[int, int] = field(init=False, default=(0, 0))

    def can(self) -> bool:
        if self.actor == self.target:
            return False
        dist = entities.dist(self.actor, self.target)
        reach = self.actor.components.get(comp.Reach, 1.5)
        if dist > reach:
            return False
        if not entities.is_alive(self.target):
            return False
        return True

    def perform(self) -> Action | None:
        if not self.can():
            return None
        seed = self.actor.registry[None].components[random.Random]
        bonus = entities.attack_bonus(self.actor)
        attack_expr = f"1d20+{bonus}"
        self.roll = int(dice.dice_roll(attack_expr, seed))
        min_roll = dice.dice_min(attack_expr)
        max_roll = dice.dice_max(attack_expr)
        ac = entities.armor_class(self.target)
        self.hit = (self.roll >= ac and self.roll > min_roll) or (self.roll >= max_roll)
        self.crit = self.roll in {min_roll, max_roll}

        aname = self.actor.components.get(comp.Name, "Something")
        tname = self.target.components.get(comp.Name, "Something")
        text = f"{aname} attacks {tname}: "
        if self.hit:
            dmg_dice = entities.damage_dice(self.actor)
            dmg_min = dice.dice_min(dmg_dice)
            self.damage = int(dice.dice_roll(dmg_dice, seed))
            if self.crit:
                self.damage += int(dice.dice_roll(dmg_dice, seed) - dmg_min + 1)
            text += f"{self.damage} points of damage!"
            if self.crit:
                text += " (critical)"
        else:
            self.damage = 0
            text += "Miss!"
        if comp.Trap in self.actor.tags and comp.HideSprite in self.actor.tags:
            self.actor.tags.discard(comp.HideSprite)
        apos = self.actor.components[comp.Position].xy
        tpos = self.target.components[comp.Position].xy
        self.actor.components[comp.Direction] = (tpos[0] - apos[0], tpos[1] - apos[1])
        damage = Damage(self.target, self.damage, self.crit)
        game_logic.push_action(self.target.registry, damage)
        self.message = text
        self.cost = 1
        return self


class BumpAction(MoveAction):
    def get_action(self) -> Action | None:
        map_entity = self.actor.relation_tag[comp.Map]
        new_pos = self.actor.components[comp.Position] + self.direction
        # Try to attack
        query = self.actor.registry.Q.all_of(
            [comp.Position, comp.HP],
            tags=[new_pos],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            if e == self.actor:
                continue
            action: Action = AttackAction(self.actor, e)
            if action.can():
                return action
        # Try to pick item
        query = self.actor.registry.Q.all_of(
            [comp.Position],
            tags=[new_pos, "items", comp.Autopick],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            if e == self.actor:
                continue
            action = Pickup(self.actor, e, bump=True)
            if action.can():
                return action
        # Try to interact
        query = self.actor.registry.Q.all_of(
            [comp.Position, comp.Interaction],
            tags=[new_pos],
            relations=[(comp.Map, map_entity)],
        )
        for e in sorted(query, key=lambda x: comp.Obstacle not in x.tags):
            if e == self.actor:
                continue
            action_class = e.components[comp.Interaction]
            action = action_class(self.actor, e, bump=True)
            if action.can():
                return action
        return None

    def can(self) -> bool:
        self.actor.components[comp.Direction] = self.direction
        if super().can():
            return True
        action = self.get_action()
        if action is not None:
            return action.can()
        return False

    def perform(self) -> Action | None:
        if not self.can():
            return None
        action = self.get_action()
        if action is not None and action.can():
            return action.perform()
        return super().perform()


@dataclass
class Interact(ActorAction):
    def get_entity_at(self, direction: tuple[int, int]) -> ecs.Entity | None:
        map_entity = self.actor.relation_tag[comp.Map]
        pos = self.actor.components[comp.Position] + direction
        query = self.actor.registry.Q.all_of(
            [comp.Position],
            tags=[pos, "items"],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            return e
        query = self.actor.registry.Q.all_of(
            [comp.Position, comp.Interaction],
            tags=[pos],
            relations=[(comp.Map, map_entity)],
        )
        for e in query:
            if e != self.actor:
                return e
        return None

    def get_entity(self) -> ecs.Entity | None:
        direction = self.actor.components.get(comp.Direction, (0, 0))
        for d in [(0, 0), direction]:
            e = self.get_entity_at(d)
            if e is not None:
                return e
        return None

    def get_action(self) -> Interaction | None:
        entity = self.get_entity()
        if entity is not None:
            if comp.Interaction in entity.components:
                action_class = entity.components[comp.Interaction]
            else:
                action_class = Pickup
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
        walkable = db.walkable[tiles]
        explorable = walkable | (funcs.moore(walkable) > 0)
        remaining = np.sum(explorable & ~explored)
        return bool(remaining > 0)

    def perform(self) -> Action | None:
        map_ = self.actor.relation_tag[comp.Map]
        tiles = map_.components[comp.Tiles]
        explored = map_.components[comp.Explored]
        walkable = db.walkable[tiles]
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


class Pickup(Interaction):
    def can(self) -> bool:
        return (
            self.target is not None
            and (not self.bump or comp.Autopick in self.target.tags)
            and "items" in self.target.tags
            and super().can()
        )

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        count = self.target.components.get(comp.Count, 1)
        self.cost = count / self.target.components.get(comp.MaxStack, 1)
        aname = self.actor.components.get(comp.Name)
        tname = items.display_name(self.target)
        if aname is not None and tname is not None:
            count = self.target.components.get(comp.Count, 1)
            self.message = f"{aname} picks {count} {tname}"
        items.pickup(actor=self.actor, item=self.target)
        return self


class Drop(Interaction):
    def can(self) -> bool:
        return (
            self.target is not None
            and self.target.relation_tag[comp.Inventory] == self.actor
        )

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        items.drop(self.target)
        aname = self.actor.components.get(comp.Name)
        tname = items.display_name(self.target)
        if aname is not None and tname is not None:
            self.message = f"{aname} drops {tname}"
        return self


class Use(Interaction):
    def can(self) -> bool:
        return (
            self.target is not None
            and self.target.relation_tag[comp.Inventory] == self.actor
            and comp.Effects in self.target.components
        )

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        aname = self.actor.components.get(comp.Name)
        tname = items.display_name(self.target)
        if aname is not None and tname is not None:
            self.message = f"{aname} uses {tname}"
        if not items.is_identified(self.target):
            items.identify(self.target)
            tname = items.display_name(self.target)
            self.message += f": it is a {tname}"
        items.apply_effects(self.target, self.actor)
        return self


class Equip(Interaction):
    def can(self) -> bool:
        return (
            self.target is not None
            and self.target.relation_tag[comp.Inventory] == self.actor
            and items.is_equippable(self.target)
        )

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        items.equip(self.actor, self.target)
        aname = self.actor.components.get(comp.Name)
        tname = items.display_name(self.target)
        if aname is not None and tname is not None:
            self.message = f"{aname} equips {tname}"
        if not items.is_identified(self.target):
            items.identify(self.target)
            tname = items.display_name(self.target)
            self.message += f": it is a {tname}"
        self.cost = 2
        return self


class Unequip(Interaction):
    def can(self) -> bool:
        return (
            self.target is not None
            and self.target.relation_tag[comp.Inventory] == self.actor
            and items.is_equipped(self.target)
        )

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        items.unequip_item(self.target)
        aname = self.actor.components.get(comp.Name)
        tname = self.target.components.get(comp.Name)
        if aname is not None and tname is not None:
            self.message = f"{aname} unequips {tname}"
        self.cost = 0
        return self


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
        maps.update_map_light(self.target.relation_tag[comp.Map], True)
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


class DisarmTrap(Interaction):
    def can(self):
        return (
            not self.bump
            and self.target is not None
            and comp.Trap in self.target.tags
            and comp.HideSprite not in self.target.tags
            and super().can()
        )

    def perform(self) -> Action | None:
        if not self.can() or self.target is None:
            return None
        self.target.clear()
        self.cost = 1
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} disarms a trap"
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


class Boulder(Interaction):
    def get_direction(self) -> tuple[int, int]:
        if self.target is None:
            return (0, 0)
        apos = self.actor.components[comp.Position].xy
        tpos = self.target.components[comp.Position].xy
        if self.bump:
            return (int(tpos[0] - apos[0]), int(tpos[1] - apos[1]))
        else:
            return (int(apos[0] - tpos[0]), int(apos[1] - tpos[1]))

    def can(self) -> bool:
        if self.target is None or not super().can():
            return False
        if entities.dist(self.actor, self.target) > 1.5:
            return False
        direction = self.get_direction()
        if self.bump:
            check_pos = self.target.components[comp.Position] + direction
        else:
            check_pos = self.actor.components[comp.Position] + direction
        return maps.is_walkable(self.actor.relation_tag[comp.Map], check_pos)

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        direction = self.get_direction()
        self.target.components[comp.Position] += direction
        if not self.bump:
            self.actor.components[comp.Position] += direction
        self.cost = 1
        return self


@dataclass
class Heal(ActorAction):
    amount: int | str
    critical: bool = False

    def can(self) -> bool:
        return comp.HP in self.actor.components

    def perform(self) -> Action | None:
        if not self.can():
            return None
        if isinstance(self.amount, str):
            seed = self.actor.registry[None].components[random.Random]
            self.amount = int(dice.dice_roll(self.amount, seed))
        max_hp = self.actor.components[comp.MaxHP]
        new_hp = min(max_hp, max(0, self.actor.components[comp.HP] + self.amount))
        self.cost = 0
        self.actor.components[comp.HP] = new_hp
        apos = self.actor.components[comp.Position]
        self.xy = apos.xy
        return self


@dataclass
class Eat(ActorAction):
    amount: int | str

    def can(self) -> bool:
        return comp.Hunger in self.actor.components

    def perform(self) -> Action | None:
        if not self.can():
            return None
        if isinstance(self.amount, str):
            seed = self.actor.registry[None].components[random.Random]
            self.amount = int(dice.dice_roll(self.amount, seed))
        self.actor.components[comp.Hunger] -= self.amount
        new_hunger = self.actor.components[comp.Hunger] - self.amount
        self.actor.components[comp.Hunger] = max(0, new_hunger)
        apos = self.actor.components[comp.Position]
        self.xy = apos.xy
        return self


@dataclass
class Damage(ActorAction):
    amount: int | str
    critical: bool = False

    def can(self) -> bool:
        return comp.HP in self.actor.components

    def perform(self) -> Action | None:
        if not self.can():
            return None
        if isinstance(self.amount, str):
            seed = self.actor.registry[None].components[random.Random]
            self.amount = int(dice.dice_roll(self.amount, seed))
        self.cost = 0
        new_hp = max(0, self.actor.components[comp.HP] - self.amount)
        self.actor.components[comp.HP] = new_hp
        apos = self.actor.components[comp.Position]
        self.xy = apos.xy
        if new_hp < 1:
            game_logic.push_action(self.actor.registry, Die(self.actor))
        if self.amount > 0:
            map_entity = self.actor.relation_tag[comp.Map]
            query = self.actor.registry.Q.all_of(
                components=[comp.Position, comp.Sprite],
                tags=[comp.Bloodstain],
                relations=[(comp.Map, map_entity)],
            )
            if len(query.get_entities()) < 1:
                self.actor.registry.new_entity(
                    components={
                        comp.Position: apos,
                        comp.Sprite: comp.Sprite("Objects/Ground0", (1, 5)),
                    }
                )
        return self


@dataclass
class Die(ActorAction):
    def perform(self) -> Action | None:
        aname = self.actor.components.get(comp.Name)
        apos = self.actor.components[comp.Position]
        self.xy = apos.xy
        if comp.Player not in self.actor.tags:
            items.drop_all(self.actor)
            self.actor.clear()
        self.actor.registry.new_entity(
            components={
                comp.Position: apos,
                comp.Sprite: comp.Sprite("Objects/Decor0", (1, 12)),
            }
        )
        if aname is not None:
            self.message = f"{aname} dies!"
        return self
