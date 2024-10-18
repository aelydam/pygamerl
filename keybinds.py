from __future__ import annotations

import pygame as pg

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
}

CONTINUOUS_ACTION_KEYS: dict[int, type[actions.ActorAction]] = {
    pg.K_x: actions.ExploreAction,
}

ACTION_SHIFT_KEYS: dict[int, type[actions.ActorAction]] = {
    pg.K_x: actions.MagicMap,
}

STATE_KEYS: dict[int, type[game_interface.State]] = {
    pg.K_ESCAPE: states.GameMenuState,
    pg.K_m: states.MapState,
}
