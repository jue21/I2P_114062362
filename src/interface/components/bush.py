import pygame as pg
from src.utils import Position, GameSettings

class Bush:
    def __init__(self, x: float, y: float):
        self.position = Position(x, y)
        self.rect = pg.Rect(x, y, GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
        # Bushes are already rendered as part of the tile layer, so we don't need a sprite
    
    def draw(self, screen: pg.Surface, camera=None):
        # Bushes are already drawn as part of the tile layer, so this is empty
        pass