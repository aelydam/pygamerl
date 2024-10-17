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
import funcs
import maps


def get_walls(grid: NDArray[np.bool_], condition: NDArray[np.bool_] | None = None):
    # Find tiles that are void but are neighbors to a floor
    walls = (funcs.moore(grid) > 0) & (~grid)
    if condition is not None:
        walls &= condition
    return walls


def spawn_enemies(map_entity: ecs.Entity, radius: int, max_count: int = 0):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    xgrid, ygrid = np.indices(grid.shape)
    walkable = ~consts.TILE_ARRAY["obstacle"][grid]
    counter = 0
    # Initialize available array from walkable points
    available = walkable.copy()
    # Consider creatures and upstairs already on the map
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
        enemy = map_entity.registry.new_entity(
            components={
                comp.Position: comp.Position((x, y), depth),
                comp.Name: "Skeleton",
                comp.Sprite: comp.Sprite("Characters/Undead0", (0, 2)),
                comp.MaxHP: 6,
                comp.HP: 6,
                comp.Initiative: 0,
                comp.FOVRadius: 6,
            },
            tags=[comp.Obstacle],
        )
        enemy.relation_tag[comp.Map] = map_entity
        counter += 1
        # Make all points within radius unavailable
        dist2 = (xgrid - x) ** 2 + (ygrid - y) ** 2
        available[dist2 <= radius**2] = False


def respawn(map_entity: ecs.Entity):
    seed = map_entity.components[np.random.RandomState]
    roll = seed.randint(1, consts.RESPAWN_RATE + 1)
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
    density=0.5,
    iterations=3,
) -> NDArray[np.bool_]:
    grid = funcs.moore(condition) >= 8
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


def add_doors(map_entity: ecs.Entity, condition: NDArray[np.bool_] | None = None):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    walkable = ~consts.TILE_ARRAY["obstacle"][grid]
    bm = funcs.bitmask(walkable)
    wmoore = funcs.moore(walkable)
    rooms = walkable & (funcs.moore(wmoore >= 8) > 0)
    doors = walkable & np.isin(bm, (6, 9)) & (funcs.moore(rooms) > 0)
    if condition is not None:
        doors &= condition
    all_x, all_y = np.where(doors)
    for x, y in zip(all_x, all_y):
        door = map_entity.registry.new_entity(
            components={
                comp.Position: comp.Position((x, y), depth),
                comp.Sprite: comp.Sprite("Objects/Door0", (0, 0)),
                comp.Interaction: actions.ToggleDoor,
            },
            tags=[comp.Opaque, comp.Obstacle],
        )


def add_downstairs(
    map_entity: ecs.Entity,
    condition: NDArray[np.bool_] | None = None,
    max_count: int = 2,
):
    grid = map_entity.components[comp.Tiles]
    depth = map_entity.components[comp.Depth]
    walkable = ~consts.TILE_ARRAY["obstacle"][grid]
    cond = walkable & (funcs.moore(walkable) >= 8)
    if condition is not None:
        cond &= condition
    all_x, all_y = np.where(cond)
    seed = map_entity.components[np.random.RandomState]
    all_i = {seed.randint(0, len(all_x)) for _ in range(max_count)}
    for i in all_i:
        xy = all_x[i], all_y[i]
        map_entity.registry.new_entity(
            components={
                comp.Position: comp.Position(xy, depth),
                comp.Sprite: comp.Sprite("Objects/Tile", (6, 3)),
                comp.Interaction: actions.Descend,
            },
            tags=[comp.Downstairs],
        )


def add_upstairs_room(map_entity: ecs.Entity) -> NDArray[np.bool_]:
    depth = map_entity.components[comp.Depth]
    seed = map_entity.components[np.random.RandomState]
    points = []
    if depth < 1:
        x = consts.MAX_ROOM_SIZE + seed.randint(
            1, consts.MAP_SHAPE[0] - consts.MAX_ROOM_SIZE
        )
        y = consts.MAX_ROOM_SIZE + seed.randint(
            1, consts.MAP_SHAPE[1] - consts.MAX_ROOM_SIZE
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
        x = min(max(1, point[0] - w // 2), consts.MAP_SHAPE[0] - w)
        y = min(max(1, point[1] - h // 2), consts.MAP_SHAPE[1] - h)
        rooms |= rect_room(consts.MAP_SHAPE, x, y, w, h)
        map_entity.registry.new_entity(
            components={
                comp.Position: comp.Position(point, depth),
                comp.Sprite: comp.Sprite("Objects/Tile", (4, 3)),
                comp.Interaction: actions.Ascend,
            },
            tags=[comp.Upstairs],
        )
    rooms[0, :] = False
    rooms[:, 0] = False
    rooms[-1, :] = False
    rooms[:, -1] = False
    return rooms


def update_bitmasks(grid: NDArray[np.int8]) -> NDArray[np.int8]:
    bm = funcs.bitmask(grid)
    for tile_name, tile_id in consts.TILE_ID.items():
        tile_name = consts.TILE_NAMES[tile_id]
        if tile_name[-1] in "1234567890":
            continue
        for j in range(16):
            new_name = f"{tile_name}{j}"
            if new_name in consts.TILE_NAMES:
                np.sum((grid == tile_id) & (bm == j))
                new_id = consts.TILE_ID[new_name]
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
    walkable = ~consts.TILE_ARRAY["obstacle"][grid]
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


def generate(map_entity: ecs.Entity):
    # Generate map
    seed = np.random.RandomState()
    map_entity.components[np.random.RandomState] = seed
    depth = map_entity.components[comp.Depth]
    if depth == 0:
        grid = generate_forest(map_entity)
    else:
        grid = generate_dungeon(map_entity)
    room_floor = grid == consts.TILE_ID["floor"]
    map_entity.components[comp.Tiles] = grid
    map_entity.components[comp.Explored] = np.full(grid.shape, False)
    # Post processing
    grid = update_bitmasks(grid)
    # Save generated map
    map_entity.components[comp.Tiles] = grid
    # Add doors
    add_doors(
        map_entity, room_floor
    )  # & (funcs.moore(room_floor, diagonals=False) > 2))
    # Stairs
    add_downstairs(map_entity, room_floor, max_count=1 + (depth > 0))
    # Spawn enemies
    spawn_enemies(map_entity, consts.ENEMY_RADIUS, consts.N_ENEMIES)


def generate_forest(map_entity: ecs.Entity) -> NDArray[np.int8]:
    grid = np.zeros(consts.MAP_SHAPE, np.int8)
    seed = map_entity.components[np.random.RandomState]
    # Create ruins
    ruins = random_rect_room(grid != 0, seed, max_iter=100)
    if ruins is None:
        ruins = rect_room(grid.shape, 2, 2, 8, 6)
    walls = ~ruins & (funcs.moore(ruins) > 0)
    # Create forest
    grass = prune(cellular_automata(~(ruins | walls), seed, density=0.5))
    # Combine areas
    areas = disjoint_areas(grass | ruins)
    if len(areas) > 2:
        conn = delaunay_corridors(grass | ruins, areas, seed, 10, 0.9)
    elif len(areas) == 2:
        conn = corridor(grass | ruins, areas[0], areas[1], seed, 10)
    #
    grass |= conn & ~walls
    ruins |= conn & walls
    walls &= ~conn
    #
    rand = seed.random(grid.shape)
    trees = ~(grass | ruins | walls) | (
        grass & (funcs.moore(grass) >= 8) & (rand < 0.25)
    )
    #
    grid[grass] = consts.TILE_ID["grass"]
    grid[trees] = consts.TILE_ID["tree"]
    grid[walls] = consts.TILE_ID["wall"]
    grid[ruins] = consts.TILE_ID["floor"]
    return grid


def generate_dungeon(map_entity: ecs.Entity) -> NDArray[np.int8]:
    grid = np.zeros(consts.MAP_SHAPE, np.int8)
    seed = map_entity.components[np.random.RandomState]
    # Create room for upstairs
    room_grid = add_upstairs_room(map_entity)
    # Create random rooms
    room_grid = room_grid | random_rooms(
        ~room_grid, seed, max_rooms=consts.NUM_ROOMS - 1
    )
    # Create corridors
    room_list = disjoint_areas(room_grid)
    corridors = delaunay_corridors(
        room_grid,
        room_list,
        seed,
        max_size=consts.MAX_ROOM_SIZE + consts.MIN_ROOM_SIZE,
    )
    # Create caves
    cave_grid = prune(cellular_automata(~room_grid & ~corridors, seed))
    #
    cave_list = disjoint_areas(cave_grid)
    new_corridors = delaunay_corridors(
        room_grid | cave_grid | corridors, cave_list + room_list, seed, noise=6
    )
    corridors[new_corridors & (funcs.moore(room_grid) > 0)] = True
    new_corridors[corridors] = False
    #
    floor = room_grid | cave_grid | corridors | new_corridors
    # Add walls
    walls = get_walls(room_grid | corridors, ~floor)
    cave_walls = get_walls(cave_grid | new_corridors, ~floor & ~walls)
    # Set tiles
    grid[cave_walls] = consts.TILE_ID["cavewall"]
    grid[walls] = consts.TILE_ID["wall"]
    grid[cave_grid | new_corridors] = consts.TILE_ID["cavefloor"]
    grid[room_grid | corridors] = consts.TILE_ID["floor"]
    return grid
