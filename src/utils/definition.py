from pygame import Rect
from .settings import GameSettings
from dataclasses import dataclass
from enum import Enum
from typing import overload, TypedDict, Protocol
import pygame as pg
import os

MouseBtn = int
Key = int

Direction = Enum('Direction', ['UP', 'DOWN', 'LEFT', 'RIGHT', 'NONE'])

# Pokemon Type System
class PokemonType(Enum):
    """Available Pokemon types/elements"""
    NORMAL = "Normal"
    FIRE = "Fire"
    WATER = "Water"
    GRASS = "Grass"
    ELECTRIC = "Electric"
    ICE = "Ice"
    FIGHTING = "Fighting"
    POISON = "Poison"
    GROUND = "Ground"
    FLYING = "Flying"
    PSYCHIC = "Psychic"
    BUG = "Bug"
    ROCK = "Rock"
    GHOST = "Ghost"
    DRAGON = "Dragon"
    DARK = "Dark"
    STEEL = "Steel"
    FAIRY = "Fairy"

# Type Effectiveness Matrix
# KEY: attacking type -> Dict[defending type] -> multiplier
TYPE_EFFECTIVENESS = {
    PokemonType.FIRE: {
        PokemonType.GRASS: 2.0,      # Fire is strong against Grass
        PokemonType.BUG: 2.0,
        PokemonType.STEEL: 2.0,
        PokemonType.ICE: 2.0,
        PokemonType.WATER: 0.5,      # Fire is weak against Water
        PokemonType.GROUND: 0.5,
        PokemonType.ROCK: 0.5,
    },
    PokemonType.WATER: {
        PokemonType.FIRE: 2.0,       # Water is strong against Fire
        PokemonType.GROUND: 2.0,
        PokemonType.ROCK: 2.0,
        PokemonType.GRASS: 0.5,      # Water is weak against Grass
        PokemonType.ELECTRIC: 0.5,
    },
    PokemonType.GRASS: {
        PokemonType.WATER: 2.0,      # Grass is strong against Water
        PokemonType.GROUND: 2.0,
        PokemonType.ROCK: 2.0,
        PokemonType.FIRE: 0.5,       # Grass is weak against Fire
        PokemonType.POISON: 0.5,
        PokemonType.FLYING: 0.5,
        PokemonType.BUG: 0.5,
    },
    PokemonType.ELECTRIC: {
        PokemonType.WATER: 2.0,      # Electric is strong against Water
        PokemonType.FLYING: 2.0,
        PokemonType.ICE: 2.0,
        PokemonType.GROUND: 0.0,     # Electric is ineffective against Ground
    },
    PokemonType.ICE: {
        PokemonType.GRASS: 2.0,
        PokemonType.FLYING: 2.0,
        PokemonType.GROUND: 2.0,
        PokemonType.DRAGON: 2.0,
        PokemonType.FIRE: 0.5,
        PokemonType.WATER: 0.5,
        PokemonType.ICE: 0.5,
        PokemonType.STEEL: 0.5,
    },
    PokemonType.FIGHTING: {
        PokemonType.NORMAL: 2.0,
        PokemonType.ICE: 2.0,
        PokemonType.ROCK: 2.0,
        PokemonType.DARK: 2.0,
        PokemonType.STEEL: 2.0,
        PokemonType.FLYING: 0.5,
        PokemonType.PSYCHIC: 0.5,
        PokemonType.FAIRY: 0.5,
    },
    PokemonType.POISON: {
        PokemonType.GRASS: 2.0,
        PokemonType.FAIRY: 2.0,
        PokemonType.POISON: 0.5,
        PokemonType.GROUND: 0.5,
        PokemonType.ROCK: 0.5,
    },
    PokemonType.GROUND: {
        PokemonType.FIRE: 2.0,
        PokemonType.ELECTRIC: 2.0,
        PokemonType.POISON: 2.0,
        PokemonType.ROCK: 2.0,
        PokemonType.GRASS: 0.5,
        PokemonType.BUG: 0.5,
        PokemonType.FLYING: 0.0,     # Ground is ineffective against Flying
    },
    PokemonType.FLYING: {
        PokemonType.FIGHTING: 2.0,
        PokemonType.BUG: 2.0,
        PokemonType.GRASS: 2.0,
        PokemonType.ROCK: 0.5,
        PokemonType.STEEL: 0.5,
        PokemonType.ELECTRIC: 0.5,
    },
    PokemonType.PSYCHIC: {
        PokemonType.FIGHTING: 2.0,
        PokemonType.POISON: 2.0,
        PokemonType.DARK: 0.5,
        PokemonType.PSYCHIC: 0.5,
        PokemonType.STEEL: 0.5,
    },
    PokemonType.BUG: {
        PokemonType.GRASS: 2.0,
        PokemonType.PSYCHIC: 2.0,
        PokemonType.DARK: 2.0,
        PokemonType.FIRE: 0.5,
        PokemonType.FIGHTING: 0.5,
        PokemonType.POISON: 0.5,
        PokemonType.FLYING: 0.5,
        PokemonType.GHOST: 0.5,
        PokemonType.STEEL: 0.5,
        PokemonType.FAIRY: 0.5,
    },
    PokemonType.ROCK: {
        PokemonType.FIRE: 2.0,
        PokemonType.ICE: 2.0,
        PokemonType.FLYING: 2.0,
        PokemonType.BUG: 2.0,
        PokemonType.WATER: 0.5,
        PokemonType.GRASS: 0.5,
        PokemonType.FIGHTING: 0.5,
        PokemonType.GROUND: 0.5,
        PokemonType.STEEL: 0.5,
    },
    PokemonType.GHOST: {
        PokemonType.GHOST: 2.0,
        PokemonType.PSYCHIC: 2.0,
        PokemonType.DARK: 0.5,
    },
    PokemonType.DRAGON: {
        PokemonType.DRAGON: 2.0,
        PokemonType.STEEL: 0.5,
        PokemonType.FAIRY: 0.0,      # Dragon is ineffective against Fairy
    },
    PokemonType.DARK: {
        PokemonType.GHOST: 2.0,
        PokemonType.PSYCHIC: 2.0,
        PokemonType.FIGHTING: 0.5,
        PokemonType.DARK: 0.5,
        PokemonType.FAIRY: 0.5,
    },
    PokemonType.STEEL: {
        PokemonType.ICE: 2.0,
        PokemonType.ROCK: 2.0,
        PokemonType.FAIRY: 2.0,
        PokemonType.FIRE: 0.5,
        PokemonType.WATER: 0.5,
        PokemonType.ELECTRIC: 0.5,
        PokemonType.GRASS: 0.5,
        PokemonType.PSYCHIC: 0.5,
        PokemonType.ICE: 0.5,
        PokemonType.ROCK: 0.5,
        PokemonType.FLYING: 0.5,
        PokemonType.POISON: 0.0,     # Steel is immune to Poison
        PokemonType.STEEL: 0.5,
    },
    PokemonType.FAIRY: {
        PokemonType.FIGHTING: 2.0,
        PokemonType.DRAGON: 2.0,
        PokemonType.DARK: 2.0,
        PokemonType.POISON: 0.5,
        PokemonType.STEEL: 0.5,
    },
    # Normal type doesn't have special effectiveness
    PokemonType.NORMAL: {},
}

def get_type_effectiveness(attacking_type: str, defending_type: str) -> float:
    """
    Get the effectiveness multiplier for an attack.
    
    Args:
        attacking_type: Type of the attacking Pokemon (as string)
        defending_type: Type of the defending Pokemon (as string)
    
    Returns:
        Effectiveness multiplier (0.0 = immune, 0.5 = not very effective, 1.0 = normal, 2.0 = super effective)
    """
    try:
        # Convert string type names to PokemonType enum
        atk_type = PokemonType(attacking_type)
        def_type = PokemonType(defending_type)
        
        # Get effectiveness from the matrix
        if atk_type in TYPE_EFFECTIVENESS:
            return TYPE_EFFECTIVENESS[atk_type].get(def_type, 1.0)
        return 1.0
    except (ValueError, KeyError):
        # If type is not recognized, return normal effectiveness
        return 1.0


@dataclass
class Position:
    x: float
    y: float
    
    def copy(self):
        return Position(self.x, self.y)
        
    def distance_to(self, other: "Position") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5
        
@dataclass
class PositionCamera:
    x: int
    y: int
    
    def copy(self):
        return PositionCamera(self.x, self.y)
        
    def to_tuple(self) -> tuple[int, int]:
        return (self.x, self.y)
        
    def transform_position(self, position: Position) -> tuple[int, int]:
        return (int(position.x) - self.x, int(position.y) - self.y)
        
    def transform_position_as_position(self, position: Position) -> Position:
        return Position(int(position.x) - self.x, int(position.y) - self.y)
        
    def transform_rect(self, rect: Rect) -> Rect:
        return Rect(rect.x - self.x, rect.y - self.y, rect.width, rect.height)

@dataclass
class Teleport:
    pos: Position
    destination: str
    
    @overload
    def __init__(self, x: int, y: int, destination: str) -> None: ...
    @overload
    def __init__(self, pos: Position, destination: str) -> None: ...

    def __init__(self, *args, **kwargs):
        if isinstance(args[0], Position):
            self.pos = args[0]
            self.destination = args[1]
        else:
            x, y, dest = args
            self.pos = Position(x, y)
            self.destination = dest
    
    def to_dict(self):
        return {
            "x": self.pos.x // GameSettings.TILE_SIZE,
            "y": self.pos.y // GameSettings.TILE_SIZE,
            "destination": self.destination
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(data["x"] * GameSettings.TILE_SIZE, data["y"] * GameSettings.TILE_SIZE, data["destination"])
    
class Monster(TypedDict):
    name: str
    hp: int
    max_hp: int
    level: int
    sprite_path: str
    sprite: pg.Surface
    element: str  # Type/element of the Pokemon (e.g., "Fire", "Water", "Grass")
    evolved_form: str  # Name of evolved form (empty string if final form)
    evolution_level: int  # Level required to evolve (0 if final form)

class Item(TypedDict):
    name: str
    count: int
    sprite_path: str
    sprite: pg.Surface
    item_type: str  # "heal", "strength", or "defense"

class Monster:
    def __init__(self, data: dict):
        self.name = data["name"]
        self.hp = data.get("hp", 10)
        self.max_hp = data.get("max_hp", self.hp)
        self.level = data.get("level", 1)

        # sprite info
        self.sprite_path = data.get("sprite_path")
        self.sprite = data.get("sprite")


# Assets folder
ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
MONSTER_SPRITES_DIR = os.path.join(ASSETS_DIR, "images", "menu_sprites")

def load_monster_sprites() -> list[Monster]:
    monsters: list[Monster] = []

    # Check if the directory exists
    if not os.path.exists(MONSTER_SPRITES_DIR):
        print(f"[WARNING] Monster sprites directory not found: {MONSTER_SPRITES_DIR}")
        return monsters

    # Loop through all PNG files in the folder
    for filename in os.listdir(MONSTER_SPRITES_DIR):
        if filename.lower().endswith(".png"):
            # Use filename (without extension) as monster name
            name = os.path.splitext(filename)[0].capitalize()
            sprite_path = os.path.join("images", "menu_sprites", filename)
            
            # Load the image (don't call .convert_alpha() - display may not be initialized)
            try:
                sprite = pg.image.load(os.path.join(ASSETS_DIR, sprite_path))
                sprite = pg.transform.scale(sprite, (40, 40))  # resize if needed
            except Exception as e:
                print(f"[WARNING] Failed to load {filename}: {e}")
                sprite = pg.Surface((40,40), pg.SRCALPHA)
                sprite.fill((255,0,0))
            
            # Create a Monster entry (example default stats)
            monster: Monster = {
                "name": name,
                "hp": 50,
                "max_hp": 50,
                "level": 5,
                "sprite_path": sprite_path,
                "sprite": sprite
            }

            monsters.append(monster)
    
    return monsters

# Usage
all_monsters = load_monster_sprites()
print(f"Loaded {len(all_monsters)} monsters")