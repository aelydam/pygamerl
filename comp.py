import datetime
from collections import deque
from dataclasses import dataclass
from typing import Protocol

import numpy as np
import tcod.ecs as ecs
from numpy.typing import NDArray

import actions

# Tags
Map = "Map"
Player = "Player"
Inventory = "Inventory"
Obstacle = "Obstacle"
Opaque = "Opaque"
HideSprite = "HideSprite"
Downstairs = "Downstairs"
Upstairs = "Upstairs"
Trap = "Trap"
Lit = "Lit"
Bloodstain = "Bloodstain"

# Map components
Depth = ("Depth", int)
Tiles = ("Tiles", NDArray[np.int8])
Explored = ("Explored", NDArray[np.bool_])

# Actor components
Name = ("Name", str)
Direction = ("Direction", tuple[int, int])
ArmorClass = ("ArmorClass", int)
AttackBonus = ("AttackBonus", int)
DamageDice = ("DamageDice", int)
MaxHP = ("MaxHP", int)
HP = ("HP", int)
FOVRadius = ("FOVRadius", int)
FOV = ("FOV", NDArray[np.bool_])
Initiative = ("Initiative", float)
LightRadius = ("LightRadius", int)
Lightsource = ("Lightsource", NDArray[np.int8])
Speed = ("Speed", int)
Reach = ("Reach", float)

# Global components
MessageLog = ("MessageLog", list[str])
InitiativeTracker = ("InitiativeTracker", deque[ecs.Entity])
ActionQueue = ("ActionQueue", deque[actions.Action])
TurnCount = ("TurnCount", int)
LastPlayed = ("LastPlayed", datetime.datetime)
PlayedTime = ("PlayedTime", float)
MaxDepth = ("MaxDepth", int)


@dataclass(frozen=True)
class Position:
    xy: tuple[int, int]
    depth: int

    def __add__(self, direction: tuple[int, int]):
        xy = (self.xy[0] + direction[0], self.xy[1] + direction[1])
        return self.__class__(xy, self.depth)


AITarget = ("AITarget", Position)


# See https://python-tcod.readthedocs.io/en/latest/tutorial/part-02.html#ecs-components
@ecs.callbacks.register_component_changed(component=Position)
def on_position_changed(
    entity: ecs.Entity, old: Position | None, new: Position | None
) -> None:
    """Mirror position components as a tag."""
    if old == new:  # New position is equivalent to its previous value
        return  # Ignore and return
    if old is not None:  # Position component removed or changed
        entity.tags.discard(old)  # Remove old position from tags
        if Map in entity.relation_tag:
            entity.relation_tag.pop(Map)
    if new is not None:  # Position component added or changed
        entity.tags.add(new)  # Add new position to tags
        entity.relation_tag[Map] = entity.registry[(Map, new.depth)]


@dataclass(frozen=True)
class Sprite:
    sheet: str
    tile: tuple[int, int]


class Interaction(Protocol):
    def __call__(
        self, actor: ecs.Entity, target: ecs.Entity, bump: bool = False
    ) -> actions.Interaction: ...
