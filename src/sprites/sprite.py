import pygame as pg
from src.core.services import resource_manager
from src.utils import Position, PositionCamera
from typing import Optional
from src.utils import GameSettings

class Sprite:
    image: pg.Surface
    rect: pg.Rect
    detected: bool
    
    def __init__(self, img_path: str, size: tuple[int, int] | None = None):
        self.image = resource_manager.get_image(img_path)
        if size is not None:
            self.image = pg.transform.scale(self.image, size)
        self.rect = self.image.get_rect()
         # Add proper attributes
        self.x = self.rect.x
        self.y = self.rect.y
        self.width = self.rect.width
        self.height = self.rect.height
        
        self.detected = False
        self.warning_sign = None
        
    def update(self, dt: float):
        pass

    def update_pos(self, pos: Position):
        self.x = round(pos.x)
        self.y = round(pos.y)
        self.rect.topleft = (self.x, self.y)

    def draw(self, screen: pg.Surface, camera: Optional[PositionCamera] = None):
        # Use camera transform if available
        draw_pos = (self.x, self.y)
        if camera is not None:
            draw_pos = camera.transform_position(Position(self.x, self.y))
        
        screen.blit(self.image, draw_pos)

        # Draw LOS rectangle if detected
        # Draw warning sign only (no LOS rectangle)
        if self.detected and self.warning_sign is not None:
            import time
    # Flashing effect
            if int(time.time() * 2) % 2:  
                self.warning_sign.draw(screen, camera)


        # Draw debug hitbox
        # if GameSettings.DRAW_HITBOXES:
        #     los_rect = self._get_los_rect()
        #     if camera is not None:
        #         los_rect = camera.transform_rect(los_rect)
        #     pg.draw.rect(screen, (255, 255, 0), los_rect, 1)

    def _get_los_rect(self):
        # Example: 3-tile radius around the sprite
        tile_size = 32  # or GameSettings.TILE_SIZE
        return pg.Rect(
            self.x - tile_size,
            self.y - tile_size,
            self.width + 2 * tile_size,
            self.height + 2 * tile_size
        )
        
    def draw_hitbox(self, screen: pg.Surface, camera: Optional[PositionCamera] = None):
        rect = self.rect
        if camera is not None:
            rect = camera.transform_rect(rect)
        pg.draw.rect(screen, (255, 0, 0), rect, 1)
        