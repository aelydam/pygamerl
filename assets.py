import os
from functools import lru_cache

import pygame as pg

import consts


@lru_cache
def image(name: str) -> pg.Surface:
    path = consts.GAME_PATH / "images" / f"{name}.png"
    return pg.image.load(path).convert_alpha()


def image_exists(name: str) -> bool:
    path = consts.GAME_PATH / "images" / f"{name}.png"
    return os.path.isfile(path)


@lru_cache
def tile(name: str, pos: tuple[int, int]) -> pg.Surface:
    sheet = image(name)
    return sheet.subsurface(
        (
            int(pos[0]) * consts.TILE_SIZE,
            int(pos[1]) * consts.TILE_SIZE,
            consts.TILE_SIZE,
            consts.TILE_SIZE,
        )
    )


@lru_cache
def frames(name: str, pos: tuple[int, int], max_count: int = 2) -> list[pg.Surface]:
    res = [tile(name, pos)]
    if name[-1] == "0":
        name = name[:-1]
        res += [
            tile(name + str(i), pos)
            for i in range(1, max_count)
            if image_exists(name + str(i))
        ]
    return res


@lru_cache
def font(name: str = consts.FONTNAME, size: int = consts.FONTSIZE) -> pg.Font:
    path = consts.GAME_PATH / "fonts" / f"{name}.ttf"
    return pg.Font(path, size)


@lru_cache
def sfx(name: str) -> pg.mixer.Sound:
    path = consts.GAME_PATH / "sfx" / f"{name}.ogg"
    return pg.mixer.Sound(path)
