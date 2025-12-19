import pygame as pg

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button, Checkbox, Slider
from src.core.services import scene_manager, sound_manager, input_manager
from typing import override

class MenuScene(Scene):
    # Background Image
    background: BackgroundSprite
    # Buttons
    play_button: Button
    setting_button: Button
    # Banner
    banner: pg.Surface | None
    banner_font: pg.font.Font | None
    # Settings overlay
    overlay_open: bool
    
    def __init__(self):
        super().__init__()
        self.background = BackgroundSprite("backgrounds/background1.png")

        px, py = GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT * 3 // 4
        self.play_button = Button(
            "UI/button_play.png", "UI/button_play_hover.png",
            px + 50, py, 100, 100,
            lambda: scene_manager.change_scene("game")
        )
        self.setting_button = Button(
            "UI/button_setting.png", "UI/button_setting_hover.png",
            px - 150, py, 100, 100,
            lambda: self._open_overlay()
        )
        
        # Load banner
        self.banner = None
        self.banner_font = None
        try:
            self.banner = pg.image.load("assets/images/UI/raw/UI_Flat_Banner02a.png").convert_alpha()
            self.banner = pg.transform.scale(self.banner, (400, 150))
            self.banner_font = pg.font.Font("assets/fonts/Minecraft.ttf", 48)
        except Exception:
            try:
                self.banner_font = pg.font.Font(None, 48)
            except:
                pass
        
        # --- Settings overlay setup ---
        self.overlay_open = False
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        overlay_w, overlay_h = 500, 350
        self.overlay_box_rect = pg.Rect(
            (sw - overlay_w) // 2, (sh - overlay_h) // 2, overlay_w, overlay_h
        )
        
        # Fonts
        try:
            self._font_med = pg.font.Font("assets/fonts/Minecraft.ttf", 28)
        except:
            self._font_med = pg.font.Font(None, 28)
        
        # Dark overlay surface
        self._dark_surface = pg.Surface((sw, sh), pg.SRCALPHA)
        self._dark_surface.fill((0, 0, 0, 150))
        
        # Back button inside overlay
        back_w, back_h = 70, 70
        back_x = self.overlay_box_rect.x + (self.overlay_box_rect.width - back_w) // 2
        back_y = self.overlay_box_rect.y + self.overlay_box_rect.height - back_h - 20
        self.back_button = Button(
            "UI/button_back.png",
            "UI/button_back_hover.png",
            back_x, back_y,
            back_w, back_h,
            lambda: self._close_overlay()
        )
        
        # Checkbox for sound
        self.checkbox_sound = Checkbox(
            self.overlay_box_rect.x + 30,
            self.overlay_box_rect.y + 60,
            label="Mute",
            checked=True
        )
        
        # Slider for music volume
        self.slider_music = Slider(
            self.overlay_box_rect.x + 30,
            self.overlay_box_rect.y + 120,
            width=200,
            value=70
        )
    
    def _open_overlay(self):
        self.overlay_open = True
    
    def _close_overlay(self):
        self.overlay_open = False
        
    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 101 Opening (Part 1).ogg")
        pass

    @override
    def exit(self) -> None:
        pass

    @override
    def update(self, dt: float) -> None:
        if self.overlay_open:
            self.back_button.update(dt)
            self.checkbox_sound.update(dt)
            self.slider_music.update(dt)
            
            # Music slider changes volume
            sound_manager.set_bgm_volume(self.slider_music.value / 100)
            
            # Checkbox toggles music
            if self.checkbox_sound.checked:
                sound_manager.resume_all()
            else:
                sound_manager.pause_all()
            
            # ESC to close overlay
            if input_manager.key_pressed(pg.K_ESCAPE):
                self._close_overlay()
        else:
            if input_manager.key_pressed(pg.K_SPACE):
                scene_manager.change_scene("game")
                return
            self.play_button.update(dt)
            self.setting_button.update(dt)

    @override
    def draw(self, screen: pg.Surface) -> None:
        self.background.draw(screen)
        
        # Draw banner with "Pokemon" text
        if self.banner is not None:
            banner_x = GameSettings.SCREEN_WIDTH // 2 - self.banner.get_width() // 2
            banner_y = GameSettings.SCREEN_HEIGHT // 4 - self.banner.get_height() // 2
            screen.blit(self.banner, (banner_x, banner_y))
            
            if self.banner_font is not None:
                text_surface = self.banner_font.render("Pokemon", True, (255, 215, 0))  # Gold color
                text_x = GameSettings.SCREEN_WIDTH // 2 - text_surface.get_width() // 2
                text_y = banner_y + self.banner.get_height() // 2 - text_surface.get_height() // 1.5
                screen.blit(text_surface, (text_x, text_y))
        
        self.play_button.draw(screen)
        self.setting_button.draw(screen)
        
        # --- Draw overlay if open ---
        if self.overlay_open:
            # Darken background
            screen.blit(self._dark_surface, (0, 0))
            
            # Draw pixel-art style orange box
            box_color = (255, 165, 0)
            border_color = (200, 120, 0)
            highlight_color = (255, 200, 100)
            
            # Draw main box
            pg.draw.rect(screen, box_color, self.overlay_box_rect)
            
            # Draw border
            pg.draw.rect(screen, border_color, self.overlay_box_rect, width=1)
            
            # Draw top/left highlight
            pg.draw.line(screen, highlight_color, 
                        (self.overlay_box_rect.left, self.overlay_box_rect.top), 
                        (self.overlay_box_rect.right-1, self.overlay_box_rect.top))
            pg.draw.line(screen, highlight_color, 
                        (self.overlay_box_rect.left, self.overlay_box_rect.top), 
                        (self.overlay_box_rect.left, self.overlay_box_rect.bottom-1))
            
            # Draw overlay title
            title = self._font_med.render("Settings", True, (20, 20, 20))
            screen.blit(title, (self.overlay_box_rect.x + 4, self.overlay_box_rect.y + 4))
            
            # Draw components
            self.back_button.draw(screen)
            self.checkbox_sound.draw(screen)
            self.slider_music.draw(screen)

