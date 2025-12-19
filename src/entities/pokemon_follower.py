# src/entities/pokemon_follower.py
import pygame as pg
from pathlib import Path
from typing import Optional
from collections import deque

from src.utils import Position, PositionCamera, GameSettings


class PokemonFollower:
    """A Pokemon that follows the player around on the map."""
    
    def __init__(self, monster: dict, player_position: Position):
        self.monster = monster
        self.position = Position(player_position.x - GameSettings.TILE_SIZE, player_position.y)
        
        # Trail of positions the player has been - follower will follow this path
        self.position_trail: deque = deque(maxlen=20)
        
        # Sprite handling
        self.sprite: Optional[pg.Surface] = None
        self.sprite_size = GameSettings.TILE_SIZE
        self._load_sprite()
        
        # Animation
        self.animation_timer = 0.0
        self.animation_frame = 0
        self.animation_frames: list[pg.Surface] = []
        self._load_animation_frames()
        
        # Following behavior
        self.follow_distance = GameSettings.TILE_SIZE * 1.2  # Distance to maintain from player
        self.speed = 4.0 * GameSettings.TILE_SIZE  # Same as player speed
        
        # Flying behavior - check if Pokemon element is Flying
        self.is_flying = self.monster.get("element", "").lower() == "flying"
        self.float_offset = 0.0  # Current floating offset for flying Pokemon
        self.float_timer = 0.0  # Timer for floating animation
        
        # Shadow properties
        self.shadow_color = (0, 0, 0, 60)
        
    def _load_sprite(self):
        """Load the sprite for the follower Pokemon."""
        # First, try to use the existing sprite from the monster dict
        if self.monster.get("sprite") is not None:
            try:
                existing_sprite = self.monster["sprite"]
                if isinstance(existing_sprite, pg.Surface):
                    self.sprite = pg.transform.scale(existing_sprite, (self.sprite_size, self.sprite_size))
                    return
            except Exception:
                pass
        
        # Try loading from sprite_path
        try:
            sprite_path = self.monster.get("sprite_path", "")
            if sprite_path:
                if "menu_sprites" in sprite_path:
                    # Extract sprite number and load idle sprite
                    sprite_num = sprite_path.split("menusprite")[-1].split(".")[0]
                    sprite_sheet_path = str(Path("assets") / "images" / "sprites" / f"sprite{sprite_num}_idle.png")
                    sprite_sheet = pg.image.load(sprite_sheet_path).convert_alpha()
                    
                    # Extract first frame from sprite sheet (assumes 4 frames horizontally)
                    frame_width = sprite_sheet.get_width() // 4
                    frame_height = sprite_sheet.get_height()
                    frame_rect = pg.Rect(0, 0, frame_width, frame_height)
                    self.sprite = sprite_sheet.subsurface(frame_rect).copy()
                    self.sprite = pg.transform.scale(self.sprite, (self.sprite_size, self.sprite_size))
                    return
                else:
                    # Load from path directly
                    full_path = f"assets/images/{sprite_path}" if not sprite_path.startswith("assets/") else sprite_path
                    self.sprite = pg.image.load(full_path).convert_alpha()
                    self.sprite = pg.transform.scale(self.sprite, (self.sprite_size, self.sprite_size))
                    return
        except Exception:
            pass
        
        # Create placeholder if all else fails
        self.sprite = pg.Surface((self.sprite_size, self.sprite_size), pg.SRCALPHA)
        pg.draw.circle(self.sprite, (100, 200, 100), (self.sprite_size // 2, self.sprite_size // 2), self.sprite_size // 3)
    
    def _load_animation_frames(self):
        """Load animation frames for walking animation."""
        self.animation_frames = []
        try:
            sprite_path = self.monster.get("sprite_path", "")
            if sprite_path and "menu_sprites" in sprite_path:
                sprite_num = sprite_path.split("menusprite")[-1].split(".")[0]
                sprite_sheet_path = str(Path("assets") / "images" / "sprites" / f"sprite{sprite_num}_idle.png")
                sprite_sheet = pg.image.load(sprite_sheet_path).convert_alpha()
                
                frame_width = sprite_sheet.get_width() // 4
                frame_height = sprite_sheet.get_height()
                
                for i in range(4):
                    frame_rect = pg.Rect(i * frame_width, 0, frame_width, frame_height)
                    frame = sprite_sheet.subsurface(frame_rect).copy()
                    frame = pg.transform.scale(frame, (self.sprite_size, self.sprite_size))
                    self.animation_frames.append(frame)
        except Exception:
            pass
        
        # If no frames loaded, use static sprite as single frame
        if not self.animation_frames and self.sprite is not None:
            self.animation_frames = [self.sprite]
    
    def update(self, dt: float, player_position: Position):
        """Update follower position to follow the player."""
        # Add current player position to trail
        self.position_trail.append(Position(player_position.x, player_position.y))
        
        # Calculate distance to player
        dx = player_position.x - self.position.x
        dy = player_position.y - self.position.y
        distance = (dx ** 2 + dy ** 2) ** 0.5
        
        # Only move if player is far enough away
        if distance > self.follow_distance:
            # Move towards player
            if distance > 0:
                move_speed = self.speed * dt
                # Move faster if too far away
                if distance > self.follow_distance * 2:
                    move_speed *= 1.5
                
                self.position.x += (dx / distance) * move_speed
                self.position.y += (dy / distance) * move_speed
        
        # Update animation
        self.animation_timer += dt
        if self.animation_timer >= 0.15:  # 150ms per frame
            self.animation_timer = 0
            if self.animation_frames:
                self.animation_frame = (self.animation_frame + 1) % len(self.animation_frames)
        
        # Update floating animation for Flying type Pokemon
        if self.is_flying:
            import math
            self.float_timer += dt
            # Gentle up-and-down floating motion
            self.float_offset = math.sin(self.float_timer * 3) * 8  # 8 pixels amplitude
    
    def draw(self, screen: pg.Surface, camera: PositionCamera):
        """Draw the follower Pokemon."""
        # Calculate screen position
        screen_x = int(self.position.x - camera.x)
        screen_y = int(self.position.y - camera.y)
        
        # For non-flying Pokemon, draw at ground level (no offset)
        # For flying Pokemon, float above the ground
        sprite_y = screen_y
        if self.is_flying:
            sprite_y = screen_y - 20 + int(self.float_offset)  # Float 20 pixels above ground with animation
        
        # Draw shadow at the base of the sprite (always on ground level)
        shadow_width = int(self.sprite_size * 0.6)
        shadow_height = int(self.sprite_size * 0.2)
        shadow_surface = pg.Surface((shadow_width, shadow_height), pg.SRCALPHA)
        pg.draw.ellipse(shadow_surface, self.shadow_color, (0, 0, shadow_width, shadow_height))
        shadow_x = screen_x + (self.sprite_size - shadow_width) // 2
        # Shadow at the bottom of the sprite area (ground level)
        shadow_y = screen_y + self.sprite_size - shadow_height
        screen.blit(shadow_surface, (shadow_x, shadow_y))
        
        # Draw sprite at the appropriate height
        if self.animation_frames and len(self.animation_frames) > 0:
            current_frame = self.animation_frames[self.animation_frame % len(self.animation_frames)]
            screen.blit(current_frame, (screen_x, sprite_y))
        elif self.sprite is not None:
            screen.blit(self.sprite, (screen_x, sprite_y))
        else:
            # Fallback: draw a colored circle if no sprite is available
            pg.draw.circle(screen, (100, 200, 100), (screen_x + self.sprite_size // 2, sprite_y + self.sprite_size // 2), self.sprite_size // 3)
    
    def set_monster(self, monster: dict, player_position: Position):
        """Change the follower to a different monster."""
        self.monster = monster
        self.position = Position(player_position.x - GameSettings.TILE_SIZE, player_position.y)
        self._load_sprite()
        self._load_animation_frames()
        self.animation_frame = 0
        self.animation_timer = 0
        self.position_trail.clear()
        # Update flying status
        self.is_flying = self.monster.get("element", "").lower() == "flying"
        self.float_offset = 0.0
        self.float_timer = 0.0
