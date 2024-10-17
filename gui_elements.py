import pygame as pg

import assets

BORDER_WIDTH = 2
BOX_PADDING = 4
BORDER_COLOR = "#DFEFD7"
BOX_BGCOLOR = "#4D494D"
BOX_FGCOLOR = "#AAAAAA"
FOCUS_BGCOLOR = "#6d696d"
FOCUS_FGCOLOR = "#FFFFFF"


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
