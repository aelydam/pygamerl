import pygame as pg

import actions
import assets
import comp
import consts
import entities
import game_interface
import gui_elements
import map_renderer
import maps
import ui_elements


class InGameState(game_interface.State):
    def __init__(self, interface: game_interface.GameInterface):
        self.interface = interface
        self.logic = interface.logic
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        font = interface.font
        self.hpbar = ui_elements.HPBar(self.ui_group, self.logic, font)
        self.log = ui_elements.MessageLog(self.ui_group, self.logic, font)
        self.minimap = ui_elements.Minimap(self.ui_group, self.logic)
        self.map_renderer = map_renderer.MapRenderer(interface)
        self.hud = ui_elements.StatsHUD(
            self.ui_group,
            self.interface,
            {
                "Depth": lambda: self.map_renderer.depth,
                "Turn": lambda: self.logic.turn_count,
                "Played": lambda: f"{self.logic.played_time // 3600:0.0f}:{self.logic.played_time // 60 % 60:0.0f}:{self.logic.played_time % 60:02.0f}",
                "FPS": lambda: int(self.interface.clock.get_fps()),
            },
        )

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key in consts.MOVE_KEYS.keys():
                dx, dy = consts.MOVE_KEYS[event.key]
                action = actions.BumpAction(self.logic.player, (dx, dy))
                if event.mod & pg.KMOD_SHIFT:
                    self.logic.continuous_action = action
                else:
                    self.logic.input_action = action
            elif event.key == pg.K_ESCAPE:
                self.logic.input_action = None
                self.logic.continuous_action = None
                self.interface.push(GameMenuState(self))
            elif event.key == pg.K_RETURN:
                self.logic.input_action = actions.Interact(self.logic.player)
                self.logic.continuous_action = None
            elif event.key == pg.K_l:
                self.logic.input_action = actions.ToggleTorch(
                    self.logic.player, self.logic.player
                )
                self.logic.continuous_action = None
            elif event.key in consts.WAIT_KEYS:
                self.logic.input_action = actions.WaitAction(self.logic.player)
                self.logic.continuous_action = None
            elif event.key == pg.K_m:
                self.interface.push(MapState(self.interface))
            elif event.key == pg.K_x:
                if event.mod & pg.KMOD_SHIFT:
                    self.logic.input_action = actions.MagicMap(self.logic.player)
                else:
                    self.logic.continuous_action = actions.ExploreAction(
                        self.logic.player
                    )
        elif event.type == pg.MOUSEBUTTONUP:
            if event.button == 3:
                self.logic.input_action = None
                self.logic.continuous_action = None
                return
            if event.button != 1:
                return
            if self.minimap.rect.collidepoint(*event.pos):
                return self.interface.push(MapState(self.interface))
            x, y = self.map_renderer.screen_to_grid(event.pos[0], event.pos[1])
            if not maps.is_explored(self.logic.map, (x, y)):
                return
            player = self.logic.player
            px, py = player.components[comp.Position].xy
            if x == px and y == py:
                self.logic.input_action = actions.WaitAction(player)
                return
            if (x - px) ** 2 + (y - py) ** 2 <= 2:
                self.logic.input_action = actions.BumpAction.to(player, (x, y))
            else:
                self.logic.continuous_action = actions.MoveToAction(player, (x, y))

    def update(self):
        self.logic.update()
        if not entities.is_alive(self.logic.player):
            self.interface.push(GameOverState(self))
            return
        if isinstance(self.logic.last_action, actions.AttackAction):
            ui_elements.Popup(
                self.map_renderer, self.logic.last_action, self.interface.font
            )
            self.logic.last_action = None

    def render(self, screen: pg.Surface):
        self.map_renderer.update()
        self.ui_group.update()
        screen.fill(consts.BACKGROUND_COLOR)
        self.map_renderer.draw(screen)
        self.ui_group.draw(screen)


class GameOverState(game_interface.State):
    def __init__(self, parent: InGameState):
        self.parent = parent
        self.interface = parent.interface
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        font = assets.font(consts.FONTNAME, consts.FONTSIZE * 3)
        self.text_surface = font.render(
            "GAME OVER", False, consts.GAMEOVER_TEXT_COLOR, None
        )
        self.text_surface = pg.transform.scale_by(self.text_surface, 2)
        self.menu = gui_elements.Menu(self.ui_group, ["New Game", "Main Menu", "Quit"])

    def update(self):
        w, h = self.interface.screen.size
        self.menu.rect.center = (w // 2, h * 2 // 3)
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        self.parent.render(screen)
        screen.fill(consts.UNEXPLORED_TINT, special_flags=pg.BLEND_MULT)
        pos = (screen.width // 2, screen.height // 3)
        rect = self.text_surface.get_rect(center=pos)
        screen.blit(self.text_surface, rect)
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key == pg.K_ESCAPE:
                self.main_menu()
            elif event.key in (pg.K_RETURN, pg.K_SPACE):
                self.select()
            else:
                self.menu.on_keyup(event.key)
        elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
            self.menu.update()
            self.select()

    def select(self):
        item = self.menu.items[self.menu.selected_index].lower()
        match item:
            case "new game":
                self.new_game()
            case "main menu":
                self.main_menu()
            case "quit":
                self.interface.clear()

    def main_menu(self):
        self.interface.logic.new_game()
        self.interface.reset(TitleState(self.interface))

    def new_game(self):
        self.interface.logic.new_game()
        while (
            not isinstance(self.interface.state, TitleState)
            and self.interface.state is not None
        ):
            self.interface.pop()
        self.interface.push(InGameState(self.interface))


class MapState(game_interface.State):
    def __init__(self, interface: game_interface.GameInterface):
        self.interface = interface
        self.logic = interface.logic
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        max_depth = self.logic.reg[None].components.get(comp.MaxDepth, 0)
        self.menu = gui_elements.Menu(
            self.ui_group, [f"Level {i}" for i in range(max_depth + 1)], 16
        )
        self.menu.rect.x = consts.TILE_SIZE // 2
        scale = min(
            (consts.SCREEN_SHAPE[0] - consts.TILE_SIZE - self.menu.width)
            // consts.MAP_SHAPE[0],
            (consts.SCREEN_SHAPE[1] - consts.TILE_SIZE) // consts.MAP_SHAPE[1],
        )
        self.map = ui_elements.Minimap(
            self.ui_group,
            self.logic,
            scale,
            follow_player=False,
            x=self.menu.width + consts.TILE_SIZE // 2,
        )
        self.menu.select(self.map.depth)
        self.menu.selected_index = self.map.depth

    def update(self):
        super().update()
        y = self.interface.screen.height // 2
        self.menu.rect.centery = y
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        screen.fill(consts.BACKGROUND_COLOR)
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE, pg.K_m):
                self.interface.pop()
            else:
                self.menu.on_keyup(event.key)
                self.map.depth = self.menu.selected_index
        elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
            if self.menu.rect.collidepoint(*event.pos):
                self.menu.update()
                self.map.depth = self.menu.selected_index
            else:
                self.interface.pop()


class TitleState(game_interface.State):
    def __init__(self, interface: game_interface.GameInterface):
        super().__init__(interface)
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        self.menu = gui_elements.Menu(
            self.ui_group,
            ["New Game", "Quit Game"],
        )
        font = assets.font(consts.FONTNAME, consts.FONTSIZE * 3)
        self.logo = font.render(consts.GAME_TITLE, False, "#FFFFFF").convert_alpha()

    def update(self):
        super().update()
        shape = self.interface.screen.size
        self.menu.rect.center = (shape[0] // 2, shape[1] * 2 // 3)
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        screen.fill(consts.BACKGROUND_COLOR)
        logo_center = (screen.width // 2, screen.height // 3)
        screen.blit(self.logo, self.logo.get_rect(center=logo_center))
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key == pg.K_RETURN:
                self.select()
            elif event.key == pg.K_ESCAPE:
                self.quit_game()
            else:
                self.menu.on_keyup(event.key)
        elif event.type == pg.MOUSEBUTTONUP and event.button == 1:
            if self.menu.rect.collidepoint(event.pos):
                self.menu.update()
                self.select()

    def select(self):
        item = self.menu.items[self.menu.selected_index].lower()
        match item:
            case "new game":
                self.new_game()
            case "quit game":
                self.quit_game()

    def new_game(self):
        self.interface.logic.new_game()
        self.interface.push(InGameState(self.interface))

    def quit_game(self):
        self.interface.pop()


class GameMenuState(game_interface.State):
    def __init__(self, parent: InGameState):
        self.parent = parent
        super().__init__(parent.interface)
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        self.menu = gui_elements.Menu(
            self.ui_group, ["Resume", "Map", "Message Log", "Quit"]
        )

    def update(self):
        super().update()
        w, h = self.interface.screen.size
        self.menu.rect.center = (w * 3 // 4, h // 2)
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        super().render(screen)
        self.parent.render(screen)
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key == pg.K_ESCAPE:
                self.interface.pop()
            elif event.key == pg.K_RETURN:
                self.select()
            else:
                self.menu.on_keyup(event.key)
        elif event.type == pg.MOUSEBUTTONUP:
            if not self.menu.rect.collidepoint(*event.pos):
                self.interface.pop()
            elif event.button == 1:
                self.menu.update()
                self.select()

    def select(self):
        item = self.menu.items[self.menu.selected_index].lower()
        match item:
            case "resume":
                self.interface.pop()
            case "quit":
                self.interface.reset(TitleState(self.interface))
            case "map":
                self.interface.push(MapState(self.interface))
            case "message log":
                self.interface.push(MessageLogState(self))


class MessageLogState(game_interface.State):
    def __init__(self, parent: InGameState):
        self.parent = parent
        super().__init__(parent.interface)
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        messages = self.interface.logic.message_log
        self.menu = gui_elements.Menu(self.ui_group, messages, 20, width=460)
        self.menu.select(-1)

    def update(self):
        super().update()
        w, h = self.interface.screen.size
        self.menu.rect.center = (w // 2, h // 2)
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        super().render(screen)
        self.parent.render(screen)
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key == pg.K_ESCAPE:
                self.interface.pop()
            else:
                self.menu.on_keyup(event.key)
        elif event.type == pg.MOUSEBUTTONUP:
            if not self.menu.rect.collidepoint(*event.pos):
                self.interface.pop()
