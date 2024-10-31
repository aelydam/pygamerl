from __future__ import annotations

from typing import Callable

import pygame as pg
import tcod.ecs as ecs

import actions
import game_interface
import states

MOVE_KEYS = {
    pg.K_UP: (0, -1),
    pg.K_DOWN: (0, 1),
    pg.K_LEFT: (-1, 0),
    pg.K_RIGHT: (1, 0),
    pg.K_w: (0, -1),
    pg.K_s: (0, 1),
    pg.K_a: (-1, 0),
    pg.K_d: (1, 0),
    pg.K_q: (-1, -1),
    pg.K_e: (1, -1),
    pg.K_z: (-1, 1),
    pg.K_c: (1, 1),
}

ACTION_KEYS: dict[int, type[actions.ActorAction]] = {
    pg.K_RETURN: actions.Interact,
    pg.K_PERIOD: actions.WaitAction,
    pg.K_SPACE: actions.WaitAction,
    pg.K_l: actions.ToggleTorch,
    pg.K_k: actions.Search,
}

CONTINUOUS_ACTION_KEYS: dict[int, type[actions.ActorAction]] = {
    pg.K_x: actions.ExploreAction,
    pg.K_COMMA: actions.Rest,
}

ACTION_SHIFT_KEYS: dict[
    int,
    type[actions.ActorAction] | Callable[[ecs.Entity], actions.Action | None],
] = {
    pg.K_x: actions.MagicMap,
    pg.K_f: actions.AttackAction.nearest,
}

STATE_KEYS: dict[int, type[game_interface.State]] = {
    pg.K_ESCAPE: states.GameMenuState,
    pg.K_m: states.MapState,
    pg.K_i: states.InventoryState,
}
