from __future__ import annotations
import pygame as pg
from src.core.services import input_manager
from typing import Callable
from .component import UIComponent


class NavigationButton(UIComponent):
    """Button specifically for navigation destinations in the navigation overlay."""
    
    def __init__(
        self,
        place_name: str,
        x: int,
        y: int,
        width: int,
        height: int,
        on_click: Callable[[], None] | None = None,
        font_size: int = 24
    ):
        self.place_name = place_name
        self.hitbox = pg.Rect(x, y, width, height)
        self.on_click = on_click
        
        # Colors
        self.color_default = (70, 70, 90)
        self.color_hover = (100, 100, 140)
        self.color_border = (200, 200, 220)
        self.color_text = (255, 255, 255)
        
        self.current_color = self.color_default
        self.is_hovered = False
        
        # Font
        try:
            self.font = pg.font.Font("assets/fonts/Minecraft.ttf", font_size)
        except:
            self.font = pg.font.Font(None, font_size)

    def handle_event(self, event: pg.event.Event):
        """Handle mouse events for the navigation button."""
        if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
            if self.hitbox.collidepoint(event.pos):
                from src.utils import Logger
                Logger.info(f"Navigation button clicked: {self.place_name}")
                if self.on_click:
                    self.on_click()
                else:
                    Logger.warning(f"No on_click handler for {self.place_name}")

    def update(self, dt: float) -> None:
        """Update button hover state based on mouse position."""
        if self.hitbox.collidepoint(input_manager.mouse_pos):
            self.is_hovered = True
            self.current_color = self.color_hover
            
            # Check for mouse click (like regular Button class)
            if input_manager.mouse_pressed(1) and self.on_click is not None:
                from src.utils import Logger
                Logger.info(f"Navigation button clicked (via update): {self.place_name}")
                self.on_click()
        else:
            self.is_hovered = False
            self.current_color = self.color_default

    def draw(self, screen: pg.Surface) -> None:
        """Draw the navigation button with place name."""
        # Draw button background
        pg.draw.rect(screen, self.current_color, self.hitbox)
        pg.draw.rect(screen, self.color_border, self.hitbox, 2)
        
        # DEBUG: Draw a bright outline if hovered
        if self.is_hovered:
            pg.draw.rect(screen, (255, 255, 0), self.hitbox, 4)
        
        # Draw place name text (centered)
        text_surface = self.font.render(self.place_name, True, self.color_text)
        text_rect = text_surface.get_rect(center=self.hitbox.center)
        screen.blit(text_surface, text_rect)
