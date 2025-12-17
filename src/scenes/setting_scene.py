'''
[TODO HACKATHON 5]
Try to mimic the menu_scene.py or game_scene.py to create this new scene
'''
import pygame as pg
from typing import override

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
from src.core.services import scene_manager, sound_manager
from src.interface.components import component

class SettingScene(Scene):
    # Background Image
    background: BackgroundSprite
    # Buttons
    back_button: Button

    def __init__(self):
        super().__init__()
        # Load background image
        self.background = BackgroundSprite("backgrounds/background1.png")

        # Position for buttons
        px, py = GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT * 3 // 4

        # Back button
        self.back_button = Button(
            img_path="UI/button_back.png",
            img_hovered_path="UI/button_back_hover.png",
            x=px - 50, y=py, width=100, height=100,
            on_click=lambda: scene_manager.change_scene("menu")
        )

        # --- Overlay box ---
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        overlay_w, overlay_h = 500, 350  # size of overlay box
        self.overlay_box_rect = pg.Rect(
            (sw - overlay_w) // 2, (sh - overlay_h) // 2, overlay_w, overlay_h
        )

    @override
    def enter(self):
        # Play background music for settings scene
        sound_manager.play_bgm("RBY 135 To Bill_s Origin From Cerulean (Route 24).ogg")

    @override
    def exit(self):
        pass

    @override
    def update(self, dt: float):
        # Update back button
        self.back_button.update(dt)

    @override
    def draw(self, screen: pg.Surface):
        # Draw background
        self.background.draw(screen)

        # --- Pixel-art overlay box ---
        box_color = (255, 165, 0)        # orange
        border_color = (200, 120, 0)     # darker orange border
        highlight_color = (255, 200, 100) # top-left highlight

    # Draw main box
        pg.draw.rect(screen, box_color, self.overlay_box_rect)

    # Draw border
        pg.draw.rect(screen, border_color, self.overlay_box_rect, width=1)

    # Draw top-left highlight for pixel style
        pg.draw.line(screen, highlight_color, 
                    (self.overlay_box_rect.left, self.overlay_box_rect.top), 
                    (self.overlay_box_rect.right-1, self.overlay_box_rect.top))  # top
        pg.draw.line(screen, highlight_color, 
                    (self.overlay_box_rect.left, self.overlay_box_rect.top), 
                    (self.overlay_box_rect.left, self.overlay_box_rect.bottom-1))  # left

    # --- Overlay title ---
        font_path = "assets/fonts/Minecraft.ttf"
        font_med = pg.font.Font(font_path, 24)
        title = font_med.render("Settings", True, (20, 20, 20))
        screen.blit(title, (self.overlay_box_rect.x + 4, self.overlay_box_rect.y + 4))

        # Draw back button
        self.back_button.draw(screen)

