import glob
import os

import numpy as np
import tcod.ecs as ecs
import yaml  # type: ignore
from numpy.typing import NDArray

import comp
import consts

tiles: NDArray[np.void]
tile_names: list[str]
tile_id: dict[str, int]
opaque: NDArray[np.bool_]
obstacle: NDArray[np.bool_]
transparency: NDArray[np.bool_]
walkable: NDArray[np.bool_]


def load_tiles() -> None:
    path = consts.GAME_PATH / "data" / "tiles.yml"
    with open(path, "r") as file:
        data = yaml.safe_load(file)
    tile_list = []
    names = []
    for k, v in data.items():
        obstacle_ = v["obstacle"] if "obstacle" in v else True
        opaque_ = v["opaque"] if "opaque" in v else True
        color = tuple(v["color"]) if "color" in v else (0, 0, 0)
        sprite = v["tile"] if "tile" in v else (0, 0)
        sheet = v["sheet"] if "sheet" in v else ""
        tile = np.asarray((obstacle_, opaque_, color, sprite, sheet), consts.TILE_DTYPE)
        tile_list.append(tile)
        names.append(k)
        if "sheet" != "" and "bitmask" in v:
            for bm, sprite in v["bitmask"].items():
                names.append(f"{k}{bm}")
                tile = np.asarray(
                    (obstacle_, opaque_, color, sprite, sheet), consts.TILE_DTYPE
                )
                tile_list.append(tile)
    global tiles, tile_names, tile_id, opaque, obstacle, transparency, walkable
    tiles = np.asarray(tile_list, consts.TILE_DTYPE)
    tile_names = names
    tile_id = {s: i for i, s in enumerate(names)}
    opaque = tiles["opaque"]
    obstacle = tiles["obstacle"]
    transparency = ~opaque
    walkable = ~obstacle


def load_entity(
    entity: ecs.Entity, name: str, data: dict[str, int | str | float | list | dict]
):
    entity.clear()
    if "Name" not in data:
        entity.components[comp.Name] = name
    for k, v in data.items():
        if k == "tags":
            assert not isinstance(v, dict)
            if isinstance(v, list):
                entity.tags |= set(v)
            else:
                entity.tags |= {v}
            continue
        assert hasattr(comp, k)
        if k == "HP":
            comp_key = comp.MaxHP
        else:
            comp_key = getattr(comp, k)
        if isinstance(comp_key, tuple):
            comp_class = comp_key[1]
        else:
            assert callable(comp_key)
            comp_class = comp_key
        if isinstance(v, dict):
            comp_obj = comp_class(**v)
        elif isinstance(v, list):
            comp_obj = comp_class(*v)
        else:
            comp_obj = comp_class(v)
        entity.components[comp_key] = comp_obj


def load_data(reg: ecs.Registry, kind: str):
    dir_name = consts.GAME_PATH / "data" / kind
    if os.path.isdir(dir_name):
        files = glob.glob(str(dir_name / "*.yml"))
    else:
        files = [f"{dir_name}.yml"]
    for fn in files:
        with open(fn, "r") as file:
            data: dict = yaml.safe_load(file)
        for k, v in data.items():
            entity = reg[(kind, k)]
            load_entity(entity, k, v)
            entity.tags |= {kind}
            if kind == "creatures":
                entity.tags |= {comp.Obstacle}
