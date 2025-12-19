# src/scenes/battle_scene.py
import pygame as pg
import random
from typing import Optional, Callable
from typing import override
from pathlib import Path

from src.scenes.scene import Scene
from src.core.services import scene_manager, sound_manager
from src.sprites import BackgroundSprite
from src.utils import GameSettings
from src.utils.definition import get_type_effectiveness
from src.utils.encounters import evolve_pokemon

class TextButton:
    """Simple rectangle button with text, hover & click detection (no external Button required)."""
    def __init__(self, x: int, y: int, w: int, h: int, text: str, on_click: Optional[Callable] = None, font=None):
        self.rect = pg.Rect(x, y, w, h)
        self.text = text
        self.on_click = on_click
        self.hovered = False
        self.font = font or pg.font.Font(None, 24)
        # Initialize based on current mouse state to prevent immediate clicks
        self._mouse_was_down = pg.mouse.get_pressed()[0]

    def update(self, dt: float):
        mx, my = pg.mouse.get_pos()
        self.hovered = self.rect.collidepoint(mx, my)

        pressed = pg.mouse.get_pressed()
        if self.hovered and pressed[0] and not self._mouse_was_down:
            # click detected
            if callable(self.on_click):
                self.on_click()
        self._mouse_was_down = pressed[0]

    def draw(self, surf: pg.Surface):
        bg = (240, 240, 240) if not self.hovered else (255, 255, 255)
        pg.draw.rect(surf, bg, self.rect)
        pg.draw.rect(surf, (0, 0, 0), self.rect, 2)  # border

        txt = self.font.render(self.text, True, (0, 0, 0))
        txt_r = txt.get_rect(center=self.rect.center)
        surf.blit(txt, txt_r)


class ItemButton(TextButton):
    """Item button that stores item index to avoid lambda capture issues."""
    def __init__(self, x: int, y: int, w: int, h: int, item_idx: int, text: str, scene: "BattleScene", font=None):
        self.item_idx = item_idx
        self.scene = scene
        super().__init__(x, y, w, h, text, on_click=self._on_item_click, font=font)
    
    def _on_item_click(self):
        """Called when this item button is clicked."""
        self.scene.use_item(self.item_idx)


def get_active_monster_from_player(player):
    if player is None:
        return None

    # try common attribute names
    candidates = [
        getattr(player, "active_monster", None),
        getattr(player, "monster", None),
        getattr(player, "active", None),
        getattr(player, "current_monster", None),
    ]
    for c in candidates:
        if isinstance(c, dict):
            return c
        if hasattr(c, "get") and callable(c.get):  # typed like dict-like
            return c

    # try lists
    for name in ("monsters", "party", "team"):
        lst = getattr(player, name, None)
        if lst and isinstance(lst, (list, tuple)) and len(lst) > 0:
            # If there's an index pointer, try to use it
            idx = getattr(player, "monster_index", None)
            if isinstance(idx, int) and 0 <= idx < len(lst):
                return lst[idx]
            # fallback first
            return lst[0]

    # last fallback: maybe player has attributes name/hp -> treat as single-monster-like object
    if getattr(player, "name", None) and getattr(player, "hp", None) is not None:
        # create a dict-like view
        return {"name": getattr(player, "name"), "hp": getattr(player, "hp"), "max_hp": getattr(player, "max_hp", getattr(player, "hp"))}

    return None


def safe_get_moves(monster: dict):
    if not monster:
        return []
    moves = monster.get("moves")
    if moves and isinstance(moves, list):
        # normalize moves if they are simple strings
        normalized = []
        for m in moves:
            if isinstance(m, dict):
                normalized.append({"name": m.get("name", "Move"), "power": int(m.get("power", 5))})
            elif isinstance(m, str):
                normalized.append({"name": m, "power": 8})
            else:
                normalized.append({"name": "Move", "power": 6})
        # ensure length 4
        while len(normalized) < 4:
            normalized.append({"name": "---", "power": 0})
        return normalized[:4]
    # default fallback moves
    return [
        {"name": "Tackle", "power": 8},
        {"name": "Growl", "power": 0},
        {"name": "Quick Hit", "power": 6},
        {"name": "Bash", "power": 10},
    ]

class BattleScene(Scene):
    def __init__(self, player, enemy, player_mon=None, bag=None, game_manager=None):
        super().__init__()
        self.player_obj = player
        self.enemy_obj = enemy
        self.bag = bag  # Store bag for accessing items
        self.game_manager = game_manager  # Store game_manager for saving
        background: BackgroundSprite

        # Handle enemy team (list of monsters) or single monster
        if isinstance(enemy, list):
            self.enemy_team = enemy
            self.enemy_mon_index = 0
            self.enemy_mon = self.enemy_team[0]
        else:
            self.enemy_mon = enemy if isinstance(enemy, dict) else (get_active_monster_from_player(enemy) or {"name": "Wild", "hp": 30, "max_hp": 30, "sprite": None})
            self.enemy_team = [self.enemy_mon]
            self.enemy_mon_index = 0
        
        # Active monster dict views (read/write to these dicts)
        # Use provided player_mon if available, otherwise try to find from player object
        if player_mon is not None:
            self.player_mon = player_mon
        else:
            self.player_mon = get_active_monster_from_player(player) or {"name": "PlayerMon", "hp": 30, "max_hp": 30, "sprite": None}

        # Ensure sprites are loaded and sized
        self._ensure_monster_sprites()

        # Background sprite (if missing, we'll fill color)
       
        self.background = BackgroundSprite("backgrounds/background1.png")
        
        # UI Frame for bottom menu area
        self.ui_frame = None
        try:
            frame_path = str(Path("assets") / "images" / "UI" / "raw" / "UI_Flat_FrameMarker01a.png")
            self.ui_frame = pg.image.load(frame_path)
            # Scale frame to fit the bottom menu area (width: screen width, height: 180)
            self.ui_frame = pg.transform.scale(self.ui_frame, (GameSettings.SCREEN_WIDTH, 180))
        except Exception:
            pass  # If frame fails to load, we'll fall back to colored rectangles
        
        # Load Pokemon ball sprite for team indicators
        self.ball_sprite = None
        self.ball_sprite_gray = None
        try:
            ball_path = str(Path("assets") / "images" / "ingame_ui" / "ball.png")
            original = pg.image.load(ball_path).convert_alpha()
            self.ball_sprite = pg.transform.scale(original, (24, 24))
            # Create grayscale version for fainted Pokemon
            gray_surf = pg.Surface((24, 24), pg.SRCALPHA)
            for x in range(24):
                for y in range(24):
                    r, g, b, a = self.ball_sprite.get_at((x, y))
                    gray_value = int(0.299 * r + 0.587 * g + 0.114 * b)
                    gray_surf.set_at((x, y), (gray_value, gray_value, gray_value, a))
            self.ball_sprite_gray = gray_surf
        except Exception:
            pass  # If ball sprite fails to load, we'll fall back to circles

        # Load banner image for Pokemon info display
        self.pokemon_banner = None
        try:
            banner_path = str(Path("assets") / "images" / "UI" / "raw" / "UI_Flat_Banner04a.png")
            self.pokemon_banner = pg.image.load(banner_path).convert_alpha()
        except Exception:
            pass  # If banner fails to load, we'll use rectangles as fallback

        # Fonts
        try:
            self.font_big = pg.font.Font("assets/fonts/Minecraft.ttf", 28)
            self.font_med = pg.font.Font("assets/fonts/Minecraft.ttf", 20)
        except Exception:
            self.font_big = pg.font.Font(None, 28)
            self.font_med = pg.font.Font(None, 20)

        # UI positions
        self.player_pos = (100, 250)
        self.enemy_pos = (800, 80)

        # State
        self.turn = "player"     # "player" or "enemy" or "anim"
        self.submenu = "main"    # "main", "fight", "bag", "monsters"
        self.message_queue: list[str] = []        # keep as before
        self.current_message_timer: float = 0.0   # countdown for message duration
        self.message_duration_default: float = 2.0  # 2 seconds default
        self.showing_message = False

        # Stat boosts from items (multipliers, reset when battle ends)
        self.player_attack_boost = 1.0  # Strength Potion multiplier
        self.player_defense_boost = 1.0  # Defense Potion multiplier
        self.enemy_attack_boost = 1.0
        self.enemy_defense_boost = 1.0

        # Evolution display
        self.evolution_display_timer = 0.0
        self.evolution_display_text = None

        # Attack animation sprites
        self.attack_animation_timer = 0.0
        self.attacking_pokemon = None  # "player" or "enemy"
        self.player_idle_sprite = None
        self.enemy_idle_sprite = None
        
        # Idle animation frames (cycle through 4 frames)
        self.player_idle_frames = []  # List of 4 frames
        self.enemy_idle_frames = []   # List of 4 frames
        self.player_attack_frames = []  # List of 4 attack frames
        self.enemy_attack_frames = []   # List of 4 attack frames
        self.idle_frame_index = 0
        self.idle_animation_timer = 0.0
        self.idle_animation_speed = 0.2  # Seconds per frame (5 FPS animation)
        
        # Load animation frames for both Pokemon
        self._load_animation_frames()
        
        # Ball throwing animation
        self.ball_throwing = False
        self.ball_throw_timer = 0.0
        self.ball_throw_duration = 2.0  # 2 second throw animation
        self.ball_sprite_throw = None
        self.ball_start_pos = None
        self.ball_end_pos = None
        self.pending_catch_item = None
        self.capture_animation = False  # Pokemon being absorbed into ball
        self.capture_timer = 0.0
        self.capture_duration = 1.5  # Duration of capture/shrink animation
        self.original_enemy_sprite = None
        self.capture_success = False
        self.pokemon_captured = False  # Flag to track if Pokemon was successfully caught
        
        # Entrance animation - Pokemon emerging from pokeball
        self.entrance_animation = True  # Start with entrance animation
        self.entrance_timer = 0
        self.entrance_duration = 2.0  # Total entrance animation duration
        self.player_entrance_done = False
        self.enemy_entrance_done = False
        
        # Moves
        self.player_moves = safe_get_moves(self.player_mon)
        self.enemy_moves = safe_get_moves(self.enemy_mon)

        # Text menu items (horizontal layout)
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        menu_y = sh - 100  # Position near bottom
        menu_w = 150  # Narrower buttons for horizontal layout
        menu_h = 40
        gap = 160  # Horizontal gap between buttons
        total_width = 4 * menu_w + 3 * (gap - menu_w)  # Total width of all buttons
        menu_start_x = (sw - total_width) // 2  # Center horizontally

        # Main command text buttons (FIGHT, BAG, MONSTERS, RUN) - horizontal layout
        self.main_buttons = [
            TextButton(menu_start_x + 0 * gap, menu_y, menu_w, menu_h, "FIGHT", on_click=self.open_fight),
            TextButton(menu_start_x + 1 * gap, menu_y, menu_w, menu_h, "BAG", on_click=self.open_bag),
            TextButton(menu_start_x + 2 * gap, menu_y, menu_w, menu_h, "MONSTERS", on_click=self.open_monsters),
            TextButton(menu_start_x + 3 * gap, menu_y, menu_w, menu_h, "RUN", on_click=self.attempt_run),
        ]

        # Fight menu move buttons (reused when in fight submenu) - horizontal layout
        self.move_buttons = []
        move_btn_w = 150
        move_gap = 160  # Horizontal gap between buttons
        move_total_width = 4 * move_btn_w + 3 * (move_gap - move_btn_w)
        move_start_x = (sw - move_total_width) // 2  # Center horizontally
        move_menu_y = sh - 100  # Same y position as main buttons
        for i in range(4):
            x = move_start_x + i * move_gap
            self.move_buttons.append(TextButton(x, move_menu_y, move_btn_w, menu_h, self.player_moves[i]["name"], on_click=(lambda i=i: self.player_use_move(i))))
        # Bag & monsters minimal placeholders (will show dialog)
        self.items = self._load_items_from_player()  # list of item dicts: {"name","count","heal"}
        self.item_buttons = []
        self.item_index_selected = -1  # Track which item button was clicked

        # Message box rect
        self.msg_rect = pg.Rect(20, GameSettings.SCREEN_HEIGHT - 240, GameSettings.SCREEN_WIDTH - 40, 60)

        # small cooldown so enemy turn doesn't instantly trigger while clicking
        self._time_since_action = 0.0

    def _load_items_from_player(self):
        # First try to load items from the bag if available
        if self.bag and hasattr(self.bag, 'items') and len(self.bag.items) > 0:
            items = []
            for it in self.bag.items:
                if isinstance(it, dict):
                    items.append({
                        "name": it.get("name", "Item"),
                        "count": int(it.get("count", 1)),
                        "item_type": it.get("item_type", "heal")  # default to heal
                    })
            if items:
                return items
        
        # try common places for items on player object; if none, give default items
        items = []
        p = self.player_obj
        for name in ("items", "bag", "inventory"):
            coll = getattr(p, name, None)
            if coll and isinstance(coll, (list, tuple)) and len(coll) > 0:
                # Expect dicts with keys name,count,item_type; normalize to expected shape
                for it in coll:
                    if isinstance(it, dict):
                        items.append({
                            "name": it.get("name", "Item"),
                            "count": int(it.get("count", 1)),
                            "item_type": it.get("item_type", "heal")  # default to heal
                        })
                return items
        # fallback: three default items
        return [
            {"name": "Heal Potion", "count": 3, "item_type": "heal"},
            {"name": "Strength Potion", "count": 2, "item_type": "strength"},
            {"name": "Defense Potion", "count": 2, "item_type": "defense"}
        ]
    
    def _update_bag_item_count(self, item_name: str, count_change: int):
        #Update the count of an item in the original bag.
        if not self.bag or not hasattr(self.bag, 'items'):
            return
        
        for bag_item in self.bag.items:
            if bag_item.get("name") == item_name:
                bag_item["count"] = max(0, bag_item.get("count", 0) + count_change)
                if bag_item["count"] == 0:
                    self.bag.items.remove(bag_item)
                break

    def _rebuild_move_buttons(self):
        """Rebuild move buttons for the current player monster."""
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        menu_h = 40
        move_btn_w = 150
        move_gap = 160
        move_total_width = 4 * move_btn_w + 3 * (move_gap - move_btn_w)
        move_start_x = (sw - move_total_width) // 2
        move_menu_y = sh - 100
        
        self.move_buttons = []
        for i in range(4):
            x = move_start_x + i * move_gap
            move_name = self.player_moves[i]["name"] if i < len(self.player_moves) else "---"
            self.move_buttons.append(TextButton(x, move_menu_y, move_btn_w, menu_h, move_name, on_click=(lambda i=i: self.player_use_move(i))))
    

    def enqueue_message(self, msg: str, duration: Optional[float] = None):
        self.message_queue.append(msg)
        self.showing_message = True
        self.current_message_timer = duration if duration is not None else self.message_duration_default

    def pop_message(self):
        if self.message_queue:
            return self.message_queue.pop(0)
        self.showing_message = False
        return None

    def _extract_sprite_frame(self, sprite_sheet: pg.Surface, frame_idx: int) -> pg.Surface:
        #Extract a single frame from a sprite sheet (assumes 4 frames horizontal layout)
        sheet_width = sprite_sheet.get_width()
        frame_width = sheet_width // 4  # Assuming 4 frames laid out horizontally (96 pixels each)
        frame_height = sprite_sheet.get_height()
        
        # Calculate frame position and extract using subsurface
        frame_rect = pg.Rect(frame_idx * frame_width, 0, frame_width, frame_height)
        extracted_frame = sprite_sheet.subsurface(frame_rect).copy()  # Copy to detach from original
        return pg.transform.scale(extracted_frame, (300, 300))

    def _get_idle_sprite_from_sheet(self, pokemon: dict) -> Optional[pg.Surface]:
        #Load idle sprite by extracting frame 0 from sprite_idle.png
        try:
            sprite_path = pokemon.get("sprite_path", "")
            if "menu_sprites" in sprite_path:
                # Extract sprite number from menusprite path (e.g., menusprite1.png -> 1)
                sprite_num = sprite_path.split("menusprite")[-1].split(".")[0]
                # Load sprite sheet and extract idle frame (frame 0)
                sprite_sheet_path = str(Path("assets") / "images" / "sprites" / f"sprite{sprite_num}_idle.png")
                sprite_sheet = pg.image.load(sprite_sheet_path)
                # Extract frame 0 (idle pose)
                return self._extract_sprite_frame(sprite_sheet, frame_idx=0)
        except Exception as e:
            pass
        return None

    def _get_attack_sprite_from_sheet(self, pokemon: dict) -> Optional[pg.Surface]:
        #Load attack sprite by extracting frame 1 from sprite_attack.png
        try:
            sprite_path = pokemon.get("sprite_path", "")
            if "menu_sprites" in sprite_path:
                # Extract sprite number from menusprite path
                sprite_num = sprite_path.split("menusprite")[-1].split(".")[0]
                # Load sprite sheet and extract attack frame (frame 1)
                sprite_sheet_path = str(Path("assets") / "images" / "sprites" / f"sprite{sprite_num}_attack.png")
                sprite_sheet = pg.image.load(sprite_sheet_path)
                # Extract frame 1 (attack pose)
                return self._extract_sprite_frame(sprite_sheet, frame_idx=1)
        except Exception as e:
            pass
        return None

    def _ensure_monster_sprites(self):
        #Ensure both player and enemy monsters have sprites loaded and sized (from sprite_idle.png).
        # Handle player sprite
        sprite = self.player_mon.get("sprite")
        sprite_path = self.player_mon.get("sprite_path")
        
        # Check if sprite is empty/placeholder (from failed .convert_alpha() in bag.py)
        is_empty_sprite = isinstance(sprite, pg.Surface) and sprite.get_width() == 40 and sprite.get_height() == 40
        
        if sprite is None or is_empty_sprite or (isinstance(sprite, pg.Surface) and sprite.get_width() != 96):
            if sprite_path:
                try:
                    # Try to load idle sprite from sprite_idle.png (frame 0)
                    idle_sprite = self._get_idle_sprite_from_sheet(self.player_mon)
                    if idle_sprite:
                        self.player_mon["sprite"] = idle_sprite
                    else:
                        # Fallback to loading menu sprite directly
                        if not sprite_path.startswith("images/"):
                            full_path = str(Path("assets") / "images" / sprite_path)
                        else:
                            full_path = str(Path("assets") / sprite_path)
                        sprite = pg.image.load(full_path)
                        sprite = pg.transform.scale(sprite, (300, 300))
                except Exception as e:
                    pass
            elif sprite is not None and isinstance(sprite, pg.Surface) and not is_empty_sprite:
                # Sprite exists and is valid, just wrong size - scale it
                self.player_mon["sprite"] = pg.transform.scale(sprite, (300, 300))
        
        # Handle enemy sprite
        sprite = self.enemy_mon.get("sprite")
        sprite_path = self.enemy_mon.get("sprite_path")
        
        # Check if sprite is empty/placeholder
        is_empty_sprite = isinstance(sprite, pg.Surface) and sprite.get_width() == 40 and sprite.get_height() == 40
        
        if sprite is None or is_empty_sprite or (isinstance(sprite, pg.Surface) and sprite.get_width() != 96):
            if sprite_path:
                try:
                    # Try to load idle sprite from sprite_idle.png (frame 0)
                    idle_sprite = self._get_idle_sprite_from_sheet(self.enemy_mon)
                    if idle_sprite:
                        self.enemy_mon["sprite"] = idle_sprite
                    else:
                        # Fallback to loading menu sprite directly
                        if not sprite_path.startswith("images/"):
                            full_path = str(Path("assets") / "images" / sprite_path)
                        else:
                            full_path = str(Path("assets") / sprite_path)
                        sprite = pg.image.load(full_path)
                        sprite = pg.transform.scale(sprite, (300, 300))
                except Exception as e:
                    pass
            elif sprite is not None and isinstance(sprite, pg.Surface) and not is_empty_sprite:
                # Sprite exists and is valid, just wrong size - scale it
                self.enemy_mon["sprite"] = pg.transform.scale(sprite, (300, 300))

    def _load_animation_frames(self):
        """Load all animation frames for both player and enemy Pokemon."""
        # Load player idle and attack frames
        self.player_idle_frames = self._get_all_frames_from_sheet(self.player_mon, "idle")
        self.player_attack_frames = self._get_all_frames_from_sheet(self.player_mon, "attack")
        
        # Load enemy idle and attack frames
        self.enemy_idle_frames = self._get_all_frames_from_sheet(self.enemy_mon, "idle")
        self.enemy_attack_frames = self._get_all_frames_from_sheet(self.enemy_mon, "attack")
        
        # Store initial idle sprites for reference
        if self.player_idle_frames:
            self.player_idle_sprite = self.player_idle_frames[0]
        if self.enemy_idle_frames:
            self.enemy_idle_sprite = self.enemy_idle_frames[0]

    def _get_all_frames_from_sheet(self, pokemon: dict, animation_type: str = "idle") -> list:
        """Load all 4 frames from a sprite sheet (idle or attack)."""
        frames = []
        try:
            sprite_path = pokemon.get("sprite_path", "")
            if "menu_sprites" in sprite_path:
                # Extract sprite number from menusprite path
                sprite_num = sprite_path.split("menusprite")[-1].split(".")[0]
                # Load sprite sheet
                sprite_sheet_path = str(Path("assets") / "images" / "sprites" / f"sprite{sprite_num}_{animation_type}.png")
                sprite_sheet = pg.image.load(sprite_sheet_path).convert_alpha()
                
                # Extract all 4 frames
                for frame_idx in range(4):
                    frame = self._extract_sprite_frame(sprite_sheet, frame_idx)
                    frames.append(frame)
        except Exception as e:
            pass
        
        return frames

    def _get_current_player_sprite(self) -> Optional[pg.Surface]:
        """Get the current sprite for the player Pokemon (animated or static)."""
        # If attack animation is active, use attack frames
        if self.attack_animation_timer > 0 and self.attacking_pokemon == "player":
            if self.player_attack_frames:
                return self.player_attack_frames[self.idle_frame_index % len(self.player_attack_frames)]
        
        # Use idle animation frames if available
        if self.player_idle_frames:
            return self.player_idle_frames[self.idle_frame_index % len(self.player_idle_frames)]
        
        # Fallback to static sprite
        return self.player_mon.get("sprite")

    def _get_current_enemy_sprite(self) -> Optional[pg.Surface]:
        """Get the current sprite for the enemy Pokemon (animated or static)."""
        # If attack animation is active, use attack frames
        if self.attack_animation_timer > 0 and self.attacking_pokemon == "enemy":
            if self.enemy_attack_frames:
                return self.enemy_attack_frames[self.idle_frame_index % len(self.enemy_attack_frames)]
        
        # Use idle animation frames if available
        if self.enemy_idle_frames:
            return self.enemy_idle_frames[self.idle_frame_index % len(self.enemy_idle_frames)]
        
        # Fallback to static sprite
        return self.enemy_mon.get("sprite")

    def _draw_pokemon_info_banner(self, screen: pg.Surface, pokemon: dict, x: int, y: int, is_player: bool = True) -> None:
        """Draw a Pokemon info banner with name, element, and HP bar."""
        banner_width = 260
        banner_height = 90
        
        # Draw banner background
        if self.pokemon_banner:
            banner_scaled = pg.transform.scale(self.pokemon_banner, (banner_width, banner_height))
            screen.blit(banner_scaled, (x, y))
        else:
            # Fallback to colored rectangle
            banner_rect = pg.Rect(x, y, banner_width, banner_height)
            pg.draw.rect(screen, (60, 60, 80), banner_rect)
            pg.draw.rect(screen, (200, 200, 200), banner_rect, 2)
        
        # Pokemon name and level (black text)
        name = pokemon.get("name", "Unknown")
        level = pokemon.get("level", 1)
        name_text = self.font_med.render(f"{name}", True, (0, 0, 0))
        level_text = self.font_med.render(f"Lv.{level}", True, (0, 0, 0))
        screen.blit(name_text, (x + 25, y + 15))
        screen.blit(level_text, (x + banner_width - 65, y + 15))
        
        # Element type
        element = pokemon.get("element", "Normal")
        # Get element color
        element_colors = {
            "Fire": (200, 60, 30),
            "Water": (30, 100, 200),
            "Grass": (60, 150, 50),
            "Electric": (200, 170, 0),
            "Ice": (100, 180, 220),
            "Fighting": (150, 50, 40),
            "Poison": (130, 50, 150),
            "Ground": (160, 120, 60),
            "Flying": (100, 140, 220),
            "Psychic": (220, 70, 120),
            "Bug": (140, 160, 30),
            "Rock": (150, 130, 80),
            "Ghost": (80, 60, 130),
            "Dragon": (100, 60, 180),
            "Dark": (80, 60, 50),
            "Steel": (150, 150, 170),
            "Fairy": (220, 120, 170),
            "Normal": (140, 140, 140),
        }
        element_color = element_colors.get(element, (140, 140, 140))
        element_text = self.font_med.render(f"{element}", True, element_color)
        screen.blit(element_text, (x + 25, y + 40))
        
        # HP bar
        hp = pokemon.get("hp", 0)
        max_hp = pokemon.get("max_hp", 1)
        hp_ratio = hp / max_hp if max_hp > 0 else 0
        
        bar_x = x + 23
        bar_y = y + 62
        bar_width = banner_width - 100
        bar_height = 8
        
        # HP bar background
        pg.draw.rect(screen, (40, 40, 40), (bar_x, bar_y, bar_width, bar_height))
        pg.draw.rect(screen, (100, 100, 100), (bar_x, bar_y, bar_width, bar_height), 1)
        
        # HP bar fill
        fill_color = (50, 205, 50) if hp_ratio > 0.5 else (255, 215, 0) if hp_ratio > 0.2 else (255, 50, 50)
        fill_width = int((bar_width - 2) * hp_ratio)
        if fill_width > 0:
            pg.draw.rect(screen, fill_color, (bar_x + 1, bar_y + 1, fill_width, bar_height - 2))
        
        # HP text (inside banner)
        hp_text = self.font_med.render(f"{hp}/{max_hp}", True, (0, 0, 0))
        screen.blit(hp_text, (bar_x + bar_width + 8, bar_y - 3))

    # menu actions
    def open_fight(self):
        if self.turn != "player": 
            return
        if self._time_since_action < 0.2:  # Debounce: prevent rapid clicks
            return
        self.submenu = "fight"
        self._time_since_action = 0.0  # Reset cooldown
        # refresh move names (in case moves changed)
        self.player_moves = safe_get_moves(self.player_mon)
        for i, btn in enumerate(self.move_buttons):
            btn.text = self.player_moves[i]["name"]

    def open_bag(self):
        if self.turn != "player":
            return
        if self._time_since_action < 0.2:  # Debounce: prevent rapid clicks
            return
        self.submenu = "bag"
        self._time_since_action = 0.0  # Reset cooldown
        # refresh item buttons
        self.items = self._load_items_from_player()
        self.item_buttons = []
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        menu_x = 40
        menu_y = sh - 170
        menu_w = 360
        gap = 46
        # Filter out non-battle items (those with null item_type or specific exclusions)
        usable_items = [it for it in self.items if it.get("item_type") is not None]
        
        # Create buttons in 2 columns: left column (4 items), right column (2 items)
        for i, it in enumerate(usable_items):
            if i < 4:
                # Left column
                x = menu_x
                y = menu_y + i * gap
            elif i < 6:
                # Right column (2 items starting after the 4 left items)
                x = menu_x + menu_w + 10
                y = menu_y + (i - 4) * gap
            else:
                break  # Only show up to 6 buttons
            self.item_buttons.append(ItemButton(x, y, menu_w, 40, self.items.index(it), f"{it['name']} x{it['count']}", self))

    def open_monsters(self):
        if self.turn != "player":
            return
        if self._time_since_action < 0.2:
            return

    # Prefer bag monsters if exists
        if self.bag and hasattr(self.bag, "monsters"):
            party = self.bag.monsters
        else:
            party = getattr(self.player_obj, "party", None) or getattr(self.player_obj, "monsters", None) or [self.player_mon]

    # Need at least 2 monsters to switch
        if len(party) < 2:
            self.enqueue_message("Only one monster available!")
            return

    # Otherwise, show buttons with scrolling support
        self.submenu = "monsters"
        self._time_since_action = 0.0
        self.monster_buttons = []
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        self._monster_menu_x = 40
        self._monster_menu_y = sh - 155  # Moved down further
        self._monster_gap = 36
        
        # Maximum visible monsters (show 4 at a time)
        self._max_visible_monsters = 4
        self._monster_scroll_offset = 0
        
        self._update_monster_buttons(party)

    # Store party in scene so switch_monster knows
        self.current_party = party

    def _update_monster_buttons(self, party):
        """Update monster buttons based on current scroll offset."""
        self.monster_buttons = []
        
        # Calculate visible range
        start_idx = self._monster_scroll_offset
        end_idx = min(start_idx + self._max_visible_monsters, len(party))
        
        menu_x = self._monster_menu_x
        menu_y = self._monster_menu_y
        gap = self._monster_gap
        monster_btn_width = 320
        
        # Side buttons (scroll up, scroll down, back) - positioned beside the 4 monster blocks
        side_btn_width = 60
        side_btn_height = 50
        side_btn_x = menu_x + monster_btn_width + 10
        side_btn_gap = 55
        
        # Use larger font for side button symbols
        large_font = pg.font.Font(None, 36)
        
        # Add scroll up button (top of side panel)
        if self._monster_scroll_offset > 0:
            self.monster_buttons.append(
                TextButton(side_btn_x, menu_y, side_btn_width, side_btn_height, "UP", on_click=lambda: self._scroll_monsters(-1, party), font=large_font)
            )
        
        # Add scroll down button (middle of side panel)
        if end_idx < len(party):
            self.monster_buttons.append(
                TextButton(side_btn_x, menu_y + side_btn_gap, side_btn_width, side_btn_height, "DN", on_click=lambda: self._scroll_monsters(1, party), font=large_font)
            )
        
        # Add back button (bottom of side panel)
        self.monster_buttons.append(
            TextButton(side_btn_x, menu_y + side_btn_gap * 2, side_btn_width, side_btn_height, "Back", on_click=self._close_monster_menu, font=large_font)
        )
        
        for display_idx, i in enumerate(range(start_idx, end_idx)):
            mon = party[i]
            y = menu_y + display_idx * gap
            name = mon.get("name", f"Mon{i}")
            hp = mon.get("hp", 0)
            max_hp = mon.get("max_hp", 30)
            # Mark currently active monster with a star
            active_marker = " *" if mon is self.player_mon else ""
            text = f"{name} HP: {hp}/{max_hp}{active_marker}"
            self.monster_buttons.append(
                TextButton(menu_x, y, monster_btn_width, 36, text, on_click=(lambda i=i: self.switch_monster(i)))
            )

    def _scroll_monsters(self, direction, party):
        """Scroll the monster list up or down."""
        new_offset = self._monster_scroll_offset + direction
        max_offset = max(0, len(party) - self._max_visible_monsters)
        self._monster_scroll_offset = max(0, min(new_offset, max_offset))
        self._update_monster_buttons(party)

    def _close_monster_menu(self):
        """Close the monster menu and return to main."""
        self.submenu = "main"
        self.monster_buttons = []

    def switch_monster(self, idx: int):
        # Use the same party retrieval logic as open_monsters
        if self.bag and hasattr(self.bag, "monsters"):
            party = self.bag.monsters
        else:
            party = getattr(self.player_obj, "party", None) or getattr(self.player_obj, "monsters", None) or [self.player_mon]
        
        if idx < 0 or idx >= len(party):
            return
    # Prevent switching to the same monster that's already active (check by object identity)
        if party[idx] is self.player_mon:
            self.enqueue_message(f"{party[idx].get('name', 'Pokemon')} is already active!")
            return
    # Swap active monster
        old_mon = self.player_mon
        self.player_mon = party[idx]
        # Reload sprites for the new active monster
        self._ensure_monster_sprites()
        # Reload animation frames for the new monster
        self.player_idle_frames = self._get_all_frames_from_sheet(self.player_mon, "idle")
        self.player_attack_frames = self._get_all_frames_from_sheet(self.player_mon, "attack")
        if self.player_idle_frames:
            self.player_idle_sprite = self.player_idle_frames[0]
        # Update moves for the new monster
        self.player_moves = safe_get_moves(self.player_mon)
        self._rebuild_move_buttons()
        self.enqueue_message(f"Switched {old_mon['name']} out! {self.player_mon['name']} is now active.")
        self.submenu = "main"
        self.turn = "enemy"
        self._time_since_action = 0.0


    def attempt_run(self):
        if self.turn != "player": 
            return
        chance = 0.5
        if random.random() < chance:
            # Escape success
            self.enqueue_message("You ran away safely!")
            self._after_battle_end(escaped=True)
        else:
            self.enqueue_message("Can't escape!")
            self.turn = "enemy"

    # actions: moves / items
    def player_use_move(self, idx: int):
        if self.turn != "player":
            return
        if self._time_since_action < 0.2:  # Debounce: prevent rapid clicks
            return
        move = self.player_moves[idx] if idx < len(self.player_moves) else {"name": "---", "power": 0}
        name = move["name"]
        power = int(move.get("power", 0))
        if power <= 0:
            self.enqueue_message(f"{self.player_mon['name']} used {name}... but nothing happened.")
            # small delay then enemy turn
            self.turn = "enemy"
            self._time_since_action = 0.0  # Reset cooldown
            return

        # Trigger attack animation with attack sprite
        self.attacking_pokemon = "player"
        self.attack_animation_timer = 0.6
        # Store idle sprite and load attack sprite
        if self.player_idle_sprite is None:
            self.player_idle_sprite = self.player_mon.get("sprite")
        attack_sprite = self._get_attack_sprite_from_sheet(self.player_mon)
        if attack_sprite:
            self.player_mon["sprite"] = attack_sprite

        # compute damage (very simple formula: power +/- random)
        variance = random.randint(-2, 2)
        dmg = max(1, power + variance)
        
        # Apply attack boost from Strength Potion
        dmg = int(dmg * self.player_attack_boost)
        
        # Apply type effectiveness multiplier
        attacker_type = self.player_mon.get("element", "Normal")
        defender_type = self.enemy_mon.get("element", "Normal")
        effectiveness = get_type_effectiveness(attacker_type, defender_type)
        dmg = int(dmg * effectiveness)
        dmg = max(1, dmg)
        
        self.enemy_mon["hp"] = max(0, int(self.enemy_mon.get("hp", 0) - dmg))
        
        # Display effectiveness message
        if effectiveness >= 2.0:
            self.enqueue_message(f"{self.player_mon['name']} used {name}! It's super effective! {dmg} damage.", duration=3.0)
        elif effectiveness <= 0.5 and effectiveness > 0:
            self.enqueue_message(f"{self.player_mon['name']} used {name}. It's not very effective... {dmg} damage.", duration=3.0)
        elif effectiveness == 0:
            self.enqueue_message(f"{self.player_mon['name']} used {name}! But it has no effect...", duration=3.0)
        else:
            self.enqueue_message(f"{self.player_mon['name']} used {name}! It dealt {dmg} damage.", duration=3.0)
        self.submenu = "main"
        self.turn = "enemy"
        self._time_since_action = 0.0  # Reset cooldown

        # check faint
        if self.enemy_mon["hp"] <= 0:
            self.enqueue_message(f"{self.enemy_mon['name']} fainted!")
            # Level up player's Pokemon
            self.player_mon["level"] = self.player_mon.get("level", 1) + 1
            self.enqueue_message(f"{self.player_mon['name']} leveled up to level {self.player_mon['level']}!")
            # Check for evolution
            pokemon_name_before_evolution = self.player_mon['name']
            if evolve_pokemon(self.player_mon):
                # Set evolution display
                self.evolution_display_text = f"{pokemon_name_before_evolution} evolved into {self.player_mon['name']}!"
                self.evolution_display_timer = 10.0  # Display for 5 seconds
                self.enqueue_message(f"{pokemon_name_before_evolution} evolved into {self.player_mon['name']}!")
                # Reload sprite for evolved form
                self.player_mon["sprite"] = None
                self._ensure_monster_sprites()
                # Reload animation frames for the evolved form
                self.player_idle_frames = self._get_all_frames_from_sheet(self.player_mon, "idle")
                self.player_attack_frames = self._get_all_frames_from_sheet(self.player_mon, "attack")
                if self.player_idle_frames:
                    self.player_idle_sprite = self.player_idle_frames[0]
            
            # Check if enemy has more monsters
            self.enemy_mon_index += 1
            if self.enemy_mon_index < len(self.enemy_team):
                # Switch to next enemy monster
                self.enemy_mon = self.enemy_team[self.enemy_mon_index]
                self.enemy_moves = safe_get_moves(self.enemy_mon)
                # Reset enemy sprite state
                self.enemy_idle_sprite = None
                self.attacking_pokemon = None
                self.attack_animation_timer = 0.0
                self._ensure_monster_sprites()
                # Reload animation frames for the new enemy monster
                self.enemy_idle_frames = self._get_all_frames_from_sheet(self.enemy_mon, "idle")
                self.enemy_attack_frames = self._get_all_frames_from_sheet(self.enemy_mon, "attack")
                if self.enemy_idle_frames:
                    self.enemy_idle_sprite = self.enemy_idle_frames[0]
                self.enqueue_message(f"Enemy sent out {self.enemy_mon['name']}!")
                self.turn = "player"
                self._time_since_action = 0.0
            else:
                # All enemy monsters defeated
                self._after_battle_end(victory=True)

    def enemy_use_move(self):
        move = random.choice(self.enemy_moves) if self.enemy_moves else {"name": "Scratch", "power": 6}
        name = move["name"]
        power = int(move.get("power", 0))
        if power <= 0:
            self.enqueue_message(f"{self.enemy_mon['name']} used {name}... but nothing happened.", duration=3.0)
            self.turn = "player"
            return
        
        # Trigger attack animation with attack sprite
        self.attacking_pokemon = "enemy"
        self.attack_animation_timer = 0.6
        # Store idle sprite and load attack sprite
        if self.enemy_idle_sprite is None:
            self.enemy_idle_sprite = self.enemy_mon.get("sprite")
        attack_sprite = self._get_attack_sprite_from_sheet(self.enemy_mon)
        if attack_sprite:
            self.enemy_mon["sprite"] = attack_sprite
        
        variance = random.randint(-2, 2)
        dmg = max(1, power + variance)
        
        # Apply attack boost from enemy (if any)
        dmg = int(dmg * self.enemy_attack_boost)
        
        # Apply type effectiveness multiplier
        attacker_type = self.enemy_mon.get("element", "Normal")
        defender_type = self.player_mon.get("element", "Normal")
        effectiveness = get_type_effectiveness(attacker_type, defender_type)
        dmg = int(dmg * effectiveness)
        dmg = max(1, dmg)
        
        # Apply player's defense boost from Defense Potion
        dmg = int(dmg / self.player_defense_boost)
        dmg = max(1, dmg)
        
        self.player_mon["hp"] = max(0, int(self.player_mon.get("hp", 0) - dmg))
        
        # Display effectiveness message
        if effectiveness >= 2.0:
            self.enqueue_message(f"{self.enemy_mon['name']} used {name}! It's super effective! {dmg} damage.", duration=3.0)
        elif effectiveness <= 0.5 and effectiveness > 0:
            self.enqueue_message(f"{self.enemy_mon['name']} used {name}. It's not very effective... {dmg} damage.", duration=3.0)
        elif effectiveness == 0:
            self.enqueue_message(f"{self.enemy_mon['name']} used {name}! But it has no effect...", duration=3.0)
        else:
            self.enqueue_message(f"{self.enemy_mon['name']} used {name}! It dealt {dmg} damage.", duration=3.0)
        self.turn = "player"
        if self.player_mon["hp"] <= 0:
            self.enqueue_message(f"{self.player_mon['name']} fainted!", duration=3.0)
            self._after_battle_end(victory=False)

    def use_item(self, idx: int):
        if self.turn != "player":
            return
        if self._time_since_action < 0.2:  # debounce
            return
        if idx < 0 or idx >= len(self.items):
            return

        item = self.items[idx]
        if item["count"] <= 0:
            self.enqueue_message("No more of that item.")
            return

        item_name = item.get("name", "").lower()
        item_type = item.get("item_type", "heal")

    # ----- Handle Pokéball separately -----
        if "pokeball" in item_name or "ball" in item_name:
            if isinstance(self.enemy_obj, dict):
                # Start ball throwing animation
                self.ball_throwing = True
                self.ball_throw_timer = 0.0
                self.ball_start_pos = (self.player_pos[0] + 150, self.player_pos[1] + 100)
                self.ball_end_pos = (self.enemy_pos[0] + 150, self.enemy_pos[1] + 150)
                self.pending_catch_item = item
                self.pending_catch_item_idx = idx
                
                # Load ball sprite for animation
                try:
                    if self.ball_sprite:
                        self.ball_sprite_throw = pg.transform.scale(self.ball_sprite, (32, 32))
                    else:
                        ball_path = str(Path("assets") / "images" / "ingame_ui" / "ball.png")
                        ball_img = pg.image.load(ball_path).convert_alpha()
                        self.ball_sprite_throw = pg.transform.scale(ball_img, (32, 32))
                except Exception:
                    pass
                self.turn = "anim"
            else:
                self.enqueue_message(f"Can't use {item['name']} on a trainer's Pokémon!")
            self._time_since_action = 0.0
            return

    # ----- Handle Heal Potion -----
        if item_type == "heal":
            heal = 30  # Heal Potion heals 30 HP
            old_hp = self.player_mon.get("hp", 0)
            self.player_mon["hp"] = min(self.player_mon.get("max_hp", 999), old_hp + heal)
            actual_heal = self.player_mon["hp"] - old_hp
            item["count"] -= 1
            # Update original bag item count
            self._update_bag_item_count(item["name"], -1)
            self.enqueue_message(f"Used {item['name']}! Restored {actual_heal} HP.")
            self.submenu = "main"
            self.turn = "enemy"

    # ----- Handle Strength Potion -----
        elif item_type == "strength":
            self.player_attack_boost = 1.5  # 50% damage increase
            item["count"] -= 1
            # Update original bag item count
            self._update_bag_item_count(item["name"], -1)
            self.enqueue_message(f"Used {item['name']}! Attack power increased!")
            self.submenu = "main"
            self.turn = "enemy"

    # ----- Handle Defense Potion -----
        elif item_type == "defense":
            self.player_defense_boost = 1.5  # 50% damage reduction
            item["count"] -= 1
            # Update original bag item count
            self._update_bag_item_count(item["name"], -1)
            self.enqueue_message(f"Used {item['name']}! Defense increased!")
            self.submenu = "main"
            self.turn = "enemy"

        # Update button text for this item only
        if 0 <= idx < len(self.item_buttons):
            self.item_buttons[idx].text = f"{item['name']} x{item['count']}"

        self._time_since_action = 0.0


    # battle end handling
    def _after_battle_end(self, victory: bool = False, escaped: bool = False):
        # Simple end: return to game scene after a short message
        if escaped:
            # go back immediately after message processed
            self.enqueue_message("Returning to the field...", duration=2.0)
        elif victory:
            self.enqueue_message("You won the battle!", duration=3.0)
        else:
            self.enqueue_message("You lost the battle...", duration=3.0)

        # set a flag so when message queue empties we exit
        # we'll put a marker message "__END__" to know when to exit
        self.message_queue.append("__END__")


    @override
    def enter(self):
        try:

            if isinstance(self.enemy_obj, dict):
            # Wild Pokémon battle
                sound_manager.play_bgm("RBY 110 Battle! (Wild Pokemon).ogg")
            else:
            # Trainer battle
                sound_manager.play_bgm("RBY 107 Battle! (Trainer).ogg")
        except Exception:
            pass

    @override
    def exit(self):
        try:
            sound_manager.stop_bgm()
        except Exception:
            pass

    @override
    def update(self, dt: float):
        # Update entrance animation
        if self.entrance_animation:
            self.entrance_timer += dt
            if self.entrance_timer >= self.entrance_duration:
                self.entrance_animation = False
                self.player_entrance_done = True
                self.enemy_entrance_done = True
            return  # Skip other updates during entrance animation
        
        # Update idle animation timer (cycle through frames)
        self.idle_animation_timer += dt
        if self.idle_animation_timer >= self.idle_animation_speed:
            self.idle_animation_timer = 0.0
            self.idle_frame_index = (self.idle_frame_index + 1) % 4
        
        # Update evolution display timer
        if self.evolution_display_timer > 0:
            self.evolution_display_timer -= dt
        
        # Update attack animation timer
        if self.attack_animation_timer > 0:
            self.attack_animation_timer -= dt
            # When attack animation ends, return to idle sprite
            if self.attack_animation_timer <= 0:
                if self.attacking_pokemon == "player" and self.player_idle_sprite:
                    self.player_mon["sprite"] = self.player_idle_sprite
                elif self.attacking_pokemon == "enemy" and self.enemy_idle_sprite:
                    self.enemy_mon["sprite"] = self.enemy_idle_sprite
                self.attacking_pokemon = None
        
        # Update ball throwing animation
        if self.ball_throwing:
            self.ball_throw_timer += dt
            if self.ball_throw_timer >= self.ball_throw_duration:
                # Throw complete, start capture animation
                self.ball_throwing = False
                self.capture_animation = True
                self.capture_timer = 0.0
                self.original_enemy_sprite = self.enemy_mon.get("sprite")
                # Determine catch success
                catch_chance = random.randint(1, 100)
                self.capture_success = catch_chance > 30
            return  # Skip other updates during animation
        
        # Update capture animation (Pokemon shrinking into ball)
        if self.capture_animation:
            self.capture_timer += dt
            if self.capture_timer >= self.capture_duration:
                # Capture animation complete, process result
                self.capture_animation = False
                item = self.pending_catch_item
                idx = self.pending_catch_item_idx
                
                if self.capture_success:
                    item["count"] -= 1
                    self._update_bag_item_count(item["name"], -1)
                    self.enqueue_message(f"Used {item['name']}! You caught {self.enemy_mon['name']}!")
                    # Hide enemy sprite after successful capture
                    self.enemy_mon["sprite"] = None
                    self.pokemon_captured = True
                    if self.bag and hasattr(self.bag, 'monsters'):
                        self.bag.monsters.append(self.enemy_mon.copy())
                        if self.game_manager:
                            self.game_manager.save("saves/game0.json")
                        self._after_battle_end(victory=True)
                else:
                    item["count"] -= 1
                    self._update_bag_item_count(item["name"], -1)
                    # Restore original sprite
                    if self.original_enemy_sprite:
                        self.enemy_mon["sprite"] = self.original_enemy_sprite
                    self.enqueue_message(f"Used {item['name']}! {self.enemy_mon['name']} broke free!")
                    self.submenu = "main"
                    self.turn = "enemy"
                
                # Update button text
                if 0 <= idx < len(self.item_buttons):
                    self.item_buttons[idx].text = f"{item['name']} x{item['count']}"
                
                self.pending_catch_item = None
                self.ball_sprite_throw = None
                self.original_enemy_sprite = None
            return  # Skip other updates during animation
        
        if self.showing_message:
    # countdown timer
            self.current_message_timer -= dt
            if self.current_message_timer <= 0:
                current = self.pop_message()
                if current == "__END__":
            # end battle, go back to game scene
                    try:
                        scene_manager.change_scene("game")
                    except Exception:
                        pass
            return  # skip normal input while showing message


        # Not showing message: normal input flow
        self._time_since_action += dt

        if self.submenu == "main":
            for b in self.main_buttons:
                b.update(dt)
        elif self.submenu == "fight":
            for b in self.move_buttons:
                b.update(dt)
        elif self.submenu == "bag":
            for b in self.item_buttons:
                b.update(dt)
        elif self.submenu == "monsters":
            for b in getattr(self, "monster_buttons", []):
                b.update(dt)


        # enemy automatic turn handling
        # If it's enemy's turn and there are no messages pending, perform enemy action
        if self.turn == "enemy" and not self.showing_message:
            # small delay so the player can see message
            self.enemy_use_move()

    @override
    def draw(self, screen: pg.Surface):
        # Background
        if self.background:
            self.background.draw(screen)
        else:
            screen.fill((60, 120, 180))  # fallback sky color

        # Calculate entrance animation progress
        entrance_progress = 0.0
        if self.entrance_animation:
            entrance_progress = min(1.0, self.entrance_timer / self.entrance_duration)
        
        # Draw entrance animation (Pokeballs releasing Pokemon)
        if self.entrance_animation:
            # Phase 1 (0-0.3): Show pokeballs
            # Phase 2 (0.3-0.6): White flash/explosion
            # Phase 3 (0.6-1.0): Pokemon growing from small to full size
            
            player_ball_pos = (self.player_pos[0] + 150, self.player_pos[1] + 150)
            enemy_ball_pos = (self.enemy_pos[0] + 150, self.enemy_pos[1] + 150)
            
            if entrance_progress < 0.3:
                # Phase 1: Draw pokeballs
                ball_scale = 1.0 + 0.2 * (entrance_progress / 0.3)  # Slight grow
                if self.ball_sprite:
                    ball_size = int(40 * ball_scale)
                    scaled_ball = pg.transform.scale(self.ball_sprite, (ball_size, ball_size))
                    screen.blit(scaled_ball, (player_ball_pos[0] - ball_size // 2, player_ball_pos[1] - ball_size // 2))
                    screen.blit(scaled_ball, (enemy_ball_pos[0] - ball_size // 2, enemy_ball_pos[1] - ball_size // 2))
                else:
                    # Fallback circles
                    pg.draw.circle(screen, (255, 50, 50), player_ball_pos, int(20 * ball_scale))
                    pg.draw.circle(screen, (255, 255, 255), player_ball_pos, int(20 * ball_scale), 3)
                    pg.draw.circle(screen, (255, 50, 50), enemy_ball_pos, int(20 * ball_scale))
                    pg.draw.circle(screen, (255, 255, 255), enemy_ball_pos, int(20 * ball_scale), 3)
            
            elif entrance_progress < 0.5:
                # Phase 2: White flash/burst effect
                flash_progress = (entrance_progress - 0.3) / 0.2
                flash_alpha = int(255 * (1.0 - flash_progress))
                flash_radius = int(50 + 100 * flash_progress)
                
                # Draw expanding white circles (flash effect)
                flash_surf = pg.Surface((flash_radius * 2, flash_radius * 2), pg.SRCALPHA)
                pg.draw.circle(flash_surf, (255, 255, 255, flash_alpha), (flash_radius, flash_radius), flash_radius)
                screen.blit(flash_surf, (player_ball_pos[0] - flash_radius, player_ball_pos[1] - flash_radius))
                screen.blit(flash_surf, (enemy_ball_pos[0] - flash_radius, enemy_ball_pos[1] - flash_radius))
            
            else:
                # Phase 3: Pokemon growing from center
                grow_progress = (entrance_progress - 0.5) / 0.5
                scale = grow_progress  # 0.0 to 1.0
                
                # Draw player Pokemon growing (use first idle frame if available)
                player_entrance_sprite = self.player_idle_frames[0] if self.player_idle_frames else self.player_mon.get("sprite")
                if player_entrance_sprite is not None:
                    try:
                        s = player_entrance_sprite
                        original_w, original_h = s.get_width(), s.get_height()
                        new_w = int(original_w * scale)
                        new_h = int(original_h * scale)
                        if new_w > 0 and new_h > 0:
                            scaled_sprite = pg.transform.scale(s, (new_w, new_h))
                            # Center on player position
                            draw_x = self.player_pos[0] + (original_w - new_w) // 2
                            draw_y = self.player_pos[1] + (original_h - new_h) // 2
                            screen.blit(scaled_sprite, (draw_x, draw_y))
                    except:
                        pass
                
                # Draw enemy Pokemon growing (use first idle frame if available)
                enemy_entrance_sprite = self.enemy_idle_frames[0] if self.enemy_idle_frames else self.enemy_mon.get("sprite")
                if enemy_entrance_sprite is not None:
                    try:
                        s = enemy_entrance_sprite
                        original_w, original_h = s.get_width(), s.get_height()
                        new_w = int(original_w * scale)
                        new_h = int(original_h * scale)
                        if new_w > 0 and new_h > 0:
                            scaled_sprite = pg.transform.scale(s, (new_w, new_h))
                            # Center on enemy position
                            draw_x = self.enemy_pos[0] + (original_w - new_w) // 2
                            draw_y = self.enemy_pos[1] + (original_h - new_h) // 2
                            screen.blit(scaled_sprite, (draw_x, draw_y))
                    except:
                        pass
            
            # Draw "Go!" text during entrance
            if entrance_progress > 0.2:
                go_text = self.font_big.render("Go!", True, (255, 255, 255))
                go_rect = go_text.get_rect(center=(GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT // 2 - 50))
                screen.blit(go_text, go_rect)
            
            return  # Don't draw normal battle UI during entrance

        # Draw enemy sprite (if available) with animation
        # Don't draw if Pokemon was successfully captured
        if not self.pokemon_captured:
            enemy_sprite = self._get_current_enemy_sprite()
            if enemy_sprite is not None:
                try:
                    s = enemy_sprite
                    # If capture animation is active, shrink the sprite
                    if self.capture_animation and self.original_enemy_sprite:
                        progress = self.capture_timer / self.capture_duration
                        scale = 1.0 - progress  # Shrink from 1.0 to 0.0
                        
                        if scale > 0.05:  # Only draw if not too small
                            original_rect = s.get_rect()
                            new_width = int(original_rect.width * scale)
                            new_height = int(original_rect.height * scale)
                            
                            if new_width > 0 and new_height > 0:
                                shrunk_sprite = pg.transform.scale(s, (new_width, new_height))
                                # Center the shrinking sprite at ball position
                                shrunk_rect = shrunk_sprite.get_rect(center=(self.ball_end_pos[0], self.ball_end_pos[1]))
                                screen.blit(shrunk_sprite, shrunk_rect)
                    else:
                        screen.blit(s, self.enemy_pos)
                except Exception:
                    pass
            else:
                # Only show placeholder if not during/after capture
                if not self.capture_animation:
                    # placeholder box
                    pg.draw.rect(screen, (200, 60, 60), pg.Rect(self.enemy_pos[0], self.enemy_pos[1], 300, 300))
                    name_surf = self.font_med.render(self.enemy_mon.get("name", "Enemy"), True, (255, 255, 255))
                    screen.blit(name_surf, (self.enemy_pos[0], self.enemy_pos[1] - 24))

        # Draw player sprite with animation
        player_sprite = self._get_current_player_sprite()
        if player_sprite is not None:
            try:
                s = player_sprite
                screen.blit(s, self.player_pos)
            except Exception:
                pass
        else:
            pg.draw.rect(screen, (60, 160, 60), pg.Rect(self.player_pos[0], self.player_pos[1], 300, 300))
            name_surf = self.font_med.render(self.player_mon.get("name", "Player"), True, (255, 255, 255))
            screen.blit(name_surf, (self.player_pos[0], self.player_pos[1] - 24))

        # Draw Pokemon info banners with name, element, and HP bar
        # Player Pokemon banner (bottom-left, near the player sprite)
        self._draw_pokemon_info_banner(screen, self.player_mon, 20, 10, is_player=True)
        
        # Enemy Pokemon banner (top-right, near the enemy sprite)
        enemy_banner_x = GameSettings.SCREEN_WIDTH - 270
        self._draw_pokemon_info_banner(screen, self.enemy_mon, enemy_banner_x, 10, is_player=False)
        
        # Draw Pokemon ball indicators for enemy team (below enemy banner)
        if len(self.enemy_team) > 1:
            ball_x = enemy_banner_x
            ball_y = 105  # Below the banner (banner ends at y=100)
            ball_spacing = 28
            for i, mon in enumerate(self.enemy_team):
                # Draw ball sprite if alive, gray version if fainted
                if mon.get("hp", 0) > 0:
                    if self.ball_sprite:
                        screen.blit(self.ball_sprite, (ball_x + i * ball_spacing, ball_y))
                    else:
                        # Fallback to circles
                        pg.draw.circle(screen, (255, 50, 50), (ball_x + i * ball_spacing + 12, ball_y + 12), 10)
                        pg.draw.circle(screen, (255, 255, 255), (ball_x + i * ball_spacing + 12, ball_y + 12), 10, 2)
                else:
                    if self.ball_sprite_gray:
                        screen.blit(self.ball_sprite_gray, (ball_x + i * ball_spacing, ball_y))
                    else:
                        # Fallback to circles
                        pg.draw.circle(screen, (100, 100, 100), (ball_x + i * ball_spacing + 12, ball_y + 12), 10)
                        pg.draw.circle(screen, (200, 200, 200), (ball_x + i * ball_spacing + 12, ball_y + 12), 10, 2)

        # Draw bottom command area (text-menu like Gen1)
        box = pg.Rect(0, GameSettings.SCREEN_HEIGHT - 180, GameSettings.SCREEN_WIDTH, 180)
        if self.ui_frame:
            screen.blit(self.ui_frame, (0, GameSettings.SCREEN_HEIGHT - 180))
        else:
            # Fallback to colored rectangles if frame image failed to load
            pg.draw.rect(screen, (40, 40, 40), box)
            pg.draw.rect(screen, (200, 200, 200), box, 3)

        # Draw menus
        if self.submenu == "main":
            for b in self.main_buttons:
                b.draw(screen)
        elif self.submenu == "fight":
            for b in self.move_buttons:
                b.draw(screen)
        elif self.submenu == "bag":
            if not self.item_buttons:
                txt = self.font_med.render("No items.", True, (255, 255, 255))
                screen.blit(txt, (40, GameSettings.SCREEN_HEIGHT - 150))
            else:
                for b in self.item_buttons:
                    b.draw(screen)
        elif self.submenu == "monsters":
            if not getattr(self, "monster_buttons", None):
                txt = self.font_med.render("No monsters.", True, (255, 255, 255))
                screen.blit(txt, (40, GameSettings.SCREEN_HEIGHT - 150))
            else:
                for b in self.monster_buttons:
                    b.draw(screen)

        # Draw ball throwing animation
        if (self.ball_throwing or self.capture_animation) and self.ball_sprite_throw and self.ball_start_pos and self.ball_end_pos:
            if self.ball_throwing:
                # Calculate current position using parabolic arc
                progress = self.ball_throw_timer / self.ball_throw_duration
                progress = min(progress, 1.0)
                
                # Linear interpolation for x
                current_x = self.ball_start_pos[0] + (self.ball_end_pos[0] - self.ball_start_pos[0]) * progress
                
                # Parabolic arc for y (goes up then down)
                arc_height = 150  # How high the ball arcs
                current_y = self.ball_start_pos[1] + (self.ball_end_pos[1] - self.ball_start_pos[1]) * progress
                current_y -= arc_height * (1 - (2 * progress - 1) ** 2)  # Parabolic trajectory
                
                # Rotate the ball as it flies
                rotation_angle = progress * 360 * 2  # 2 full rotations
                rotated_ball = pg.transform.rotate(self.ball_sprite_throw, rotation_angle)
                ball_rect = rotated_ball.get_rect(center=(int(current_x), int(current_y)))
                screen.blit(rotated_ball, ball_rect)
            elif self.capture_animation:
                # Keep ball at end position during capture
                screen.blit(self.ball_sprite_throw, self.ball_sprite_throw.get_rect(center=self.ball_end_pos))

        # Draw evolution display overlay
        if self.evolution_display_timer > 0 and self.evolution_display_text:
            # Draw semi-transparent overlay
            overlay = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            screen.blit(overlay, (0, 0))
            
            # Draw evolution text in center
            try:
                evolution_font = pg.font.Font("assets/fonts/Minecraft.ttf", 48)
            except:
                evolution_font = pg.font.Font(None, 48)
            evolution_text_surf = evolution_font.render(self.evolution_display_text, True, (255, 255, 0))
            evolution_text_rect = evolution_text_surf.get_rect(center=(GameSettings.SCREEN_WIDTH // 2, GameSettings.SCREEN_HEIGHT // 2))
            screen.blit(evolution_text_surf, evolution_text_rect)

        # Draw message box if any message showing
        if self.showing_message and self.message_queue:
            # draw top message
            fm = self.font_med
            # box
            pg.draw.rect(screen, (0, 0, 0), self.msg_rect)
            pg.draw.rect(screen, (255, 255, 255), self.msg_rect, 2)
            # display first queued message
            msg = self.message_queue[0] if self.message_queue else ""
            lines = []
            # wrap text simple
            max_chars = 60
            while len(msg) > 0:
                lines.append(msg[:max_chars])
                msg = msg[max_chars:]
            for i, line in enumerate(lines[:3]):
                screen.blit(fm.render(line, True, (255, 255, 255)), (self.msg_rect.x + 8, self.msg_rect.y + 8 + i * 20))

        # If not showing message, optionally show a prompt line
        if not self.showing_message and self.turn == "player":
            prompt = self.font_med.render("Choose an action.", True, (200, 200, 200))
            screen.blit(prompt, (GameSettings.SCREEN_WIDTH - 240, GameSettings.SCREEN_HEIGHT - 36))

