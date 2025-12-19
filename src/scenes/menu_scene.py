import pygame as pg

from src.utils import GameSettings
from src.sprites import BackgroundSprite
from src.scenes.scene import Scene
from src.interface.components import Button
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
            lambda: scene_manager.change_scene("setting")
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
        
    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 101 Opening (Part 1).ogg")
        pass

    @override
    def exit(self) -> None:
        pass

    @override
    def update(self, dt: float) -> None:
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
                text_y = banner_y + self.banner.get_height() // 2 - text_surface.get_height() // 2
                screen.blit(text_surface, (text_x, text_y))
        
        self.play_button.draw(screen)
        self.setting_button.draw(screen)

