from __future__ import annotations
import pygame 
import random
from enum import Enum
from dataclasses import dataclass
from typing import override

from .entity import Entity
from src.sprites import Sprite
from src.core import GameManager
from src.core.services import input_manager, scene_manager
from src.utils import GameSettings, Direction, Position, PositionCamera
import pygame as pg


class EnemyTrainerClassification(Enum):
    STATIONARY = "stationary"

@dataclass
class IdleMovement:
    def update(self, enemy: "EnemyTrainer", dt: float) -> None:
        return

class EnemyTrainer(Entity):
    classification: EnemyTrainerClassification
    max_tiles: int | None
    _movement: IdleMovement
    warning_sign: Sprite
    detected: bool
    los_direction: Direction

    @override
    def __init__(
        self,
        x: float,
        y: float,
        game_manager: GameManager,
        classification: EnemyTrainerClassification = EnemyTrainerClassification.STATIONARY,
        max_tiles: int | None = 2,
        facing: Direction | None = None,
        name: str = "Trainer",
        sprite_path: str | None = None
    ) -> None:
        if sprite_path is None:
            character_files = [f"character/ow{i}.png" for i in range(1, 11)]
            sprite_path = random.choice(character_files)
        super().__init__(x, y, game_manager, sprite_path)
        self.name =name
        self.classification = classification
        self.max_tiles = max_tiles
        if classification == EnemyTrainerClassification.STATIONARY:
            self._movement = IdleMovement()
            if facing is None:
                raise ValueError("Idle EnemyTrainer requires a 'facing' Direction at instantiation")
            self._set_direction(facing)
        else:
            raise ValueError("Invalid classification")
        self.warning_sign = Sprite("exclamation.png", (GameSettings.TILE_SIZE // 2, GameSettings.TILE_SIZE // 2))
        self.warning_sign.update_pos(Position(x + GameSettings.TILE_SIZE // 4, y - GameSettings.TILE_SIZE // 2))
        self.detected = False

        self.alert_time = 0.0
        self.state = "idle"  # idle → alert → walking → battle
        self.walk_speed = 2 * GameSettings.TILE_SIZE

    def _face_player(self, player) -> None:
        """Face the player based on relative position."""
        dx = player.position.x - self.position.x
        dy = player.position.y - self.position.y

        if abs(dx) > abs(dy):
            self.direction = Direction.RIGHT if dx > 0 else Direction.LEFT
        else:
            self.direction = Direction.DOWN if dy > 0 else Direction.UP

    # Switch animation to the new direction
        self.animation.switch(self.direction.name.lower())
        self.los_direction = self.direction


    @override
    def update(self, dt: float) -> None:
        self._movement.update(self, dt)
    
        player = self.game_manager.player
        if player is None:
            self.detected = False
            self.state = "idle"
            return

        # Check if player is still in line of sight
        has_los = self._has_los_to_player()
        
        if self.state == "idle" and has_los:
            # Face the player
            self._face_player(player)
            # Start alert
            self.state = "alert"
            self.alert_time = 0.5  # show "!" for 0.5 seconds
            self.detected = True
            return

        if self.state == "alert":
            # If player moved out of sight, return to idle
            if not has_los:
                self.state = "idle"
                self.detected = False
                return
            
            self.alert_time -= dt

        
        
    @override
    def draw(self, screen: pygame.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)
        if self.detected:
            self.warning_sign.draw(screen, camera)
        # if GameSettings.DRAW_HITBOXES:
        #     los_rect = self._get_los_rect()
        #     if los_rect is not None:
        #         pygame.draw.rect(screen, (255, 255, 0), camera.transform_rect(los_rect), 1)

            if self.state == "alert" and self.warning_sign:
                import time
                if int(time.time() * 2) % 2:
                    if self.warning_sign:
                        self.warning_sign.draw(screen, camera)

    def _set_direction(self, direction: Direction) -> None:
        self.direction = direction
        if direction == Direction.RIGHT:
            self.animation.switch("right")
        elif direction == Direction.LEFT:
            self.animation.switch("left")
        elif direction == Direction.DOWN:
            self.animation.switch("down")
        else:
            self.animation.switch("up")
        self.los_direction = self.direction

    def _get_los_rect(self) -> pygame.Rect | None:
    # Width and height of the LOS rectangle
        los_length = 150
        if hasattr(self.animation, "current_frame"):
            width = self.animation.current_frame.get_width()
            height = self.animation.current_frame.get_height()
        else:
            width = height = GameSettings.TILE_SIZE  # fallback

        px, py = self.position.x, self.position.y

        if self.los_direction == Direction.UP:
            return pygame.Rect(
                px,
                py - los_length,
                width,
                los_length
            )
        elif self.los_direction == Direction.DOWN:
            return pygame.Rect(
                px,
                py + height,
                width,
                los_length
            )
        elif self.los_direction == Direction.LEFT:
            return pygame.Rect(
                px - los_length,
                py,
                los_length,
                height
            )
        elif self.los_direction == Direction.RIGHT:
            return pygame.Rect(
                px + width,
                py,
                los_length,
                height
            )
        return None


    def _has_los_to_player(self) -> bool:
        player = self.game_manager.player
        if player is None:
            self.detected = False
            return False
        los_rect = self._get_los_rect()
        if los_rect and los_rect.colliderect(player.get_rect()):
            self.detected = True
            return True
        else:
            self.detected = False
            return False
        
    @classmethod
    @override
    def from_dict(cls, data: dict, game_manager: GameManager) -> "EnemyTrainer":
        classification = EnemyTrainerClassification(data.get("classification", "stationary"))
        max_tiles = data.get("max_tiles")
        facing_val = data.get("facing")
        facing: Direction | None = None
        if facing_val is not None:
            if isinstance(facing_val, str):
                facing = Direction[facing_val]
            elif isinstance(facing_val, Direction):
                facing = facing_val

        name = data.get("name", "Trainer")
        sprite_path = None  # Always use random sprite selection for enemy trainers
        if facing is None and classification == EnemyTrainerClassification.STATIONARY:
            facing = Direction.DOWN
        return cls(
            data["x"] * GameSettings.TILE_SIZE,
            data["y"] * GameSettings.TILE_SIZE,
            game_manager,
            classification,
            max_tiles,
            facing,
            name,
            sprite_path
        )

    @override
    def to_dict(self) -> dict[str, object]:
        base: dict[str, object] = super().to_dict()
        base["classification"] = self.classification.value
        base["facing"] = self.direction.name
        base["max_tiles"] = self.max_tiles
        base["name"] = self.name
        base["sprite_path"] = "character/ow2.png"  # Default sprite for trainers
        return base