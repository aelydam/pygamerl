from __future__ import annotations

import random

import numpy as np
import scipy.spatial  # type: ignore
import tcod
import tcod.ecs as ecs
from numpy.typing import NDArray

import actions
import comp
import consts
import db
import dice
import entities
import funcs
import items
import maps


def get_walls(grid: NDArray[np.bool_], condition: NDArray[np.bool_] | None = None):
    # Find tiles that are void but are neighbors to a floor
    walls = (funcs.moore(grid) > 0) & (~grid)
    if condition is not None:
        walls &= condition
    return walls


def get_spawn_table(
    map_entity: ecs.Entity, tags: list[str]
) -> tuple[list[ecs.Entity], list[float]]:
    depth = map_entity.components[comp.Depth]
    kinds = list(
        map_entity.registry.Q.all_of(components=[comp.SpawnWeight], tags=tags)
        .none_of(
            components=[comp.Position, comp.Initiative],
            relations=[(comp.Inventory, ...), (comp.Map, ...)],
        )
        .get_entities()
    )
    kinds = [
        e
        for e in kinds
        if e.components.get(comp.MaxDepth, depth + 1) >= depth
        and e.components.get(comp.MinDepth, -1) <= depth
    ]
    weights = [
        e.components[comp.SpawnWeight]
        * e.components.get(comp.SpawnWeightDecay, 0.9)
        ** ((e.components.get(comp.NativeDepth, depth) - depth) ** 2)
        for e in kinds
    ]
    total = np.sum(weights)
    probs = [w / total for w in weights]
    return kinds, probs


def pick_creature_kind(map_entity: ecs.Entity) -> ecs.Entity:
    kinds, probs = get_spawn_table(map_entity, ["creatures"])
    seed = map_entity.components[np.random.RandomState]
    i = seed.choice(list(range(len(kinds))), p=probs)
    return kinds[i]


def pick_item_kind(map_entity: ecs.Entity) -> ecs.Entity:
    kinds, probs = get_spawn_table(map_entity, ["items"])
    seed = map_entity.components[np.random.RandomState]
    i = seed.choice(list(range(len(kinds))), p=probs)
    return kinds[i]


def pick_item_count(map_entity: ecs.Entity, item: ecs.Entity) -> int:
    max_stack = item.components.get(comp.MaxStack, 1)
    if max_stack > 1 and comp.SpawnCount in item.components:
        seed = map_entity.components[np.random.RandomState]
        dice_expr = item.components[comp.SpawnCount]
        depth = map_entity.components[comp.Depth]
        count = int(dice.dice_roll(dice_expr, seed, {"depth": depth}))
        return count
    return 1


def spawn_enemies(map_entity: ecs.Entity, radius: int, max_count: int = 0):
    grid = map_entity.components[comp.Tiles]
    xgrid, ygrid = np.indices(grid.shape)
    walkable = db.walkable[grid]
    counter = 0
    # Initialize available array from walkable points
    available = walkable.copy()
    # Remove all positiions with entities
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        relations=[(comp.Map, map_entity)],
    ).get_entities()
    for e in query:
        x, y = e.components[comp.Position].xy
        available[x, y] = False

    # Consider radius of creatures and upstairs already on the map
    query = (
        map_entity.registry.Q.all_of(
            components=[comp.Position, comp.HP],
            relations=[(comp.Map, map_entity)],
        ).get_entities()
        | map_entity.registry.Q.all_of(
            components=[comp.Position],
            tags=[comp.Upstairs],
            relations=[(comp.Map, map_entity)],
        ).get_entities()
    )
    for e in query:
        x, y = e.components[comp.Position].xy
        dist2 = (xgrid - x) ** 2 + (ygrid - y) ** 2
        available[dist2 <= radius**2] = False
    # While there are available spots and still below max_count
    while (counter < max_count or max_count < 1) and np.sum(available) > 0:
        # Pick a random available point
        all_x, all_y = np.where(available)
        i = random.randint(0, len(all_x) - 1)
        x, y = all_x[i], all_y[i]
        # Spawn enemy and increase counter
        kind = pick_creature_kind(map_entity)
        entities.spawn_creature(map_entity, (x, y), kind)
        counter += 1
        # Make all points within radius unavailable
        dist2 = (xgrid - x) ** 2 + (ygrid - y) ** 2
        available[dist2 <= radius**2] = False


def spawn_items(
    map_entity: ecs.Entity,
    radius: int = consts.MAX_ROOM_SIZE,
    max_count: int = 0,
    condition: NDArray[np.bool_] | None = None,
):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    xgrid, ygrid = np.indices(grid.shape)
    walkable = db.walkable[grid]
    counter = 0
    # Initialize available array from walkable points
    available = walkable.copy()
    # Remove all positiions with entities
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        relations=[(comp.Map, map_entity)],
    ).get_entities()
    for e in query:
        x, y = e.components[comp.Position].xy
        available[x, y] = False
    # While there are available spots and still below max_count
    while (counter < max_count or max_count < 1) and np.sum(available) > 0:
        if np.sum(available) < 1:
            break
        all_x, all_y = np.where(available)
        i = random.randint(0, len(all_x) - 1)
        x, y = all_x[i], all_y[i]
        #
        kind = pick_item_kind(map_entity)
        count = pick_item_count(map_entity, kind)
        if count < 1:
            continue
        items.spawn_item(map_entity, (x, y), kind, count)
        dist2 = (xgrid - x) ** 2 + (ygrid - y) ** 2
        available[dist2 <= radius**2] = False
        counter += 1


def respawn(map_entity: ecs.Entity):
    seed = map_entity.components[np.random.RandomState]
    depth = map_entity.components[comp.Depth]
    rate = consts.BASE_RESPAWN_RATE - consts.DEPTH_RESPAWN_RATE * depth
    roll = seed.randint(1, rate + 1)
    if roll <= 1:
        spawn_enemies(map_entity, consts.ENEMY_RADIUS, 1)


def rect_room(
    shape: tuple[int, int], x: int, y: int, w: int, h: int
) -> NDArray[np.bool_]:
    grid_x, grid_y = np.indices(shape)
    return (grid_x >= x) & (grid_y >= y) & (grid_x < x + w) & (grid_y < y + h)


def random_room_size(
    seed: np.random.RandomState,
    min_size: int = consts.MIN_ROOM_SIZE,
    max_size: int = consts.MAX_ROOM_SIZE,
) -> tuple[int, int]:
    w = (seed.randint(min_size, max_size) + seed.randint(min_size, max_size)) // 2
    med_size = (min_size + max_size) / 2
    if w == med_size:
        h = (seed.randint(min_size, max_size) + seed.randint(min_size, max_size)) // 2
    elif w < med_size:
        h = (seed.randint(w, max_size) + seed.randint(w, max_size)) // 2
    else:
        h = (seed.randint(min_size, w) + seed.randint(min_size, w)) // 2
    return w, h


def random_rect_room(
    occupied: NDArray[np.bool_],
    seed: np.random.RandomState,
    min_size: int = consts.MIN_ROOM_SIZE,
    max_size: int = consts.MAX_ROOM_SIZE,
    max_iter: int = 20,
) -> NDArray[np.bool_] | None:
    shape = occupied.shape
    for _ in range(max_iter):
        w, h = random_room_size(seed, min_size, max_size)
        x = seed.randint(1, shape[0] - 2 - w)
        y = seed.randint(1, shape[1] - 2 - h)
        room = rect_room(shape, x, y, w, h)
        exterior = funcs.moore(room) > 0
        if np.sum(exterior & occupied) < 1:
            return room
    return None


def area_centroid(area: NDArray[np.bool_]) -> tuple[int, int]:
    res = tuple(np.median(np.argwhere(area), axis=0).astype(np.int8))
    return (int(res[0]), int(res[1]))


def corridor_cost_matrix(
    walkable: NDArray[np.bool_],
    seed: np.random.RandomState | None = None,
    noise: int = 0,
) -> NDArray[np.int32]:
    cost = 6 - walkable
    wmoore = funcs.moore(walkable)
    bm = funcs.bitmask(1 * walkable)
    corridor = walkable & (wmoore == 2) & np.isin(bm, (6, 9))
    rooms = walkable & (funcs.moore(wmoore >= 8) > 0) & ~corridor
    wall = ~walkable & (funcs.moore(rooms) > 0)
    cost[wall] += 15
    cost[~walkable & (wmoore == 1)] += 10
    cost[rooms & (wmoore == 3)] += 10
    cost[walkable & ~rooms & (funcs.moore(rooms) > 0) & ~corridor] += 10
    # cost[walkable & (wmoore == 2)] -= 3
    if noise == 0:
        cost[~walkable & (funcs.moore(wall) > 0)] -= 2
    cost[walkable & corridor] = 1
    cost[walkable & (cost < 1)] = 1
    if seed is not None and noise > 0:
        noise_grid = seed.randint(-noise, noise + 1, walkable.shape)
        cost += noise_grid * ~walkable
    cost[:, 0] = 0
    cost[0, :] = 0
    cost[:, -1] = 0
    cost[-1:,] = 0
    return cost


def corridor(
    walkable: NDArray[np.bool_],
    area1: NDArray[np.bool_],
    area2: NDArray[np.bool_],
    seed: np.random.RandomState | None = None,
    noise: int = 0,
    max_size: int = 0,
) -> NDArray[np.bool_]:
    grid = np.full(walkable.shape, False)
    cost = corridor_cost_matrix(walkable | area1 | area2, seed, noise)
    cost[area1] = 1
    cost[area2] = 1
    if np.sum(area1) >= np.sum(area2):
        origin = area_centroid(area2)
        target = area1 & (funcs.moore(area1) >= 8)
        if np.sum(target) < 1:
            target = area1
    else:
        origin = area_centroid(area1)
        target = area2 & (funcs.moore(area2) >= 8)
        if np.sum(target) < 1:
            target = area2
    dijkstra = tcod.path.maxarray(grid.shape, dtype=np.int32)
    dijkstra[target] = 0
    tcod.path.dijkstra2d(dijkstra, cost, 1, 0, out=dijkstra)
    path = tcod.path.hillclimb2d(dijkstra, origin, True, False)
    for point in path:
        grid[point[0], point[1]] = True
    if max_size > 0 and np.sum(grid & ~walkable & ~area1 & ~area2) > max_size:
        return np.full(grid.shape, False)
    return grid & ~walkable & ~area1 & ~area2


def delaunay_corridors(
    walkable: NDArray[np.bool_],
    areas: list[NDArray[np.bool_]],
    seed: np.random.RandomState,
    noise: int = 0,
    nomst_prob: float = 0.10,
    max_size: int = 0,
):
    points = [area_centroid(area) for area in areas]
    distmat = scipy.spatial.distance.cdist(points, points, metric="minkowski")
    mst = scipy.sparse.csgraph.minimum_spanning_tree(distmat).toarray().astype(int)
    grid = walkable.copy()
    connected = np.full(mst.shape, False)
    for i, j in zip(*np.where(mst != 0)):
        path = corridor(grid, areas[i], areas[j], seed, noise, max_size)
        if max_size < 1 or np.sum(path & ~grid) <= max_size:
            grid |= path
            connected[i, j] = True
            connected[j, i] = True
    if nomst_prob > 0:
        delaunay = scipy.spatial.Delaunay(points).simplices.tolist()
        for a, b, c in delaunay:
            if not connected[a, b] and seed.random() <= nomst_prob:
                path = corridor(grid, areas[a], areas[b], seed, noise, max_size)
                if max_size < 1 or np.sum(path & ~grid) <= max_size:
                    grid |= path
                    connected[a, b] = True
                    connected[b, a] = True
            if not connected[a, c] and seed.random() <= nomst_prob:
                path = corridor(grid, areas[a], areas[c], seed, noise, max_size)
                if max_size < 1 or np.sum(path & ~grid) <= max_size:
                    grid |= path
                    connected[a, c] = True
                    connected[c, a] = True
            if not connected[b, c] and seed.random() <= nomst_prob:
                path = corridor(grid, areas[b], areas[c], seed, noise, max_size)
                if max_size < 1 or np.sum(path & ~grid) <= max_size:
                    grid |= path
                    connected[b, c] = True
                    connected[c, b] = True
    return grid & ~walkable


def disjoint_areas(grid: NDArray[np.bool_]) -> list[NDArray[np.bool_]]:
    areas, n_areas = scipy.ndimage.label(grid)
    return [
        grid & (areas == i) for i in range(n_areas + 1) if np.sum(grid[areas == i]) > 0
    ]


def random_rooms(
    condition: NDArray[np.bool_],
    seed: np.random.RandomState,
    max_rooms: int = consts.NUM_ROOMS,
    max_iter: int = 100,
) -> NDArray:
    room_grid: NDArray[np.bool_] = np.full(condition.shape, False)
    n_rooms = 0
    for _ in range(max_iter):
        if n_rooms > max_rooms:
            break
        room = random_rect_room(room_grid | ~condition, seed, max_iter=4)
        if room is None:
            continue
        room_grid |= room
        n_rooms += 1
    return room_grid


def random_walk(condition: NDArray[np.bool_], walkers: int = 5, steps: int = 500):
    # Random walk algorithm
    # Repeat for each walker
    grid = np.full(condition.shape, False)
    for walkers in range(walkers):
        x, y = (consts.MAP_SHAPE[0] // 2, consts.MAP_SHAPE[1] // 2)
        grid[x, y] = True
        # Walk each step
        for step in range(steps):
            # Choose a random direction
            dx, dy = random.choice([(0, 1), (1, 0), (0, -1), (-1, 0)])
            # If next step is within map bounds
            if (
                maps.is_in_bounds(grid, (x + dx * 2, y + dy * 2))
                and condition[x + dx, y + dy]
            ):
                # Walk
                x += dx
                y += dy
                # Set as floor
                grid[x, y] = True
            else:
                break
    return grid


def cellular_automata(
    condition: NDArray[np.bool_],
    seed: np.random.RandomState,
    density: float = 0.5,
    iterations: int = 3,
    min_moore: int = 8,
) -> NDArray[np.bool_]:
    grid = condition & (funcs.moore(condition) >= min_moore)
    grid &= seed.random(condition.shape) <= density
    for _ in range(iterations):
        neighbors = funcs.moore(grid)
        grid[neighbors <= 3] = False
        grid[neighbors > 4] = True
        grid[0, :] = False
        grid[:, 0] = False
        grid[-1, :] = False
        grid[:, -1] = False
    return grid


def prune(area: NDArray[np.bool_], min_area: int = 16) -> NDArray[np.bool_]:
    areas, n_areas = scipy.ndimage.label(area)
    grid = area.copy()
    for i in range(n_areas + 1):
        if np.sum(areas == i) < min_area:
            grid[areas == i] = False
    return grid


def spawn_prop(
    map_entity: ecs.Entity, kind: str, position: tuple[int, int]
) -> ecs.Entity:
    depth = map_entity.components[comp.Depth]
    template = map_entity.registry[("props", kind)]
    entity = template.instantiate()
    entity.components[comp.Position] = comp.Position(position, depth)
    return entity


def add_doors(map_entity: ecs.Entity, condition: NDArray[np.bool_] | None = None):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    walkable = db.walkable[grid]
    bm = funcs.bitmask(walkable)
    wmoore = funcs.moore(walkable)
    rooms = walkable & (funcs.moore(wmoore >= 8) > 0)
    doors = walkable & np.isin(bm, (6, 9)) & (funcs.moore(rooms) > 0)
    if condition is not None:
        doors &= condition
    all_x, all_y = np.where(doors)
    for x, y in zip(all_x, all_y):
        door = spawn_prop(map_entity, "Door", (x, y))
        door.tags |= {comp.Opaque, comp.Obstacle}


def add_torches(
    map_entity: ecs.Entity,
    max_count: int = 30,
    radius: int = 8,
    condition: NDArray[np.bool_] | None = None,
):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    walkable = db.walkable[grid]
    corridor = np.isin(funcs.bitmask(walkable), (6, 9))
    wall_bm = funcs.bitmask(~walkable)
    wmoore = funcs.moore(walkable)
    available = (
        (wmoore == 3)
        & ~walkable
        & (funcs.moore(walkable, diagonals=False) == 1)
        & np.isin(wall_bm, (7, 11, 13, 14))
        & (funcs.moore(corridor) == 0)
    )
    if condition is not None:
        available &= condition
    #
    grid_x, grid_y = np.indices(grid.shape)
    radius2 = radius**2
    for _ in range(max_count):
        if np.sum(available) < 1:
            break
        all_x, all_y = np.where(available)
        i = seed.randint(0, len(all_x))
        x, y = all_x[i], all_y[i]
        torch = spawn_prop(map_entity, "Torch", (x, y))
        dist2 = (grid_x - x) ** 2 + (grid_y - y) ** 2
        available[dist2 < radius2] = False
    #


def add_downstairs(
    map_entity: ecs.Entity,
    condition: NDArray[np.bool_] | None = None,
    max_count: int = 2,
):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    walkable = db.walkable[grid]
    # Create dijkstra map to upstairs
    cost = maps.cost_matrix(map_entity)
    dijkstra = tcod.path.maxarray(grid.shape, dtype=np.int32)
    query = (
        map_entity.registry.Q.all_of(
            components=[comp.Position],
            tags=[comp.Upstairs],
            relations=[(comp.Map, map_entity)],
        ).get_entities()
        | map_entity.registry.Q.all_of(
            components=[comp.Position],
            tags=[comp.Chest],
            relations=[(comp.Map, map_entity)],
        ).get_entities()
    )
    for e in query:
        pos = e.components[comp.Position]
        dijkstra[pos.xy] = 0
    tcod.path.dijkstra2d(dijkstra, cost, 2, 3, out=dijkstra)

    cond = walkable & (funcs.moore(walkable) >= 8)
    if condition is not None:
        cond &= condition
    # Remove all positiions with entities
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        relations=[(comp.Map, map_entity)],
    ).get_entities()
    for e in query:
        x, y = e.components[comp.Position].xy
        cond[x, y] = False

    for _ in range(max_count):
        cutoff = (np.mean(dijkstra[cond]) + np.max(dijkstra[cond])) / 2
        if np.sum(cond & (dijkstra >= cutoff)) < 1:
            break
        all_x, all_y = np.where(cond & (dijkstra >= cutoff))
        i = seed.randint(0, len(all_x))
        xy = all_x[i], all_y[i]
        spawn_prop(map_entity, "Downstairs", xy)
        dijkstra[xy] = 0
        tcod.path.dijkstra2d(dijkstra, cost, 2, 3, out=dijkstra)


def add_traps(
    map_entity: ecs.Entity,
    radius: int = consts.MAX_ROOM_SIZE,
    max_count: int = 10,
    condition: NDArray[np.bool_] | None = None,
    bones_prob: float = 0.2,
):
    tiles = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    walkable = db.walkable[tiles]
    bm = funcs.bitmask(walkable)
    wmoore = funcs.moore(walkable)
    available = walkable & (wmoore == 2) & np.isin(bm, (6, 9))
    if condition is not None:
        available &= condition
    grid_x, grid_y = np.indices(tiles.shape)
    for _ in range(max_count):
        if np.sum(available) < 1:
            break
        all_x, all_y = np.where(available)
        i = seed.randint(0, len(all_x))
        x, y = all_x[i], all_y[i]
        dist2 = (grid_x - x) ** 2 + (grid_y - y) ** 2
        available[dist2 <= radius**2] = False
        trap = spawn_prop(map_entity, "Trap", (x, y))
        trap.tags |= {comp.Hidden}
        if seed.randint(0, 100) <= 100 * bones_prob:
            spawn_prop(map_entity, "Bones", (x, y))


def add_boulders(
    map_entity: ecs.Entity,
    radius: int = consts.MIN_ROOM_SIZE,
    max_count: int = 20,
    condition: NDArray[np.bool_] | None = None,
):
    tiles = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    walkable = db.walkable[tiles]
    bm = funcs.bitmask(walkable)
    wmoore = funcs.moore(walkable)
    available = walkable & (wmoore > 4) & ~np.isin(bm, (6, 9))
    if condition is not None:
        available &= condition
    grid_x, grid_y = np.indices(tiles.shape)
    for _ in range(max_count):
        if np.sum(available) < 1:
            break
        all_x, all_y = np.where(available)
        i = seed.randint(0, len(all_x))
        x, y = all_x[i], all_y[i]
        dist2 = (grid_x - x) ** 2 + (grid_y - y) ** 2
        available[dist2 <= radius**2] = False
        spawn_prop(map_entity, "Boulder", (x, y))


def add_upstairs_room(map_entity: ecs.Entity) -> NDArray[np.bool_]:
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    points = []
    if depth < 1:
        x = seed.randint(
            consts.MAX_ROOM_SIZE,
            consts.MAP_SHAPE[0] - consts.MAX_ROOM_SIZE,
        )
        y = seed.randint(
            consts.MAX_ROOM_SIZE,
            consts.MAP_SHAPE[1] - consts.MAX_ROOM_SIZE,
        )
        points = [(x, y)]
    else:
        prev_map = maps.get_map(map_entity.registry, depth - 1)
        query = map_entity.registry.Q.all_of(
            components=[comp.Position, comp.Interaction],
            tags=[comp.Downstairs],
            relations=[(comp.Map, prev_map)],
        )
        points = [e.components[comp.Position].xy for e in query]
    rooms = np.full(consts.MAP_SHAPE, False)
    for point in points:
        w, h = random_room_size(seed)
        x = min(max(1, point[0] - w // 2 + 1), consts.MAP_SHAPE[0] - w - 1)
        y = min(max(1, point[1] - h // 2 + 1), consts.MAP_SHAPE[1] - h - 1)
        rooms |= rect_room(consts.MAP_SHAPE, x, y, w, h)
        rooms[point] = True
        spawn_prop(map_entity, "Upstairs", point)
    rooms[0, :] = False
    rooms[:, 0] = False
    rooms[-1, :] = False
    rooms[:, -1] = False
    return rooms


def update_bitmasks(grid: NDArray[np.int8]) -> NDArray[np.int8]:
    bm = funcs.bitmask(grid)
    for tile_name, tile_id in db.tile_id.items():
        tile_name = db.tile_names[tile_id]
        if tile_name[-1] in "1234567890":
            continue
        for j in range(16):
            new_name = f"{tile_name}{j}"
            if new_name in db.tile_names:
                np.sum((grid == tile_id) & (bm == j))
                new_id = db.tile_id[new_name]
                grid[(grid == tile_id) & (bm == j)] = new_id
    return grid


def player_spawn(map_entity: ecs.Entity) -> comp.Position:
    # Spawn at upstairs
    query = map_entity.registry.Q.all_of(
        components=[comp.Position, comp.Interaction],
        tags=[comp.Upstairs],
        relations=[(comp.Map, map_entity)],
    )
    for e in query:
        return e.components[comp.Position]
    #
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    walkable = db.walkable[grid]
    # Fallback: spawn away from downstairs
    query = map_entity.registry.Q.all_of(
        components=[comp.Position, comp.Interaction],
        tags=[comp.Downstairs],
        relations=[(comp.Map, map_entity)],
    )
    dijkstra = tcod.path.maxarray(grid.shape, dtype=np.int32)
    max_int = dijkstra.max()
    for e in query:
        pos = e.components[comp.Position]
        dijkstra[pos.xy] = 0
    all_x, all_y = np.where(walkable)
    if np.sum(dijkstra == 0) > 0:
        cost = maps.cost_matrix(map_entity)
        tcod.path.dijkstra2d(dijkstra, cost, 2, 3, out=dijkstra)
        dj_mean = dijkstra[dijkstra < max_int].mean()
        dj_max = dijkstra[dijkstra < max_int].max()
        points = (dijkstra >= dj_mean) & (dijkstra <= dj_max)
        if np.sum(points) > 0:
            all_x, all_y = np.where(points)

    # Fallback: Pick any random point
    seed = map_entity.components[np.random.RandomState]
    i = seed.randint(0, len(all_x))
    return comp.Position((all_x[i], all_y[i]), depth)


def add_chests(map_entity: ecs.Entity, room_grid: NDArray[np.bool_]):
    grid = map_entity.components[comp.Tiles]
    seed = map_entity.components[np.random.RandomState]
    depth = map_entity.components[comp.Depth]
    walkable = db.walkable[grid]
    # Separate rooms
    rmoore = funcs.moore(room_grid)
    inroom = room_grid & (funcs.moore(rmoore == 8) > 0)
    room_list = disjoint_areas(inroom)
    # Count the connections of each room
    room_connections = [
        # Walkable tiles that are not in the room but are next to the room
        np.sum(walkable & ~r & (funcs.moore(r) > 0))
        for r in room_list
    ]
    # Remove all positiions with entities
    noentity = walkable.copy()
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        relations=[(comp.Map, map_entity)],
    )
    for e in query:
        x, y = e.components[comp.Position].xy
        noentity[x, y] = False
    # Find rooms with only one connection
    room_list = [r for r, c in zip(room_list, room_connections) if c == 1]
    if len(room_list) < 1:
        return
    # Create a matrix with all locked rooms
    locked_room_grid = room_list[0]
    # CReate a grid with upstairs position
    query = map_entity.registry.Q.all_of(
        components=[comp.Position],
        tags=[comp.Upstairs],
        relations=[(comp.Map, map_entity)],
    )
    upstairs_grid = np.full(walkable.shape, False)
    for u in query:
        uxy = u.components[comp.Position].xy
        upstairs_grid[uxy] = True
    # Iterate over rooms
    for room in room_list:
        locked_room_grid |= room
        door_tile = walkable & ~room & (funcs.moore(room) > 0)
        available = room & noentity & (funcs.moore(door_tile) == 0)
        if np.sum(available) < 1:
            continue
        # Randomize position
        all_x, all_y = np.where(available)
        i = seed.randint(0, len(all_x))
        pos = (all_x[i], all_y[i])
        # Spawn chest
        chest = spawn_prop(map_entity, "Chest", pos)
        # Populate chest with items
        n_items = (seed.randint(1, 6) + seed.randint(1, 6)) // 2
        for _ in range(n_items):
            kind = pick_item_kind(map_entity)
            count = pick_item_count(map_entity, kind)
            items.add_item(chest, kind, count)

        # Don't lock the room if there is no door or if there is an upstairs
        if np.sum(door_tile) < 1 or np.sum(room & upstairs_grid) > 0:
            continue

        # Spawn key somewhere else
        all_x, all_y = np.where(walkable & ~locked_room_grid)
        i = seed.randint(0, len(all_x))
        key_pos = (all_x[i], all_y[i])
        key_entity = items.spawn_item(map_entity, key_pos, "Key")

        # Find door entity
        door_xy = tuple(np.argwhere(door_tile).tolist()[0])
        query = map_entity.registry.Q.all_of(
            components=[comp.Position, comp.Interaction],
            tags=[comp.Door, comp.Position(door_xy, depth)],
            relations=[(comp.Map, map_entity)],
        )
        door_entity, *_ = query.get_entities()
        door_entity.tags |= {comp.Locked}
        door_entity.relation_tag[comp.Key] = key_entity
        spr = door_entity.components.get(comp.LockedSprite)
        if spr is not None:
            door_entity.components[comp.Sprite] = spr


def generate(map_entity: ecs.Entity):
    # Generate map
    world_seed = map_entity.registry[None].components[np.random.RandomState]
    seed_id = world_seed.randint(1, 999999)
    seed = np.random.RandomState(seed_id)
    map_entity.components[comp.Seed] = seed_id
    map_entity.components[np.random.RandomState] = seed
    depth = map_entity.components[comp.Depth]
    if depth > 0:
        map_entity.components[comp.XPGain] = 5 * ((depth + 1) // 2)
    if depth <= 0:
        grid = generate_forest(map_entity)
    else:
        grid = generate_dungeon(map_entity)
    room_floor = grid == db.tile_id["floor"]
    map_entity.components[comp.Tiles] = grid
    map_entity.components[comp.Explored] = np.full(grid.shape, False)
    # Post processing
    grid = update_bitmasks(grid)
    # Save generated map
    map_entity.components[comp.Tiles] = grid
    # Add props
    add_doors(map_entity, room_floor)
    add_torches(map_entity, condition=funcs.moore(room_floor) > 0)
    add_traps(map_entity)
    add_boulders(map_entity, condition=grid == db.tile_id["cavefloor"])
    add_chests(map_entity, room_floor)
    add_downstairs(map_entity, room_floor, max_count=1 + (depth > 0))
    spawn_items(map_entity)
    spawn_enemies(map_entity, consts.ENEMY_RADIUS, consts.N_ENEMIES)


def random_lake(
    condition: NDArray[np.bool_],
    seed: np.random.RandomState,
    min_size: int = consts.MAX_ROOM_SIZE,
    max_size: int = consts.MAX_ROOM_SIZE * 2,
) -> NDArray[np.bool_]:
    area = random_rect_room(~condition, seed, min_size, max_size)
    if area is None:
        return np.full(condition.shape, False)
    return cellular_automata(area, seed)


def generate_forest(map_entity: ecs.Entity) -> NDArray[np.int8]:
    grid = np.zeros(consts.MAP_SHAPE, np.int8)
    seed = map_entity.components[np.random.RandomState]
    # Create ruins
    ruins = random_rect_room(grid != 0, seed, max_iter=100)
    if ruins is None:
        ruins = rect_room(grid.shape, 2, 2, 8, 6)
    walls = ~ruins & (funcs.moore(ruins) > 0)
    # Create lake
    lake = random_lake(~(ruins | walls), seed)
    lake |= random_lake(~(ruins | walls | lake), seed)
    lake |= random_lake(~(ruins | walls | lake), seed)
    # Add grass around lake
    grass = (~lake) & (funcs.moore(lake) > 0)
    rand = seed.random(grid.shape)
    grass |= (~lake) & (funcs.moore(grass) > 0) & (rand <= 0.6)
    # Create forest
    grass |= cellular_automata(~(ruins | walls | lake), seed, density=0.5)
    # Combine areas
    areas = disjoint_areas(grass | ruins)
    if len(areas) > 2:
        conn = delaunay_corridors(grass | ruins | lake, areas, seed, 10, 0.4)
    elif len(areas) == 2:
        conn = corridor(grass | ruins | lake, areas[0], areas[1], seed, 10)
    #
    grass |= conn & ~walls
    ruins |= conn & walls
    walls &= ~conn
    lake &= ~conn
    #
    rand = seed.random(grid.shape)
    trees = ~(grass | ruins | walls | lake) | (
        grass & (funcs.moore(grass) >= 8) & (rand < 0.25)
    )
    #
    grid[grass] = db.tile_id["grass"]
    grid[trees] = db.tile_id["tree"]
    grid[lake] = db.tile_id["water"]
    grid[walls] = db.tile_id["wall"]
    grid[ruins] = db.tile_id["floor"]
    return grid


def generate_dungeon(map_entity: ecs.Entity) -> NDArray[np.int8]:
    grid = np.zeros(consts.MAP_SHAPE, np.int8)
    seed = map_entity.components[np.random.RandomState]
    # Create room for upstairs
    upstairs_room = add_upstairs_room(map_entity)
    room_grid = upstairs_room.copy()
    walls = funcs.moore(room_grid) > 0
    # Create lake
    lake = random_lake(~(room_grid | walls), seed)
    lake |= random_lake(~(room_grid | walls | lake), seed)
    # Add dirt around lake
    cave_grid = ~lake & ~room_grid & (funcs.moore(lake) > 0)
    rand = seed.random(grid.shape)
    cave_grid |= ~lake & ~room_grid & (funcs.moore(cave_grid) > 0) & (rand <= 0.4)
    cave_grid[0, :] = False
    cave_grid[-1, :] = False
    cave_grid[:, 0] = False
    cave_grid[:, -1] = False

    # Create random rooms
    room_grid = room_grid | random_rooms(
        ~(room_grid | lake | cave_grid), seed, max_rooms=consts.NUM_ROOMS - 1
    )
    # Create caves
    cave_grid |= prune(cellular_automata(~(room_grid | lake | cave_grid), seed))
    # Create corridors
    area_list = disjoint_areas(cave_grid | room_grid)
    corridors = delaunay_corridors(
        room_grid | cave_grid, area_list, seed, noise=5, nomst_prob=0.15
    )
    #
    floor = room_grid | cave_grid | corridors
    # Add walls
    walls = get_walls(room_grid, ~floor & ~lake)
    cave_walls = get_walls(cave_grid | corridors, ~floor & ~walls)
    # Set tiles
    grid[cave_walls] = db.tile_id["cavewall"]
    grid[walls] = db.tile_id["wall"]
    grid[lake] = db.tile_id["water"]
    grid[cave_grid | corridors] = db.tile_id["cavefloor"]
    near_room = funcs.moore(room_grid) > 0
    grid[room_grid | (corridors & near_room)] = db.tile_id["floor"]
    #
    room_list = disjoint_areas(room_grid & ~upstairs_room)
    decorate_rooms(map_entity, room_list)
    return grid


def decorate_rooms(map_entity: ecs.Entity, room_list: list[NDArray[np.bool_]]):
    seed = map_entity.components[np.random.RandomState]
    kinds = [dining_room, library_room, center_decor_room, storage_room, None, None]
    indices = [i for i in range(len(kinds))]
    weights = [10.0 for k in kinds]
    for room in room_list:
        w, h = int(room.sum(axis=0).max()), int(room.sum(axis=1).max())
        if w <= consts.MIN_ROOM_SIZE or h <= consts.MIN_ROOM_SIZE:
            continue
        prob = [w / sum(weights) for w in weights]
        i = seed.choice(indices, p=prob)
        weights[i] *= 0.2
        decorate_fun = kinds[i]
        if decorate_fun is not None:
            decorate_fun(map_entity, room)


def dining_room(map_entity: ecs.Entity, room: NDArray[np.bool_]):
    depth = map_entity.components[comp.Depth]
    w, h = int(room.sum(axis=0).max()), int(room.sum(axis=1).max())
    cx, cy = area_centroid(room)
    rmoore = funcs.moore(room)
    x_grid, y_grid = np.indices(room.shape)
    # Spawn tables
    if w > h:
        table = (y_grid == int(cy)) & (funcs.moore(rmoore >= 8) >= 8)
    else:
        table = (x_grid == int(cx)) & (funcs.moore(rmoore >= 8) >= 8)
    all_x, all_y = np.where(table)
    for x, y in zip(all_x, all_y):
        spawn_prop(map_entity, "Table", (x, y))
    # Spawn chairs
    chairs = (funcs.moore(table, diagonals=False) > 0) & ~table & room
    all_x, all_y = np.where(chairs)
    for x, y in zip(all_x, all_y):
        if x > cx:
            spawn_prop(map_entity, "Chair2", (x, y))
        else:
            spawn_prop(map_entity, "Chair", (x, y))


def library_room(map_entity: ecs.Entity, room: NDArray[np.bool_]):
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    w, h = int(room.sum(axis=0).max()), int(room.sum(axis=1).max())
    cx, cy = area_centroid(room)
    rmoore = funcs.moore(room)
    x_grid, y_grid = np.indices(room.shape)
    shelf = room & (rmoore == 8)
    if w > h:
        shelf &= np.abs(x_grid - int(cx)) % 2 == 0
        if h >= 7:
            shelf &= y_grid != int(cy)
    else:
        shelf &= np.abs(y_grid - int(cy)) % 2 == 0
        if w >= 7:
            shelf &= x_grid != int(cx)
    #
    books = list(
        map_entity.registry.Q.all_of(components=[comp.Text], tags=["books"])
        .none_of(
            components=[comp.Position],
            relations=[(comp.Map, ...), (comp.Inventory, ...)],
        )
        .get_entities()
    )
    #
    all_x, all_y = np.where(shelf)
    for x, y in zip(all_x, all_y):
        if seed.randint(0, 10) < 5:
            prop = "Empty Shelf"
        else:
            prop = "Bookshelf"
        shelf = spawn_prop(map_entity, prop, (x, y))
        if prop == "Empty Shelf":
            continue
        # Add book
        kind = books[seed.randint(0, len(books))]
        items.add_item(shelf, kind, 1)


def center_decor_room(map_entity: ecs.Entity, room: NDArray[np.bool_]):
    choices = ["Altar", "Statue", "Fountain", "Plaque", "Coffin", "Throne"]
    seed = map_entity.components[np.random.RandomState]
    depth = map_entity.components[comp.Depth]
    w, h = int(room.sum(axis=0).max()), int(room.sum(axis=1).max())
    #
    cx, cy = area_centroid(room)
    prop = choices[seed.randint(0, len(choices))]
    spawn_prop(map_entity, prop, (cx, cy))
    #
    if min(w, h) <= consts.MIN_ROOM_SIZE + 2:
        return
    rmoore8 = funcs.moore(room) >= 8
    statues = room & rmoore8 & (funcs.moore(rmoore8) == 3)
    all_x, all_y = np.where(statues)
    for x, y in zip(all_x, all_y):
        spawn_prop(map_entity, "Statue", (x, y))


def storage_room(map_entity: ecs.Entity, room: NDArray[np.bool_], prob: float = 0.5):
    seed = map_entity.components[np.random.RandomState]
    rmoore = funcs.moore(room)
    cx, cy = area_centroid(room)
    x_grid, y_grid = np.indices(room.shape)
    w, h = int(room.sum(axis=0).max()), int(room.sum(axis=1).max())
    rand = seed.random(room.shape)
    points = room & (rmoore >= 8) & (rand <= prob)
    if w > 6:
        points &= x_grid != int(cx)
    if h > 6:
        points &= y_grid != int(cy)
    all_x, all_y = np.where(points)
    props = ["Barrel", "Barrel", "Vase", "Logs"]
    for x, y in zip(all_x, all_y):
        k = seed.randint(0, len(props))
        spawn_prop(map_entity, props[k], (x, y))
