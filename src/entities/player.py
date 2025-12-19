from __future__ import annotations
import pygame as pg
from .entity import Entity
from src.core.services import input_manager
from src.utils import Position, PositionCamera, GameSettings, Logger, Direction
from src.core import GameManager
import math
from typing import override

class Player(Entity):
    speed: float = 4.0 * GameSettings.TILE_SIZE
    sprint_multiplier: float = 2.0  # Sprint speed multiplier
    game_manager: GameManager
    is_moving: bool = False
    
    # Jump properties
    is_jumping: bool = False
    jump_height: float = 20.0  # Max height of jump in pixels
    jump_duration: float = 0.4  # Total jump duration in seconds
    jump_timer: float = 0.0
    jump_offset: float = 0.0  # Current vertical offset for jump animation

    def __init__(self, x: float, y: float, game_manager: GameManager) -> None:
        super().__init__(x, y, game_manager)
        self.is_jumping = False
        self.jump_timer = 0.0
        self.jump_offset = 0.0

    def get_rect(self) -> pg.Rect:
        return pg.Rect(self.position.x, self.position.y, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)

    @override
    def update(self, dt: float) -> None:
        dis = Position(0, 0)

        # --- Movement input ---
        if input_manager.key_down(pg.K_LEFT) or input_manager.key_down(pg.K_a):
            dis.x -= 1
        if input_manager.key_down(pg.K_RIGHT) or input_manager.key_down(pg.K_d):
            dis.x += 1
        if input_manager.key_down(pg.K_UP) or input_manager.key_down(pg.K_w):
            dis.y -= 1
        if input_manager.key_down(pg.K_DOWN) or input_manager.key_down(pg.K_s):
            dis.y += 1

        # --- Update direction based on input ---
        if dis.x > 0:
            self._set_direction("right")
        elif dis.x < 0:
            self._set_direction("left")
        elif dis.y > 0:
            self._set_direction("down")
        elif dis.y < 0:
            self._set_direction("up")

        # --- Check for jump ---
        if input_manager.key_pressed(pg.K_j) and not self.is_jumping:
            self.is_jumping = True
            self.jump_timer = 0.0
        
        # --- Update jump animation ---
        if self.is_jumping:
            self.jump_timer += dt
            if self.jump_timer >= self.jump_duration:
                self.is_jumping = False
                self.jump_timer = 0.0
                self.jump_offset = 0.0
            else:
                # Use sine curve for smooth jump arc
                progress = self.jump_timer / self.jump_duration
                self.jump_offset = -math.sin(progress * math.pi) * self.jump_height

        # --- Check for sprint ---
        current_speed = self.speed
        if input_manager.key_down(pg.K_LSHIFT) or input_manager.key_down(pg.K_RSHIFT):
            current_speed *= self.sprint_multiplier

        # --- Normalize and scale ---
        length = math.hypot(dis.x, dis.y)
        self.is_moving = length > 0
        if length > 0:
            dis.x = (dis.x / length) * current_speed * dt
            dis.y = (dis.y / length) * current_speed * dt

        # --- Apply movement separately for X and Y ---
        # --- X axis ---
        prev_x = self.position.x
        self.position.x += dis.x
        self.animation.update_pos(self.position)

        if self.game_manager.current_map.check_collision(self.animation.rect) or \
            any(self.animation.rect.colliderect(npc.animation.rect) for npc in self.game_manager.current_enemy_trainers) or \
            any(self.animation.rect.colliderect(shopkeeper.animation.rect) for shopkeeper in self.game_manager.current_map.shopkeepers):
            self.position.x = self._snap_to_grid(prev_x)
            self.animation.update_pos(self.position)

        # --- Y axis ---
        prev_y = self.position.y
        self.position.y += dis.y
        self.animation.update_pos(self.position)

        if self.game_manager.current_map.check_collision(self.animation.rect) or \
            any(self.animation.rect.colliderect(npc.animation.rect) for npc in self.game_manager.current_enemy_trainers) or \
            any(self.animation.rect.colliderect(shopkeeper.animation.rect) for shopkeeper in self.game_manager.current_map.shopkeepers):
            self.position.y = self._snap_to_grid(prev_y)
            self.animation.update_pos(self.position)

        # Clamp position to stay within map bounds for tile1.tmx
        current_map = self.game_manager.current_map
        if self.game_manager.current_map_key == "tile1.tmx":
            # Clamp x position to stay within tile1.tmx bounds - prevent going out of bounds
            if self.position.x < 0:
                self.position.x = 0
                self.animation.update_pos(self.position)
                Logger.info(f"Player clamped at left edge of tile1.tmx (x=0)")
                return  # Don't continue, just clamp and return
            map_pixel_width = current_map.tmxdata.width * GameSettings.TILE_SIZE
            if self.position.x >= map_pixel_width - GameSettings.TILE_SIZE:
                self.position.x = map_pixel_width - GameSettings.TILE_SIZE
                self.animation.update_pos(self.position)
                Logger.info(f"Player clamped at right edge of tile1.tmx (x={self.position.x})")
                return  # Don't continue, just clamp and return
        elif self.position.x < 0 and self.game_manager.current_map_key == "map.tmx":
            # Only teleport to tile1.tmx from map.tmx
            Logger.info(f"Player went out of bounds left (x={self.position.x}), teleporting to tile1.tmx")
            self.game_manager.switch_map("tile1.tmx")
            return

        # Check teleportation
        tp = self.game_manager.current_map.check_teleport(self.position)
        if tp:
            dest = tp.destination
            self.game_manager.switch_map(dest)
                
        super().update(dt)

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        # Apply jump offset to draw position
        if self.is_jumping and self.jump_offset != 0:
            # Draw shadow at ground level (not affected by jump)
            self.draw_shadow(screen, camera, y_offset=0)
            # Create a temporary position with jump offset for drawing character
            original_rect_y = self.animation.rect.y
            self.animation.rect.y += int(self.jump_offset)
            self.animation.draw(screen, camera)
            if GameSettings.DRAW_HITBOXES:
                self.animation.draw_hitbox(screen, camera)
            self.animation.rect.y = original_rect_y
        else:
            super().draw(screen, camera)
    
    def _set_direction(self, direction: str) -> None:
        """Update direction and switch animation based on direction string."""
        if direction == "right":
            self.direction = Direction.RIGHT
        elif direction == "left":
            self.direction = Direction.LEFT
        elif direction == "down":
            self.direction = Direction.DOWN
        elif direction == "up":
            self.direction = Direction.UP
        self.animation.switch(direction)
        
    @override
    def to_dict(self) -> dict[str, object]:
        return super().to_dict()
    
    @classmethod
    @override
    def from_dict(cls, data: dict[str, object], game_manager: GameManager) -> Player:
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, game_manager)
    

        #length = math.hypot(dis.x, dis.y)
        #if length != 0:
            #dis.x = dis.x / length* self.speed* dt    
            #dis.y = dis.y / length* self.speed* dt   
