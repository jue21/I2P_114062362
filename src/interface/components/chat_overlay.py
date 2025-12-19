from __future__ import annotations
import pygame as pg
from typing import Optional, Callable, List, Dict
from .component import UIComponent
from src.core.services import input_manager
from src.utils import Logger


class ChatOverlay(UIComponent):
    """Lightweight chat UI similar to Minecraft: toggle with a key, type, press Enter to send."""
    is_open: bool
    _input_text: str
    _cursor_timer: float
    _cursor_visible: bool
    _just_opened: bool
    _send_callback: Callable[[str], bool] | None    #  NOTE: This is a callable function, you need to give it a function that sends the message
    _get_messages: Callable[[int], list[dict]] | None # NOTE: This is a callable function, you need to give it a function that gets the messages
    _font_msg: pg.font.Font
    _font_input: pg.font.Font

    def __init__(
        self,
        send_callback: Callable[[str], bool] | None = None,
        get_messages: Callable[[int], list[dict]] | None = None,
        *,
        font_path: str = "assets/fonts/Minecraft.ttf"
    ) -> None:
        self.is_open = False
        self._input_text = ""
        self._cursor_timer = 0.0
        self._cursor_visible = True
        self._just_opened = False
        self._send_callback = send_callback
        self._get_messages = get_messages

        try:
            self._font_msg = pg.font.Font(font_path, 16)
            self._font_input = pg.font.Font(font_path, 18)
        except Exception:
            self._font_msg = pg.font.SysFont("arial", 16)
            self._font_input = pg.font.SysFont("arial", 18)

    def open(self) -> None:
        if not self.is_open:
            self.is_open = True
            self._cursor_timer = 0.0
            self._cursor_visible = True
            self._just_opened = True

    def close(self) -> None:
        self.is_open = False

    def _handle_typing(self) -> None:
        """Handle text input for chat."""
        # Letters
        shift = input_manager.key_down(pg.K_LSHIFT) or input_manager.key_down(pg.K_RSHIFT)
        for k in range(pg.K_a, pg.K_z + 1):
            if input_manager.key_pressed(k):
                ch = chr(ord('a') + (k - pg.K_a))
                self._input_text += (ch.upper() if shift else ch)
        
        # Numbers
        for k in range(pg.K_0, pg.K_9 + 1):
            if input_manager.key_pressed(k):
                self._input_text += chr(ord('0') + (k - pg.K_0))
        
        # Space
        if input_manager.key_pressed(pg.K_SPACE):
            self._input_text += " "
        
        # Backspace
        if input_manager.key_pressed(pg.K_BACKSPACE):
            if len(self._input_text) > 0:
                self._input_text = self._input_text[:-1]
        
        # Enter to send
        if input_manager.key_pressed(pg.K_RETURN) or input_manager.key_pressed(pg.K_KP_ENTER):
            txt = self._input_text.strip()
            if txt and self._send_callback:
                ok = False
                try:
                    ok = self._send_callback(txt)
                except Exception:
                    ok = False
                if ok:
                    self._input_text = ""

    def update(self, dt: float) -> None:
        if not self.is_open:
            return
        # Close on Escape
        if input_manager.key_pressed(pg.K_ESCAPE):
            self.close()
            return
        # Typing
        if self._just_opened:
            self._just_opened = False
        else:
            self._handle_typing()
        # Cursor blink
        self._cursor_timer += dt
        if self._cursor_timer >= 0.5:
            self._cursor_timer = 0.0
            self._cursor_visible = not self._cursor_visible

    def draw(self, screen: pg.Surface) -> None:
        # Only show chat when open
        if not self.is_open:
            return
        
        sw, sh = screen.get_size()
        x = 10
        
        # Show last 5 messages when chat is open
        msgs = self._get_messages(50) if self._get_messages else []
        if msgs:
            # Take only the last 5 messages
            recent_msgs = list(msgs)[-5:]
            
            # Calculate height needed for messages
            line_height = 20
            num_lines = len(recent_msgs)
            msg_height = num_lines * line_height + 16
            
            # Position messages above input box area
            y = sh - msg_height - 40
            
            container_w = max(200, int((sw - 20) * 0.6))
            bg = pg.Surface((container_w, msg_height), pg.SRCALPHA)
            bg.fill((0, 0, 0, 120))
            _ = screen.blit(bg, (x, y))
            
            # Render messages
            draw_y = y + 8
            for m in recent_msgs:
                sender_id = m.get("from", "")
                text = str(m.get("text", ""))
                # Format: "Player[ID]: message"
                display_text = f"Player[{sender_id}]: {text}"
                surf = self._font_msg.render(display_text, True, (255, 255, 255))
                _ = screen.blit(surf, (x + 10, draw_y))
                draw_y += line_height
        # Input box
        box_h = 28
        box_w = max(100, int((sw - 20) * 0.6))
        box_y = sh - box_h - 6
        # Background box
        bg2 = pg.Surface((box_w, box_h), pg.SRCALPHA)
        bg2.fill((0, 0, 0, 160))
        _ = screen.blit(bg2, (x, box_y))
        # Text
        txt = self._input_text
        text_surf = self._font_input.render(txt, True, (255, 255, 255))
        _ = screen.blit(text_surf, (x + 8, box_y + 4))
        # Caret
        if self._cursor_visible:
            cx = x + 8 + text_surf.get_width() + 2
            cy = box_y + 6
            pg.draw.rect(screen, (255, 255, 255), pg.Rect(cx, cy, 2, box_h - 12))