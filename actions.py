from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np
import tcod
import tcod.ecs as ecs

import comp
import conditions
import consts
import db
import dice
import entities
import funcs
import game_logic
import items
import maps
import procgen


@dataclass
class Action:
    message: str = field(init=False, default="")
    cost: float = field(init=False, default=0)
    append_message: bool = field(init=False, default=False)

    def can(self) -> bool:
        return True

    def perform(self) -> Action | None:
        return self


@dataclass
class ActorAction(Action):
    actor: ecs.Entity


@dataclass
class Effect(ActorAction):
    blame: ecs.Entity | None


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
                heal = Heal(self.actor, None, "min(1d4,1d4)")
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
        if comp.MovementSFX in self.actor.components:
            self.sfx = self.actor.components[comp.MovementSFX]
        if comp.Player in self.actor.tags:
            steps = self.actor.registry[None].components.get(comp.PlayerSteps, 0)
            self.actor.registry[None].components[comp.PlayerSteps] = steps + self.cost
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

    @classmethod
    def flee(cls, actor: ecs.Entity) -> MoveAction | None:
        map_entity = actor.relation_tag[comp.Map]
        a_pos = actor.components[comp.Position].xy
        cost = maps.cost_matrix(map_entity)
        # Increase the cost near walls
        cost[(cost > 0) & (funcs.moore(cost == 0) > 0)] += 1
        cost[a_pos] = 1
        #
        dijkstra = tcod.path.maxarray(cost.shape, dtype=np.int32)
        enemies = entities.enemies_in_fov(actor)
        if len(enemies) < 1 and comp.AITarget not in actor.components:
            return None
        # Set "targets"
        for e in enemies:
            e_pos = e.components[comp.Position].xy
            dijkstra[e_pos] = 0
        if comp.AITarget in actor.components:
            e_pos = actor.components[comp.AITarget].xy
            dijkstra[e_pos] = 0
        # Create Dijkstra map
        tcod.path.dijkstra2d(dijkstra, cost, 2, 3, out=dijkstra)
        # Invert dijkstra map
        dijkstra = np.where(dijkstra <= 256, 256 - dijkstra, dijkstra)
        #
        path = tcod.path.hillclimb2d(dijkstra, a_pos, True, True).tolist()
        if len(path) < 2:
            return None
        dx, dy = path[1][0] - path[0][0], path[1][1] - path[0][1]
        return MoveAction(actor, (dx, dy))


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
class Projectile(ActorAction):
    target: tuple[int, int]

    def can(self) -> bool:
        return (
            comp.Position in self.actor.components
            and entities.dist(self.actor, self.target) > 0
        )

    def perform(self) -> Action | None:
        if not self.can():
            return None
        pos = self.actor.components[comp.Position]
        path = tcod.los.bresenham(pos.xy, self.target).tolist()
        if len(path) < 2:
            return None
        direction = (path[1][0] - path[0][0], path[1][1] - path[0][1])
        self.actor.components[comp.Position] += direction
        if entities.dist(self.actor, self.target) >= 1:
            game_logic.push_action(self.actor.registry, self)
        else:
            self.actor.clear()
        self.cost = 0
        return self


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
            if not entities.is_in_fov(self.actor, xy):
                continue
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
        if not entities.is_alive(self.target):
            return False
        dist = entities.dist(self.actor, self.target)
        weapon_range = entities.attack_range(self.actor)
        if dist > weapon_range:
            return False
        if weapon_range > 2 and not entities.has_ammo(self.actor):
            return False
        if dist >= 1.5 and not entities.is_in_fov(self.actor, self.target):
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
        verb = self.actor.components.get(comp.AttacksVerb, "attacks")
        text = f"{aname} {verb} {tname}: "
        if self.hit:
            dmg_dice = entities.damage_dice(self.actor)
            dmg_min = dice.dice_min(dmg_dice)
            self.damage = int(dice.dice_roll(dmg_dice, seed))
            if self.crit:
                self.damage += int(dice.dice_roll(dmg_dice, seed) - dmg_min + 1)
            if comp.OnAttack in self.actor.components:
                apply_effects(self.target, self.actor.components[comp.OnAttack])
        else:
            self.damage = 0
            text += "Miss!"
        # Reveal trap
        if comp.Trap in self.actor.tags and comp.Hidden in self.actor.tags:
            self.actor.tags.discard(comp.Hidden)
        # Change player direction
        apos = self.actor.components[comp.Position].xy
        tpos = self.target.components[comp.Position].xy
        self.actor.components[comp.Direction] = (tpos[0] - apos[0], tpos[1] - apos[1])
        # Push damage to action queue
        damage = Damage(
            self.target, blame=self.actor, amount=self.damage, critical=self.crit
        )
        damage.append_message = True
        game_logic.push_action(self.target.registry, damage)
        self.message = text
        self.cost = 1
        # Remove ammo
        weapon_range = entities.attack_range(self.actor)
        if weapon_range > 2 and entities.has_ammo(self.actor):
            ammo = items.equipment_at_slot(self.actor, comp.EquipSlot.Quiver)
            assert ammo is not None
            ammo.components[comp.Count] -= 1
            # Add projectile
            if comp.Sprite in ammo.components:
                pos0 = self.actor.components[comp.Position]
                dx, dy = tpos[0] - apos[0], tpos[1] - apos[1]
                angle = math.degrees(math.atan2(-dy, dx))
                proj_entity = ammo.registry.new_entity(
                    components={
                        comp.Sprite: ammo.components[comp.Sprite],
                        comp.Position: pos0,
                        comp.SpriteRotation: angle,
                    }
                )
                proj_action = Projectile(proj_entity, tpos)
                game_logic.push_action(proj_entity.registry, proj_action)
            if ammo.components.get(comp.Count, 1) < 1:
                ammo.clear()
                if comp.EquipSlot.Quiver in self.actor.relation_tag:
                    self.actor.relation_tag.pop(comp.EquipSlot.Quiver)
        # Sound effect
        mainhand = items.equipment_at_slot(self.actor, comp.EquipSlot.Main_Hand)
        if mainhand is not None and comp.AttackSFX in mainhand.components:
            self.sfx = mainhand.components[comp.AttackSFX]
        elif comp.AttackSFX in self.actor.components:
            self.sfx = self.actor.components[comp.AttackSFX]
        return self

    @classmethod
    def nearest(cls, actor: ecs.Entity) -> AttackAction | None:
        target = entities.nearest_enemy(actor)
        if target is None:
            return None
        return cls(actor, target)


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


class Search(ActorAction):
    def perform(self) -> Action | None:
        apos = self.actor.components[comp.Position]
        map_entity = self.actor.relation_tag[comp.Map]
        found_something = False
        directions = {(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)}
        for d in directions:
            pos = apos + d
            if not entities.is_in_fov(self.actor, pos):
                continue
            query = self.actor.registry.Q.all_of(
                components=[comp.Position],
                tags=[comp.Hidden, pos],
                relations=[(comp.Map, map_entity)],
            )
            for e in query:
                see = See(self.actor, None, e)
                game_logic.push_action(self.actor.registry, see)
                self.actor.components[comp.Direction] = d
                found_something = True
        aname = self.actor.components.get(comp.Name)
        if not found_something and aname is not None:
            self.message = f"{aname} sees nothing"
        self.cost = 1
        return self


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
            and (
                comp.Position in self.target.components
                or comp.Inventory in self.target.relation_tag
            )
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


class ToggleMainHand(ActorAction):
    def can(self):
        return (
            entities.is_alive(self.actor)
            and items.equipment_at_slot(self.actor, comp.EquipSlot.Ready) is not None
        )

    def perform(self) -> Action | None:
        if not self.can():
            return None
        ready = items.equipment_at_slot(self.actor, comp.EquipSlot.Ready)
        assert ready is not None
        return Equip(self.actor, ready).perform()


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
            verb = self.target.components.get(comp.UsesVerb, "uses")
            self.message = f"{aname} {verb} {tname}"
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
            and (items.is_equipped(self.target) or items.is_ready(self.target))
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
        if self.target is None or not self.can():
            return None
        spr: comp.Sprite | None = None
        if comp.Locked in self.target.tags:
            if comp.Key in self.target.relation_tag:
                key = self.target.relation_tag[comp.Key]
                if key.relation_tag.get(comp.Inventory) != self.actor:
                    self.cost = 0
                    self.message = "The door is locked"
                    return self
            verb = "unlocks"
            self.target.tags.discard(comp.Locked)
            spr = self.target.components.get(comp.ClosedSprite)
        elif comp.Obstacle in self.target.tags:
            verb = "opens"
            self.target.tags.discard(comp.Obstacle)
            if comp.Opaque in self.target.tags:
                self.target.tags.discard(comp.Opaque)
            spr = self.target.components.get(comp.OpenSprite)
        else:
            verb = "closes"
            self.target.tags |= {comp.Obstacle, comp.Opaque}
            spr = self.target.components.get(comp.ClosedSprite)
        if spr is not None:
            self.target.components[comp.Sprite] = spr
        maps.update_map_light(self.target.relation_tag[comp.Map], True)
        entities.update_fov(self.actor)
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
            and comp.Hidden not in self.target.tags
            and super().can()
        )

    def perform(self) -> Action | None:
        if not self.can() or self.target is None:
            return None
        xp = self.target.components.get(comp.XPGain)
        self.target.clear()
        self.cost = 1
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} disarms a trap"

        if (
            self.actor is not None
            and xp is not None
            and comp.XP in self.actor.components
        ):
            gainxp = GainXP(self.actor, self.target, xp)
            gainxp.append_message = True
            game_logic.push_action(self.actor.registry, gainxp)
        return self


class Descend(Interaction):
    def can(self) -> bool:
        return not self.bump and super().can()

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        pos = self.target.components[comp.Position]
        new_depth = pos.depth + 1
        map_entity = maps.get_map(self.actor.registry, new_depth)
        new_pos = comp.Position(pos.xy, new_depth)
        self.actor.components[comp.Position] = new_pos
        self.cost = 1
        if new_depth > self.actor.registry[None].components.get(comp.MaxDepth, 0):
            self.actor.registry[None].components[comp.MaxDepth] = new_depth
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} descends the stairs"
        if comp.XPGain in map_entity.components:
            xp = map_entity.components[comp.XPGain]
            if xp > 0:
                gainxp = GainXP(self.actor, None, xp)
                gainxp.append_message = True
                game_logic.push_action(self.actor.registry, gainxp)
            map_entity.components.pop(comp.XPGain)
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
        return maps.is_walkable(
            self.actor.relation_tag[comp.Map], check_pos, not self.bump
        )

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        direction = self.get_direction()
        new_pos = self.target.components[comp.Position] + direction
        self.cost = 1
        if not self.bump:
            self.actor.components[comp.Position] += direction
        else:
            # Check if there is someone at the position
            map_entity = self.target.relation_tag[comp.Map]
            query = self.actor.registry.Q.all_of(
                components=[comp.Position, comp.HP],
                tags=[new_pos],
                relations=[(comp.Map, map_entity)],
            )
            for e in query:
                attack = AttackAction(self.target, e)
                game_logic.push_action(self.actor.registry, attack)
                return self
        self.target.components[comp.Position] = new_pos
        return self


class OpenContainer(Interaction):
    def can(self) -> bool:
        return (
            self.target is not None
            and entities.dist(self.actor, self.target) < 1.5
            and entities.is_alive(self.actor)
        )

    def perform(self) -> Action | None:
        if self.target is None or not self.can():
            return None
        spr = self.target.components.get(comp.OpenSprite)
        if spr is not None:
            self.target.components[comp.Sprite] = spr
        # this is just a dummy action
        # it is intended to trigger a callback in interface side
        aname = self.actor.components.get(comp.Name)
        tname = self.target.components.get(comp.Name)
        if aname is not None and tname is not None:
            self.message = f"{aname} opens {tname}"
            if len(list(items.inventory(self.target))) < 1:
                self.message += ": empty"
        return self


@dataclass
class Heal(Effect):
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
class Eat(Effect):
    amount: int | str

    def can(self) -> bool:
        return comp.Hunger in self.actor.components

    def perform(self) -> Action | None:
        if not self.can():
            return None
        if isinstance(self.amount, str):
            seed = self.actor.registry[None].components[random.Random]
            self.amount = int(dice.dice_roll(self.amount, seed))
        new_hunger = self.actor.components[comp.Hunger] - self.amount
        self.actor.components[comp.Hunger] = max(0, new_hunger)
        apos = self.actor.components[comp.Position]
        self.xy = apos.xy
        return self


@dataclass
class Damage(Effect):
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
            game_logic.push_action(self.actor.registry, Die(self.actor, self.blame))
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
        if self.amount > 0:
            aname = self.actor.components.get(comp.Name)
            if not self.append_message and aname is not None:
                self.message = f"{aname} takes "
            self.message += f"{self.amount} points of damage!"
            if self.critical:
                self.message += " (critical)"
        if new_hp > 0 and self.amount > 0 and comp.OnDamage in self.actor.components:
            apply_effects(self.actor, self.actor.components[comp.OnDamage])
        return self


@dataclass
class Die(Effect):
    def perform(self) -> Action | None:
        aname = self.actor.components.get(comp.Name)
        apos = self.actor.components[comp.Position]
        self.xy = apos.xy
        xp = self.actor.components.get(comp.XPGain)
        map_entity = self.actor.relation_tag[comp.Map]
        procgen.spawn_prop(map_entity, "Bones", apos.xy)
        if aname is not None:
            self.message = f"{aname} dies!"
        if self.blame is not None:
            if xp is not None and comp.XP in self.blame.components:
                gain = GainXP(self.blame, self.actor, xp)
                gain.append_message = True
                game_logic.push_action(self.actor.registry, gain)
            if comp.Player in self.blame.tags and ecs.IsA in self.actor.relation_tag:
                # Increase creature kind counter
                kind = self.actor.relation_tag[ecs.IsA]
                kills = kind.components.get(comp.PlayerKills, 0) + 1
                kind.components[comp.PlayerKills] = kills
                # Increase global counter
                kills = (
                    self.actor.registry[None].components.get(comp.PlayerKills, 0) + 1
                )
                self.actor.registry[None].components[comp.PlayerKills] = kills
        if comp.Player not in self.actor.tags:
            items.drop_all(self.actor)
            self.actor.clear()
        return self


@dataclass
class GainXP(Effect):
    amount: int

    def can(self) -> bool:
        return self.amount > 0 and comp.XP in self.actor.components

    def perform(self) -> Action | None:
        if not self.can():
            return None
        self.actor.components[comp.XP] += self.amount
        if self.append_message:
            self.message = f"({self.amount}XP)"
        else:
            aname = self.actor.components[comp.Name]
            self.message = f"{aname} gains {self.amount} points of experience"
        if entities.can_level_up(self.actor):
            game_logic.push_action(self.actor.registry, LevelUp(self.actor, None))

        return self


@dataclass
class LevelUp(Effect):
    def can(self) -> bool:
        return entities.can_level_up(self.actor)

    def perform(self) -> Action | None:
        if not self.can():
            return None
        level = self.actor.components.get(comp.Level, 1)
        new_level = level + 1
        new_hp = 8
        self.actor.components[comp.MaxHP] += new_hp
        self.actor.components[comp.HP] += new_hp
        if new_level % 2 == 0:
            self.actor.components[comp.AttackBonus] += 1
        if new_level % 4 == 0:
            self.actor.components[comp.AttackBonus] += 1
            self.actor.components[comp.DamageBonus] += 1
        self.actor.components[comp.Level] = new_level
        aname = self.actor.components.get(comp.Name)
        if aname is not None:
            self.message = f"{aname} advances to level {new_level}!"
        if entities.can_level_up(self.actor):
            game_logic.push_action(self.actor.registry, LevelUp(self.actor, None))
        return self


@dataclass
class See(Effect):
    target: ecs.Entity

    def can(self) -> bool:
        return entities.is_in_fov(self.actor, self.target)

    def perform(self) -> Action | None:
        aname = self.actor.components.get(comp.Name)
        tname = self.target.components.get(comp.Name)
        self.target.tags |= {comp.Seen}
        if comp.Hidden in self.target.tags:
            self.target.tags.discard(comp.Hidden)
        if aname is not None and tname is not None:
            self.message = f"{aname} sees {tname}"
            wielding = items.equipment_at_slot(self.target, comp.EquipSlot.Main_Hand)
            if wielding is not None:
                self.message += ", wielding " + items.display_name(wielding)
            wearing = items.equipment_at_slot(self.target, comp.EquipSlot.Chest)
            if wearing is not None:
                self.message += ", wearing " + items.display_name(wearing)
        return self


@dataclass
class AddCondition(Effect):
    condition: ecs.Entity | str
    turns: int | str

    def can(self) -> bool:
        return True

    def perform(self) -> Action | None:
        if isinstance(self.condition, str):
            condition = self.actor.registry[("conditions", self.condition)]
        else:
            condition = self.condition
        if isinstance(self.turns, str):
            seed = self.actor.registry[None].components[random.Random]
            turns = int(dice.dice_roll(self.turns, seed))
        else:
            turns = self.turns
        aname = self.actor.components.get(comp.Name)
        cname = condition.components.get(comp.Name)
        conditions.add_condition(self.actor, condition, turns)
        if aname is not None and cname is not None:
            self.message = f"{aname} gets condition {cname}"
        conditions.apply_condition_effect(condition, self.actor)
        return self


@dataclass
class RemoveCondition(Effect):
    condition: ecs.Entity | str

    def can(self) -> bool:
        if isinstance(self.condition, str):
            condition = self.actor.registry[("conditions", self.condition)]
        else:
            condition = self.condition
        return (
            comp.ConditionTurns in self.actor.relation_components
            and condition in self.actor.relation_components[comp.ConditionTurns]
        )

    def perform(self) -> Action | None:
        if isinstance(self.condition, str):
            condition = self.actor.registry[("conditions", self.condition)]
        else:
            condition = self.condition
        aname = self.actor.components.get(comp.Name)
        cname = condition.components.get(comp.Name)
        conditions.remove_condition(self.actor, condition)
        if aname is not None and cname is not None:
            self.message = f"{aname} loses condition {cname}"
        return self


@dataclass
class Split(Effect):
    minimum_hp: int = 3

    def can(self) -> bool:
        return (
            self.actor.components.get(comp.HP, 0) >= max(2, self.minimum_hp)
            and ecs.IsA in self.actor.relation_tag
            and comp.Map in self.actor.relation_tag
            and comp.Position in self.actor.components
        )

    def perform(self) -> Action | None:
        hp = self.actor.components[comp.HP]
        new_hp = hp // 2
        if new_hp < 1:
            return None
        kind = self.actor.relation_tag[ecs.IsA]
        map_entity = self.actor.relation_tag[comp.Map]
        pos = self.actor.components[comp.Position]
        copy = entities.spawn_creature(map_entity, pos.xy, kind)
        copy.components[comp.HP] = new_hp
        self.actor.components[comp.HP] = new_hp
        MoveAction.random(copy).perform()
        copy.components[comp.Initiative] = max(
            1, self.actor.components[comp.Initiative]
        )
        return self


class Read(Effect):
    def can(self) -> bool:
        return (
            super().can()
            and self.blame is not None
            and comp.Text in self.blame.components
        )

    def perform(self) -> Action | None:
        if not self.can():
            return None
        return self


def apply_effects(
    actor: ecs.Entity,
    effects: dict[comp.Effect, dict | list | str | int | None],
    blame: ecs.Entity | None = None,
):
    for effect, args in effects.items():
        if isinstance(args, dict):
            action = effect(actor, blame=blame, **args)
        elif isinstance(args, list):
            action = effect(actor, blame, *args)
        elif args is not None:
            action = effect(actor, blame, args)
        else:
            action = effect(actor, blame)
        game_logic.push_action(actor.registry, action)
