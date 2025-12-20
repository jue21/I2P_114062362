import pygame as pg
import threading
import time
import math
from pathlib import Path

from src.scenes.scene import Scene
from src.core import GameManager, OnlineManager
from src.utils import Logger, PositionCamera, GameSettings, Position
from src.core.services import sound_manager, input_manager
from src.sprites import Sprite, Animation
from src.interface.components import Button
from src.interface.components.shop_overlay import ShopOverlay
from src.interface.components.navigation_overlay import NavigationOverlay
from src.interface.components.chat_overlay import ChatOverlay
from typing import override, Dict, Tuple
from src.interface.components import Checkbox, Slider
from src.utils.definition import load_monster_sprites
import random
from src.scenes.catch_scene import CatchMonsterScene
from src.core.services import scene_manager
from src.utils.encounters import generate_random_monster
from src.entities.pokemon_follower import PokemonFollower

class GameScene(Scene):
    game_manager: GameManager
    online_manager: OnlineManager | None
    sprite_online: Sprite
    online_animations: dict[str, Animation]
    _chat_bubbles: Dict[int, Tuple[str, float]]
    _online_last_pos: Dict[int, Position]
    _last_chat_id_seen: int
    _chat_font: pg.font.Font | None

    def __init__(self):
        super().__init__()
        # --- Game manager setup ---
        manager = GameManager.load("saves/game0.json")
        if manager is None:
            Logger.error("Failed to load game manager")
            exit(1)
        self.game_manager = manager

        if GameSettings.IS_ONLINE:
            self.online_manager = OnlineManager()
            self.online_manager.start()
        else:
            self.online_manager = None

        self.sprite_online = Sprite("ingame_ui/options1.png", (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE))
        self.online_animations = {}
        
        # Online player indicator icon (shown above player's head when others are connected)
        self.online_indicator_icon = None
        try:
            self.online_indicator_icon = pg.image.load("assets/images/UI/raw/UI_Flat_IconPoint01a.png").convert_alpha()
            self.online_indicator_icon = pg.transform.scale(self.online_indicator_icon, (24, 24))
        except Exception as e:
            Logger.warning(f"Failed to load online indicator icon: {e}")
        
        # --- Chat system ---
        self._chat_bubbles: Dict[int, Tuple[str, float]] = {}
        self._online_last_pos: Dict[int, Position] = {}
        self._last_chat_id_seen = 0
        self._chat_font = pg.font.Font(None, 20)
        
        # --- Chat Overlay ---
        self._chat_overlay = ChatOverlay(
            send_callback=self._send_chat_message,
            get_messages=self._get_chat_messages
        ) if GameSettings.IS_ONLINE else None
        
        # --- Overlay / Menu state ---
        self.overlay_open = False

        # --- Bush interaction state ---
        self.bush_touched = False

        self.warning_sprite = pg.image.load("assets/images/exclamation.png").convert_alpha()
        self.warning_sprite = pg.transform.scale(self.warning_sprite, (32, 32))  # size as needed
        self.warning_visible = False
        self.warning_position = None
        self.warning_bounce = 0
        self.warning_bounce_dir = 1  # 1 = up, -1 = down
        self.warning_bounce_speed = 30  # pixels per second
        
        # Bush warning display for debugging
        self.bush_warning_visible = False
        self.bush_warning_position = None

        # --- Battle Transition (Cloud Screen) ---
        self.transition_active = False
        self.transition_timer = 0.0
        self.transition_duration = 1.5  # Total transition duration
        self.transition_phase = "in"  # "in" = clouds coming in, "out" = clouds going out
        self.pending_battle_scene = None
        self.pending_battle_scene_name = None
        self._init_cloud_surfaces()

        # --- Christmas Decorations ---
        self._init_christmas_decorations()

        # --- Mini-map setup ---
        self.minimap_size = 200  # mini-map is 200x200 pixels
        self.minimap_pos = (10, 10)  # top-left corner with 10px padding
        self.minimap_surface = None
        self._minimap_needs_update = False  # Flag to delay minimap update by one frame
        self._create_minimap()

        # --- Top-right settings button ---
        self.settings_button = Button(
            "UI/button_setting.png",
            "UI/button_setting_hover.png",
            GameSettings.SCREEN_WIDTH - 120,  # X position (top-right)
            20,                              # Y position
            70, 70,                          # Width, height
            lambda: self._open_overlay()     # Opens overlay
        )

        # --- Overlay box --- layout info
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        overlay_w, overlay_h = 500, 350
        self.overlay_box_rect = pg.Rect(
            (sw - overlay_w) // 2, (sh - overlay_h) // 2, overlay_w, overlay_h
        )

        # --- Top-right backpack button (beside settings) ---
        self.backpack_button = Button(
            "UI/button_backpack.png",
            "UI/button_backpack_hover.png",
            GameSettings.SCREEN_WIDTH - 200,  # left of settings button
            20,
            70, 70,
            lambda: self._open_backpack()
        )

        # --- Top-right shop button (beside backpack) ---
        self.shop_button = Button(
            "UI/button_shop.png",
            "UI/button_shop_hover.png",
            GameSettings.SCREEN_WIDTH - 280,  # left of backpack button
            20,
            70, 70,
            lambda: self._handle_shop_button()
        )
        self.shop_button_visible = False  # Only show when near shopkeeper

        # --- Top-right navigation button (beside shop) ---
        self.navigation_button = Button(
            "UI/raw/UI_Flat_Button02a_4.png",
            "UI/raw/UI_Flat_Button02a_4.png",  # Will handle hover effect manually
            GameSettings.SCREEN_WIDTH - 360,  # left of shop button
            20,
            70, 70,
            lambda: self._open_navigation()
        )
        
        # Load navigation logo
        self.navigation_logo = None
        try:
            self.navigation_logo = pg.image.load("assets/images/direction-icon-png-4710.png").convert_alpha()
            self.navigation_logo = pg.transform.scale(self.navigation_logo, (50, 50))
        except Exception:
            pass
        
        # Navigation button hover effect
        self.navigation_button_hover_scale = 1.0
        
        # --- Navigation Overlay ---
        self.navigation_overlay = NavigationOverlay(self.game_manager)

        self.backpack_open = False

        backpack_w, backpack_h = 600, 400

        # backpack overlay box
        self.backpack_box_rect = pg.Rect(
            (sw - backpack_w) // 2,
            (sh - backpack_h) // 2,
            backpack_w,
            backpack_h
        )

        close_btn_size = 40
        close_btn_x = self.backpack_box_rect.right - close_btn_size - 10  # 10 px padding from right edge
        close_btn_y = self.backpack_box_rect.y + 10  # 10 px padding from top edge

        self.backpack_close_button = Button(
            "UI/button_x.png",
            "UI/button_x_hover.png",
            close_btn_x,
            close_btn_y,
            close_btn_size,
            close_btn_size,
            lambda: self._close_backpack()
        )

        self.backpack_scroll_y = 0  # initial scroll offset
        self.backpack_scroll_speed = 20  # pixels per scroll
        
        # Load banner image for monster blocks
        try:
            self.monster_banner = pg.image.load("assets/images/UI/raw/UI_Flat_Banner03a.png").convert_alpha()
        except:
            self.monster_banner = None  # Fallback if image not found
        
        # --- Backpack tabs ---
        self.backpack_tab = "monsters"  # "monsters" or "items"
        self.backpack_monsters_button = Button(
            "UI/button_setting.png",
            "UI/button_setting_hover.png",
            self.backpack_box_rect.x + 20,
            self.backpack_box_rect.y + 50,
            100, 40,
            lambda: self._set_backpack_tab("monsters")
        )
        self.backpack_items_button = Button(
            "UI/button_setting.png",
            "UI/button_setting_hover.png",
            self.backpack_box_rect.x + 130,
            self.backpack_box_rect.y + 50,
            100, 40,
            lambda: self._set_backpack_tab("items")
        )

        # --- Shop Overlay ---
        self.shop_overlay = None  # Will be set when player interacts with shopkeeper
        self.shop_open = False

        # --- Back button inside overlay ---
        back_w, back_h = 70, 70
        back_x = self.overlay_box_rect.x + (self.overlay_box_rect.width - back_w) // 2
        back_y = self.overlay_box_rect.y + self.overlay_box_rect.height - back_h - 20
        self.back_button = Button(
            "UI/button_back.png",
            "UI/button_back_hover.png",
            back_x, back_y,
            back_w, back_h,
            lambda: self._close_overlay()
        )

        # Fonts
        font_path = "assets/fonts/Minecraft.ttf"
        self._font_med = pg.font.Font(font_path, 28)

        # Dark overlay surface
        self._dark_surface = pg.Surface((sw, sh), pg.SRCALPHA)
        self._dark_surface.fill((0, 0, 0, 150))  # semi-transparent black

        # Checkbox example
        self.checkbox_sound = Checkbox(
            self.overlay_box_rect.x + 30,
            self.overlay_box_rect.y + 60,
            label="Mute",
            checked=True
        )

    # Slider example
        self.slider_music = Slider(
            self.overlay_box_rect.x + 30,
            self.overlay_box_rect.y + 120,
            width=200,
            value=70
        )

        # Save button
        save_w, save_h = 70, 70
        padding = 20
        save_x = self.overlay_box_rect.x + padding  # left side
        save_y = self.overlay_box_rect.y + self.overlay_box_rect.height - save_h - padding

        self.save_button = Button(
            "UI/button_save.png",
            "UI/button_save_hover.png",
            save_x, save_y,
            save_w, save_h,
            lambda: self.game_manager.save("saves/game0.json")
        )


        def function_load():
            Logger.info("Load button clicked.")
            new_game_manager = GameManager.load("saves/game0.json")
            if new_game_manager:
                self.game_manager = new_game_manager
                Logger.info("Game loaded successfully.")
            else:
                Logger.error("Failed to load game during load button click.")


        # Load button
        load_x = save_x + save_w + padding  # right of Save button with some space
        load_y = save_y
        self.load_button = Button(
            "UI/button_load.png",
            "UI/button_load_hover.png",
            load_x, load_y,
            save_w, save_h,
            lambda: function_load()  # call GameManager API
        )

        self.backpack_scroll_y = 0
        self.backpack_scroll_speed = 20

        # --- Pokemon Follower ---
        self.pokemon_follower = None  # Will be set when player selects a monster to follow
        self._follow_button_rects = {}  # Initialize follow button rects

        # --- Online Battle Dialog ---
        self.online_battle_dialog_open = False
        self.online_battle_target_id = None  # Player ID of the online player to battle
        self._online_battle_dialog_font = pg.font.Font("assets/fonts/Minecraft.ttf", 20)
        self._online_battle_title_font = pg.font.Font("assets/fonts/Minecraft.ttf", 24)
        # Dialog box dimensions
        dialog_w, dialog_h = 400, 150
        self.online_battle_dialog_rect = pg.Rect(
            (sw - dialog_w) // 2, (sh - dialog_h) // 2, dialog_w, dialog_h
        )
        # Yes/No button dimensions and positions
        btn_w, btn_h = 100, 40
        btn_y = self.online_battle_dialog_rect.y + self.online_battle_dialog_rect.height - btn_h - 20
        self.online_battle_yes_rect = pg.Rect(
            self.online_battle_dialog_rect.x + 60, btn_y, btn_w, btn_h
        )
        self.online_battle_no_rect = pg.Rect(
            self.online_battle_dialog_rect.right - 60 - btn_w, btn_y, btn_w, btn_h
        )
        
        # --- Incoming Challenge Dialog ---
        self.incoming_challenge_open = False
        self.incoming_challenge_from_id = -1  # Player ID who challenged us
        self.incoming_challenge_opponent_monster = None  # Monster data from challenger
        # Reuse same dialog dimensions for incoming challenge
        self.incoming_challenge_dialog_rect = pg.Rect(
            (sw - dialog_w) // 2, (sh - dialog_h) // 2, dialog_w, dialog_h
        )
        self.incoming_challenge_yes_rect = pg.Rect(
            self.incoming_challenge_dialog_rect.x + 60, btn_y, btn_w, btn_h
        )
        self.incoming_challenge_no_rect = pg.Rect(
            self.incoming_challenge_dialog_rect.right - 60 - btn_w, btn_y, btn_w, btn_h
        )
        
        # --- Challenge Status ---
        self.waiting_for_challenge_response = False  # True when we sent a challenge and waiting
        self.challenge_declined_message_timer = 0.0  # Timer to show "Challenge declined" message

        # --- Loading animation shown when entering the scene ---
        self.show_loading = False
        self.loading_duration = 3.0  # seconds
        self.loading_timer = 0.0
        self._loading_angle = 0.0
        self.loading_ball_sprite = None
        try:
            ball_path = str(Path("assets") / "images" / "ingame_ui" / "ball.png")
            ball_img = pg.image.load(ball_path).convert_alpha()
            self.loading_ball_sprite = pg.transform.scale(ball_img, (96, 96))
        except Exception:
            self.loading_ball_sprite = None

    def _open_overlay(self):
        self.overlay_open = True

    def _close_overlay(self):
        self.overlay_open = False

    def _open_backpack(self):
        self.backpack_open = True
        self.overlay_open = False  # optional: prevent both opening at once

    def _close_backpack(self):
        self.backpack_open = False
    
    def _set_pokemon_follower(self, monster_index: int):
        """Set a Pokemon from the bag to follow the player."""
        if monster_index < 0 or monster_index >= len(self.game_manager.bag.monsters):
            return
        
        monster = self.game_manager.bag.monsters[monster_index]
        if self.game_manager.player:
            player_pos = self.game_manager.player.position
            if self.pokemon_follower is None:
                self.pokemon_follower = PokemonFollower(monster, player_pos)
            else:
                self.pokemon_follower.set_monster(monster, player_pos)
            Logger.info(f"Pokemon {monster.get('name', 'Unknown')} is now following the player!")
        self._close_backpack()
    
    def _remove_pokemon_follower(self):
        """Remove the currently following Pokemon."""
        self.pokemon_follower = None
        Logger.info("Pokemon follower removed.")
    
    def _open_navigation(self):
        """Open the navigation overlay."""
        self.navigation_overlay.open()
        self.overlay_open = False
        self.backpack_open = False
        self.shop_open = False
    
    def _set_backpack_tab(self, tab: str):
        """Switch backpack tab and reset scroll."""
        self.backpack_tab = tab
        self.backpack_scroll_y = 0
    
    def _open_shop(self, shopkeeper):
        """Open shop overlay for a shopkeeper."""
        self.shop_overlay = ShopOverlay(shopkeeper, self.game_manager.bag, self._font_med)
        self.shop_overlay.close_button.on_click = self._close_shop
        self.shop_open = True
    
    def _close_shop(self):
        """Close the shop overlay."""
        self.shop_open = False
        self.shop_overlay = None

    def _handle_shop_button(self):
        """Handle shop button click - opens shop if near a shopkeeper."""
        if self.game_manager.player:
            player_rect = self.game_manager.player.get_rect()
            interaction_range = player_rect.inflate(GameSettings.TILE_SIZE * 2, GameSettings.TILE_SIZE * 2)
            
            for shopkeeper in getattr(self.game_manager.current_map, 'shopkeepers', []):
                if interaction_range.colliderect(shopkeeper.animation.rect):
                    self._open_shop(shopkeeper)
                    return


    @override
    def enter(self) -> None:
        sound_manager.play_bgm("RBY 103 Pallet Town.ogg")
        if self.online_manager:
            self.online_manager.enter()
        
        # Reset all enemies to idle state
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.state = "idle"
            enemy.detected = False
            enemy.alert_time = 0.0
        # Start a short loading animation to cover any setup delay
        self.show_loading = True
        self.loading_timer = self.loading_duration
        self._loading_angle = 0.0

    @override
    def exit(self) -> None:
        if self.online_manager:
            self.online_manager.exit()

    def _trigger_battle(self, enemy):
        """
        Called when player interacts with enemy to start battle.
        """
        
        # Switch to BattleScene with cloud transition
        from src.scenes.battle_scene import BattleScene
        from src.core.services import scene_manager
        Logger.info(f"Battle started with {enemy.name}!")
        # Pass the first monster from the bag as the player's active monster
        player_mon = self.game_manager.bag.monsters[0] if self.game_manager.bag.monsters else None
        # Generate 1-3 random monsters for the enemy trainer
        enemy_team_size = random.randint(1, 3)
        enemy_team = [generate_random_monster() for _ in range(enemy_team_size)]
        battle_scene = BattleScene(player=self.game_manager.player, player_mon=player_mon, enemy=enemy_team, bag=self.game_manager.bag, game_manager=self.game_manager)
        
        # Start cloud transition instead of immediate scene change
        self._start_battle_transition(battle_scene, "battle")

    def _trigger_online_battle(self, opponent_id: int, opponent_monster: dict = None):
        Logger.info(f"[DEBUG] _trigger_online_battle called: my_id={self.online_manager.player_id if self.online_manager else None}, opponent_id={opponent_id}, opponent_monster={opponent_monster}")
        """
        Start a battle with an online player (called when both players agree).
        """
        from src.scenes.battle_scene import BattleScene
        Logger.info(f"Online battle started with player {opponent_id}!")

        # Get our own player ID
        my_id = self.online_manager.player_id if self.online_manager else -1
        # Get our own monster
        my_mon = self.game_manager.bag.monsters[0] if self.game_manager.bag.monsters else None

        # If we are the challenger, our monster is always player_mon
        # If we are the accepter, the challenger is always player_mon
        # The server always sends opponent_id as the other player's ID
        # So, if my_id < opponent_id, I am the challenger (lower ID challenges higher ID)
        # If my_id > opponent_id, I am the accepter
        if my_id < 0 or opponent_monster is None or my_mon is None:
            Logger.warning(f"Could not determine battle roles: my_id={my_id}, opponent_id={opponent_id}, my_mon={my_mon}, opponent_monster={opponent_monster}")
            return

        # Always use the same order: challenger is player_mon, accepter is enemy_mon
        if my_id < opponent_id:
            # I am the challenger
            player_mon = my_mon
            enemy_mon = dict(opponent_monster)
            Logger.info(f"I am the challenger. player_mon={player_mon.get('name')}, enemy_mon={enemy_mon.get('name')}")
        else:
            # I am the accepter
            player_mon = dict(opponent_monster)
            enemy_mon = my_mon
            Logger.info(f"I am the accepter. player_mon={player_mon.get('name')}, enemy_mon={enemy_mon.get('name')}")

        enemy_mon["sprite"] = None  # Will be loaded by BattleScene
        enemy_team = [enemy_mon]

        battle_scene = BattleScene(
            player=self.game_manager.player,
            player_mon=player_mon,
            enemy=enemy_team,
            bag=self.game_manager.bag,
            game_manager=self.game_manager
        )

        # Start cloud transition
        self._start_battle_transition(battle_scene, f"online_battle_{opponent_id}")

    def _close_online_battle_dialog(self):
        """Close the online battle confirmation dialog."""
        self.online_battle_dialog_open = False
        self.online_battle_target_id = None

    def _get_serializable_monster_data(self) -> dict:
        """Get the player's active monster data in a format that can be sent over the network."""
        if not self.game_manager.bag.monsters:
            Logger.warning("No monsters in bag to serialize!")
            return None
        monster = self.game_manager.bag.monsters[0]
        Logger.info(f"Serializing monster for network: {monster.get('name', 'Unknown')}")
        # Create a copy without the sprite (can't serialize pygame surfaces)
        return {
            "name": monster.get("name", "Unknown"),
            "hp": monster.get("hp", 50),
            "max_hp": monster.get("max_hp", 50),
            "level": monster.get("level", 1),
            "element": monster.get("element", "Normal"),
            "sprite_path": monster.get("sprite_path", ""),
            "moves": monster.get("moves", []),
            "evolved_form": monster.get("evolved_form", ""),
            "evolution_level": monster.get("evolution_level", 0),
        }

    def _confirm_online_battle(self):
        """Called when user clicks 'Yes' to send battle challenge."""
        if self.online_battle_target_id is not None and self.online_manager:
            # Get our monster data to send
            monster_data = self._get_serializable_monster_data()
            # Send challenge through server with our monster data
            self.online_manager.send_battle_challenge(self.online_battle_target_id, monster_data)
            self.waiting_for_challenge_response = True
            Logger.info(f"Sent battle challenge to player {self.online_battle_target_id} with monster {monster_data.get('name') if monster_data else 'None'}")
        self._close_online_battle_dialog()

    def _accept_incoming_challenge(self):
        """Accept an incoming battle challenge."""
        if self.incoming_challenge_from_id >= 0 and self.online_manager:
            # Get our monster data to send
            monster_data = self._get_serializable_monster_data()
            self.online_manager.accept_battle_challenge(self.incoming_challenge_from_id, monster_data)
            Logger.info(f"Accepted battle challenge from player {self.incoming_challenge_from_id}")
        self.incoming_challenge_open = False
        self.incoming_challenge_from_id = -1
        self.incoming_challenge_opponent_monster = None

    def _decline_incoming_challenge(self):
        """Decline an incoming battle challenge."""
        if self.incoming_challenge_from_id >= 0 and self.online_manager:
            self.online_manager.decline_battle_challenge(self.incoming_challenge_from_id)
            Logger.info(f"Declined battle challenge from player {self.incoming_challenge_from_id}")
        self.incoming_challenge_open = False
        self.incoming_challenge_from_id = -1
        self.incoming_challenge_opponent_monster = None

    @override
    def update(self, dt: float):
        if GameSettings.DEBUG:
            Logger.debug(f"GameScene.update running, dt={dt}")
        # If loading animation active, update it and skip normal updates
        if getattr(self, 'show_loading', False):
            self.loading_timer -= dt
            self._loading_angle = (self._loading_angle + dt * 180.0) % 360.0
            if self.loading_timer <= 0:
                self.show_loading = False
            return
        # Update battle transition if active
        if self.transition_active:
            self._update_transition(dt)
            return  # Skip other updates during transition
        
        # --- Check for online battle events ---
        if self.online_manager:
            # Check if someone is challenging us (allow challenge to appear even if other dialogs are open)
            challenger_id, challenger_monster = self.online_manager.get_pending_challenge()
            if challenger_id >= 0 and not self.incoming_challenge_open:
                # Close other dialogs when a challenge comes in
                self.online_battle_dialog_open = False
                self.online_battle_target_id = None
                self.overlay_open = False
                self.backpack_open = False
                self.shop_open = False
                
                self.incoming_challenge_open = True
                self.incoming_challenge_from_id = challenger_id
                self.incoming_challenge_opponent_monster = challenger_monster
                monster_name = challenger_monster.get('name', 'None') if challenger_monster else 'None'
                Logger.info(f"CHALLENGE RECEIVED: from player {challenger_id}, their monster: {monster_name}")
            
            # Check if battle should start (both players agreed)
            battle_opponent, opponent_monster = self.online_manager.get_battle_start_opponent()
            if battle_opponent >= 0:
                self.waiting_for_challenge_response = False
                self.incoming_challenge_open = False
                monster_name = opponent_monster.get('name', 'None') if opponent_monster else 'None'
                Logger.info(f"BATTLE STARTING: opponent {battle_opponent}, their monster: {monster_name}")
                self._trigger_online_battle(battle_opponent, opponent_monster)
                return  # Don't process other updates, battle is starting
            
            # Check if our challenge was declined
            if self.online_manager.was_challenge_declined():
                self.waiting_for_challenge_response = False
                self.challenge_declined_message_timer = 3.0  # Show message for 3 seconds
                Logger.info("Battle challenge was declined")
        
        # Update challenge declined message timer
        if self.challenge_declined_message_timer > 0:
            self.challenge_declined_message_timer -= dt
        
        # Update game objects first
        prev_map_key = self.game_manager.current_map_key
        self.game_manager.try_switch_map()
        
        # Check if map changed
        map_changed = self.game_manager.current_map_key != prev_map_key
        
        # If map changed, schedule minimap recreation for next frame to avoid rendering glitches
        if map_changed:
            self._minimap_needs_update = True
        
        # Update minimap from previous frame's map change (with delay to ensure map is fully loaded)
        if self._minimap_needs_update:
            self._create_minimap()
            self._minimap_needs_update = False
        
        if self.game_manager.player:
            # Don't update player movement when chat is open
            if not (self._chat_overlay and self._chat_overlay.is_open):
                self.game_manager.player.update(dt)
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.update(dt)
        # Update shopkeeper positions for collision detection (but don't animate)
        for shopkeeper in self.game_manager.current_map.shopkeepers:
            shopkeeper.animation.update_pos(shopkeeper.position)
        self.game_manager.bag.update(dt)
        
        # Update Pokemon follower
        if self.pokemon_follower and self.game_manager.player:
            self.pokemon_follower.update(dt, self.game_manager.player.position)
        
        # Update falling leaves
        self._update_leaves(dt)

        if self.game_manager.player and self.online_manager:
            # Convert direction enum to string
            direction_str = self.game_manager.player.direction.name.lower()
            self.online_manager.update(
                self.game_manager.player.position.x,
                self.game_manager.player.position.y,
                self.game_manager.current_map.path_name,
                direction_str,
                self.game_manager.player.is_moving
            )
            
            # Update online player animations
            current_players = set()
            for player_data in self.online_manager.get_list_players():
                if player_data["map"] == self.game_manager.current_map.path_name:
                    player_id = player_data["id"]
                    current_players.add(player_id)
                    
                    # Create animation if not exists
                    if player_id not in self.online_animations:
                        self.online_animations[player_id] = Animation(
                            "character/ow1.png", ["down", "left", "right", "up"], 4,
                            (GameSettings.TILE_SIZE, GameSettings.TILE_SIZE)
                        )
                    
                    # Update animation
                    animation = self.online_animations[player_id]
                    pos = Position(player_data["x"], player_data["y"])
                    animation.update_pos(pos)
                    
                    # Set direction
                    direction = player_data.get("direction", "down")
                    animation.switch(direction)
                    
                    # Update animation based on movement
                    is_moving = player_data.get("is_moving", False)
                    if is_moving:
                        animation.update(dt)
                    else:
                        animation.accumulator = 0
            
            # Remove animations for players who left
            to_remove = [pid for pid in self.online_animations.keys() if pid not in current_players]
            for pid in to_remove:
                del self.online_animations[pid]
            
            # Update chat bubbles from recent messages
            try:
                msgs = self.online_manager.get_recent_chat(50)
                max_id = self._last_chat_id_seen
                now = time.monotonic()
                for m in msgs:
                    mid = int(m.get("id", 0))
                    if mid <= self._last_chat_id_seen:
                        continue
                    sender = int(m.get("from", -1))
                    text = str(m.get("text", ""))
                    if sender >= 0 and text:
                        self._chat_bubbles[sender] = (text, now + 5.0)
                    if mid > max_id:
                        max_id = mid
                self._last_chat_id_seen = max_id
            except Exception:
                pass
        
        # Update chat overlay
        if self._chat_overlay:
            if input_manager.key_pressed(pg.K_t):
                self._chat_overlay.open()
            self._chat_overlay.update(dt)

        # Bush state tracking - MUST happen before spacebar check
        if self.game_manager.player:
            self.bush_warning_visible = False
            player_rect = self.game_manager.player.get_rect()
            
            for bush in self.game_manager.current_map.bushes:
                collision = player_rect.colliderect(bush.rect)
                
                if collision:
                    bush.in_bush = True
                else:
                    bush.in_bush = False
        
        # Check for spacebar to trigger battle with alert enemy or bush encounter
        spacebar_pressed = (not self.overlay_open and not self.backpack_open and not self.shop_open and
                           not self.online_battle_dialog_open and
                           (input_manager.key_pressed(pg.K_SPACE) or input_manager.key_pressed(pg.K_RETURN)))
        
        if spacebar_pressed:
            # First check if player is near an online player
            online_player_found = False
            if self.game_manager.player and self.online_manager and len(self.online_animations) > 0:
                player_pos = self.game_manager.player.position
                # Check distance to each online player
                for player_id, animation in self.online_animations.items():
                    online_pos = Position(animation.rect.x, animation.rect.y)
                    # Calculate distance (use animation world position)
                    for player_data in self.online_manager.get_list_players():
                        if player_data["id"] == player_id and player_data["map"] == self.game_manager.current_map.path_name:
                            online_world_pos = Position(player_data["x"], player_data["y"])
                            dist = ((player_pos.x - online_world_pos.x) ** 2 + (player_pos.y - online_world_pos.y) ** 2) ** 0.5
                            if dist < GameSettings.TILE_SIZE * 2:  # Within 2 tiles
                                self.online_battle_dialog_open = True
                                self.online_battle_target_id = player_id
                                online_player_found = True
                                break
                    if online_player_found:
                        break
            
            # If no online player nearby, check for shopkeeper
            shopkeeper_found = False
            if not online_player_found and self.game_manager.player:
                player_rect = self.game_manager.player.get_rect()
                # Expand rect to check nearby tiles
                interaction_range = player_rect.inflate(GameSettings.TILE_SIZE * 2, GameSettings.TILE_SIZE * 2)
                
                for shopkeeper in getattr(self.game_manager.current_map, 'shopkeepers', []):
                    if interaction_range.colliderect(shopkeeper.animation.rect):
                        self._open_shop(shopkeeper)
                        shopkeeper_found = True
                        break
            
            if not online_player_found and not shopkeeper_found:
                # Check if any enemy is in alert state (detected player)
                enemy_battle_triggered = False
                for enemy in self.game_manager.current_enemy_trainers:
                    if enemy.state == "alert":
                        self._trigger_battle(enemy)
                        enemy_battle_triggered = True
                        break
                
                # If no enemy battle triggered, check for bush encounter
                if not enemy_battle_triggered and self.game_manager.player:
                    for bush in self.game_manager.current_map.bushes:
                        in_bush = hasattr(bush, 'in_bush') and bush.in_bush
                        if in_bush:
                            # Trigger wild monster battle with cloud transition
                            wild_monster = generate_random_monster()
                            from src.scenes.battle_scene import BattleScene
                            Logger.info(f"Wild {wild_monster['name']} appeared!")
                            player_mon = self.game_manager.bag.monsters[0] if self.game_manager.bag.monsters else None
                            battle_scene = BattleScene(player=self.game_manager.player, player_mon=player_mon, enemy=wild_monster, bag=self.game_manager.bag, game_manager=self.game_manager)
                            # Start cloud transition instead of immediate scene change
                            self._start_battle_transition(battle_scene, "wild_battle")
                            break

        # self.warning_visible = False
        # for enemy in self.game_manager.current_enemy_trainers:
        #     dist = self.game_manager.player.position.distance_to(enemy.position)
        #     if dist < 150:  # adjust detection range
        #         self.warning_visible = True
        #         self.warning_position = enemy.position
        #         break

        # Animate warning bounce
        if self.warning_visible:
            dt_sec = dt  # dt is already in seconds from your update
            self.warning_bounce += self.warning_bounce_dir * self.warning_bounce_speed * dt_sec
            if self.warning_bounce > 10:  # max bounce
                self.warning_bounce = 10
                self.warning_bounce_dir = -1
            elif self.warning_bounce < 0:
                self.warning_bounce = 0
                self.warning_bounce_dir = 1

        # Update buttons
        
        self.settings_button.update(dt)
        self.backpack_button.update(dt)
        self.navigation_button.update(dt)
        
        # Update navigation button hover effect
        mx, my = pg.mouse.get_pos()
        nav_rect = self.navigation_button.hitbox
        if nav_rect.collidepoint(mx, my):
            self.navigation_button_hover_scale = min(1.15, self.navigation_button_hover_scale + dt * 2)
        else:
            self.navigation_button_hover_scale = max(1.0, self.navigation_button_hover_scale - dt * 2)

        # Check if player is near a shopkeeper and show shop button
        self.shop_button_visible = False
        if self.game_manager.player:
            player_rect = self.game_manager.player.get_rect()
            interaction_range = player_rect.inflate(GameSettings.TILE_SIZE * 2, GameSettings.TILE_SIZE * 2)
            
            for shopkeeper in getattr(self.game_manager.current_map, 'shopkeepers', []):
                if interaction_range.colliderect(shopkeeper.animation.rect):
                    self.shop_button_visible = True
                    break
        
        if self.shop_button_visible:
            self.shop_button.update(dt)
        
        # Update navigation overlay
        if self.navigation_overlay:
            self.navigation_overlay.update(dt)

        if self.overlay_open:
            self.back_button.update(dt)
            self.checkbox_sound.update(dt)
            self.slider_music.update(dt)
            self.save_button.update(dt)
            self.load_button.update(dt)

        if self.backpack_open:
            self.backpack_close_button.update(dt)
            self.backpack_monsters_button.update(dt)
            self.backpack_items_button.update(dt)
        
        if self.shop_open and self.shop_overlay:
            self.shop_overlay.update(dt)

            # Music slider changes volume
        sound_manager.set_bgm_volume(self.slider_music.value / 100)

            # Checkbox toggles music
        if self.checkbox_sound.checked:
            sound_manager.resume_all()
        else:
            sound_manager.pause_all()


    # Public: call this from main loop
    def handle_event(self, event: pg.event.Event):
        # Handle incoming challenge dialog events first if open
        if self.incoming_challenge_open:
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pg.mouse.get_pos()
                if self.incoming_challenge_yes_rect.collidepoint(mx, my):
                    self._accept_incoming_challenge()
                    return
                elif self.incoming_challenge_no_rect.collidepoint(mx, my):
                    self._decline_incoming_challenge()
                    return
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE or event.key == pg.K_n:
                    self._decline_incoming_challenge()
                    return
                elif event.key == pg.K_RETURN or event.key == pg.K_y:
                    self._accept_incoming_challenge()
                    return
            return  # Block other events while dialog is open
        
        # Handle online battle dialog events first if open
        if self.online_battle_dialog_open:
            if event.type == pg.MOUSEBUTTONDOWN and event.button == 1:
                mx, my = pg.mouse.get_pos()
                if self.online_battle_yes_rect.collidepoint(mx, my):
                    self._confirm_online_battle()
                    return
                elif self.online_battle_no_rect.collidepoint(mx, my):
                    self._close_online_battle_dialog()
                    return
            if event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    self._close_online_battle_dialog()
                    return
                elif event.key == pg.K_RETURN or event.key == pg.K_y:
                    self._confirm_online_battle()
                    return
                elif event.key == pg.K_n:
                    self._close_online_battle_dialog()
                    return
            return  # Block other events while dialog is open
        
        # Handle navigation events first if overlay is active
        if self.navigation_overlay and self.navigation_overlay.active:
            self.navigation_overlay.handle_event(event)
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                self.navigation_overlay.close()
            return
        
        # Handle shop events
        if self.shop_open and self.shop_overlay:
            self.shop_overlay.handle_input(event)
            if event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
                self._close_shop()
            return
        
        if event.type == pg.MOUSEBUTTONDOWN:
            # Forward event to buttons using handle_event
            if not self.overlay_open:
                self.settings_button.handle_event(event)  # triggers click
            else:
                self.back_button.handle_event(event)      # triggers click

            if self.overlay_open:
                self.checkbox_sound.update(0)  # Checkbox uses update(), not handle_event
                self.slider_music.update(0)    # Slider uses update(), not handle_event
                self.save_button.handle_event(event)  # trigger click
                self.load_button.handle_event(event)

            if not self.overlay_open and not self.backpack_open:
                self.backpack_button.handle_event(event)
                self.navigation_button.handle_event(event)

            if self.backpack_open:
                self.backpack_close_button.handle_event(event)
                self.backpack_monsters_button.handle_event(event)
                self.backpack_items_button.handle_event(event)
                
                # Handle Follow button clicks in monsters tab (on actual mouse click)
                if self.backpack_tab == "monsters" and event.button == 1:
                    mx, my = pg.mouse.get_pos()
                    # Calculate button positions directly (same logic as in draw)
                    start_y = self.backpack_box_rect.y + 110
                    monster_block_w, monster_block_h = 260, 50
                    padding_x, padding_y = 10, 5
                    columns = 2
                    follow_btn_w, follow_btn_h = 50, 30
                    
                    for index, mon in enumerate(self.game_manager.bag.monsters):
                        col = index % columns
                        row = index // columns
                        block_x = self.backpack_box_rect.x + 20 + col * (monster_block_w + padding_x)
                        block_y = start_y + row * (monster_block_h + padding_y) - self.backpack_scroll_y
                        
                        # Only check if inside overlay box
                        if block_y + monster_block_h < self.backpack_box_rect.y + self.backpack_box_rect.height - 10 and block_y > self.backpack_box_rect.y + 100:
                            follow_btn_x = block_x + monster_block_w - follow_btn_w - 8
                            follow_btn_y = block_y + (monster_block_h - follow_btn_h) // 2
                            follow_btn_rect = pg.Rect(follow_btn_x, follow_btn_y, follow_btn_w, follow_btn_h)
                            
                            if follow_btn_rect.collidepoint(mx, my):
                                is_following = (self.pokemon_follower is not None and 
                                               self.pokemon_follower.monster.get("name") == mon.get("name"))
                                if is_following:
                                    self._remove_pokemon_follower()
                                else:
                                    self._set_pokemon_follower(index)
                                break

            if self.backpack_open:
                if event.type == pg.MOUSEBUTTONDOWN:
                    if event.button == 4:  # scroll up
                        self.backpack_scroll_y = max(0, self.backpack_scroll_y - self.backpack_scroll_speed)
                    elif event.button == 5:  # scroll down
                        if self.backpack_tab == "monsters":
                            monster_block_h = 50
                            padding_y = 5
                            rows = (len(self.game_manager.bag.monsters) + 1) // 2  # 2 monsters per row
                            content_height = rows * (monster_block_h + padding_y)
                            max_scroll = max(0, content_height - (self.backpack_box_rect.height - 110))
                        else:  # items tab
                            item_height = 35
                            content_height = len(self.game_manager.bag._items_data) * item_height
                            max_scroll = max(0, content_height - (self.backpack_box_rect.height - 110))
                        self.backpack_scroll_y = min(max_scroll, self.backpack_scroll_y + self.backpack_scroll_speed)

        elif event.type == pg.KEYDOWN:
            if not self.overlay_open and not self.backpack_open:
                if event.key in (pg.K_SPACE, pg.K_RETURN):
                    # Check if any enemy is in alert state (detected player)
                    for enemy in self.game_manager.current_enemy_trainers:
                        if enemy.state == "alert":
                            self._trigger_battle(enemy)
                            break

    def _draw_backpack_tab_button(self, screen: pg.Surface, button: Button, label: str, active: bool) -> None:
        """Draw a backpack tab button with text in Pokemon style."""
        # Check if mouse is hovering over button
        is_hovered = button.hitbox.collidepoint(pg.mouse.get_pos())
        
        if active:
            color = (255, 215, 0)  # Gold/active
            border_color = (200, 120, 0)
        else:
            color = (200, 165, 100)  # Muted orange/inactive
            border_color = (150, 100, 50)
        
        pg.draw.rect(screen, color, button.hitbox)
        pg.draw.rect(screen, border_color, button.hitbox, 2)
        
        # Highlight edge effect on hover
        if is_hovered:
            pg.draw.line(screen, (255, 255, 200), button.hitbox.topleft, button.hitbox.topright, 1)
            pg.draw.line(screen, (255, 255, 200), button.hitbox.topleft, button.hitbox.bottomleft, 1)

        font = pg.font.Font("assets/fonts/Minecraft.ttf", 14)
        text_surf = font.render(label, True, (20, 20, 20))
        text_rect = text_surf.get_rect(center=button.hitbox.center)
        screen.blit(text_surf, text_rect)

    def _draw_backpack_monsters(self, screen: pg.Surface) -> None:
        """Draw the monsters tab content."""
        monster_font = pg.font.Font("assets/fonts/Minecraft.ttf", 16)
        hp_font = pg.font.Font("assets/fonts/Minecraft.ttf", 14)
        follow_font = pg.font.Font("assets/fonts/Minecraft.ttf", 12)

        start_y = self.backpack_box_rect.y + 110  # starting y inside box below tabs
        monster_block_w, monster_block_h = 260, 50  # Wider to fit Follow button
        monster_sprite_size = 45
        padding_x, padding_y = 10, 5
        columns = 2  # number of monsters per row
        
        # Store follow button rects for click detection
        if not hasattr(self, '_follow_button_rects'):
            self._follow_button_rects = {}
        self._follow_button_rects.clear()

        for index, mon in enumerate(self.game_manager.bag.monsters):
            col = index % columns
            row = index // columns

            block_x = self.backpack_box_rect.x + 20 + col * (monster_block_w + padding_x)
            block_y = start_y + row * (monster_block_h + padding_y) - self.backpack_scroll_y

            # Only draw if inside overlay box
            if block_y + monster_block_h < self.backpack_box_rect.y + self.backpack_box_rect.height - 10 and block_y > self.backpack_box_rect.y + 100:
                block_rect = pg.Rect(block_x, block_y, monster_block_w, monster_block_h)
                
                # Draw banner as background
                if self.monster_banner:
                    banner_scaled = pg.transform.scale(self.monster_banner, (monster_block_w, monster_block_h))
                    screen.blit(banner_scaled, (block_x, block_y))
                else:
                    # Fallback to colored background
                    pg.draw.rect(screen, (255, 215, 0), block_rect)
                    pg.draw.rect(screen, (200, 120, 0), block_rect, 1)

                # Sprite - centered vertically and positioned on the left with padding
                mon_image = pg.transform.scale(mon["sprite"], (monster_sprite_size, monster_sprite_size))
                sprite_x = block_x + 8
                sprite_y = block_y + (monster_block_h - monster_sprite_size) // 2
                screen.blit(mon_image, (sprite_x, sprite_y))

                # Name + Level - positioned to the right of sprite
                txt = monster_font.render(mon["name"], True, (0,0,0))
                screen.blit(txt, (block_x + 58, block_y + 3))
                lvl_txt = monster_font.render(f"Lv.{mon['level']}", True, (0,0,0))
                screen.blit(lvl_txt, (block_x + 58, block_y + 20))

                # HP bar - positioned below the name/level
                hp, max_hp = mon["hp"], mon["max_hp"]
                bar_w, bar_h = 50, 5
                bar_x, bar_y = block_x + 58, block_y + 38
                pg.draw.rect(screen, (0,0,0), (bar_x, bar_y, bar_w, bar_h), 1)
                hp_ratio = hp / max_hp
                fill_w = int((bar_w - 2) * hp_ratio)
                fill_color = (50,205,50) if hp_ratio > 0.5 else (255,215,0) if hp_ratio > 0.2 else (255,0,0)
                pg.draw.rect(screen, fill_color, (bar_x+1, bar_y+1, fill_w, bar_h-2))
                
                # Follow button - on the right side of the block
                follow_btn_w, follow_btn_h = 50, 30
                follow_btn_x = block_x + monster_block_w - follow_btn_w - 8
                follow_btn_y = block_y + (monster_block_h - follow_btn_h) // 2
                follow_btn_rect = pg.Rect(follow_btn_x, follow_btn_y, follow_btn_w, follow_btn_h)
                
                # Check if this monster is currently following
                is_following = (self.pokemon_follower is not None and 
                               self.pokemon_follower.monster.get("name") == mon.get("name"))
                
                # Button hover detection
                mx, my = pg.mouse.get_pos()
                is_hovered = follow_btn_rect.collidepoint(mx, my)
                
                # Draw button
                if is_following:
                    btn_color = (100, 200, 100) if not is_hovered else (120, 220, 120)
                    btn_text = "Stop"
                else:
                    btn_color = (200, 150, 50) if not is_hovered else (220, 170, 70)
                    btn_text = "Follow"
                
                pg.draw.rect(screen, btn_color, follow_btn_rect)
                pg.draw.rect(screen, (100, 80, 40), follow_btn_rect, 2)
                
                follow_txt = follow_font.render(btn_text, True, (255, 255, 255))
                follow_txt_rect = follow_txt.get_rect(center=follow_btn_rect.center)
                screen.blit(follow_txt, follow_txt_rect)
                
                # Store button rect for click detection
                self._follow_button_rects[index] = (follow_btn_rect, is_following)

    def _draw_backpack_items(self, screen: pg.Surface) -> None:
        """Draw the items tab content."""
        item_font = pg.font.Font("assets/fonts/Minecraft.ttf", 16)
        item_sprite_size = 24
        
        start_y = self.backpack_box_rect.y + 110
        item_height = 35
        item_x = self.backpack_box_rect.x + 20
        
        for idx, item in enumerate(self.game_manager.bag._items_data):
            item_y = start_y + idx * item_height - self.backpack_scroll_y
            
            if item_y < self.backpack_box_rect.y + 110:
                continue
            if item_y > self.backpack_box_rect.bottom - 10:
                break
            
            # Item background
            item_rect = pg.Rect(item_x, item_y, self.backpack_box_rect.width - 40, item_height)
            pg.draw.rect(screen, (255, 215, 0), item_rect)
            pg.draw.rect(screen, (200, 120, 0), item_rect, 1)
            
            # Try to load item image
            item_name = item.get('name', 'Unknown')
            item_image = None
            
            if "potion" in item_name.lower():
                try:
                    item_image = pg.image.load("assets/images/ingame_ui/potion.png").convert_alpha()
                except:
                    pass
            elif "ball" in item_name.lower():
                try:
                    item_image = pg.image.load("assets/images/ingame_ui/ball.png").convert_alpha()
                except:
                    pass
            elif "coin" in item_name.lower():
                try:
                    item_image = pg.image.load("assets/images/ingame_ui/coin.png").convert_alpha()
                except:
                    pass
            
            # Draw item image if found
            if item_image:
                scaled_img = pg.transform.scale(item_image, (item_sprite_size, item_sprite_size))
                screen.blit(scaled_img, (item_x + 10, item_y + 5))
                text_x = item_x + item_sprite_size + 20
            else:
                text_x = item_x + 10
            
            txt = item_font.render(f"{item_name} x{item['count']}", True, (20,20,20))
            screen.blit(txt, (text_x, item_y + 8))

    def _init_cloud_surfaces(self):
        """Initialize cloud surfaces for battle transition effect"""
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        
        # Create multiple cloud "puffs" at different positions
        self.clouds = []
        num_clouds = 15
        for i in range(num_clouds):
            cloud_w = random.randint(150, 300)
            cloud_h = random.randint(100, 200)
            cloud_surf = pg.Surface((cloud_w, cloud_h), pg.SRCALPHA)
            
            # Draw fluffy cloud shape using overlapping circles
            base_color = (240, 240, 250)
            num_puffs = random.randint(5, 8)
            for _ in range(num_puffs):
                puff_x = random.randint(20, cloud_w - 20)
                puff_y = random.randint(20, cloud_h - 20)
                puff_r = random.randint(30, 60)
                pg.draw.circle(cloud_surf, base_color, (puff_x, puff_y), puff_r)
            
            # Random starting position (off-screen)
            start_x = random.randint(-cloud_w, sw)
            start_y = random.randint(-cloud_h, sh)
            
            # Direction to move (towards center then covering screen)
            self.clouds.append({
                'surface': cloud_surf,
                'start_x': start_x if random.random() > 0.5 else sw + random.randint(0, 200),
                'start_y': start_y,
                'target_x': random.randint(0, sw - cloud_w),
                'target_y': random.randint(0, sh - cloud_h),
                'delay': random.uniform(0, 0.3)  # Staggered appearance
            })
    
    def _start_battle_transition(self, battle_scene, scene_name: str):
        """Start the cloud transition effect before switching to battle"""
        self.transition_active = True
        self.transition_timer = 0.0
        self.transition_phase = "in"
        self.pending_battle_scene = battle_scene
        self.pending_battle_scene_name = scene_name
        # Regenerate cloud positions for fresh animation
        self._init_cloud_surfaces()
    
    def _update_transition(self, dt: float):
        """Update the cloud transition animation"""
        if not self.transition_active:
            return
        
        self.transition_timer += dt
        
        # When clouds fully cover screen, switch scene
        if self.transition_phase == "in" and self.transition_timer >= self.transition_duration:
            # Switch to battle scene
            scene_manager.register_scene(self.pending_battle_scene_name, self.pending_battle_scene)
            scene_manager.change_scene(self.pending_battle_scene_name)
            self.transition_active = False
            self.pending_battle_scene = None
            self.pending_battle_scene_name = None
    
    def _draw_transition(self, screen: pg.Surface):
        """Draw the cloud transition effect"""
        if not self.transition_active:
            return
        
        progress = min(1.0, self.transition_timer / self.transition_duration)
        
        # Draw each cloud moving towards its target position
        for cloud in self.clouds:
            # Account for staggered delay
            cloud_progress = max(0, (self.transition_timer - cloud['delay']) / (self.transition_duration - 0.3))
            cloud_progress = min(1.0, cloud_progress)
            
            # Ease-in effect for smoother animation
            eased_progress = cloud_progress * cloud_progress * (3 - 2 * cloud_progress)
            
            # Calculate current position
            start_x = cloud['start_x']
            start_y = cloud['start_y']
            target_x = cloud['target_x']
            target_y = cloud['target_y']
            
            current_x = start_x + (target_x - start_x) * eased_progress
            current_y = start_y + (target_y - start_y) * eased_progress
            
            # Scale up slightly as they approach
            scale = 1.0 + 0.5 * eased_progress
            scaled_surf = pg.transform.scale(
                cloud['surface'],
                (int(cloud['surface'].get_width() * scale), int(cloud['surface'].get_height() * scale))
            )
            
            screen.blit(scaled_surf, (int(current_x), int(current_y)))
        
        # Add a white overlay that fades in as transition completes
        if progress > 0.6:
            overlay_alpha = int(255 * (progress - 0.6) / 0.4)
            white_overlay = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
            white_overlay.fill((255, 255, 255, overlay_alpha))
            screen.blit(white_overlay, (0, 0))

    def _init_christmas_decorations(self):
        """Initialize falling leaves"""
        # Leaves list: each is [x, y, speed, size, sway_offset, rotation, color_idx]
        self.leaves = []
        for _ in range(25):  # 25 leaves
            self.leaves.append([
                random.randint(0, GameSettings.SCREEN_WIDTH),  # x
                random.randint(-50, GameSettings.SCREEN_HEIGHT),  # y
                random.uniform(25, 60),  # fall speed (slower than snow)
                random.randint(4, 8),  # size
                random.uniform(0, 6.28),  # sway phase
                random.uniform(0, 360),  # rotation angle
                random.randint(0, 3)  # color index
            ])
        self.leaf_time = 0
        # Leaf colors (various greens and autumn colors)
        self.leaf_colors = [
            (34, 139, 34),   # Forest green
            (50, 205, 50),   # Lime green
            (60, 179, 113),  # Medium sea green
            (85, 170, 85),   # Light green
        ]
    
    def _update_leaves(self, dt: float):
        """Update falling leaf positions"""
        self.leaf_time += dt
        for leaf in self.leaves:
            # Fall down (slower, more floating)
            leaf[1] += leaf[2] * dt
            # Sway left/right using sine wave (more pronounced swaying)
            leaf[4] += dt * 1.5
            leaf[0] += 30 * dt * math.sin(leaf[4])
            # Rotate the leaf
            leaf[5] += 40 * dt  # Rotation speed
            
            # Reset if off screen
            if leaf[1] > GameSettings.SCREEN_HEIGHT + 10:
                leaf[1] = random.randint(-30, -10)
                leaf[0] = random.randint(0, GameSettings.SCREEN_WIDTH)
                leaf[5] = random.uniform(0, 360)
    
    def _draw_leaves(self, screen: pg.Surface):
        """Draw falling leaves"""
        for leaf in self.leaves:
            x, y = int(leaf[0]), int(leaf[1])
            size = leaf[3]
            rotation = leaf[5]
            color_idx = leaf[6]
            color = self.leaf_colors[color_idx]
            
            # Create a small leaf shape
            leaf_surface = pg.Surface((size * 2, size * 2), pg.SRCALPHA)
            # Draw leaf as an ellipse (oval shape)
            pg.draw.ellipse(leaf_surface, color, (0, size // 2, size * 2, size))
            # Add a small stem/vein
            pg.draw.line(leaf_surface, (30, 80, 30), (size, size // 2), (size, size + size // 2), 1)
            
            # Rotate the leaf
            rotated_leaf = pg.transform.rotate(leaf_surface, rotation)
            leaf_rect = rotated_leaf.get_rect(center=(x, y))
            screen.blit(rotated_leaf, leaf_rect)

    def _create_minimap(self):
        """Create a mini-map surface for the current map with actual map colors"""
        try:
            if not self.game_manager.current_map:
                return
            
            map_data = self.game_manager.current_map.tmxdata
            map_width_pixels = map_data.width * GameSettings.TILE_SIZE
            map_height_pixels = map_data.height * GameSettings.TILE_SIZE
            
            # Calculate scale factor to fit map in minimap_size
            scale_x = self.minimap_size / map_width_pixels
            scale_y = self.minimap_size / map_height_pixels
            scale = min(scale_x, scale_y)
            
            # Create minimap surface
            minimap_w = int(map_width_pixels * scale)
            minimap_h = int(map_height_pixels * scale)
            self.minimap_surface = pg.Surface((minimap_w, minimap_h))
            
            # Get the map's pre-rendered surface and scale it down
            if hasattr(self.game_manager.current_map, '_surface'):
                map_surface = self.game_manager.current_map._surface
                scaled_map = pg.transform.scale(map_surface, (minimap_w, minimap_h))
                
                # Draw the scaled map onto the minimap
                self.minimap_surface.blit(scaled_map, (0, 0))
            
            # Draw minimap border
            pg.draw.rect(self.minimap_surface, (200, 200, 200), (0, 0, minimap_w, minimap_h), 2)
            
            # Store scale for drawing player
            self.minimap_scale = scale
        except Exception as e:
            Logger.warning(f"Error creating minimap: {e}")
            # Create a blank minimap if there's an error
            self.minimap_surface = pg.Surface((self.minimap_size, self.minimap_size))
            self.minimap_surface.fill((100, 100, 100))
        self.minimap_scale = scale

    def _draw_minimap(self, screen: pg.Surface):
        """Draw the mini-map on screen with player sprite"""
        if not self.minimap_surface or not self.game_manager.player:
            return
        
        # Draw minimap background with frame
        frame_rect = pg.Rect(self.minimap_pos[0] - 2, self.minimap_pos[1] - 2, 
                            self.minimap_surface.get_width() + 4, self.minimap_surface.get_height() + 4)
        pg.draw.rect(screen, (0, 0, 0), frame_rect)
        pg.draw.rect(screen, (200, 200, 200), frame_rect, 2)
        
        # Draw the minimap surface
        screen.blit(self.minimap_surface, self.minimap_pos)
        
        # Draw player sprite on minimap
        player = self.game_manager.player
        player_x = int(player.position.x * self.minimap_scale)
        player_y = int(player.position.y * self.minimap_scale)
        player_screen_x = self.minimap_pos[0] + player_x
        player_screen_y = self.minimap_pos[1] + player_y
        
        # Draw player sprite scaled down (12x12 pixels)
        if player.animation:
            try:
                # Get current frame from animation
                frames = player.animation.animations.get(player.animation.cur_row, [])
                if frames:
                    # Get the current frame index based on animation progress
                    frame_idx = int((player.animation.accumulator / player.animation.loop) * player.animation.n_keyframes)
                    frame_idx = frame_idx % len(frames)
                    player_sprite = frames[frame_idx]
                    scaled_player = pg.transform.scale(player_sprite, (12, 12))
                    # Center the sprite on the position
                    screen.blit(scaled_player, (player_screen_x - 6, player_screen_y - 6))
                else:
                    # Fallback to green circle if no frames
                    pg.draw.circle(screen, (0, 255, 0), (player_screen_x, player_screen_y), 4)
            except Exception:
                # Fallback to green circle if sprite loading fails
                pg.draw.circle(screen, (0, 255, 0), (player_screen_x, player_screen_y), 4)
                pg.draw.circle(screen, (0, 200, 0), (player_screen_x, player_screen_y), 4, 1)
        else:
            # Fallback to green circle
            pg.draw.circle(screen, (0, 255, 0), (player_screen_x, player_screen_y), 4)
            pg.draw.circle(screen, (0, 200, 0), (player_screen_x, player_screen_y), 4, 1)
        
        # Draw leaves on minimap
        minimap_w = self.minimap_surface.get_width()
        minimap_h = self.minimap_surface.get_height()
        for leaf in self.leaves:
            # Scale leaf position to minimap
            leaf_x = int(leaf[0] / GameSettings.SCREEN_WIDTH * minimap_w) + self.minimap_pos[0]
            leaf_y = int(leaf[1] / GameSettings.SCREEN_HEIGHT * minimap_h) + self.minimap_pos[1]
            # Only draw if within minimap bounds
            if (self.minimap_pos[0] <= leaf_x < self.minimap_pos[0] + minimap_w and
                self.minimap_pos[1] <= leaf_y < self.minimap_pos[1] + minimap_h):
                pg.draw.circle(screen, (50, 180, 50), (leaf_x, leaf_y), 1)

    @override
    def draw(self, screen: pg.Surface):
        # If loading animation active, draw rotating ball centered and skip normal draw
        if getattr(self, 'show_loading', False):
            screen.fill((0, 0, 0))
            # draw rotating ball
            if self.loading_ball_sprite:
                rotated = pg.transform.rotate(self.loading_ball_sprite, self._loading_angle)
                r = rotated.get_rect(center=(GameSettings.SCREEN_WIDTH//2, GameSettings.SCREEN_HEIGHT//2))
                screen.blit(rotated, r.topleft)
            # draw loading text
            try:
                font = pg.font.Font("assets/fonts/Minecraft.ttf", 28)
            except Exception:
                font = pg.font.Font(None, 28)
            text = font.render("Loading...", True, (255, 255, 255))
            tx = GameSettings.SCREEN_WIDTH//2 - text.get_width()//2
            ty = GameSettings.SCREEN_HEIGHT//2 + 80
            screen.blit(text, (tx, ty))
            return
        # --- Camera ---
        camera = PositionCamera(0, 0)
        if self.game_manager.player:
            player = self.game_manager.player
            camera = PositionCamera(
                player.position.x - GameSettings.SCREEN_WIDTH // 2,
                player.position.y - GameSettings.SCREEN_HEIGHT // 2
            )
            self.game_manager.current_map.draw(screen, camera)
            
            # Draw Pokemon follower (behind player)
            if self.pokemon_follower:
                self.pokemon_follower.draw(screen, camera)
            
            player.draw(screen, camera)
            
            # Draw online indicator icon above player's head if other players are connected
            if self.online_manager and self.online_indicator_icon and len(self.online_animations) > 0:
                player_screen_pos = camera.transform_position_as_position(player.position)
                icon_x = player_screen_pos.x + (GameSettings.TILE_SIZE - 24) // 2  # Center above player
                icon_y = player_screen_pos.y - 30  # Above player's head
                screen.blit(self.online_indicator_icon, (icon_x, icon_y))
        else:
            if self.game_manager.current_map:
                self.game_manager.current_map.draw(screen, camera)

        # Draw enemies and bag
        for enemy in self.game_manager.current_enemy_trainers:
            enemy.draw(screen, camera)
        self.game_manager.bag.draw(screen)

        # Draw online players
        if self.online_manager and self.game_manager.player:
            for player_id, animation in self.online_animations.items():
                animation.draw(screen, camera)
                # Store last position for chat bubbles
                self._online_last_pos[player_id] = Position(animation.rect.x, animation.rect.y)
        
        # Draw chat bubbles
        try:
            self._draw_chat_bubbles(screen, camera)
        except Exception as e:
            Logger.warning(f"Error drawing chat bubbles: {e}")

        # warning sign
        if self.warning_visible and self.warning_position:
            cam = PositionCamera(
                self.game_manager.player.position.x - GameSettings.SCREEN_WIDTH // 2,
                self.game_manager.player.position.y - GameSettings.SCREEN_HEIGHT // 2
            )
            screen_pos = cam.transform_position_as_position(self.warning_position)
            # adjust Y position to be above trainer sprite, with bounce
            offset_y = 32 + self.warning_bounce
            screen.blit(self.warning_sprite, (screen_pos.x - 16, screen_pos.y - offset_y))  # offset above trainer


        # --- Draw UI buttons ---
        self.settings_button.draw(screen)
        self.backpack_button.draw(screen)
        
        # Draw navigation button with logo and hover effect
        # Draw button with hover effect (scale the button itself)
        if self.navigation_button_hover_scale > 1.0:
            # Scale button when hovering
            button_img = self.navigation_button.img_button.image
            scaled_size = (int(70 * self.navigation_button_hover_scale), int(70 * self.navigation_button_hover_scale))
            scaled_button = pg.transform.scale(button_img, scaled_size)
            button_x = self.navigation_button.hitbox.x + 35 - scaled_size[0] // 2
            button_y = self.navigation_button.hitbox.y + 35 - scaled_size[1] // 2
            screen.blit(scaled_button, (button_x, button_y))
        else:
            # Normal button
            self.navigation_button.draw(screen)
        
        # Draw logo on top
        if self.navigation_logo:
            logo_size = int(50 * self.navigation_button_hover_scale)
            scaled_logo = pg.transform.scale(self.navigation_logo, (logo_size, logo_size))
            logo_x = self.navigation_button.hitbox.x + 35 - logo_size // 2
            logo_y = self.navigation_button.hitbox.y + 35 - logo_size // 2
            screen.blit(scaled_logo, (logo_x, logo_y))
        
        if self.shop_button_visible:
            self.shop_button.draw(screen)

        # --- Draw falling leaves ---
        self._draw_leaves(screen)

        # --- Draw mini-map ---
        self._draw_minimap(screen)
        
        # --- Draw navigation path arrows (if any) ---
        if self.navigation_overlay:
            self.navigation_overlay.draw(screen, camera)

        # --- Draw overlay if open ---
        if self.overlay_open:
    # 1️⃣ Darken background slightly (optional)
            screen.blit(self._dark_surface, (0, 0))

    # 2️⃣ Draw pixel-art style orange box
            box_color = (255, 165, 0)        # main orange
            border_color = (200, 120, 0)     # darker orange border for pixel look
            highlight_color = (255, 200, 100) # optional highlight top/left edges

    # Draw main box
            pg.draw.rect(screen, box_color, self.overlay_box_rect)

    # Draw border (1px)
            pg.draw.rect(screen, border_color, self.overlay_box_rect, width=1)

    # Draw top/left highlight (like Pokémon menu boxes)
            pg.draw.line(screen, highlight_color, 
                        (self.overlay_box_rect.left, self.overlay_box_rect.top), 
                        (self.overlay_box_rect.right-1, self.overlay_box_rect.top))  # top
            pg.draw.line(screen, highlight_color, 
                        (self.overlay_box_rect.left, self.overlay_box_rect.top), 
                        (self.overlay_box_rect.left, self.overlay_box_rect.bottom-1))  # left

    # 3️⃣ Draw overlay title
            title = self._font_med.render("Settings", True, (20, 20, 20))
            screen.blit(title, (self.overlay_box_rect.x + 4, self.overlay_box_rect.y + 4))  # small padding for pixel style

            # back button
            self.back_button.draw(screen)

            self.checkbox_sound.draw(screen)
            self.slider_music.draw(screen)
            self.save_button.draw(screen)
            self.load_button.draw(screen)

        # --- BACKPACK OVERLAY ---
        if self.backpack_open:
    # Dark background
            screen.blit(self._dark_surface, (0, 0))

    # Draw Pokemon-style box
            pg.draw.rect(screen, (255,165,0), self.backpack_box_rect)
            pg.draw.rect(screen, (200,120,0), self.backpack_box_rect, 1)

    # Title
            title = self._font_med.render("Backpack", True, (20,20,20))
            screen.blit(title, (self.backpack_box_rect.x + 4, self.backpack_box_rect.y + 4))

    # Draw tab buttons
            self._draw_backpack_tab_button(screen, self.backpack_monsters_button, "Monsters", self.backpack_tab == "monsters")
            self._draw_backpack_tab_button(screen, self.backpack_items_button, "Items", self.backpack_tab == "items")

    # Draw content based on active tab
            if self.backpack_tab == "monsters":
                self._draw_backpack_monsters(screen)
            else:
                self._draw_backpack_items(screen)

    # Back button
            self.backpack_close_button.draw(screen)

        # --- SHOP OVERLAY ---
        if self.shop_open and self.shop_overlay:
            self.shop_overlay.draw(screen)
        
        # --- CHAT OVERLAY ---
        if self._chat_overlay:
            self._chat_overlay.draw(screen)
        
        # --- ONLINE BATTLE DIALOG ---
        if self.online_battle_dialog_open:
            self._draw_online_battle_dialog(screen)
        
        # --- INCOMING CHALLENGE DIALOG ---
        if self.incoming_challenge_open:
            self._draw_incoming_challenge_dialog(screen)
        
        # --- WAITING FOR RESPONSE / DECLINED MESSAGE ---
        if self.waiting_for_challenge_response:
            self._draw_waiting_message(screen)
        elif self.challenge_declined_message_timer > 0:
            self._draw_declined_message(screen)
        
        # --- BATTLE TRANSITION (cloud screen) ---
        if self.transition_active:
            self._draw_transition(screen)
    
    def _draw_online_battle_dialog(self, screen: pg.Surface) -> None:
        """Draw the online battle confirmation dialog."""
        # Dark overlay
        screen.blit(self._dark_surface, (0, 0))
        
        # Dialog box (Pokemon-style)
        box_color = (255, 165, 0)        # main orange
        border_color = (200, 120, 0)     # darker orange border
        highlight_color = (255, 200, 100)
        
        # Draw main box
        pg.draw.rect(screen, box_color, self.online_battle_dialog_rect)
        pg.draw.rect(screen, border_color, self.online_battle_dialog_rect, 2)
        
        # Draw highlights
        pg.draw.line(screen, highlight_color, 
                    (self.online_battle_dialog_rect.left + 2, self.online_battle_dialog_rect.top + 2), 
                    (self.online_battle_dialog_rect.right - 2, self.online_battle_dialog_rect.top + 2))
        pg.draw.line(screen, highlight_color, 
                    (self.online_battle_dialog_rect.left + 2, self.online_battle_dialog_rect.top + 2), 
                    (self.online_battle_dialog_rect.left + 2, self.online_battle_dialog_rect.bottom - 2))
        
        # Title
        title = self._online_battle_title_font.render("Online Battle", True, (20, 20, 20))
        title_rect = title.get_rect(centerx=self.online_battle_dialog_rect.centerx, 
                                   top=self.online_battle_dialog_rect.top + 15)
        screen.blit(title, title_rect)
        
        # Question text
        question = self._online_battle_dialog_font.render(
            "Would you like to have a battle with this player?", True, (20, 20, 20)
        )
        question_rect = question.get_rect(centerx=self.online_battle_dialog_rect.centerx,
                                         top=self.online_battle_dialog_rect.top + 55)
        screen.blit(question, question_rect)
        
        # Get mouse position for hover effects
        mx, my = pg.mouse.get_pos()
        
        # Yes button
        yes_hovered = self.online_battle_yes_rect.collidepoint(mx, my)
        yes_color = (100, 200, 100) if not yes_hovered else (120, 220, 120)
        pg.draw.rect(screen, yes_color, self.online_battle_yes_rect)
        pg.draw.rect(screen, (50, 150, 50), self.online_battle_yes_rect, 2)
        yes_text = self._online_battle_dialog_font.render("Yes", True, (255, 255, 255))
        yes_text_rect = yes_text.get_rect(center=self.online_battle_yes_rect.center)
        screen.blit(yes_text, yes_text_rect)
        
        # No button
        no_hovered = self.online_battle_no_rect.collidepoint(mx, my)
        no_color = (200, 100, 100) if not no_hovered else (220, 120, 120)
        pg.draw.rect(screen, no_color, self.online_battle_no_rect)
        pg.draw.rect(screen, (150, 50, 50), self.online_battle_no_rect, 2)
        no_text = self._online_battle_dialog_font.render("No", True, (255, 255, 255))
        no_text_rect = no_text.get_rect(center=self.online_battle_no_rect.center)
        screen.blit(no_text, no_text_rect)

    def _draw_incoming_challenge_dialog(self, screen: pg.Surface) -> None:
        """Draw the incoming battle challenge dialog."""
        # Dark overlay
        screen.blit(self._dark_surface, (0, 0))
        
        # Side notification banner (right side of screen) for extra visibility
        banner_w, banner_h = 250, 60
        banner_x = GameSettings.SCREEN_WIDTH - banner_w - 20
        banner_y = 100
        banner_rect = pg.Rect(banner_x, banner_y, banner_w, banner_h)
        
        # Animated pulsing effect
        pulse = abs(math.sin(time.monotonic() * 3)) * 0.3 + 0.7
        pulse_color = (int(255 * pulse), int(100 * pulse), int(100 * pulse))
        
        pg.draw.rect(screen, pulse_color, banner_rect)
        pg.draw.rect(screen, (200, 50, 50), banner_rect, 3)
        
        side_text = self._online_battle_dialog_font.render("⚔ BATTLE CHALLENGE! ⚔", True, (255, 255, 255))
        side_text_rect = side_text.get_rect(center=banner_rect.center)
        screen.blit(side_text, side_text_rect)
        
        # Dialog box (Pokemon-style) in center
        box_color = (255, 165, 0)
        border_color = (200, 120, 0)
        highlight_color = (255, 200, 100)
        
        # Draw main box
        pg.draw.rect(screen, box_color, self.incoming_challenge_dialog_rect)
        pg.draw.rect(screen, border_color, self.incoming_challenge_dialog_rect, 2)
        
        # Draw highlights
        pg.draw.line(screen, highlight_color, 
                    (self.incoming_challenge_dialog_rect.left + 2, self.incoming_challenge_dialog_rect.top + 2), 
                    (self.incoming_challenge_dialog_rect.right - 2, self.incoming_challenge_dialog_rect.top + 2))
        pg.draw.line(screen, highlight_color, 
                    (self.incoming_challenge_dialog_rect.left + 2, self.incoming_challenge_dialog_rect.top + 2), 
                    (self.incoming_challenge_dialog_rect.left + 2, self.incoming_challenge_dialog_rect.bottom - 2))
        
        # Title
        title = self._online_battle_title_font.render("Battle Challenge!", True, (20, 20, 20))
        title_rect = title.get_rect(centerx=self.incoming_challenge_dialog_rect.centerx, 
                                   top=self.incoming_challenge_dialog_rect.top + 15)
        screen.blit(title, title_rect)
        
        # Challenge text
        challenge_text = self._online_battle_dialog_font.render(
            f"A player is challenging you to a battle!", True, (20, 20, 20)
        )
        challenge_rect = challenge_text.get_rect(centerx=self.incoming_challenge_dialog_rect.centerx,
                                                top=self.incoming_challenge_dialog_rect.top + 55)
        screen.blit(challenge_text, challenge_rect)
        
        # Get mouse position for hover effects
        mx, my = pg.mouse.get_pos()
        
        # Accept button
        yes_hovered = self.incoming_challenge_yes_rect.collidepoint(mx, my)
        yes_color = (100, 200, 100) if not yes_hovered else (120, 220, 120)
        pg.draw.rect(screen, yes_color, self.incoming_challenge_yes_rect)
        pg.draw.rect(screen, (50, 150, 50), self.incoming_challenge_yes_rect, 2)
        yes_text = self._online_battle_dialog_font.render("Accept", True, (255, 255, 255))
        yes_text_rect = yes_text.get_rect(center=self.incoming_challenge_yes_rect.center)
        screen.blit(yes_text, yes_text_rect)
        
        # Decline button
        no_hovered = self.incoming_challenge_no_rect.collidepoint(mx, my)
        no_color = (200, 100, 100) if not no_hovered else (220, 120, 120)
        pg.draw.rect(screen, no_color, self.incoming_challenge_no_rect)
        pg.draw.rect(screen, (150, 50, 50), self.incoming_challenge_no_rect, 2)
        no_text = self._online_battle_dialog_font.render("Decline", True, (255, 255, 255))
        no_text_rect = no_text.get_rect(center=self.incoming_challenge_no_rect.center)
        screen.blit(no_text, no_text_rect)

    def _draw_waiting_message(self, screen: pg.Surface) -> None:
        """Draw 'Waiting for response...' message."""
        # Semi-transparent overlay at top of screen
        msg_w, msg_h = 350, 50
        msg_rect = pg.Rect(
            (GameSettings.SCREEN_WIDTH - msg_w) // 2, 20, msg_w, msg_h
        )
        
        # Draw background
        pg.draw.rect(screen, (50, 50, 50, 200), msg_rect)
        pg.draw.rect(screen, (255, 200, 100), msg_rect, 2)
        
        # Draw text
        text = self._online_battle_dialog_font.render("Waiting for response...", True, (255, 255, 255))
        text_rect = text.get_rect(center=msg_rect.center)
        screen.blit(text, text_rect)

    def _draw_declined_message(self, screen: pg.Surface) -> None:
        """Draw 'Challenge declined' message."""
        msg_w, msg_h = 300, 50
        msg_rect = pg.Rect(
            (GameSettings.SCREEN_WIDTH - msg_w) // 2, 20, msg_w, msg_h
        )
        
        # Draw background
        pg.draw.rect(screen, (100, 50, 50), msg_rect)
        pg.draw.rect(screen, (200, 100, 100), msg_rect, 2)
        
        # Draw text
        text = self._online_battle_dialog_font.render("Challenge declined", True, (255, 255, 255))
        text_rect = text.get_rect(center=msg_rect.center)
        screen.blit(text, text_rect)

    def _draw_chat_bubbles(self, screen: pg.Surface, camera: PositionCamera) -> None:
        """Draw chat bubbles above players."""
        if not self.online_manager:
            return
        
        # Remove expired bubbles
        now = time.monotonic()
        expired = [pid for pid, (_, ts) in self._chat_bubbles.items() if ts <= now]
        for pid in expired:
            del self._chat_bubbles[pid]
        
        if not self._chat_bubbles:
            return
        
        # Draw local player's chat bubble
        local_pid = self.online_manager.player_id
        if self.game_manager.player and local_pid in self._chat_bubbles:
            text, _ = self._chat_bubbles[local_pid]
            world_pos = self.game_manager.player.position
            self._draw_chat_bubble_for_pos(screen, camera, world_pos, text)
        
        # Draw other players' bubbles
        for pid, (text, _) in self._chat_bubbles.items():
            if pid == local_pid:
                continue
            if pid not in self._online_last_pos:
                continue
            world_pos = self._online_last_pos[pid]
            self._draw_chat_bubble_for_pos(screen, camera, world_pos, text)
    
    def _draw_chat_bubble_for_pos(self, screen: pg.Surface, camera: PositionCamera, world_pos: Position, text: str) -> None:
        """Draw a single chat bubble at a world position."""
        # Convert world position to screen position
        screen_pos = camera.transform_position_as_position(world_pos)
        
        # Position bubble above the character
        bubble_x = screen_pos.x
        bubble_y = screen_pos.y - 40
        
        # Render text
        text_surface = self._chat_font.render(text, True, (0, 0, 0))
        text_width = text_surface.get_width()
        text_height = text_surface.get_height()
        
        # Bubble dimensions with padding
        padding = 5
        bubble_width = text_width + padding * 2
        bubble_height = text_height + padding * 2
        
        # Draw bubble background (white with border)
        bubble_rect = pg.Rect(bubble_x - bubble_width // 2, bubble_y, bubble_width, bubble_height)
        pg.draw.rect(screen, (255, 255, 255), bubble_rect)
        pg.draw.rect(screen, (0, 0, 0), bubble_rect, 1)
        
        # Draw small pointer below bubble
        pointer_x = bubble_x
        pointer_y = bubble_y + bubble_height
        pg.draw.polygon(screen, (255, 255, 255), [
            (pointer_x - 5, pointer_y),
            (pointer_x + 5, pointer_y),
            (pointer_x, pointer_y + 5)
        ])
        pg.draw.polygon(screen, (0, 0, 0), [
            (pointer_x - 5, pointer_y),
            (pointer_x + 5, pointer_y),
            (pointer_x, pointer_y + 5)
        ], 1)
        
        # Draw text
        screen.blit(text_surface, (bubble_x - text_width // 2, bubble_y + padding))
    
    def _send_chat_message(self, message: str) -> bool:
        """Callback for sending chat messages."""
        if not self.online_manager:
            return False
        try:
            self.online_manager.send_chat(message)
            # Add to local chat bubbles immediately
            now = time.monotonic()
            self._chat_bubbles[self.online_manager.player_id] = (message, now + 5.0)
            return True
        except Exception as e:
            Logger.warning(f"Failed to send chat message: {e}")
            return False
    
    def _get_chat_messages(self, count: int) -> list[dict]:
        """Callback for getting recent chat messages."""
        if not self.online_manager:
            return []
        try:
            return self.online_manager.get_recent_chat(count)
        except Exception:
            return []