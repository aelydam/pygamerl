import pygame as pg


SCREEN_SHAPE = (1280, 720)
MAP_SHAPE = (60, 60)
TILE_SIZE = 32
FPS = 60
N_ENEMIES = 5
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
    pg.K_c: (1, 1)
}
WAIT_KEYS = (pg.K_RETURN, pg.K_SPACE, pg.K_PERIOD)
