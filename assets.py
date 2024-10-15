from functools import lru_cache

import pygame as pg

import consts


@lru_cache
def image(name: str) -> pg.Surface:
    path = consts.GAME_PATH / "images" / f"{name}.png"
    return pg.image.load(path).convert_alpha()


@lru_cache
def tile(name: str, pos: tuple[int, int]) -> pg.Surface:
    sheet = image(name)
    return sheet.subsurface(
        (
            pos[0] * consts.TILE_SIZE,
            pos[1] * consts.TILE_SIZE,
            consts.TILE_SIZE,
            consts.TILE_SIZE,
        )
    )


@lru_cache
def font(name: str = consts.FONTNAME, size: int = consts.FONTSIZE) -> pg.Font:
    path = consts.GAME_PATH / "fonts" / f"{name}.ttf"
    return pg.Font(path, size)
