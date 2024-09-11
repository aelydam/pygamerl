import random
import numpy as np
import tcod

import consts
import entities


class GameLogic:
    def __init__(self, interface):
        self.entities = []
        self.current_turn = -1
        self.interface = interface
        self.input_action = None
        self.message_log = []
        self.last_action = None
        self.init_map()
        self.init_player()

    def log(self, text):
        self.message_log.append(text)

    def init_map(self):
        self.map = np.zeros(consts.MAP_SHAPE)
        for walkers in range(5):
            x, y = (consts.MAP_SHAPE[0] // 2, consts.MAP_SHAPE[1] // 2)
            self.map[x, y] = 1
            for iterators in range(500):
                dx, dy = random.choice([(0, 1), (1, 0), (0, -1), (-1, 0)])
                if x + dx > 0 and x + dx < consts.MAP_SHAPE[0] - 1 and \
                        y + dy > 0 and y + dy < consts.MAP_SHAPE[1] - 1:
                    x += dx
                    y += dy
                    self.map[x, y] = 1
                else:
                    break
        self.explored = np.full(consts.MAP_SHAPE, False)

    def init_player(self):
        x, y = np.where(self.map == 1)
        i = list(range(len(x)))
        random.shuffle(i)
        self.player = entities.Player(self, x[i[0]], y[i[0]])
        self.entities.append(self.player)
        for k in range(1, consts.N_ENEMIES+1):
            enemy = entities.Enemy(self, x[i[k]], y[i[k]])
            self.entities.append(enemy)

    def update(self):
        if self.current_turn >= len(self.entities):
            self.current_turn = 0
        entity = self.entities[self.current_turn]
        action = None
        if entity.hp < 1:
            self.entities.remove(entity)
            return
        if isinstance(entity, entities.Player):
            if self.input_action is not None and self.input_action.can():
                action = self.input_action
            else:
                return
        else:
            action = entity.next_action()
        if action is not None:
            self.last_action = action.perform()
        self.input_action = None
        self.current_turn += 1
        if self.current_turn >= len(self.entities):
            self.current_turn = 0
        self.entities[self.current_turn].update_fov()

    def astar_path(self,
                   origin: tuple[int, int],
                   target: tuple[int, int]) -> list[tuple[int, int]]:
        cost = self.map.copy()
        for e in self.entities:
            cost[e.x, e.y] = 0
        cost[origin[0], origin[1]] = 1
        cost[target[0], target[1]] = 1
        graph = tcod.path.SimpleGraph(cost=cost.astype(np.int8),
                                      cardinal=5, diagonal=7)
        pathfinder = tcod.path.Pathfinder(graph)
        pathfinder.add_root(origin)
        return pathfinder.path_to(target).tolist()

    def is_walkable(self, x: int, y: int) -> bool:
        if self.map[x, y] == 0:
            return False
        for e in self.entities:
            if e.x == x and e.y == y:
                return False
        return True
