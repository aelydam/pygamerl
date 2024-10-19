import numpy as np
import yaml  # type: ignore
from numpy.typing import NDArray

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
