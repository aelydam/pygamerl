import glob
import os
from enum import Enum

import numpy as np
import tcod.ecs as ecs
import yaml  # type: ignore
from numpy.typing import NDArray

import actions
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
        if k == "Inventory":
            if isinstance(v, list):
                entity.components[comp.TempInventory] = {i: "1" for i in v}
            elif isinstance(v, dict):
                entity.components[comp.TempInventory] = {
                    i: str(q) for i, q in v.items()
                }
            elif isinstance(v, str):
                entity.components[comp.TempInventory] = {v: "1"}
            continue
        if k == "Equipment":
            if isinstance(v, dict):
                entity.components[comp.TempEquipment] = list(v.items())
            elif isinstance(v, list):
                entity.components[comp.TempEquipment] = v
            elif isinstance(v, str):
                entity.components[comp.TempEquipment] = [v]
            continue
        if k == "Effects":
            if isinstance(v, dict):
                effects = {getattr(actions, kk): vv for kk, vv in v.items()}
            elif isinstance(v, list):
                effects = {getattr(actions, kk): {} for kk in v}
            elif isinstance(v, str):
                effects = {getattr(actions, v): {}}
            else:
                continue
            entity.components[comp.Effects] = effects
            continue
        if k == "Unidentified":
            if not isinstance(v, str):
                continue
            kind = pick_unknown(entity.registry, v)
            if kind is not None:
                entity.relation_tag[ecs.IsA] = kind
                entity.components[comp.UnidentifiedName] = kind.components[comp.Name]
            continue
        if k == "HP":
            comp_key = comp.HPDice
        else:
            comp_key = getattr(comp, k)
        assert hasattr(comp, k)
        if isinstance(comp_key, tuple):
            comp_class = comp_key[1]
        else:
            assert callable(comp_key)
            comp_class = comp_key
        if issubclass(comp_class, Enum):
            entity.components[comp_key] = comp_class.__members__[v]  # type: ignore
            continue
        elif isinstance(v, dict):
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
        category = os.path.splitext(os.path.basename(fn))[0]
        with open(fn, "r") as file:
            data: dict = yaml.safe_load(file)
        for k, v in data.items():
            entity = reg[(kind, k)]
            load_entity(entity, k, v)
            entity.tags |= {kind, category}
            if kind == "creatures":
                entity.tags |= {comp.Obstacle}
                if comp.Speed not in entity.components:
                    entity.components[comp.Speed] = consts.BASE_SPEED
                if comp.FOVRadius not in entity.components:
                    entity.components[comp.FOVRadius] = consts.DEFAULT_FOV_RADIUS


def load_unknowns(reg: ecs.Registry):
    fn = consts.GAME_PATH / "data" / "unknowns.yml"
    with open(fn, "r") as file:
        data: dict = yaml.safe_load(file)
    for kind, items in data.items():
        g_key = f"unknown_{kind}"
        for k, v in items.items():
            entity = reg[(g_key, k)]
            load_entity(entity, k, v)
            entity.tags |= {g_key}


def pick_unknown(reg: ecs.Registry, kind: str) -> ecs.Entity | None:
    g_key = f"unknown_{kind}"
    query = reg.Q.all_of(tags=[g_key]).none_of(tags=["unknown_used"])
    kinds = list(query.get_entities())
    seed = reg[None].components[np.random.RandomState]
    i = seed.randint(0, len(kinds))
    picked = kinds[i]
    picked.tags |= {"unknown_used"}
    return picked
