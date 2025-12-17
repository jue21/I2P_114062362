import pygame as pg
from pytmx import load_pygame, TiledMap
from pathlib import Path
from .logger import Logger
import os

ASSETS_DIR = Path("assets")

def load_img(path: str) -> pg.Surface:
    Logger.info(f"Loading image: {path}")
    full_path = str(ASSETS_DIR / "images" / path)
    
    if not os.path.exists(full_path):
        Logger.warning(f"Image file not found: {path}. Creating placeholder.")
        # Create a placeholder surface
        placeholder = pg.Surface((100, 100))
        placeholder.fill((200, 100, 100))  # Brownish color for missing assets
        return placeholder
    
    try:
        img = pg.image.load(full_path)
        if not img:
            Logger.error(f"Failed to load image: {path}")
            placeholder = pg.Surface((100, 100))
            placeholder.fill((200, 100, 100))
            return placeholder
        return img.convert_alpha()
    except Exception as e:
        Logger.error(f"Error loading image {path}: {e}")
        placeholder = pg.Surface((100, 100))
        placeholder.fill((200, 100, 100))
        return placeholder

def load_sound(path: str) -> pg.mixer.Sound:
    Logger.info(f"Loading sound: {path}")
    full_path = str(ASSETS_DIR / "sounds" / path)
    
    if not os.path.exists(full_path):
        Logger.warning(f"Sound file not found: {path}. Creating silent placeholder.")
        # Create a silent sound (1 second of silence)
        return pg.mixer.Sound(buffer=bytes(44100 * 2))
    
    try:
        sound = pg.mixer.Sound(full_path)
        if not sound:
            Logger.error(f"Failed to load sound: {path}")
            return pg.mixer.Sound(buffer=bytes(44100 * 2))
        return sound
    except Exception as e:
        Logger.error(f"Error loading sound {path}: {e}")
        return pg.mixer.Sound(buffer=bytes(44100 * 2))

def load_font(path: str, size: int) -> pg.font.Font:
    Logger.info(f"Loading font: {path}")
    full_path = str(ASSETS_DIR / "fonts" / path)
    
    if not os.path.exists(full_path):
        Logger.warning(f"Font file not found: {path}. Using default font.")
        return pg.font.Font(None, size)
    
    try:
        font = pg.font.Font(full_path, size)
        if not font:
            Logger.error(f"Failed to load font: {path}")
            return pg.font.Font(None, size)
        return font
    except Exception as e:
        Logger.error(f"Error loading font {path}: {e}")
        return pg.font.Font(None, size)

def load_tmx(path: str) -> TiledMap:
    full_path = str(ASSETS_DIR / "maps" / path)
    if not os.path.exists(full_path):
        Logger.error(f"Map file not found: {path}")
        raise FileNotFoundError(f"Map file not found: {full_path}")
    tmxdata = load_pygame(full_path)
    if tmxdata is None:
        Logger.error(f"Failed to load map: {path}")
    return tmxdata
