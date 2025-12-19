import pygame as pg
import threading
import time

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
            "UI/button_setting.png",
            "UI/button_setting_hover.png",
            GameSettings.SCREEN_WIDTH - 360,  # left of shop button
            20,
            70, 70,
            lambda: self._open_navigation()
        )
        
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

    def _open_overlay(self):
        self.overlay_open = True

    def _close_overlay(self):
        self.overlay_open = False

    def _open_backpack(self):
        self.backpack_open = True
        self.overlay_open = False  # optional: prevent both opening at once

    def _close_backpack(self):
        self.backpack_open = False
    
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

    @override
    def exit(self) -> None:
        if self.online_manager:
            self.online_manager.exit()

    def _trigger_battle(self, enemy):
        """
        Called when player interacts with enemy to start battle.
        """
        
    # Example: switch to your BattleScene
    # You would replace this with your actual scene switch logic
        from src.scenes.battle_scene import BattleScene
        from src.core.services import scene_manager
        Logger.info(f"Battle started with {enemy.name}!")
        # Pass the first monster from the bag as the player's active monster
        player_mon = self.game_manager.bag.monsters[0] if self.game_manager.bag.monsters else None
        # Generate 2-3 random monsters for the enemy trainer
        enemy_team_size = random.randint(2, 3)
        enemy_team = [generate_random_monster() for _ in range(enemy_team_size)]
        battle_scene = BattleScene(player=self.game_manager.player, player_mon=player_mon, enemy=enemy_team, bag=self.game_manager.bag, game_manager=self.game_manager)
        # Register a temporary scene (or you can use a key like "battle")
        scene_manager.register_scene("battle", battle_scene)

    # Switch to the battle scene
        scene_manager.change_scene("battle")

    @override
    def update(self, dt: float):
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
                           (input_manager.key_pressed(pg.K_SPACE) or input_manager.key_pressed(pg.K_RETURN)))
        
        if spacebar_pressed:
            # First check if player is near a shopkeeper
            shopkeeper_found = False
            if self.game_manager.player:
                player_rect = self.game_manager.player.get_rect()
                # Expand rect to check nearby tiles
                interaction_range = player_rect.inflate(GameSettings.TILE_SIZE * 2, GameSettings.TILE_SIZE * 2)
                
                for shopkeeper in getattr(self.game_manager.current_map, 'shopkeepers', []):
                    if interaction_range.colliderect(shopkeeper.animation.rect):
                        self._open_shop(shopkeeper)
                        shopkeeper_found = True
                        break
            
            if not shopkeeper_found:
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
                            # Trigger wild monster battle
                            wild_monster = generate_random_monster()
                            from src.scenes.battle_scene import BattleScene
                            Logger.info(f"Wild {wild_monster['name']} appeared!")
                            player_mon = self.game_manager.bag.monsters[0] if self.game_manager.bag.monsters else None
                            battle_scene = BattleScene(player=self.game_manager.player, player_mon=player_mon, enemy=wild_monster, bag=self.game_manager.bag, game_manager=self.game_manager)
                            scene_manager.register_scene("wild_battle", battle_scene)
                            scene_manager.change_scene("wild_battle")
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
            # Forward event to buttons
            if not self.overlay_open:
                self.settings_button.update(0)  # triggers click
            else:
                self.back_button.update(0)      # triggers click

            if self.overlay_open:
                self.checkbox_sound.handle_event(event)
                self.slider_music.handle_event(event)
                self.save_button.update(0)  # trigger click
                self.load_button.update(0)

            if not self.overlay_open and not self.backpack_open:
                self.backpack_button.update(0)
                self.navigation_button.update(0)

            if self.backpack_open:
                self.backpack_close_button.update(0)
                self.backpack_monsters_button.update(0)
                self.backpack_items_button.update(0)

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

        start_y = self.backpack_box_rect.y + 110  # starting y inside box below tabs
        monster_block_w, monster_block_h = 200, 50
        monster_sprite_size = 45
        padding_x, padding_y = 10, 5
        columns = 2  # number of monsters per row

        for index, mon in enumerate(self.game_manager.bag.monsters):
            col = index % columns
            row = index // columns

            block_x = self.backpack_box_rect.x + 20 + col * (monster_block_w + padding_x)
            block_y = start_y + row * (monster_block_h + padding_y) - self.backpack_scroll_y

            # Only draw if inside overlay box
            if block_y + monster_block_h < self.backpack_box_rect.y + self.backpack_box_rect.height - 10:
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
                bar_w, bar_h = 65, 5
                bar_x, bar_y = block_x + 130, block_y + 16
                pg.draw.rect(screen, (0,0,0), (bar_x, bar_y, bar_w, bar_h), 1)
                hp_ratio = hp / max_hp
                fill_w = int((bar_w - 2) * hp_ratio)
                fill_color = (50,205,50) if hp_ratio > 0.5 else (255,215,0) if hp_ratio > 0.2 else (255,0,0)
                pg.draw.rect(screen, fill_color, (bar_x+1, bar_y+1, fill_w, bar_h-2))

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

    @override
    def draw(self, screen: pg.Surface):
        # --- Camera ---
        camera = PositionCamera(0, 0)
        if self.game_manager.player:
            player = self.game_manager.player
            camera = PositionCamera(
                player.position.x - GameSettings.SCREEN_WIDTH // 2,
                player.position.y - GameSettings.SCREEN_HEIGHT // 2
            )
            self.game_manager.current_map.draw(screen, camera)
            player.draw(screen, camera)
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
        self.navigation_button.draw(screen)
        if self.shop_button_visible:
            self.shop_button.draw(screen)

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