import os

import pygame as pg
import tcod.ecs as ecs

import actions
import assets
import audio
import comp
import consts
import entities
import game_interface
import gui_elements
import items
import keybinds
import map_renderer
import maps
import ui_elements


class InGameState(game_interface.State):
    def __init__(self, parent: game_interface.GameInterface | game_interface.State):
        super().__init__(parent)
        self.logic = self.interface.logic
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        font = self.interface.font
        self.hpbar = ui_elements.Bar(
            self.ui_group,
            font,
            current_fun=lambda: self.logic.player.components.get(comp.HP, 0),
            max_fun=lambda: self.logic.player.components.get(comp.MaxHP, 0),
            label="HP",
        )
        self.hungerbar = ui_elements.Bar(
            self.ui_group,
            font,
            current_fun=lambda: entities.hunger(self.logic.player),
            max_fun=lambda: consts.MAX_HUNGER,
            y=self.hpbar.rect.bottom,
            good_color=consts.HPBAR_BAD_COLOR,
            bad_color=consts.HPBAR_GOOD_COLOR,
            bad_ratio=0.8,
            label="Hunger",
        )
        self.xpbar = ui_elements.Bar(
            self.ui_group,
            font,
            current_fun=lambda: entities.xp_in_current_level(self.logic.player),
            max_fun=lambda: entities.xp_to_next_level(self.logic.player),
            text_fun=lambda: str(self.logic.player.components.get(comp.Level, 1)),
            y=self.hungerbar.rect.bottom,
            good_color=consts.HPBAR_GOOD_COLOR,
            bad_color=consts.HPBAR_GOOD_COLOR,
            label="Level",
        )
        self.conditions = ui_elements.ConditionsHUD(
            self.ui_group,
            (self.xpbar.rect.x, self.xpbar.rect.bottom + 4),
            font,
            self.logic,
        )
        self.log = ui_elements.MessageLog(self.ui_group, self.logic, font)
        self.minimap = ui_elements.Minimap(self.ui_group, self.logic)
        self.map_renderer = map_renderer.MapRenderer(self.interface)
        self.map_renderer.center = self.logic.player.components[comp.Position].xy
        self.hud = ui_elements.StatsHUD(
            self.ui_group,
            self.interface,
            {
                "Depth": lambda: self.map_renderer.depth,
                "Pos": lambda: ",".join(
                    str(i) for i in self.logic.player.components[comp.Position].xy
                ),
                "AC": lambda: entities.armor_class(self.logic.player),
                "Hit": lambda: entities.attack_bonus(self.logic.player),
                "Dmg": lambda: entities.damage_dice(self.logic.player),
                "Money": lambda: f"${items.money(self.logic.player):.1f}",
                "Turn": lambda: self.logic.turn_count,
                "FPS": lambda: int(self.interface.clock.get_fps()),
            },
        )
        self.register_callbacks()
        self.update_bgm()

    def handle_event(self, event: pg.Event):
        action: actions.Action
        if event.type == pg.KEYUP:
            if event.key in keybinds.MOVE_KEYS.keys():
                dx, dy = keybinds.MOVE_KEYS[event.key]
                action = actions.BumpAction(self.logic.player, (dx, dy))
                if event.mod & pg.KMOD_SHIFT:
                    self.logic.continuous_action = action
                elif event.mod & pg.KMOD_ALT:
                    self.map_renderer.move_center((dx, dy))
                    self.map_renderer.cursor = self.map_renderer.center
                else:
                    self.logic.input_action = action
            elif event.key == pg.K_ESCAPE and self.logic.continuous_action is not None:
                self.logic.input_action = None
                self.logic.continuous_action = None
            elif event.mod & pg.KMOD_SHIFT and event.key in keybinds.ACTION_SHIFT_KEYS:
                self.logic.continuous_action = None
                action_class = keybinds.ACTION_SHIFT_KEYS[event.key]
                self.logic.input_action = action_class(self.logic.player)
            elif event.key in keybinds.ACTION_KEYS:
                self.logic.continuous_action = None
                action_class = keybinds.ACTION_KEYS[event.key]
                self.logic.input_action = action_class(self.logic.player)
            elif event.key in keybinds.CONTINUOUS_ACTION_KEYS:
                self.logic.input_action = None
                action_class = keybinds.CONTINUOUS_ACTION_KEYS[event.key]
                self.logic.continuous_action = action_class(self.logic.player)
            elif event.key in keybinds.STATE_KEYS:
                state = keybinds.STATE_KEYS[event.key]
                self.logic.input_action = None
                self.logic.continuous_action = None
                self.interface.push(state(self))

        elif event.type == pg.MOUSEBUTTONUP:
            if event.button == 3:
                self.logic.input_action = None
                self.logic.continuous_action = None
                return
            if event.button != 1:
                return
            if self.minimap.rect.collidepoint(*event.pos):
                return self.interface.push(MapState(self))
            x, y = self.map_renderer.screen_to_grid(event.pos[0], event.pos[1])
            if not maps.is_explored(self.logic.map, (x, y)):
                return
            player = self.logic.player
            px, py = player.components[comp.Position].xy
            if x == px and y == py:
                interaction = actions.Interact(player)
                if interaction.can():
                    self.logic.input_action = interaction
                else:
                    self.logic.input_action = actions.WaitAction(player)
                return
            if (x - px) ** 2 + (y - py) ** 2 <= 2:
                self.logic.input_action = actions.BumpAction.to(player, (x, y))
            else:
                self.logic.continuous_action = actions.MoveToAction(player, (x, y))

        elif event.type == pg.MOUSEMOTION:
            self.map_renderer.cursor = self.map_renderer.screen_to_grid(*event.pos)

    def update(self):
        self.logic.update()
        if not entities.is_alive(self.logic.player):
            self.interface.push(GameOverState(self))
            return
        if (
            isinstance(self.logic.last_action, actions.ActorAction)
            and self.logic.last_action.actor == self.logic.player
        ):
            self.map_renderer.center = self.logic.player.components[comp.Position].xy
            self.map_renderer.cursor = None

    def update_bgm(self):
        depth = self.logic.map.components[comp.Depth]
        for i in range(depth, -1, -1):
            if i in audio.DEPTH_BGM:
                bgm = audio.DEPTH_BGM[i]
                return self.interface.play_bgm(bgm)

    def popup_callback(self, action: actions.Damage | actions.Heal):
        ui_elements.Popup(self.map_renderer, action, self.interface.font)

    def stairs_callback(self, actions: actions.Descend | actions.Ascend):
        self.update_bgm()

    def sfx_callback(self, action: actions.Action):
        if hasattr(action, "sfx") and action.sfx != "":
            return self.interface.play_sfx(action.sfx)
        if action.__class__ in audio.ACTION_SFX:
            sfx = audio.ACTION_SFX[action.__class__]
            return self.interface.play_sfx(sfx)
        for a, sfx in audio.ACTION_SFX.items():
            if isinstance(action, a):
                return self.interface.play_sfx(sfx)

    def register_callbacks(self):
        self.logic.register_callback(actions.Damage, self.popup_callback)
        self.logic.register_callback(actions.Heal, self.popup_callback)
        for action_class in audio.ACTION_SFX.keys():
            self.logic.register_callback(action_class, self.sfx_callback)

    def render(self, screen: pg.Surface):
        self.log.rect.bottomleft = (8, screen.height - 8)
        self.map_renderer.update()
        self.ui_group.update()
        screen.fill(consts.BACKGROUND_COLOR)
        self.map_renderer.draw(screen)
        self.interface.logic.visual_metadata["screenshot"] = pg.surfarray.array2d(
            screen
        )
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
    def __init__(self, parent: game_interface.State):
        super().__init__(parent)
        self.logic = self.interface.logic
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
        self.parent.render(screen)
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
            ["New Game", "Last Game", "Load Game", "Quit Game"],
        )
        font = assets.font(consts.FONTNAME, consts.FONTSIZE * 3)
        self.logo = font.render(consts.GAME_TITLE, False, "#FFFFFF").convert_alpha()
        if len(self.interface.logic.list_savefiles()) > 0:
            self.menu.select(1)
        else:
            self.menu.disabled_indexes = {1, 2}
            self.menu.select(0)
            self.menu.redraw()
        self.interface.play_bgm(audio.TITLE_BGM)

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
            case "load game":
                files = self.interface.logic.list_savefiles()
                if len(files) > 0:
                    self.interface.push(LoadGameState(self))
            case "last game":
                files = self.interface.logic.list_savefiles()
                if len(files) > 0:
                    self.interface.logic.load_game(files[0])
                    self.interface.push(InGameState(self.interface))

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
            self.ui_group, ["Resume", "Inventory", "Map", "Message Log", "Quit"]
        )

    def update(self):
        super().update()
        w, h = self.interface.screen.size
        self.menu.rect.center = (w * 3 // 4, h // 2)
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        super().render(screen)
        self.parent.render(screen)
        if self.interface.state == self:
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
                self.interface.logic.save_game()
                self.interface.reset(TitleState(self.interface))
            case "map":
                self.interface.push(MapState(self))
            case "inventory":
                self.interface.push(InventoryState(self))
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


class InventoryState(game_interface.State):
    def __init__(self, parent: InGameState):
        self.parent = parent
        super().__init__(parent.interface)
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        self.menu = gui_elements.Menu(self.ui_group, [], 16, width=240)
        self.refresh()
        self.menu.select(0)

    @staticmethod
    def item_text(item: ecs.Entity) -> str:
        count = item.components.get(comp.Count, 1)
        name = items.display_name(item)
        equipped = " [E]" if items.is_equipped(item) else ""
        return f"{count}x {name}{equipped}"

    @staticmethod
    def item_icon(item: ecs.Entity) -> pg.Surface | None:
        if comp.Sprite not in item.components:
            return None
        spr = item.components[comp.Sprite]
        return assets.tile(spr.sheet, tuple(spr.tile))

    @staticmethod
    def item_sortkey(item: ecs.Entity) -> tuple:
        return (
            str(item.components.get(comp.EquipSlot, "Z")),
            items.display_name(item),
            100 - item.components.get(comp.Count, 1),
        )

    def update(self):
        super().update()
        logic = self.interface.logic
        if (
            len(logic.initiative) < 1
            or logic.current_entity != logic.player
            or len(logic.action_queue) > 0
            or logic.input_action is not None
        ):
            logic.update()
            self.refresh()
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
            elif event.key == pg.K_RETURN:
                self.select()
            elif event.key == pg.K_DELETE:
                self.drop()
            else:
                self.menu.on_keyup(event.key)
        elif event.type == pg.MOUSEBUTTONUP:
            if not self.menu.rect.collidepoint(*event.pos):
                self.interface.pop()
            elif self.menu.pressed_index == self.menu.selected_index:
                self.select()

    def refresh(self):
        self.items = sorted(
            list(items.inventory(self.interface.logic.player)), key=self.item_sortkey
        )
        names = [self.item_text(i) for i in self.items]
        icons = [self.item_icon(i) for i in self.items]
        self.menu.set_items(names, icons, True)

    def drop(self):
        if len(self.items) < 1:
            return
        item = self.items[self.menu.selected_index]
        player = self.interface.logic.player
        if items.is_equipped(item):
            self.interface.logic.input_action = actions.Unequip(player, item)
        else:
            self.interface.logic.input_action = actions.Drop(player, item)

    def select(self):
        if len(self.items) < 1:
            return
        item = self.items[self.menu.selected_index]
        player = self.interface.logic.player
        if items.is_equipped(item):
            self.interface.logic.input_action = actions.Unequip(player, item)
        elif items.is_equippable(item):
            self.interface.logic.input_action = actions.Equip(player, item)
        else:
            self.interface.logic.input_action = actions.Use(player, item)
            self.interface.pop()


class LoadGameState(game_interface.State):
    def __init__(self, parent: game_interface.State):
        super().__init__(parent)
        self.ui_group: pg.sprite.Group = pg.sprite.Group()
        self.files = self.interface.logic.list_savefiles()
        text, icons = self.item_lists()
        self.menu = gui_elements.Menu(
            self.ui_group, text, 6, 224, icons, lines_per_item=3
        )
        self.filename = ""
        self.background = pg.Surface(consts.SCREEN_SHAPE)
        self.load_btn = gui_elements.Button(self.ui_group, "Load", 224 // 3)
        self.delete_btn = gui_elements.Button(self.ui_group, "Delete", 224 // 3)

    def item_lists(self) -> tuple[list[str], list[pg.Surface | None]]:
        text_list: list[str] = []
        surf_list: list[pg.Surface | None] = []
        for fn in self.files:
            metadata = self.interface.logic.file_metadata(fn)
            last_played = metadata["last_played"]
            depth = metadata["depth"]
            level = metadata["player_level"]
            turns = metadata["turns"]
            money = metadata["money"]
            text = "\n".join(
                [
                    f"{last_played:%Y-%m-%d %H:%M}",
                    f"Lv:{level} Depth:{depth}",
                    f"Turn:{turns} Money:{money}",
                ]
            )
            text_list.append(text)
            if "player_sprite" not in metadata:
                surf_list.append(None)
            else:
                spr: comp.Sprite = metadata["player_sprite"]
                surf_list.append(assets.tile(spr.sheet, tuple(spr.tile)))
        return text_list, surf_list

    def update(self):
        super().update()
        if len(self.files) < 1:
            return
        shape = self.interface.screen.size
        self.menu.rect.midleft = (consts.TILE_SIZE, shape[1] // 2)
        self.load_btn.rect.topleft = self.menu.rect.bottomleft
        self.delete_btn.rect.topleft = self.load_btn.rect.topright
        filename = self.files[self.menu.selected_index]
        if filename != self.filename:
            self.metadata = self.interface.logic.file_metadata(filename)
            self.filename = filename
            if "screenshot" in self.metadata:
                pg.surfarray.blit_array(self.background, self.metadata["screenshot"])
            else:
                self.background.fill(consts.BACKGROUND_COLOR)
        self.ui_group.update()

    def render(self, screen: pg.Surface):
        screen.blit(self.background)
        self.ui_group.draw(screen)

    def handle_event(self, event: pg.Event):
        if event.type == pg.KEYUP:
            if event.key == pg.K_ESCAPE:
                self.interface.pop()
            elif event.key == pg.K_RETURN:
                self.select()
            elif event.key == pg.K_DELETE:
                self.delete_file()
            else:
                self.menu.on_keyup(event.key)

        elif event.type == pg.MOUSEBUTTONUP:
            if self.load_btn.rect.collidepoint(event.pos):
                if event.button == 1:
                    self.select()
            if self.delete_btn.rect.collidepoint(event.pos):
                if event.button == 1:
                    self.delete_file()
            elif self.menu.rect.collidepoint(event.pos):
                if self.menu.pressed_index == self.menu.selected_index:
                    self.select()
            else:
                self.interface.pop()

    def delete_file(self):
        filename = self.files[self.menu.selected_index]
        self.interface.logic.delete_game(filename)

        self.files = self.interface.logic.list_savefiles()
        text, icons = self.item_lists()
        if len(self.files) < 1:
            return self.interface.pop()
        if self.menu.selected_index >= len(self.files):
            self.menu.selected_index = len(self.files) - 1
        self.menu.set_items(text, icons, True)

    def select(self):
        filename = self.files[self.menu.selected_index]
        self.interface.logic.load_game(filename)
        self.interface.pop()
        self.interface.push(InGameState(self.interface))
