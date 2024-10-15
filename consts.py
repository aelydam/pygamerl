import pathlib

import numpy as np
import pygame as pg

GAME_PATH = pathlib.Path(__file__).parent

SCREEN_SHAPE = (640, 480)
FPS = 60

TILE_SIZE = 16
ENTITY_YOFFSET = TILE_SIZE // 4

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
WAIT_KEYS = (pg.K_RETURN, pg.K_SPACE, pg.K_PERIOD)

MAP_SHAPE = (60, 60)
N_ENEMIES = 10
ENEMY_RADIUS = 12
FOV_RADIUS = 6

FONTNAME = "Ac437_IBM_BIOS"
FONTSIZE = 8

BACKGROUND_COLOR = "#000000"
UNEXPLORED_TINT = "#808080"

HPBAR_BG_COLOR = "#808080"
HPBAR_GOOD_COLOR = "#00FF00"
HPBAR_BAD_COLOR = "#FF0000"
HPBAR_TEXT_COLOR = "#000000"

LOG_TEXT_COLOR = "#FFFFFF"
POPUP_TEXT_COLOR = "#FFFFFF"
TOOLTIP_TEXT_COLOR = "#FFFFFF"
GAMEOVER_TEXT_COLOR = "#FFFFFF"

CURSOR_DEFAULT_COLOR = "#FFFFFF"
CURSOR_IMPOSSIBLE_COLOR = "#FF0000"

TILE_DTYPE = np.dtype(
    [
        ("obstacle", bool),
        ("opaque", bool),
        ("color", "3B"),
        ("sprite", "2B"),
        ("sheet", "U24"),
    ]
)
TILES: dict[str, tuple[bool, bool, tuple[int, int, int], tuple[int, int], str]] = {
    "void": (True, False, (0, 0, 0), (0, 0), ""),
    "floor": (False, False, (40, 40, 40), (1, 7), "Objects/Floor"),
    "wall": (True, True, (90, 88, 117), (1, 3), "Objects/Wall"),
}
TILE_ARRAY = np.asarray(
    [np.array(tile, dtype=TILE_DTYPE) for tile in TILES.values()], dtype=TILE_DTYPE
)
TILE_VOID = list(TILES.keys()).index("void")
TILE_FLOOR = list(TILES.keys()).index("floor")
TILE_WALL = list(TILES.keys()).index("wall")
