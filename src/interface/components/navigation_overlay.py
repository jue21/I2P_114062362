from __future__ import annotations
import pygame as pg
from typing import TYPE_CHECKING, Callable
from collections import deque
from .navigation_button import NavigationButton
from .button import Button
from src.utils import GameSettings, Position, PositionCamera
from src.core.services import input_manager

if TYPE_CHECKING:
    from src.core import GameManager


class NavigationOverlay:
    """Overlay for navigation with place selection and pathfinding."""
    
    # Map destinations to their spawn positions (in tile coordinates)
    DESTINATIONS = {
        "gym": {"map": "gym.tmx", "x": 7, "y": 13},
        "map": {"map": "map.tmx", "x": 12, "y": 12},
        "tile1": {"map": "tile1.tmx", "x": 15, "y": 10}
    }
    
    def __init__(self, game_manager: "GameManager"):
        self.game_manager = game_manager
        self.active = False
        self.current_path = []  # List of (x, y) tile coordinates
        self.path_arrows = []  # Visual arrow positions
        
        # Overlay dimensions
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        self.overlay_w, self.overlay_h = 400, 400
        self.overlay_rect = pg.Rect(
            (sw - self.overlay_w) // 2,
            (sh - self.overlay_h) // 2,
            self.overlay_w,
            self.overlay_h
        )
        
        # Dark background
        self._dark_surface = pg.Surface((sw, sh), pg.SRCALPHA)
        self._dark_surface.fill((0, 0, 0, 150))
        
        # Font
        try:
            self.font_title = pg.font.Font("assets/fonts/Minecraft.ttf", 32)
            self.font_normal = pg.font.Font("assets/fonts/Minecraft.ttf", 20)
        except:
            self.font_title = pg.font.Font(None, 32)
            self.font_normal = pg.font.Font(None, 20)
        
        # Create navigation buttons for each destination
        self.nav_buttons = []
        button_y = self.overlay_rect.y + 80
        button_spacing = 70
        
        for idx, (place_name, dest_data) in enumerate(self.DESTINATIONS.items()):
            btn = NavigationButton(
                place_name=place_name.upper(),
                x=self.overlay_rect.x + 50,
                y=button_y + idx * button_spacing,
                width=300,
                height=50,
                on_click=lambda pn=place_name: self._navigate_to(pn),
                font_size=24
            )
            self.nav_buttons.append(btn)
        
        # Close button
        close_btn_size = 40
        close_btn_x = self.overlay_rect.right - close_btn_size - 10
        close_btn_y = self.overlay_rect.y + 10
        
        self.close_button = Button(
            "UI/button_x.png",
            "UI/button_x_hover.png",
            close_btn_x,
            close_btn_y,
            close_btn_size,
            close_btn_size,
            lambda: self.close()
        )
        
        # Clear path button (positioned at bottom of overlay)
        clear_btn_w, clear_btn_h = 150, 50
        clear_btn_x = self.overlay_rect.x + (self.overlay_rect.width - clear_btn_w) // 2
        clear_btn_y = self.overlay_rect.bottom - clear_btn_h - 20
        
        self.clear_path_button = NavigationButton(
            place_name="CLEAR PATH",
            x=clear_btn_x,
            y=clear_btn_y,
            width=clear_btn_w,
            height=clear_btn_h,
            on_click=lambda: self.clear_path(),
            font_size=18
        )
        
        # Arrow sprite for path visualization
        self._create_arrow_sprite()
    
    def _create_arrow_sprite(self):
        """Create a simple arrow sprite for path visualization."""
        arrow_size = GameSettings.TILE_SIZE // 2
        self.arrow_sprite = pg.Surface((arrow_size, arrow_size), pg.SRCALPHA)
        # Draw a simple arrow pointing up (will be rotated)
        color = (150, 50, 255, 200)  # Purple with transparency
        points = [
            (arrow_size // 2, 5),  # Top
            (arrow_size - 5, arrow_size - 5),  # Bottom right
            (arrow_size // 2, arrow_size // 2),  # Center
            (5, arrow_size - 5)  # Bottom left
        ]
        pg.draw.polygon(self.arrow_sprite, color, points)
    
    def open(self):
        """Open the navigation overlay."""
        from src.utils import Logger
        Logger.info("Navigation overlay opened")
        Logger.info(f"Created {len(self.nav_buttons)} navigation buttons:")
        for btn in self.nav_buttons:
            Logger.info(f"  - {btn.place_name} at ({btn.hitbox.x}, {btn.hitbox.y})")
        self.active = True
    
    def close(self):
        """Close the navigation overlay (keeps path visible)."""
        self.active = False
    
    def clear_path(self):
        """Clear the current navigation path and arrows."""
        from src.utils import Logger
        if self.current_path:
            Logger.info(f"Cleared navigation path with {len(self.path_arrows)} arrows")
        self.current_path = []
        self.path_arrows = []
    
    def _navigate_to(self, place_name: str):
        """Navigate to the selected place using BFS pathfinding."""
        from src.utils import Logger
        
        if not self.game_manager.player:
            Logger.warning("No player found for navigation")
            return
        
        dest_data = self.DESTINATIONS.get(place_name)
        if not dest_data:
            Logger.warning(f"Destination {place_name} not found")
            return
        
        # Get current player position in tiles
        player_pos = self.game_manager.player.position
        start_tile = (
            int(player_pos.x // GameSettings.TILE_SIZE),
            int(player_pos.y // GameSettings.TILE_SIZE)
        )
        
        Logger.info(f"Navigating from {start_tile} to {place_name}")
        
        # Get destination
        dest_map = dest_data["map"]
        dest_tile = (dest_data["x"], dest_data["y"])
        
        # Check if we need to switch maps
        current_map_name = self.game_manager.current_map.path_name
        
        if current_map_name != dest_map:
            # For cross-map navigation, find path to the map transition point first
            # Then show path on current map to the edge/teleporter
            Logger.info(f"Cross-map navigation: {current_map_name} -> {dest_map}")
            self._find_path_to_map_transition(start_tile, dest_map)
        else:
            # Same map - use BFS to find path
            Logger.info(f"Same-map navigation to tile {dest_tile}")
            path = self._bfs_pathfind(start_tile, dest_tile)
            if path:
                Logger.info(f"Path found with {len(path)} steps")
                self.current_path = path
                self._create_arrow_path()
                Logger.info(f"Created {len(self.path_arrows)} arrow markers")
            else:
                Logger.warning("No path found!")
        
        # Close overlay after selecting destination (path remains visible)
        self.close()
    
    def _find_path_to_map_transition(self, start_tile: tuple[int, int], target_map: str):
        """Find path to a teleporter or map edge leading to target map."""
        current_map = self.game_manager.current_map
        
        # Find teleporters that lead to target map
        target_teleporters = []
        for tp in current_map.teleporters:
            if tp.destination == target_map:
                tp_tile = (
                    int(tp.pos.x // GameSettings.TILE_SIZE),
                    int(tp.pos.y // GameSettings.TILE_SIZE)
                )
                target_teleporters.append(tp_tile)
        
        # If there are teleporters, pathfind to the nearest one
        if target_teleporters:
            best_path = None
            best_length = float('inf')
            
            for tp_tile in target_teleporters:
                path = self._bfs_pathfind(start_tile, tp_tile)
                if path and len(path) < best_length:
                    best_path = path
                    best_length = len(path)
            
            if best_path:
                self.current_path = best_path
                self._create_arrow_path()
                return
        
        # Otherwise, check for map edge transitions (like between map.tmx and tile1.tmx)
        # For now, create a simple message or path toward the edge
        current_map_name = current_map.path_name
        
        # Handle map.tmx <-> tile1.tmx boundary transitions
        if current_map_name == "map.tmx" and target_map == "tile1.tmx":
            # Go to left edge (x=0)
            edge_tile = (0, start_tile[1])
            path = self._bfs_pathfind(start_tile, edge_tile)
            if path:
                self.current_path = path
                self._create_arrow_path()
        elif current_map_name == "tile1.tmx" and target_map == "map.tmx":
            # Go to right edge
            map_width = current_map.tmxdata.width
            edge_tile = (map_width - 1, start_tile[1])
            path = self._bfs_pathfind(start_tile, edge_tile)
            if path:
                self.current_path = path
                self._create_arrow_path()
    
    def _bfs_pathfind(self, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
        """
        BFS pathfinding algorithm to find the shortest path from start to goal.
        Returns a list of (x, y) tile coordinates representing the path.
        """
        current_map = self.game_manager.current_map
        map_width = current_map.tmxdata.width
        map_height = current_map.tmxdata.height
        
        # BFS setup
        queue = deque([(start, [start])])
        visited = {start}
        
        # Directions: up, down, left, right
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        
        while queue:
            (x, y), path = queue.popleft()
            
            # Check if we reached the goal
            if (x, y) == goal:
                return path
            
            # Explore neighbors
            for dx, dy in directions:
                nx, ny = x + dx, y + dy
                
                # Check bounds
                if not (0 <= nx < map_width and 0 <= ny < map_height):
                    continue
                
                # Skip if already visited
                if (nx, ny) in visited:
                    continue
                
                # Check collision at this tile
                tile_rect = pg.Rect(
                    nx * GameSettings.TILE_SIZE,
                    ny * GameSettings.TILE_SIZE,
                    GameSettings.TILE_SIZE,
                    GameSettings.TILE_SIZE
                )
                
                if current_map.check_collision(tile_rect):
                    continue
                
                # Add to queue
                visited.add((nx, ny))
                queue.append(((nx, ny), path + [(nx, ny)]))
        
        # No path found
        return []
    
    def _create_arrow_path(self):
        """Create arrow sprites along the path for visualization."""
        self.path_arrows = []
        
        for i in range(len(self.current_path) - 1):
            curr_tile = self.current_path[i]
            next_tile = self.current_path[i + 1]
            
            # Calculate arrow direction
            dx = next_tile[0] - curr_tile[0]
            dy = next_tile[1] - curr_tile[1]
            
            # Determine rotation angle based on direction
            if dx > 0:  # Right
                angle = 90
            elif dx < 0:  # Left
                angle = 270
            elif dy > 0:  # Down
                angle = 180
            else:  # Up
                angle = 0
            
            # Store arrow info (tile position and rotation)
            self.path_arrows.append({
                'tile': curr_tile,
                'angle': angle
            })
    
    def handle_event(self, event: pg.event.Event):
        """Handle events for navigation buttons."""
        if not self.active:
            return
        
        from src.utils import Logger
        if event.type == pg.MOUSEBUTTONDOWN:
            Logger.info(f"Mouse click at {event.pos} in navigation overlay")
        
        self.close_button.handle_event(event)
        self.clear_path_button.handle_event(event)
        for btn in self.nav_buttons:
            btn.handle_event(event)
    
    def update(self, dt: float):
        """Update navigation overlay and buttons."""
        if not self.active:
            return
        
        self.close_button.update(dt)
        self.clear_path_button.update(dt)
        for btn in self.nav_buttons:
            btn.update(dt)
    
    def draw(self, screen: pg.Surface, camera: PositionCamera | None = None):
        """Draw the navigation overlay or path arrows."""
        from src.utils import Logger
        
        # If overlay is active, draw it
        if self.active:
            # Draw dark background
            screen.blit(self._dark_surface, (0, 0))
            
            # Draw overlay box
            pg.draw.rect(screen, (50, 50, 70), self.overlay_rect)
            pg.draw.rect(screen, (200, 200, 220), self.overlay_rect, 3)
            
            # Draw title
            title_text = self.font_title.render("Navigation", True, (255, 255, 255))
            title_rect = title_text.get_rect(centerx=self.overlay_rect.centerx, y=self.overlay_rect.y + 20)
            screen.blit(title_text, title_rect)
            
            # Draw navigation buttons
            for btn in self.nav_buttons:
                btn.draw(screen)
            
            # Draw clear path button
            self.clear_path_button.draw(screen)
            
            # Draw close button
            self.close_button.draw(screen)
        
        # Draw path arrows if path exists (draw even when overlay is closed)
        if self.current_path and camera:
            for arrow_data in self.path_arrows:
                tile = arrow_data['tile']
                angle = arrow_data['angle']
                
                # Convert tile position to pixel position
                pixel_x = tile[0] * GameSettings.TILE_SIZE + GameSettings.TILE_SIZE // 2
                pixel_y = tile[1] * GameSettings.TILE_SIZE + GameSettings.TILE_SIZE // 2
                
                # Transform to camera space
                screen_pos = camera.transform_position(Position(pixel_x, pixel_y))
                
                # Handle both tuple and Position object returns
                if isinstance(screen_pos, tuple):
                    screen_x, screen_y = screen_pos
                else:
                    screen_x, screen_y = screen_pos.x, screen_pos.y
                
                # Rotate and draw arrow
                rotated_arrow = pg.transform.rotate(self.arrow_sprite, angle)
                arrow_rect = rotated_arrow.get_rect(center=(screen_x, screen_y))
                screen.blit(rotated_arrow, arrow_rect)
