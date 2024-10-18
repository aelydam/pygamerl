import pygame as pg

import assets

BORDER_WIDTH = 2
BOX_PADDING = 4
BORDER_COLOR = "#DFEFD7"
BOX_BGCOLOR = "#4D494D"
BOX_FGCOLOR = "#AAAAAA"
FOCUS_BGCOLOR = "#6d696d"
FOCUS_FGCOLOR = "#FFFFFF"
SCROLLBAR_COLOR = "#DFEFD7"
SCROLLBAR_SIZE = 2
SCROLLBAR_PADDING = 1


def get_screen_scale() -> int:
    screen_size = pg.display.get_window_size()
    canvas_size = pg.display.get_surface().size
    return screen_size[0] // canvas_size[0]


def scaled_mouse_pos() -> tuple[int, int]:
    mouse_pos = pg.mouse.get_pos()
    scale = get_screen_scale()
    return (mouse_pos[0] // scale, mouse_pos[1] // scale)


class Box(pg.sprite.Sprite):
    def __init__(self, group: pg.sprite.Group, surface: pg.Surface | None):
        if surface is None:
            surface = pg.Surface((1, 1))
        self.group = group
        super().__init__(group)
        self.border = BORDER_WIDTH
        self.padding = BOX_PADDING
        self.bgcolor = BOX_BGCOLOR
        self.fgcolor = BOX_FGCOLOR
        self.border_color = BORDER_COLOR
        self.default_bgcolor = BOX_BGCOLOR
        self.default_fgcolor = BOX_FGCOLOR
        self.focus_bgcolor = FOCUS_BGCOLOR
        self.focus_fgcolor = FOCUS_FGCOLOR
        self.scrollbar_color = SCROLLBAR_COLOR
        self.scrollbar_size = SCROLLBAR_SIZE
        self.scrollbar_padding = SCROLLBAR_PADDING
        self.rect: pg.Rect = surface.get_rect(topleft=(0, 0))
        self.set_surface(surface)

    def set_surface(self, surface: pg.Surface):
        self._surface = surface
        w = self._surface.width + 2 * (self.border + self.padding)
        h = self._surface.height + 2 * (self.border + self.padding)
        self.rect = pg.Rect(self.rect.x, self.rect.y, w, h)
        self.image = pg.Surface((w, h)).convert_alpha()
        self.image.fill("#00000000")
        rect = pg.Rect(self.border, self.border, w - self.border, h - self.border)
        self.image.fill(self.bgcolor, rect)
        pg.draw.rect(
            self.image, self.border_color, (0, 0, w, h), self.border, self.border
        )
        self.image.blit(
            surface, (self.border + self.padding, self.border + self.padding)
        )


class Textbox(Box):
    def __init__(self, group: pg.sprite.Group, text: str, width: int = 96):
        super().__init__(group, None)
        self.width = width
        self.text: str | None = None
        self.set_text(text)

    def set_text(self, text: str, force: bool = False):
        if not force and text == self.text:
            return
        self.text = text
        font = assets.font()
        wraplength = self.width - 2 * (self.border + self.padding)
        text_surf = font.render(text, False, self.fgcolor, wraplength=wraplength)
        self._surface = pg.Surface((wraplength, text_surf.height)).convert_alpha()
        self._surface.fill("#00000000")

        parts = text.split("|")
        text_surf = font.render(parts[0], False, self.fgcolor, wraplength=wraplength)
        self._surface.blit(text_surf, (0, 0))
        if len(parts) > 1:
            text_surf = font.render(
                parts[1], False, self.fgcolor, wraplength=wraplength
            )
            self._surface.blit(text_surf, (wraplength - text_surf.width, 0))

        self.set_surface(self._surface)


class Button(Textbox):
    def __init__(self, group: pg.sprite.Group, text: str, width: int = 96):
        super().__init__(group, text, width)
        self.hovering = False
        self.text: str = text
        self.disabled = False
        self.selected = False

    def update(self, *args, **kwargs) -> None:
        mouse_pos = pg.mouse.get_pos()
        mouse_pressed = pg.mouse.get_pressed()
        hovering = not self.disabled and self.rect.collidepoint(*mouse_pos)
        pressed = hovering and mouse_pressed[0]
        if pressed or self.selected:
            bgcolor = self.focus_bgcolor
        else:
            bgcolor = self.default_bgcolor
        if hovering or self.selected:
            fgcolor = self.focus_fgcolor
        else:
            fgcolor = self.default_fgcolor
        self.hovering = True
        if bgcolor == self.bgcolor and fgcolor == self.fgcolor:
            return
        self.fgcolor = fgcolor
        self.bgcolor = bgcolor
        self.set_text(self.text, force=True)


class Menu(Box):
    def __init__(
        self,
        group: pg.sprite.Group,
        items: list[str],
        max_rows: int = 0,
        width: int = 96,
    ):
        super().__init__(group, None)
        self.width = width
        if max_rows < 1:
            max_rows = len(items)
        self.max_rows = max_rows
        self.items: list[str] = []
        self.scroll_index = 0
        self.selected_index = 0
        self.disabled = False
        self.pressed_index = -1
        self.set_items(items)
        self.redraw()

    def set_items(self, items: list, force: bool = False):
        if not force and items == self.items:
            return
        self.items = items
        self.redraw()

    def redraw(self):
        rows = self.max_rows
        if rows < 1:
            rows = len(self.items)
        font = assets.font()
        item_h = font.size("Hg")[1] + 2 * self.padding
        self.item_h = item_h
        w = self.width - 2 * self.border
        surface = pg.Surface((w, item_h * rows)).convert_alpha()
        surface.fill("#00000000")
        for i in range(rows):
            index = i + self.scroll_index
            if index < 0 or index >= len(self.items):
                break
            text = self.items[index]
            if index == self.selected_index:
                bgcolor = self.focus_bgcolor
                fgcolor = self.focus_fgcolor
            else:
                bgcolor = self.default_bgcolor
                fgcolor = self.default_fgcolor
            rect = pg.Rect(0, i * item_h, w, item_h)
            surface.fill(bgcolor, rect)
            text_surf = font.render(text, False, fgcolor)
            surface.blit(text_surf, (rect.x + self.padding, rect.y + self.padding))
        # Scrollbar
        if rows < len(self.items):
            scroll_item_h = (item_h * rows - 2 * self.scrollbar_padding) / len(
                self.items
            )
            scroll_h = int(rows * scroll_item_h) + 1
            scroll_x = int(self.scrollbar_padding + self.scroll_index * scroll_item_h)
            rect = pg.Rect(
                w - self.scrollbar_size - self.scrollbar_padding,
                scroll_x,
                self.scrollbar_size,
                scroll_h,
            )
            surface.fill(self.scrollbar_color, rect)
        self.set_surface(surface)

    def set_surface(self, surface: pg.Surface):
        padding = self.padding
        self.padding = 0
        super().set_surface(surface)
        self.padding = padding

    def update(self, *args, **kwargs):
        mouse_pos = pg.mouse.get_pos()
        mouse_pressed = pg.mouse.get_pressed()
        hovering = not self.disabled and self.rect.collidepoint(*mouse_pos)
        my = mouse_pos[1] - self.rect.y - self.border
        index = self.scroll_index + my // self.item_h
        pressed = hovering and mouse_pressed[0]
        clicked = not pressed and (index == self.pressed_index)
        if not hovering or index < 0 or index >= len(self.items):
            self.pressed_index = -1
            return
        if clicked:
            self.select(index)
            self.pressed_index = -1
        elif pressed:
            self.pressed_index = index

    def select(self, index: int):
        if index < 0:
            index = len(self.items) - 1
        elif index >= len(self.items):
            index = 0
        old_index = self.selected_index
        self.selected_index = index
        if index < self.scroll_index:
            self.scroll_index = index
        elif index >= self.scroll_index + self.max_rows:
            self.scroll_index = index - self.max_rows + 1
        if old_index != index:
            self.redraw()

    def select_delta(self, delta: int):
        self.select(self.selected_index + delta)

    def on_keyup(self, key: int):
        match key:
            case pg.K_DOWN:
                self.select_delta(1)
            case pg.K_UP:
                self.select_delta(-1)
            case pg.K_PAGEDOWN:
                index = min(len(self.items) - 1, self.scroll_index + self.max_rows)
                self.scroll_index = max(
                    0, min(index, len(self.items) - self.max_rows + 1)
                )
                self.select(index)
            case pg.K_PAGEUP:
                index = max(0, self.scroll_index - self.max_rows)
                self.scroll_index = max(
                    0, min(index, len(self.items) - self.max_rows + 1)
                )
                self.select(index)
