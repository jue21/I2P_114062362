import pygame as pg
import time
from src.utils import GameSettings
from src.interface.components import Button
from src.core.services import resource_manager
from src.data.bag import Bag


class ShopOverlay:
    """
    A shop overlay UI for buying and selling items.
    Synchronized with the player's bag.
    """
    def __init__(self, shopkeeper, bag: Bag, font: pg.font.Font):
        self.shopkeeper = shopkeeper
        self.bag = bag
        self.font = font
        
        # Overlay dimensions
        sw, sh = GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT
        self.width = 700
        self.height = 500
        self.rect = pg.Rect(
            (sw - self.width) // 2,
            (sh - self.height) // 2,
            self.width,
            self.height
        )
        
        # Tab system: "buy", "sell_items", or "sell_monsters"
        self.current_tab = "buy"
        
        # Scroll offset for items list
        self.scroll_offset = 0
        self.scroll_speed = 30
        
        # Close button
        close_size = 40
        self.close_button = Button(
            "UI/button_x.png",
            "UI/button_x_hover.png",
            self.rect.right - close_size - 10,
            self.rect.y + 10,
            close_size,
            close_size,
            lambda: None  # Will be set by game_scene
        )
        
        # Tab buttons
        tab_width = 180  # Increased from 100 to accommodate longer text
        tab_height = 40
        buy_x = self.rect.x + 20
        sell_items_x = buy_x + tab_width + 10
        sell_monsters_x = sell_items_x + tab_width + 20
        tab_y = self.rect.y + 50  # Moved lower to avoid covering title
        
        self.buy_button = Button(
            "UI/button_back.png",
            "UI/button_back_hover.png",
            buy_x, tab_y,
            tab_width, tab_height,
            lambda: self.switch_tab("buy")
        )
        
        self.sell_items_button = Button(
            "UI/button_back.png",
            "UI/button_back_hover.png",
            sell_items_x, tab_y,
            tab_width, tab_height,
            lambda: self.switch_tab("sell_items")
        )
        
        self.sell_monsters_button = Button(
            "UI/button_back.png",
            "UI/button_back_hover.png",
            sell_monsters_x, tab_y,
            tab_width, tab_height,
            lambda: self.switch_tab("sell_monsters")
        )
        
        # Item display area (inside the rect with padding)
        self.items_area_rect = pg.Rect(
            self.rect.x + 20,
            self.rect.y + 100,  # Adjusted to be below the tab buttons
            self.rect.width - 40,
            self.rect.height - 160
        )
        
        # Selected item for purchase/sale
        self.selected_item_index = None
        self.quantity_input = ""
        # Prevent duplicate rapid purchases
        self._last_buy_time = 0.0
        
        # Buy button rects for item purchase
        self.buy_item_buttons = []  # List of Button objects
        
        # Sell button rects for item/monsters selling
        self.sell_item_buttons = []  # List of Button objects for selling items
        self.sell_monster_buttons = []  # List of Button objects for selling monsters
        
        # Initialize buy buttons for default tab
        self._create_buy_buttons()
    
    def switch_tab(self, tab: str) -> None:
        """Switch between buy, sell_items, and sell_monsters tabs."""
        if tab in ["buy", "sell_items", "sell_monsters"]:
            self.current_tab = tab
            self.scroll_offset = 0
            self.selected_item_index = None
            self.quantity_input = ""
            if tab == "buy":
                self._create_buy_buttons()
                self.sell_item_buttons = []
                self.sell_monster_buttons = []
            elif tab == "sell_items":
                self._create_sell_item_buttons()
                self.buy_item_buttons = []
                self.sell_monster_buttons = []
            elif tab == "sell_monsters":
                self._create_sell_monster_buttons()
                self.buy_item_buttons = []
                self.sell_item_buttons = []
    
    def _create_buy_buttons(self) -> None:
        """Create Button objects for each shop item."""
        self.buy_item_buttons = []
        items = self.get_items_list()
        
        for idx, item in enumerate(items):
            button = Button(
                "UI/button_shop.png",
                "UI/button_shop_hover.png",
                self.items_area_rect.right - 50,  # x will be updated in draw
                0,  # y will be updated in draw
                40, 34,
                lambda item=item: self._execute_buy(item, 1)
            )
            self.buy_item_buttons.append(button)
    
    def _create_sell_item_buttons(self) -> None:
        """Create Button objects for selling each item."""
        self.sell_item_buttons = []
        items = self.get_items_list()
        
        for idx, item in enumerate(items):
            button = Button(
                "UI/button_shop.png",
                "UI/button_shop_hover.png",
                self.items_area_rect.right - 50,  # x will be updated in draw
                0,  # y will be updated in draw
                40, 34,
                lambda item=item: self._execute_sell_item(item, 1)
            )
            self.sell_item_buttons.append(button)
    
    def _create_sell_monster_buttons(self) -> None:
        """Create Button objects for selling each monster."""
        self.sell_monster_buttons = []
        monsters = self.get_items_list()
        
        for idx, monster in enumerate(monsters):
            button = Button(
                "UI/button_shop.png",
                "UI/button_shop_hover.png",
                self.items_area_rect.right - 50,  # x will be updated in draw
                0,  # y will be updated in draw
                40, 34,
                lambda monster=monster: self._execute_sell_monster(monster, 1)
            )
            self.sell_monster_buttons.append(button)
    
    def get_items_list(self) -> list[dict]:
        """Get the current items list based on active tab."""
        if self.current_tab == "buy":
            return self.shopkeeper.shop_items
        elif self.current_tab == "sell_items":
            return self.bag.items
        elif self.current_tab == "sell_monsters":
            return self.bag.monsters
        return []
    
    def _get_item_image(self, item_name: str) -> pg.Surface | None:
        """Get the sprite image for an item based on its name."""
        item_name_lower = item_name.lower()
        
        # Map item names to image files
        if "potion" in item_name_lower:
            return resource_manager.get_image("ingame_ui/potion.png")
        elif "ball" in item_name_lower:
            return resource_manager.get_image("ingame_ui/ball.png")
        elif "coin" in item_name_lower:
            return resource_manager.get_image("ingame_ui/coin.png")
        
        return None
    
    def handle_input(self, event: pg.event.Event) -> None:
        """Handle input for the shop overlay."""
        if event.type == pg.MOUSEBUTTONDOWN:
            # Check close button
            if self.close_button.hitbox.collidepoint(event.pos):
                if self.close_button.on_click:
                    self.close_button.on_click()
                return
            
            # Check tab buttons
            if self.buy_button.hitbox.collidepoint(event.pos):
                if self.buy_button.on_click:
                    self.buy_button.on_click()
                return
            
            if self.sell_items_button.hitbox.collidepoint(event.pos):
                if self.sell_items_button.on_click:
                    self.sell_items_button.on_click()
                return
            
            if self.sell_monsters_button.hitbox.collidepoint(event.pos):
                if self.sell_monsters_button.on_click:
                    self.sell_monsters_button.on_click()
                return
            
            # Check buy button clicks
            self._update_buy_button_positions()
            for button in self.buy_item_buttons:
                if button.hitbox.collidepoint(event.pos):
                    if button.on_click:
                        button.on_click()
                    return
            
            # Check sell item button clicks
            self._update_sell_item_button_positions()
            for button in self.sell_item_buttons:
                if button.hitbox.collidepoint(event.pos):
                    if button.on_click:
                        button.on_click()
                    return
            
            # Check sell monster button clicks
            self._update_sell_monster_button_positions()
            for button in self.sell_monster_buttons:
                if button.hitbox.collidepoint(event.pos):
                    if button.on_click:
                        button.on_click()
                    return
            
            # Check item selection in items area
            if self.items_area_rect.collidepoint(event.pos):
                items = self.get_items_list()
                item_height = 50
                clicked_index = (event.pos[1] - self.items_area_rect.y + self.scroll_offset) // item_height
                if 0 <= clicked_index < len(items):
                    self.selected_item_index = clicked_index
        
        elif event.type == pg.KEYDOWN:
            # Handle quantity input
            if event.unicode.isdigit():
                self.quantity_input += event.unicode
                if len(self.quantity_input) > 3:
                    self.quantity_input = self.quantity_input[-3:]
            elif event.key == pg.K_BACKSPACE:
                self.quantity_input = self.quantity_input[:-1]
            elif event.key == pg.K_RETURN:
                self.confirm_transaction()
        
        elif event.type == pg.MOUSEWHEEL:
            # Handle scrolling
            self.scroll_offset -= event.y * self.scroll_speed
            # clamp scroll to available items
            items = self.get_items_list()
            item_height = 50
            max_scroll = max(0, len(items) * item_height - self.items_area_rect.height)
            if self.scroll_offset < 0:
                self.scroll_offset = 0
            if self.scroll_offset > max_scroll:
                self.scroll_offset = max_scroll
            # Update button positions after scrolling
            self._update_buy_button_positions()
    
    def _update_buy_button_positions(self) -> None:
        """Update positions of buy item buttons based on current scroll."""
        if self.current_tab != "buy":
            return
        
        items = self.get_items_list()
        item_height = 50
        y_offset = self.items_area_rect.y
        
        for idx, button in enumerate(self.buy_item_buttons):
            if idx < len(items):
                item_y = y_offset + (idx * item_height) - self.scroll_offset
                button.hitbox.x = self.items_area_rect.right - 50
                button.hitbox.y = item_y + 8
    
    def _update_sell_item_button_positions(self) -> None:
        """Update positions of sell item buttons based on current scroll."""
        if self.current_tab != "sell_items":
            return
        
        items = self.get_items_list()
        item_height = 50
        y_offset = self.items_area_rect.y
        
        for idx, button in enumerate(self.sell_item_buttons):
            if idx < len(items):
                item_y = y_offset + (idx * item_height) - self.scroll_offset
                button.hitbox.x = self.items_area_rect.right - 50
                button.hitbox.y = item_y + 8
    
    def _update_sell_monster_button_positions(self) -> None:
        """Update positions of sell monster buttons based on current scroll."""
        if self.current_tab != "sell_monsters":
            return
        
        monsters = self.get_items_list()
        item_height = 50
        y_offset = self.items_area_rect.y
        
        for idx, button in enumerate(self.sell_monster_buttons):
            if idx < len(monsters):
                item_y = y_offset + (idx * item_height) - self.scroll_offset
                button.hitbox.x = self.items_area_rect.right - 50
                button.hitbox.y = item_y + 8
    
    def confirm_transaction(self) -> None:
        """Execute a buy or sell transaction."""
        if self.selected_item_index is None or not self.quantity_input:
            return
        
        try:
            quantity = int(self.quantity_input)
        except ValueError:
            return
        
        items = self.get_items_list()
        if self.selected_item_index >= len(items):
            return
        
        item = items[self.selected_item_index]
        
        if self.current_tab == "buy":
            self._execute_buy(item, quantity)
        elif self.current_tab == "sell_items":
            self._execute_sell_item(item, quantity)
        elif self.current_tab == "sell_monsters":
            self._execute_sell_monster(item, quantity)
        
        self.quantity_input = ""
    
    def _execute_buy(self, item: dict, quantity: int) -> None:
        """Handle buying an item."""
        # Prevent duplicate rapid buys from double-clicks
        now = time.time()
        if now - self._last_buy_time < 0.25:
            return
        self._last_buy_time = now
        total_cost = item.get("price", 0) * quantity
        
        # Check if shopkeeper has enough items
        if item.get("count", 0) < quantity:
            # Not enough items in shop - silently fail
            return
        
        # Check if player has enough coins
        coin_item = None
        for bag_item in self.bag.items:
            if "coin" in bag_item.get("name", "").lower():
                coin_item = bag_item
                break
        
        if coin_item is None or coin_item.get("count", 0) < total_cost:
            # Not enough coins - silently fail or could add UI feedback
            return
        
        # Deduct from shopkeeper's inventory
        item["count"] -= quantity
        if item["count"] <= 0:
            # Restock item when count reaches 0
            item["count"] = 10
        
        # Deduct coins
        coin_item["count"] -= total_cost
        if coin_item["count"] == 0:
            self.bag.items.remove(coin_item)
        
        # Add the purchased item to bag
        existing_item = None
        for bag_item in self.bag.items:
            if bag_item.get("name") == item["name"]:
                existing_item = bag_item
                break
        
        if existing_item:
            existing_item["count"] += quantity
        else:
            # Add new item to bag
            new_item = {
                "name": item["name"],
                "count": quantity,
                "sprite_path": item.get("sprite_path", ""),
                "sprite": item.get("sprite")
            }
            self.bag.items.append(new_item)
        
        self.selected_item_index = None
    
    def _execute_sell_item(self, item: dict, quantity: int) -> None:
        """Handle selling an item."""
        if item.get("count", 0) < quantity:
            return
        
        # Calculate sell price (half of buy price, or default value)
        sell_price = item.get("sell_price", item.get("price", 10) // 2) * quantity
        
        # Remove items from bag
        item["count"] -= quantity
        if item["count"] == 0:
            self.bag.items.remove(item)
        
        # Add coins to player's bag
        self._add_coins_to_bag(sell_price)
        
        self.selected_item_index = None
    
    def _execute_sell_monster(self, monster: dict, quantity: int) -> None:
        """Handle selling a monster."""
        # Monsters are sold individually (quantity should be 1)
        if quantity != 1:
            return
        
        # Calculate sell price based on monster level/strength
        base_price = 100  # Base price for any monster
        level_bonus = monster.get("level", 1) * 10
        sell_price = base_price + level_bonus
        
        # Remove monster from bag
        if monster in self.bag.monsters:
            self.bag.monsters.remove(monster)
        
        # Add coins to player's bag
        self._add_coins_to_bag(sell_price)
        
        self.selected_item_index = None
    
    def _add_coins_to_bag(self, amount: int) -> None:
        """Add coins to the player's bag."""
        # Find existing coin item or create new one
        coin_item = None
        for item in self.bag.items:
            if "coin" in item.get("name", "").lower():
                coin_item = item
                break
        
        if coin_item:
            coin_item["count"] += amount
        else:
            # Create new coin item
            new_coin = {
                "name": "Coins",
                "count": amount,
                "sprite_path": "ingame_ui/coin.png"
            }
            # Try to load sprite
            try:
                from src.core.services import resource_manager
                new_coin["sprite"] = resource_manager.get_image("ingame_ui/coin.png")
            except:
                pass
            self.bag.items.append(new_coin)
    
    def update(self, dt: float) -> None:
        """Update shop overlay state."""
        self.buy_button.update(dt)
        self.sell_items_button.update(dt)
        self.sell_monsters_button.update(dt)
        self.close_button.update(dt)
        
        # Update buy item buttons
        for button in self.buy_item_buttons:
            button.update(dt)
        
        # Update sell item buttons
        for button in self.sell_item_buttons:
            button.update(dt)
        
        # Update sell monster buttons
        for button in self.sell_monster_buttons:
            button.update(dt)
        
        # Keep button positions updated
        self._update_buy_button_positions()
        self._update_sell_item_button_positions()
        self._update_sell_monster_button_positions()
    
    def draw(self, screen: pg.Surface) -> None:
        """Draw the shop overlay."""
        # Draw semi-transparent background
        dark_surface = pg.Surface((GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT), pg.SRCALPHA)
        dark_surface.fill((0, 0, 0, 150))
        screen.blit(dark_surface, (0, 0))
        
        # --- Pixel-art overlay box (matching settings overlay style) ---
        box_color = (255, 165, 0)        # orange
        border_color = (200, 120, 0)     # darker orange border
        highlight_color = (255, 200, 100) # top-left highlight
        
        # Draw main box
        pg.draw.rect(screen, box_color, self.rect)
        
        # Draw border
        pg.draw.rect(screen, border_color, self.rect, width=1)
        
        # Draw top-left highlight for pixel style
        pg.draw.line(screen, highlight_color, 
                    (self.rect.left, self.rect.top), 
                    (self.rect.right-1, self.rect.top))  # top
        pg.draw.line(screen, highlight_color, 
                    (self.rect.left, self.rect.top), 
                    (self.rect.left, self.rect.bottom-1))  # left
        
        # Draw title
        title_surf = self.font.render(f"{self.shopkeeper.name}'s Shop", True, (20, 20, 20))
        screen.blit(title_surf, (self.rect.x + 10, self.rect.y + 10))
        
        # Draw tab buttons
        self._draw_tab_button(screen, self.buy_button, "Buy", self.current_tab == "buy")
        self._draw_tab_button(screen, self.sell_items_button, "Sell Items", self.current_tab == "sell_items")
        self._draw_tab_button(screen, self.sell_monsters_button, "Sell Monsters", self.current_tab == "sell_monsters")
        
        # Draw close button
        self.close_button.draw(screen)
        
        # Draw items list
        self._draw_items_list(screen)
        
        # Draw selected item details
        if self.selected_item_index is not None:
            self._draw_item_details(screen)
    
    def _draw_tab_button(self, screen: pg.Surface, button: Button, label: str, active: bool) -> None:
        """Draw a tab button with text in Pokemon style."""
        # Use orange/gold colors like the main overlay
        if active:
            color = (255, 215, 0)  # Gold/active
            border_color = (200, 120, 0)
        else:
            color = (200, 165, 100)  # Muted orange/inactive
            border_color = (150, 100, 50)
        
        pg.draw.rect(screen, color, button.hitbox)
        pg.draw.rect(screen, border_color, button.hitbox, 1)
        
        text_surf = self.font.render(label, True, (20, 20, 20))
        text_rect = text_surf.get_rect(center=button.hitbox.center)
        screen.blit(text_surf, text_rect)
    
    def _draw_items_list(self, screen: pg.Surface) -> None:
        """Draw the list of items in the current tab."""
        items = self.get_items_list()
        item_height = 50
        small_font = pg.font.Font("assets/fonts/Minecraft.ttf", 18)
        
        # Draw items area background with Pokemon style
        pg.draw.rect(screen, (255, 215, 0), self.items_area_rect)
        pg.draw.rect(screen, (200, 120, 0), self.items_area_rect, 1)
        
        # Draw items (clip to items area to avoid drawing outside box)
        y_offset = self.items_area_rect.y
        prev_clip = screen.get_clip()
        screen.set_clip(self.items_area_rect)
        for idx, item in enumerate(items):
            item_y = y_offset + (idx * item_height) - self.scroll_offset

            # Default visibility: draw if any part is visible
            if item_y + item_height < self.items_area_rect.y:
                continue
            if item_y > self.items_area_rect.bottom:
                continue

            # For monster rows, require the whole row to be inside the items area
            if self.current_tab == "sell_monsters":
                if item_y < self.items_area_rect.y or (item_y + item_height) > self.items_area_rect.bottom:
                    continue
            
            # Highlight selected item with gold color
            if idx == self.selected_item_index:
                pg.draw.rect(screen, (255, 255, 200), 
                            (self.items_area_rect.x, item_y, self.items_area_rect.width, item_height))
            
            # Draw item image
            item_name = item.get('name', 'Unknown')
            if self.current_tab == "sell_monsters":
                # For monsters, use their sprite
                item_image = item.get("sprite")
            else:
                # For items, use the mapped image
                item_image = self._get_item_image(item_name)
            
            if item_image:
                scaled_img = pg.transform.scale(item_image, (32, 32))
                screen.blit(scaled_img, (self.items_area_rect.x + 10, item_y + 9))
                text_x = self.items_area_rect.x + 50
            else:
                text_x = self.items_area_rect.x + 10
            
            # Draw item name and details
            if self.current_tab == "buy":
                text = f"{item_name} - ${item.get('price', 0)} (x{item.get('count', 0)})"
            elif self.current_tab == "sell_items":
                sell_price = item.get("sell_price", item.get("price", 10) // 2)
                text = f"{item_name} x{item.get('count', 0)} - ${sell_price} each"
            elif self.current_tab == "sell_monsters":
                level = item.get("level", 1)
                sell_price = 100 + (level * 10)  # Base 100 + 10 per level
                hp = item.get("hp", 0)
                max_hp = item.get("max_hp", 30)
                text = f"{item_name} (Lv.{level}) HP:{hp}/{max_hp} - ${sell_price}"
            
            text_surf = small_font.render(text, True, (20, 20, 20))
            screen.blit(text_surf, (text_x, item_y + 15))
            
            # Draw appropriate button for current tab
            if self.current_tab == "buy" and idx < len(self.buy_item_buttons):
                button = self.buy_item_buttons[idx]
                # Update button position based on current scroll
                button.hitbox.x = self.items_area_rect.right - 50
                button.hitbox.y = item_y + 8
                button.draw(screen)
            elif self.current_tab == "sell_items" and idx < len(self.sell_item_buttons):
                button = self.sell_item_buttons[idx]
                # Update button position based on current scroll
                button.hitbox.x = self.items_area_rect.right - 50
                button.hitbox.y = item_y + 8
                button.draw(screen)
            elif self.current_tab == "sell_monsters" and idx < len(self.sell_monster_buttons):
                button = self.sell_monster_buttons[idx]
                # Update button position based on current scroll
                button.hitbox.x = self.items_area_rect.right - 50
                button.hitbox.y = item_y + 8
                button.draw(screen)
        # restore clip after drawing all items
        screen.set_clip(prev_clip)
    
    def _draw_item_details(self, screen: pg.Surface) -> None:
        """Draw details of the selected item."""
        items = self.get_items_list()
        if self.selected_item_index >= len(items):
            return
        
        item = items[self.selected_item_index]
        small_font = pg.font.Font("assets/fonts/Minecraft.ttf", 18)
        
        # Draw quantity input area
        details_y = self.items_area_rect.bottom + 20
        text = f"Quantity: {self.quantity_input}"
        text_surf = small_font.render(text, True, (20, 20, 20))
        screen.blit(text_surf, (self.rect.x + 20, details_y))
        
        # Draw confirm button hint
        hint = "Press ENTER to confirm"
        hint_surf = small_font.render(hint, True, (100, 50, 0))
        screen.blit(hint_surf, (self.rect.x + 20, details_y + 40))
