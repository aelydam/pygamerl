import pathlib

import numpy as np
import pygame as pg

GAME_TITLE = "Pygame Roguelike"

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
WAIT_KEYS = (pg.K_SPACE, pg.K_PERIOD)

MAP_SHAPE = (64, 48)
N_ENEMIES = 10
ENEMY_RADIUS = 12
RESPAWN_RATE = 60
MIN_ROOM_SIZE = 4
MAX_ROOM_SIZE = 12
NUM_ROOMS = 10
CORRIDOR_PROB = 0.15

FOV_RADIUS = 6
MAX_LIGHT_RADIUS = 5

FONTNAME = "Ac437_IBM_BIOS"
FONTSIZE = 8

BACKGROUND_COLOR = "#000000"
UNEXPLORED_TINT = "#606060"

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
    "grass": (False, False, (109, 170, 44), (8, 7), "Objects/Floor"),
    "tree": (True, True, (109, 170, 44), (3, 3), "Objects/Tree0"),
    "floor": (False, False, (40, 40, 40), (1, 2 * 3 + 1), "Objects/Floor"),
    "cavefloor": (False, False, (40, 40, 40), (1, 19 + 3), "Objects/Floor"),
    "wall": (True, True, (90, 88, 117), (1, 10), "Objects/Wall"),
    "wall12": (True, True, (90, 88, 117), (0, 9), "Objects/Wall"),
    "wall6": (True, True, (90, 88, 117), (1, 9), "Objects/Wall"),
    "wall10": (True, True, (90, 88, 117), (2, 9), "Objects/Wall"),
    "wall14": (True, True, (90, 88, 117), (4, 9), "Objects/Wall"),
    "wall8": (True, True, (90, 88, 117), (0, 10), "Objects/Wall"),
    "wall9": (True, True, (90, 88, 117), (0, 10), "Objects/Wall"),
    "wall1": (True, True, (90, 88, 117), (1, 10), "Objects/Wall"),
    "wall13": (True, True, (90, 88, 117), (3, 10), "Objects/Wall"),
    "wall15": (True, True, (90, 88, 117), (4, 10), "Objects/Wall"),
    "wall11": (True, True, (90, 88, 117), (5, 10), "Objects/Wall"),
    "wall4": (True, True, (90, 88, 117), (0, 11), "Objects/Wall"),
    "wall5": (True, True, (90, 88, 117), (0, 11), "Objects/Wall"),
    "wall2": (True, True, (90, 88, 117), (2, 11), "Objects/Wall"),
    "wall3": (True, True, (90, 88, 117), (2, 11), "Objects/Wall"),
    "wall7": (True, True, (90, 88, 117), (4, 11), "Objects/Wall"),
    "cavewall": (True, True, (90, 88, 117), (1, 19), "Objects/Wall"),
    "cavewall12": (True, True, (90, 88, 117), (0, 18), "Objects/Wall"),
    "cavewall6": (True, True, (90, 88, 117), (1, 18), "Objects/Wall"),
    "cavewall10": (True, True, (90, 88, 117), (2, 18), "Objects/Wall"),
    "cavewall14": (True, True, (90, 88, 117), (4, 18), "Objects/Wall"),
    "cavewall8": (True, True, (90, 88, 117), (0, 19), "Objects/Wall"),
    "cavewall9": (True, True, (90, 88, 117), (0, 19), "Objects/Wall"),
    "cavewall1": (True, True, (90, 88, 117), (1, 19), "Objects/Wall"),
    "cavewall13": (True, True, (90, 88, 117), (3, 19), "Objects/Wall"),
    "cavewall15": (True, True, (90, 88, 117), (4, 19), "Objects/Wall"),
    "cavewall11": (True, True, (90, 88, 117), (5, 19), "Objects/Wall"),
    "cavewall4": (True, True, (90, 88, 117), (0, 20), "Objects/Wall"),
    "cavewall5": (True, True, (90, 88, 117), (0, 20), "Objects/Wall"),
    "cavewall2": (True, True, (90, 88, 117), (2, 20), "Objects/Wall"),
    "cavewall3": (True, True, (90, 88, 117), (2, 20), "Objects/Wall"),
    "cavewall7": (True, True, (90, 88, 117), (4, 20), "Objects/Wall"),
}
# Dawnlike wall bitmask:
#  12 |  6  | 10  |    | 14 |
# 8/9 | 0/1 |     | 13 | 15 | 11
# 4/5 |     | 2/3 |    |  7 |

TILE_ARRAY = np.asarray(
    [np.array(tile, dtype=TILE_DTYPE) for tile in TILES.values()], dtype=TILE_DTYPE
)
TILE_VOID = list(TILES.keys()).index("void")
TILE_FLOOR = list(TILES.keys()).index("floor")
TILE_WALL = list(TILES.keys()).index("wall")
TILE_NAMES = list(TILES.keys())
TILE_ID = {s: i for i, s in enumerate(TILES.keys())}
