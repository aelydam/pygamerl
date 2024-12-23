import pathlib

import numpy as np
import pygame as pg

GAME_ID = "pygamerl"
GAME_TITLE = "Pygame Roguelike"

GAME_PATH = pathlib.Path(__file__).parent
SAVE_PATH = pathlib.Path(pg.system.get_pref_path(GAME_ID, GAME_ID))

SCREEN_SHAPE = (640, 480)
FPS = 60

TILE_SIZE = 16
ENTITY_YOFFSET = TILE_SIZE // 4

MAP_SHAPE = (64, 48)
N_ENEMIES = 10
ENEMY_RADIUS = 12
BASE_RESPAWN_RATE = 80
DEPTH_RESPAWN_RATE = 2
MIN_ROOM_SIZE = 4
MAX_ROOM_SIZE = 12
NUM_ROOMS = 10
CORRIDOR_PROB = 0.15

DEFAULT_FOV_RADIUS = 24
MAX_LIGHT_RADIUS = 5
BASE_SPEED = 5
MAX_HUNGER = 20
XP_LEVEL2 = 30
XP_FACTOR = 0.85

FONTNAME = "Px437_IBM_EGA_8x8"
FONTSIZE = 8

BACKGROUND_COLOR = "#000000"
UNEXPLORED_TINT = "#606060"

HPBAR_BG_COLOR = "#757161"
HPBAR_GOOD_COLOR = "#6DAA2C"
HPBAR_BAD_COLOR = "#D34549"
HPBAR_TEXT_COLOR = "#000000"

MINIMAP_PLAYER_COLOR = "#597DCF"
MINIMAP_INTERACT_COLOR = "#DBD75D"
MINIMAP_CREATURE_COLOR = "#D34549"

LOG_TEXT_COLOR = "#FFFFFF"
POPUP_TEXT_COLOR = "#FFFFFF"
TOOLTIP_TEXT_COLOR = "#FFFFFF"
GAMEOVER_TEXT_COLOR = "#FFFFFF"
TITLE_TEXT_COLOR = "#FFFFFF"

CURSOR_DEFAULT_COLOR = "#FFFFFF"
CURSOR_IMPOSSIBLE_COLOR = "#D34549"

TILE_DTYPE = np.dtype(
    [
        ("obstacle", bool),
        ("opaque", bool),
        ("color", "3B"),
        ("sprite", "2B"),
        ("sheet", "U24"),
        ("bgtile", "B"),
    ]
)
