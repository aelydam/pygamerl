
import random
import numpy as np
import pygame as pg
import tcod

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

class WaitAction:
    def can(self):
        return True

    def perform(self):
        return self

class MoveAction:
    def __init__(self, dx, dy, actor):
        self.dx, self.dy, self.actor = dx, dy, actor

    def can(self):
        dist = (self.dx**2 + self.dy**2)**0.5
        if dist > 1.5:
            return False
        new_x = self.actor.x + self.dx
        new_y = self.actor.y + self.dy
        if new_x < 0 or new_y < 0 or new_x >= MAP_SHAPE[0] or new_y >= MAP_SHAPE[1]:
            return False
        return self.actor.game_logic.is_walkable(new_x, new_y)
    
    def perform(self):
        if not self.can():
            return
        self.actor.x += self.dx
        self.actor.y += self.dy
        return self

class AttackAction:
    def __init__(self, target, actor):
        self.target = target
        self.actor = actor

    def can(self):
        dist = ((self.target.x-self.actor.x)**2+(self.target.y-self.actor.y)**2)**0.5
        if dist > 1.5:
            return False
        if self.target.hp < 1:
            return False
        return True

    def perform(self):
        if not self.can():
            return None
        roll = random.randint(1, 20) + self.actor.tohit
        if isinstance(self.actor, Player):
            text = "You attack the enemy: "
        else:
            text = "The enemy attacks you: "
        if roll >= self.target.ac:
            self.damage = random.randint(1, self.actor.damage)
            self.target.hp = max(0, self.target.hp - self.damage)
            text += f"{self.damage} points of damage!"
        else:
            self.damage = 0
            text += "Miss!"
        self.actor.game_logic.log(text)
        if self.target.hp < 0:
            if isinstance(self.target, Player):
                self.actor.game_logic.log("You die!")
            else:
                self.actor.game_logic.log("The enemy dies!")
        return self

class BumpAction:
    def __init__(self, dx, dy, actor):
        self.dx, self.dy, self.actor = dx, dy, actor

    def get_entity(self):
        new_x = self.actor.x + self.dx
        new_y = self.actor.y + self.dy
        for e in self.actor.game_logic.entities:
            if e.x == new_x and e.y == new_y and e != self.actor:
                return e
        return None

    def can(self):
        move = MoveAction(self.dx, self.dy, self.actor)
        if move.can():
            return True
        entity = self.get_entity()
        return entity is not None

    def perform(self):
        if not self.can():
            return None
        move = MoveAction(self.dx, self.dy, self.actor)
        if move.can():
            return move.perform()
        entity = self.get_entity()
        attack = AttackAction(entity, self.actor)
        return attack.perform()

class Entity:
    def __init__(self, game_logic, x, y, sprite, row, col):
        self.game_logic = game_logic
        self.x, self.y = x, y
        self.sprite, self.row, self.col = sprite, row, col
        self.max_hp = 10
        self.hp = 10
        self.tohit = 4
        self.damage = 6
        self.ac = 12
        self.fov_radius = 5
        self.update_fov()

    def update_fov(self):
        transparency = self.game_logic.map!=0
        self.fov = tcod.map.compute_fov(
            transparency, (self.x, self.y), self.fov_radius,
            algorithm=tcod.constants.FOV_SYMMETRIC_SHADOWCAST)

class Player(Entity):
    def __init__(self, game_logic, x, y):
        super().__init__(game_logic, x, y, '32rogues/rogues.png', 1, 1)
        self.max_hp = 40
        self.hp = 40

    def update_fov(self):
        super().update_fov()
        self.game_logic.explored |= self.fov

class Enemy(Entity):
    def __init__(self, game_logic, x, y):
        super().__init__(game_logic, x, y, '32rogues/monsters.png', 0, 0)

    def next_action(self):
        player = self.game_logic.player
        px, py = player.x, player.y
        dist = ((px-self.x)**2 + (py-self.y)**2)**0.5
        if player.hp < 1 or not self.fov[px, py]:
            dx, dy = random.randint(-1, 1), random.randint(-1, 1)
            return MoveAction(dx, dy, self)
        if dist < 1.5:
            return AttackAction(player, self)
        path = self.game_logic.astar_path((self.x, self.y), (player.x, player.y))
        if len(path) < 2:
            return WaitAction()
        dx = path[1][0] - path[0][0]
        dy = path[1][1] - path[0][1]
        return MoveAction(dx, dy, self)

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
        self.map = np.zeros(MAP_SHAPE)
        for walkers in range(5):
            x, y = (MAP_SHAPE[0] // 2, MAP_SHAPE[1] // 2)
            self.map[x, y] = 1
            for iterators in range(500):
                dx, dy = random.choice([(0,1), (1,0), (0,-1), (-1,0)])
                if x+dx>0 and y+dy>0 and x+dx<MAP_SHAPE[0]-1 and y+dy<MAP_SHAPE[1]-1:
                    x += dx
                    y += dy
                    self.map[x, y] = 1
                else:
                    break
        self.explored = np.zeros(MAP_SHAPE)!=0

    def init_player(self):
        x, y = np.where(self.map == 1)
        i = list(range(len(x)))
        random.shuffle(i)
        self.player = Player(self, x[i[0]], y[i[0]])
        self.entities.append(self.player)
        for k in range(1, N_ENEMIES+1):
            enemy = Enemy(self, x[i[k]], y[i[k]])
            self.entities.append(enemy)

    def update(self):
        if self.current_turn >= len(self.entities):
            self.current_turn = 0
        entity = self.entities[self.current_turn]
        action = None
        if entity.hp < 1:
            self.entities.remove(entity)
            return
        if isinstance(entity, Player):
            if self.input_action is None:
                return
            else:
                action = self.input_action
        else:
            action = entity.next_action()
        if action is not None:
            self.last_action = action.perform()
        self.input_action = None
        self.current_turn += 1
        if self.current_turn >= len(self.entities):
            self.current_turn = 0
        self.entities[self.current_turn].update_fov()

    def astar_path(self, origin, target):
        cost = self.map.copy()
        for e in self.entities:
            cost[e.x, e.y] = 0
        cost[origin[0], origin[1]] = 1
        cost[target[0], target[1]] = 1
        graph = tcod.path.SimpleGraph(cost=cost.astype(np.int8), cardinal=5, diagonal=7)
        pathfinder = tcod.path.Pathfinder(graph)
        pathfinder.add_root(origin)
        return pathfinder.path_to(target).tolist()

    def is_walkable(self, x, y):
        if self.map[x, y] == 0:
            return False
        for e in self.entities:
            if e.x == x and e.y == y:
                return False
        return True


# RENDERING ==========================================

class EntitySprite(pg.sprite.Sprite):
    def __init__(self, group, interface, game_logic, entity):
        super().__init__(group)
        self.group = group
        self.entity = entity
        self.game_logic = game_logic
        self.interface = interface
        self.is_in_fov = None
        tilesheet = pg.image.load(self.entity.sprite).convert_alpha()
        self.tile = tilesheet.subsurface(
            pg.Rect(self.entity.row*TILE_SIZE, self.entity.col*TILE_SIZE,
                TILE_SIZE, TILE_SIZE))
        self.image = self.tile
        self.hpbar = MapHPBar(group, self)

    def update(self):
        if self.entity.hp < 1:
            self.kill()
            return
        x, y = self.interface.grid_to_screen(self.entity.x, self.entity.y)
        self.rect = pg.Rect(x, y, TILE_SIZE, TILE_SIZE)
        is_in_fov = self.game_logic.player.fov[self.entity.x, self.entity.y]
        if is_in_fov == self.is_in_fov:
            return
        self.is_in_fov = is_in_fov
        if is_in_fov:
            self.image = self.tile
        else:
            self.image = pg.Surface((1,1)).convert_alpha()
            self.image.fill("#00000000")

class TileSprite(pg.sprite.Sprite):
    def __init__(self, group, interface, game_logic, x, y):
        super().__init__(group)
        self.group = group
        self.x, self.y = x, y
        self.game_logic = game_logic
        self.interface = interface
        self.is_explored = False
        self.is_in_fov = False
        self.is_walkable = None
        self.image = pg.Surface((TILE_SIZE, TILE_SIZE)).convert_alpha()
        self.image.fill("#00000000")
        self.wall = interface.tilesheet.subsurface((TILE_SIZE, TILE_SIZE, TILE_SIZE, TILE_SIZE))
        self.wall2 = interface.tilesheet.subsurface((0, TILE_SIZE, TILE_SIZE, TILE_SIZE))
    
    def update(self):
        x, y = self.interface.grid_to_screen(self.x, self.y)
        self.rect = pg.Rect(x, y, TILE_SIZE, TILE_SIZE)

        is_walkable = self.game_logic.map[self.x, self.y] == 1
        is_explored = self.game_logic.explored[self.x, self.y]
        is_in_fov = self.game_logic.player.fov[self.x, self.y]
        if is_explored == self.is_explored and is_in_fov == self.is_in_fov and is_walkable == self.is_walkable:
            return
        self.is_walkable = is_walkable
        self.is_explored = is_explored
        self.is_in_fov = is_in_fov
        k = 255
        if not is_in_fov:
            k //= 2
        if not is_explored:
            k *= 0
        if not is_walkable:
            walkable_below = (self.y < MAP_SHAPE[1] - 1) and (self.game_logic.map[self.x, self.y+1] == 1)
            if walkable_below:
                self.image.blit(self.wall, (0,0))
            else:
                self.image.blit(self.wall2, (0,0))
        else:
            self.image.fill("#404040")
        self.image.set_alpha(k)

class MapHPBar(pg.sprite.Sprite):
    def __init__(self, group, parent):
        super().__init__(group)
        self.parent = parent
        self.fill = 0
        self.is_in_fov = None

    def update(self):
        x, y = self.parent.rect.x, self.parent.rect.bottom
        w, h = self.parent.rect.width, 4
        self.rect = pg.Rect(x, y, w, h)
        entity = self.parent.entity
        if entity.hp < 1:
            self.kill()
        fill = int(self.rect.width * entity.hp / entity.max_hp)
        is_in_fov = self.parent.is_in_fov
        if fill == self.fill and self.is_in_fov == is_in_fov:
            return
        if fill > self.fill:
            self.fill += 1
        elif fill < self.fill:
            self.fill -= 1
        self.parent.is_in_fov = is_in_fov
        self.image = pg.Surface(self.rect.size).convert_alpha()
        if not is_in_fov:
            self.image.fill("#00000000")
            return
        self.image.fill("#808080")
        if self.fill >= self.rect.width // 2:
            color = '#00FF00'
        else:
            color = '#FF0000'
        pg.draw.rect(self.image, color, pg.Rect(0, 0, self.fill, self.rect.height))


class HPBar(pg.sprite.Sprite):
    def __init__(self, group, game_logic, interface):
        super().__init__(group)
        self.game_logic = game_logic
        self.font: pg.font.Font = interface.font
        self.rect = pg.Rect(16, 16, 200, 20)
        self.fill = 0

    def update(self):
        player = self.game_logic.player
        fill = int(self.rect.width * player.hp / player.max_hp)
        if fill == self.fill:
            return
        if fill > self.fill:
            self.fill += 1
        elif fill < self.fill:
            self.fill -= 1
        if self.fill >= self.rect.width // 2:
            color = '#00FF00'
        else:
            color = '#FF0000'
        self.image = pg.Surface(self.rect.size)
        self.image.fill("#808080")
        pg.draw.rect(self.image, color, pg.Rect(0, 0, self.fill, self.rect.height))
        surf = self.font.render(f"{player.hp}/{player.max_hp}", False, '#000000', '#FFFFFF')
        surf.set_colorkey("#FFFFFF")
        self.image.blit(surf, surf.get_rect(center=(self.rect.width//2, self.rect.height//2)))


class MessageLog(pg.sprite.Sprite):
    def __init__(self, group, game_logic: GameLogic, interface):
        super().__init__(group)
        self.rect = pg.Rect(16, 16+24, SCREEN_SHAPE[0]//2, 24*10)
        self.image = pg.Surface(self.rect.size).convert_alpha()
        self.image.fill("#00000000")
        self.game_logic = game_logic
        self.last_text = None
        self.log_len = 0
        self.font = interface.font

    def update(self):
        log_len = len(self.game_logic.message_log)
        if log_len < 1:
            return
        last_text = self.game_logic.message_log[-1]
        if last_text == self.last_text and log_len == self.log_len:
            return
        self.image.fill("#00000000")
        for i in range(1, min(11, log_len)):
            text = self.game_logic.message_log[-i]
            surf = self.font.render(text, False, "#FFFFFF", "#000000")
            surf.set_colorkey("#000000")
            self.image.blit(surf, (0, i*20))

class Popup(pg.sprite.Sprite):
    def __init__(self, group, action, interface):
        super().__init__(group)
        self.action = action
        self.counter = 0
        self.interface = interface
        self.x, self.y = self.action.target.x, self.action.target.y
        text = str(self.action.damage)
        if text == '0':
            text = 'MISS'
        self.image = self.interface.font.render(text, False, "#FFFFFF", "#000000")
        self.image.set_colorkey("#000000")

    def update(self):
        if self.counter > TILE_SIZE:
            self.kill()
            return
        x, y = self.interface.grid_to_screen(self.x, self.y)
        x += TILE_SIZE // 2
        y -= self.counter // 2
        self.rect = self.image.get_rect(center=(x,y))
        self.counter += 1

class Minimap(pg.sprite.Sprite):
    def __init__(self, group, game_logic):
        super().__init__(group)
        self.game_logic = game_logic
        self.scale = 4
        w, h = MAP_SHAPE[0] * self.scale, MAP_SHAPE[1] * self.scale
        x, y = SCREEN_SHAPE[0] - w - 16, 16
        self.rect = pg.Rect(x, y, w, h)

    def update(self):
        player = self.game_logic.player
        walkable = self.game_logic.map == 1
        explored = self.game_logic.explored
        fov = player.fov
        grid = np.ones((MAP_SHAPE[0], MAP_SHAPE[1], 3))
        for k in range(3):
            grid[:,:,k] += 120 * explored * walkable
            grid[:,:,k] += 120 * explored * walkable * fov
            grid[:,:,k] += 40 * explored * (walkable==False)
            grid[:,:,k] += 40 * explored * (walkable==False) * fov
        for e in self.game_logic.entities:
            if fov[e.x, e.y]:
                if isinstance(e, Player):
                    grid[e.x, e.y, :] = [0, 0, 255]
                else:
                    grid[e.x, e.y, :] = [255, 0, 0]
        self.image = pg.surfarray.make_surface(grid.astype(np.uint8))
        self.image.set_colorkey((1,1,1))
        self.image = pg.transform.scale_by(self.image, self.scale)

class GameInterface:
    def __init__(self):
        pg.init()
        self.screen = pg.display.set_mode(SCREEN_SHAPE)
        self.clock = pg.time.Clock()
        self.font = pg.font.Font()
        self.logic = GameLogic(self)
        self.sprite_group = pg.sprite.Group()
        self.ui_group = pg.sprite.Group()
        self.tilesheet = pg.image.load('32rogues/tiles.png').convert_alpha()
        self.hpbar = HPBar(self.ui_group, self.logic, self)
        self.log = MessageLog(self.ui_group, self.logic, self)
        self.minimap = Minimap(self.ui_group, self.logic)
        self.init_sprites()

    def init_sprites(self):
        for x in range(MAP_SHAPE[0]):
            for y in range(MAP_SHAPE[1]):
                TileSprite(self.sprite_group, self, self.logic, x, y)
        for e in self.logic.entities:
            EntitySprite(self.sprite_group, self, self.logic, e)

    def grid_to_screen(self, i, j):
        pi, pj = self.logic.player.x, self.logic.player.y
        x = SCREEN_SHAPE[0]//2 + (i-pi) * TILE_SIZE
        y = SCREEN_SHAPE[1]//2 + (j-pj) * TILE_SIZE
        return (x, y)

    def screen_to_grid(self, x, y):
        pi, pj = self.logic.player.x, self.logic.player.y
        i = (x - SCREEN_SHAPE[0]//2) // TILE_SIZE + pi
        j = (y - SCREEN_SHAPE[1]//2) // TILE_SIZE + pj
        return (i, j)

    def handle_events(self):
        for event in pg.event.get():
            if event.type == pg.QUIT:
                self.running = False
            elif event.type == pg.KEYDOWN:
                if event.key in MOVE_KEYS.keys():
                    dx, dy = MOVE_KEYS[event.key]
                    self.logic.input_action = BumpAction(dx, dy, self.logic.player)
                elif event.key in WAIT_KEYS:
                    self.logic.input_action = WaitAction()

    def update(self):
        self.logic.update()

    def render(self):
        if isinstance(self.logic.last_action, AttackAction):
            Popup(self.ui_group, self.logic.last_action, self)
            self.logic.last_action = None
        self.sprite_group.update()
        self.ui_group.update()
        self.screen.fill("#000000")
        self.sprite_group.draw(self.screen)
        self.ui_group.draw(self.screen)
        pg.display.flip()
    
    def run(self):
        self.running = True
        while self.running:
            self.delta_time = self.clock.tick(FPS) / 1000
            self.handle_events()
            self.update()
            self.render()
        pg.quit()


if __name__ == '__main__':
    interface = GameInterface()
    interface.run()
