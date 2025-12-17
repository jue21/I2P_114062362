from __future__ import annotations
from src.utils import Logger, GameSettings, Position, Teleport
import json, os
import pygame as pg
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.maps.map import Map
    from src.entities.player import Player
    from src.entities.enemy_trainer import EnemyTrainer
    from src.data.bag import Bag

class GameManager:
    # Entities
    player: Player | None
    enemy_trainers: dict[str, list[EnemyTrainer]]
    bag: "Bag"
    
    # Map properties
    current_map_key: str
    maps: dict[str, Map]
    
    # Changing Scene properties
    should_change_scene: bool
    next_map: str
    entry_position: Position | None  # Track where player entered tile1.tmx
    gym_entry_position: Position | None  # Track where player entered gym
    
    def __init__(self, maps: dict[str, Map], start_map: str, 
                 player: Player | None,
                 enemy_trainers: dict[str, list[EnemyTrainer]], 
                 bag: Bag | None = None):
                     
        from src.data.bag import Bag
        # Game Properties
        self.maps = maps
        self.current_map_key = start_map
        self.player = player
        self.enemy_trainers = enemy_trainers
        self.bag = bag if bag is not None else Bag([], [])
        
        # Check If you should change scene
        self.should_change_scene = False
        self.next_map = ""
        self.entry_position = None  # Track entry point for returning from tile1
        self.gym_entry_position = None  # Track entry point for returning from gym
        
    @property
    def current_map(self) -> Map:
        return self.maps[self.current_map_key]
        
    @property
    def current_enemy_trainers(self) -> list[EnemyTrainer]:
        return self.enemy_trainers[self.current_map_key]
        
    @property
    def current_teleporter(self) -> list[Teleport]:
        return self.maps[self.current_map_key].teleporters
    
    def switch_map(self, target: str) -> None:
        if target not in self.maps:
            Logger.warning(f"Map '{target}' not loaded; cannot switch.")
            return
        
        # Prevent switching to the same map
        if target == self.current_map_key:
            Logger.warning(f"Cannot switch to '{target}' - already on this map!")
            return
        
        self.next_map = target
        self.should_change_scene = True
            
    def try_switch_map(self) -> None:
        if self.should_change_scene:
            prev_map = self.current_map_key
            self.current_map_key = self.next_map
            self.next_map = ""
            self.should_change_scene = False
            if self.player:
                # Handle boundary teleportation (left/right edges)
                if prev_map == "map.tmx" and self.current_map_key == "tile1.tmx":
                    # Going from map.tmx to tile1.tmx (left edge of map.tmx → right side of tile1.tmx near gym)
                    # Save player's exact entry position for returning
                    self.entry_position = Position(self.player.position.x, self.player.position.y)
                    # Move to right side of tile1.tmx (emerge from bush row nearest to gym), keep y-coordinate
                    tile1_map = self.maps["tile1.tmx"]
                    rightmost_x = tile1_map.tmxdata.width * GameSettings.TILE_SIZE - GameSettings.TILE_SIZE
                    self.player.position.x = rightmost_x
                    self.player.animation.update_pos(self.player.position)
                elif prev_map == "tile1.tmx" and self.current_map_key == "map.tmx":
                    # Going from tile1.tmx to map.tmx (right edge of tile1 → left-most side of bush row on map.tmx)
                    # Restore player to saved entry position
                    if self.entry_position:
                        # Place player at x=0 (left-most side of the left bush row)
                        self.player.position = Position(GameSettings.TILE_SIZE * 0, self.entry_position.y)
                        self.entry_position = None
                    else:
                        # Fallback if no entry position saved
                        self.player.position = Position(GameSettings.TILE_SIZE * 0, GameSettings.TILE_SIZE * 10)
                    self.player.animation.update_pos(self.player.position)
                elif prev_map == "map.tmx" and self.current_map_key == "gym.tmx":
                    # Entering gym from map.tmx - save entry position (gym entrance at x=24, y=24)
                    self.gym_entry_position = Position(self.player.position.x, self.player.position.y)
                    # Place player at gym spawn position
                    self.player.position = self.maps[self.current_map_key].spawn
                    self.player.animation.update_pos(self.player.position)
                elif prev_map == "gym.tmx" and self.current_map_key == "map.tmx":
                    # Exiting gym back to map.tmx - return to gym entrance
                    if self.gym_entry_position:
                        self.player.position = self.gym_entry_position
                        self.gym_entry_position = None
                    else:
                        # Fallback to gym entrance if no position saved (x=24, y=25)
                        self.player.position = Position(GameSettings.TILE_SIZE * 24, GameSettings.TILE_SIZE * 25)
                    self.player.animation.update_pos(self.player.position)
                else:
                    # Other teleportation cases
                    self.player.position = self.maps[self.current_map_key].spawn
                    self.player.animation.update_pos(self.player.position)
            
    def check_collision(self, rect: pg.Rect) -> bool:
        if self.maps[self.current_map_key].check_collision(rect):
            return True
        for entity in self.enemy_trainers[self.current_map_key]:
            if rect.colliderect(entity.animation.rect):
                return True
        # Check shopkeeper collision
        for i, shopkeeper in enumerate(self.current_map.shopkeepers):
            shop_rect = shopkeeper.animation.rect
            collides = rect.colliderect(shop_rect)
            if collides:
                Logger.debug(f"Shopkeeper {i} collision - Player rect: {rect}, Shopkeeper rect: {shop_rect}")
                return True
        
        return False
        
    def save(self, path: str) -> None:
        try:
            with open(path, "w") as f:
                json.dump(self.to_dict(), f, indent=2)
            Logger.info(f"Game saved to {path}")
        except json.JSONEncodeError as e:
            Logger.error(f"JSON encode error while saving to {path}: {e}")
        except Exception as e:
            Logger.error(f"Failed to save game to {path}: {e}")
            import traceback
            Logger.error(f"Traceback: {traceback.format_exc()}")
             
    @classmethod
    def load(cls, path: str) -> "GameManager | None":
        if not os.path.exists(path):
            Logger.error(f"No file found: {path}, ignoring load function")
            return None

        try:
            with open(path, "r") as f:
                data = json.load(f)
            Logger.info(f"JSON data loaded successfully from {path}")
        except json.JSONDecodeError as e:
            Logger.error(f"JSON decode error while loading {path}: {e}")
            return None
        except Exception as e:
            Logger.error(f"Error reading file {path}: {e}")
            return None
        
        try:
            return cls.from_dict(data)
        except Exception as e:
            Logger.error(f"Error deserializing game data from {path}: {e}")
            import traceback
            Logger.error(f"Traceback: {traceback.format_exc()}")
            return None

    def to_dict(self) -> dict[str, object]:
        map_blocks: list[dict[str, object]] = []
        for key, m in self.maps.items():
            block = m.to_dict()
            block["enemy_trainers"] = [t.to_dict() for t in self.enemy_trainers.get(key, [])]
            block["shopkeepers"] = [s.to_dict() for s in m.shopkeepers]
            # spawn = self.player_spawns.get(key)
            # block["player"] = {
            #     "x": spawn["x"] / GameSettings.TILE_SIZE,
            #     "y": spawn["y"] / GameSettings.TILE_SIZE
            # }
            map_blocks.append(block)
        return {
            "map": map_blocks,
            "current_map": self.current_map_key,
            "player": self.player.to_dict() if self.player is not None else None,
            "bag": self.bag.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "GameManager":
        from src.maps.map import Map
        from src.entities.player import Player
        from src.entities.enemy_trainer import EnemyTrainer
        from src.entities.shopkeeper import Shopkeeper
        from src.data.bag import Bag
        
        Logger.info("Loading maps")
        maps_data = data["map"]
        maps: dict[str, Map] = {}
        player_spawns: dict[str, Position] = {}
        trainers: dict[str, list[EnemyTrainer]] = {}

        for entry in maps_data:
            path = entry["path"]
            maps[path] = Map.from_dict(entry)
            sp = entry.get("player")
            if sp:
                player_spawns[path] = Position(
                    sp["x"] * GameSettings.TILE_SIZE,
                    sp["y"] * GameSettings.TILE_SIZE
                )
        current_map = data["current_map"]
        gm = cls(
            maps, current_map,
            None, # Player
            trainers,
            bag=None
        )
        gm.current_map_key = current_map
        
        Logger.info("Loading enemy trainers")
        for m in data["map"]:
            raw_data = m["enemy_trainers"]
            gm.enemy_trainers[m["path"]] = [EnemyTrainer.from_dict(t, gm) for t in raw_data]
        
        Logger.info("Loading shopkeepers")
        for m in data["map"]:
            raw_shopkeepers = m.get("shopkeepers", [])
            gm.maps[m["path"]].shopkeepers = [Shopkeeper.from_dict(s, gm) for s in raw_shopkeepers]
        
        Logger.info("Loading Player")
        if data.get("player"):
            gm.player = Player.from_dict(data["player"], gm)
        
        Logger.info("Loading bag")
        from src.data.bag import Bag as _Bag
        gm.bag = Bag.from_dict(data.get("bag", {})) if data.get("bag") else _Bag([], [])

        return gm