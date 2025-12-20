from __future__ import annotations
import pygame as pg
from typing import override
from .entity import Entity
from src.core import GameManager
from src.utils import GameSettings, Direction, Position, PositionCamera


class Shopkeeper(Entity):
    """
    An NPC that sells and buys items.
    Synchronized with player's bag.
    """
    name: str
    shop_items: list[dict]  # Items available for purchase
    facing: Direction
    can_interact: bool

    def __init__(
        self,
        x: float,
        y: float,
        game_manager: GameManager,
        name: str = "Shopkeeper",
        facing: Direction | None = None,
        shop_items: list[dict] | None = None,
        sprite_path: str = "character/ow1.png"
    ) -> None:
        super().__init__(x, y, game_manager, sprite_path)
        self.name = name
        self.facing = facing or Direction.DOWN
        self.can_interact = True
        
        # Default shop items: name and price
        self.shop_items = shop_items or [
            {"name": "Heal Potion", "price": 5, "count": 10},
            {"name": "Strength Potion", "price": 12, "count": 6},
            {"name": "Defense Potion", "price": 12, "count": 6},
            {"name": "Super Potion", "price": 10, "count": 5},
            {"name": "Pokéball", "price": 20, "count": 15},
            {"name": "Great Ball", "price": 60, "count": 8},
            {"name": "Ultra Ball", "price": 120, "count": 5},
        ]
        
        self._set_direction(self.facing)

    def _set_direction(self, direction: Direction) -> None:
        """Set the direction the shopkeeper faces."""
        self.facing = direction
        direction_name = direction.name.lower()
        self.animation.switch(direction_name)

    @override
    def update(self, dt: float) -> None:
        super().update(dt)

    @override
    def draw(self, screen: pg.Surface, camera: PositionCamera) -> None:
        super().draw(screen, camera)

    def to_dict(self) -> dict[str, object]:
        return {
            "x": self.position.x / GameSettings.TILE_SIZE,
            "y": self.position.y / GameSettings.TILE_SIZE,
            "name": self.name,
            "facing": self.facing.name,
            "shop_items": self.shop_items,
            "sprite_path": "character/ow3.png"  # Default sprite for shopkeepers
        }

    @classmethod
    @override
    def from_dict(cls, data: dict, game_manager: GameManager) -> "Shopkeeper":
        facing_val = data.get("facing")
        facing: Direction | None = None
        if facing_val is not None:
            if isinstance(facing_val, str):
                facing = Direction[facing_val]
            elif isinstance(facing_val, Direction):
                facing = facing_val
        
        if facing is None:
            facing = Direction.DOWN
        
        name = data.get("name", "Shopkeeper")
        shop_items = data.get("shop_items", [])
        sprite_path = data.get("sprite_path", "character/ow3.png")
        
        return cls(
            data["x"] * GameSettings.TILE_SIZE,
            data["y"] * GameSettings.TILE_SIZE,
            game_manager,
            name,
            facing,
            shop_items,
            sprite_path
        )
