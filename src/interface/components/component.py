import pygame as pg
from typing import Protocol

class UIComponent(Protocol):
    def update(self, dt: float) -> None: ...
    def draw(self, screen: pg.Surface) -> None: ...

MonsterInfoType = UIComponent
ItemInfoType = UIComponent

class Checkbox:
    def __init__(self, x, y, size=40, checked=False, label="", font=None):
        self.rect = pg.Rect(x, y, size, size)
        self.checked = checked
        self.label = label
        font_path = "assets/fonts/Minecraft.ttf"
        self.font = font or pg.font.Font(font_path, 24)
        self.hovered = False
        self.clicked = False
        
        # Load toggle images
        self.toggle_on_img = None
        self.toggle_off_img = None
        try:
            self.toggle_on_img = pg.image.load("assets/images/UI/raw/UI_Flat_ToggleOn01a.png").convert_alpha()
            self.toggle_on_img = pg.transform.scale(self.toggle_on_img, (size , size))
            self.toggle_off_img = pg.image.load("assets/images/UI/raw/UI_Flat_ToggleOff01a.png").convert_alpha()
            self.toggle_off_img = pg.transform.scale(self.toggle_off_img, (size , size))
            # Update rect width to match image
            self.rect.width = size * 2
        except Exception:
            pass  # Fall back to drawing if images fail to load

    def update(self, dt: float) -> None:
        mouse_pos = pg.mouse.get_pos()
        mouse_pressed = pg.mouse.get_pressed()
        self.hovered = self.rect.collidepoint(mouse_pos)

        # Toggle checked on click
        if self.hovered and mouse_pressed[0] and not self.clicked:
            self.checked = not self.checked
            self.clicked = True
        if not mouse_pressed[0]:
            self.clicked = False

    def draw(self, surface: pg.Surface) -> None:
        # Use toggle images if available
        if self.toggle_on_img and self.toggle_off_img:
            if self.checked:
                # Mute ON - no music playing (show OFF toggle visually)
                surface.blit(self.toggle_off_img, self.rect.topleft)
            else:
                # Mute OFF - music playing (show ON toggle visually)
                surface.blit(self.toggle_on_img, self.rect.topleft)
        else:
            # Fallback to drawing if images not loaded
            base_color = (255, 165, 0)
            border_color = (0, 0, 0)
            check_color = (0, 200, 0)
            hover_color = (255, 200, 100)

            pg.draw.rect(surface, base_color, self.rect)
            pg.draw.rect(surface, border_color, self.rect, 2)
            pg.draw.line(surface, hover_color, self.rect.topleft, (self.rect.right - 1, self.rect.top))
            pg.draw.line(surface, hover_color, self.rect.topleft, (self.rect.left, self.rect.bottom - 1))

            if not self.checked:
                pg.draw.line(surface, check_color, self.rect.topleft, self.rect.bottomright, 3)
                pg.draw.line(surface, check_color, self.rect.topright, self.rect.bottomleft, 3)

        # Draw label
        if self.label:
            label_surf = self.font.render(self.label, True, (20, 20, 20))
            surface.blit(label_surf, (self.rect.right + 6, self.rect.centery - label_surf.get_height() // 2))


class Slider:
    def __init__(self, x, y, width=200, min_val=0, max_val=100, value=50):
        self.rect = pg.Rect(x, y, width, 6)
        self.min_val = min_val
        self.max_val = max_val
        self.value = value
        self.handle_radius = 10
        self.dragging = False
        self.hovered = False

    def update(self, dt: float) -> None:
        mouse_pos = pg.mouse.get_pos()
        mouse_pressed = pg.mouse.get_pressed()

        # Compute handle position
        handle_x = self.rect.x + int((self.value - self.min_val) / (self.max_val - self.min_val) * self.rect.width)
        handle_y = self.rect.y + self.rect.height // 2
        handle_rect = pg.Rect(handle_x - self.handle_radius, handle_y - self.handle_radius,
                              self.handle_radius*2, self.handle_radius*2)

        self.hovered = handle_rect.collidepoint(mouse_pos)

        # Start dragging if clicked
        if self.hovered and mouse_pressed[0]:
            self.dragging = True
        if not mouse_pressed[0]:
            self.dragging = False

        # Update value while dragging
        if self.dragging:
            rel_x = max(0, min(mouse_pos[0] - self.rect.x, self.rect.width))
            self.value = self.min_val + (rel_x / self.rect.width) * (self.max_val - self.min_val)

    def draw(self, surface: pg.Surface) -> None:
        bar_color = (255, 255, 255)
        handle_color = (0, 255, 0) if not self.hovered else (255, 200, 0)
        # Draw bar
        pg.draw.rect(surface, bar_color, self.rect)
        # Draw handle
        handle_x = self.rect.x + int((self.value - self.min_val) / (self.max_val - self.min_val) * self.rect.width)
        handle_y = self.rect.y + self.rect.height // 2
        pg.draw.circle(surface, handle_color, (handle_x, handle_y), self.handle_radius)
