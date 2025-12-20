import asyncio
import threading
import time
import queue
import collections
import json
from collections import deque
from typing import Optional
from src.utils import Logger, GameSettings

try:
    import websockets
except ImportError:
    Logger.error("websockets library not installed. Run: pip install websockets")
    websockets = None

from typing import Any


class OnlineManager:
    list_players: list[dict]
    player_id: int
    # WebSocket state
    _ws: Optional[Any]
    _ws_loop: Optional[asyncio.AbstractEventLoop]
    _ws_thread: Optional[threading.Thread]
    _stop_event: threading.Event
    _lock: threading.Lock
    _update_queue: queue.Queue
    _chat_out_queue: queue.Queue
    _chat_messages: collections.deque
    _last_chat_id: int
    # Battle challenge state
    _battle_out_queue: queue.Queue
    _pending_challenge_from: int  # ID of player who challenged us
    _battle_start_opponent: int  # ID of opponent when battle should start
    _battle_declined: bool  # Whether our challenge was declined

    def __init__(self):
        if websockets is None:
            Logger.error("WebSockets library not available")
            raise ImportError("websockets library required")

        self.base: str = GameSettings.ONLINE_SERVER_URL
        # Convert HTTP URL to WebSocket URL
        if self.base.startswith("http://"):
            self.ws_url = self.base.replace("http://", "ws://")
        elif self.base.startswith("https://"):
            self.ws_url = self.base.replace("https://", "wss://")
        else:
            self.ws_url = f"ws://{self.base}"

        self.player_id = -1
        self.list_players = []
        self._ws = None
        self._ws_loop = None
        self._ws_thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._update_queue = queue.Queue(maxsize=10)
        self._chat_out_queue = queue.Queue(maxsize=50)
        self._chat_messages = deque(maxlen=200)
        self._last_chat_id = 0
        
        # Battle challenge state
        self._battle_out_queue = queue.Queue(maxsize=10)
        self._pending_challenge_from = -1
        self._pending_opponent_monster = None  # Monster data from challenger
        self._battle_start_opponent = -1
        self._battle_start_opponent_monster = None  # Monster data for battle start
        self._battle_declined = False

        Logger.info("OnlineManager initialized")

    def enter(self):
        self.start()

    def exit(self):
        self.stop()

    def get_list_players(self) -> list[dict]:
        """Get list of players"""
        with self._lock:
            return list(self.list_players)

    def update(self, x: float, y: float, map_name: str, direction: str = "down", is_moving: bool = False) -> bool:
        """Queue position update with direction and movement state."""
        if self.player_id == -1:
            return False
        try:
            self._update_queue.put_nowait({
                "x": x,
                "y": y,
                "map": map_name,
                "direction": direction,
                "is_moving": is_moving,
            })
            return True
        except queue.Full:
            return False

    def start(self) -> None:
        if self._ws_thread and self._ws_thread.is_alive():
            return

        self._stop_event.clear()

        self._ws_thread = threading.Thread(
            target=self._ws_thread_func,
            name="OnlineManagerWebSocket",
            daemon=True
        )
        self._ws_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._ws_loop and self._ws_loop.is_running():
            # Schedule stop in the event loop
            asyncio.run_coroutine_threadsafe(self._close_ws(), self._ws_loop)
        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=3)

    def _ws_thread_func(self) -> None:
        """Run WebSocket event loop in a separate thread"""
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)
        try:
            self._ws_loop.run_until_complete(self._ws_main())
        except Exception as e:
            Logger.error(f"WebSocket thread error: {e}")
        finally:
            self._ws_loop.close()
            self._ws_loop = None

    async def _close_ws(self) -> None:
        """Close WebSocket connection"""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _ws_main(self) -> None:
        """Main WebSocket connection and message handling"""
        reconnect_delay = 1.0
        max_reconnect_delay = 30.0

        while not self._stop_event.is_set():
            try:
                # Connect to WebSocket server
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=20,
                    ping_timeout=10
                ) as websocket:
                    self._ws = websocket
                    Logger.info("WebSocket connected")
                    reconnect_delay = 1.0  # Reset delay on successful connection

                    # Start sender task
                    sender_task = asyncio.create_task(self._ws_sender(websocket))

                    # Handle incoming messages
                    try:
                        async for message in websocket:
                            if self._stop_event.is_set():
                                break
                            await self._handle_message(message)
                    except websockets.exceptions.ConnectionClosed:
                        Logger.warning("WebSocket connection closed")
                    finally:
                        sender_task.cancel()
                        try:
                            await sender_task
                        except asyncio.CancelledError:
                            pass

            except Exception as e:
                Logger.warning(f"WebSocket connection error: {e}, reconnecting in {reconnect_delay}s")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)
            finally:
                self._ws = None
                if not self._stop_event.is_set():
                    await asyncio.sleep(0.5)

    async def _handle_message(self, message: str) -> None:
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")

            if msg_type == "registered":
                self.player_id = int(data.get("id", -1))
                Logger.info(f"OnlineManager registered with id={self.player_id}")

            elif msg_type == "players_update":
                players_data = data.get("players", {})
                with self._lock:
                    filtered = []
                    for pid_str, player_data in players_data.items():
                        pid = int(pid_str)
                        if pid != self.player_id:
                            filtered.append({
                                "id": pid,
                                "x": float(player_data.get("x", 0)),
                                "y": float(player_data.get("y", 0)),
                                "map": str(player_data.get("map", "")),
                                "direction": str(player_data.get("direction", "down")),
                                "is_moving": bool(player_data.get("is_moving", False)),
                            })
                    self.list_players = filtered
                    if len(filtered) > 0:
                        Logger.info(f"Updated {len(filtered)} online players")

            elif msg_type == "chat_update":
                messages = data.get("messages", [])
                with self._lock:
                    for m in messages:
                        self._chat_messages.append(m)
                        mid = int(m.get("id", self._last_chat_id))
                        if mid > self._last_chat_id:
                            self._last_chat_id = mid

            elif msg_type == "battle_challenge_received":
                # Another player is challenging us to battle
                challenger_id = int(data.get("from", -1))
                opponent_monster = data.get("opponent_monster", None)
                monster_name = opponent_monster.get('name', 'None') if opponent_monster else 'None'
                Logger.info(f"[OnlineManager] battle_challenge_received from {challenger_id}, monster: {monster_name}")
                if challenger_id >= 0:
                    with self._lock:
                        self._pending_challenge_from = challenger_id
                        self._pending_opponent_monster = opponent_monster
                    Logger.info(f"Received battle challenge from player {challenger_id}")

            elif msg_type == "battle_start":
                # Battle is starting (both players agreed)
                opponent_id = int(data.get("opponent_id", -1))
                opponent_monster = data.get("opponent_monster", None)
                monster_name = opponent_monster.get('name', 'None') if opponent_monster else 'None'
                Logger.info(f"[OnlineManager] battle_start received: opponent {opponent_id}, monster: {monster_name}")
                if opponent_id >= 0:
                    with self._lock:
                        self._battle_start_opponent = opponent_id
                        self._battle_start_opponent_monster = opponent_monster
                        self._pending_challenge_from = -1  # Clear pending challenge
                        self._pending_opponent_monster = None
                    Logger.info(f"Battle starting with player {opponent_id}")

            elif msg_type == "battle_declined":
                # Our challenge was declined
                with self._lock:
                    self._battle_declined = True
                Logger.info("Battle challenge was declined")

            elif msg_type == "error":
                Logger.warning(f"Server error: {data.get('message', 'unknown')}")

        except json.JSONDecodeError as e:
            Logger.warning(f"Failed to parse WebSocket message: {e}")
        except Exception as e:
            Logger.warning(f"Error handling WebSocket message: {e}")

    async def _ws_sender(self, websocket: Any) -> None:
        """Send updates to server via WebSocket"""
        update_interval = 0.0167  # 60 updates per second
        last_update = time.monotonic()

        while not self._stop_event.is_set():
            try:
                # Send position updates
                now = time.monotonic()
                if now - last_update >= update_interval:
                    # Collapse queue to latest entry to avoid sending stale movement
                    latest_update = None
                    try:
                        while True:
                            latest_update = self._update_queue.get_nowait()
                    except queue.Empty:
                        pass

                    if latest_update and self.player_id >= 0:
                        message = {
                            "type": "player_update",
                            "x": latest_update.get("x"),
                            "y": latest_update.get("y"),
                            "map": latest_update.get("map"),
                            "direction": latest_update.get("direction", "down"),
                            "is_moving": latest_update.get("is_moving", False),
                        }
                        await websocket.send(json.dumps(message))
                        last_update = now

                # Send chat messages
                try:
                    chat_text = self._chat_out_queue.get_nowait()
                    if self.player_id >= 0:
                        message = {
                            "type": "chat_send",
                            "text": chat_text
                        }
                        await websocket.send(json.dumps(message))
                except queue.Empty:
                    pass

                # Send battle messages
                try:
                    battle_msg = self._battle_out_queue.get_nowait()
                    if self.player_id >= 0:
                        await websocket.send(json.dumps(battle_msg))
                except queue.Empty:
                    pass

                await asyncio.sleep(0.01)  # Small sleep to prevent busy waiting

            except Exception as e:
                Logger.warning(f"WebSocket send error: {e}")
                await asyncio.sleep(0.1)
                
    def send_chat(self, text: str) -> bool:
        if self.player_id == -1:
            return False
        t = (text or "").strip()
        if not t:
            return False
        try:
            self._chat_out_queue.put_nowait(t)
            return True
        except queue.Full:
            return False

    def get_recent_chat(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._chat_messages)[-limit:]

    # --- Battle Challenge Methods ---
    
    def send_battle_challenge(self, target_id: int, monster_data: dict = None) -> bool:
        """Send a battle challenge to another player with our monster data."""
        if self.player_id == -1 or target_id < 0:
            return False
        try:
            self._battle_out_queue.put_nowait({
                "type": "battle_challenge",
                "target_id": target_id,
                "monster_data": monster_data
            })
            return True
        except queue.Full:
            return False

    def accept_battle_challenge(self, challenger_id: int, monster_data: dict = None) -> bool:
        """Accept a battle challenge from another player with our monster data."""
        if self.player_id == -1 or challenger_id < 0:
            return False
        try:
            self._battle_out_queue.put_nowait({
                "type": "battle_accept",
                "challenger_id": challenger_id,
                "monster_data": monster_data
            })
            return True
        except queue.Full:
            return False

    def decline_battle_challenge(self, challenger_id: int) -> bool:
        """Decline a battle challenge from another player."""
        if self.player_id == -1 or challenger_id < 0:
            return False
        try:
            self._battle_out_queue.put_nowait({
                "type": "battle_decline",
                "challenger_id": challenger_id
            })
            with self._lock:
                self._pending_challenge_from = -1
            return True
        except queue.Full:
            return False

    def get_pending_challenge(self) -> tuple[int, dict]:
        """Get the player ID who is challenging us and their monster data, or (-1, None) if none."""
        with self._lock:
            return (self._pending_challenge_from, self._pending_opponent_monster)

    def clear_pending_challenge(self) -> None:
        """Clear the pending challenge."""
        with self._lock:
            self._pending_challenge_from = -1
            self._pending_opponent_monster = None

    def get_battle_start_opponent(self) -> tuple[int, dict]:
        """Get the opponent ID and monster data for a battle that should start, or (-1, None) if none."""
        with self._lock:
            opponent = self._battle_start_opponent
            monster = self._battle_start_opponent_monster
            self._battle_start_opponent = -1  # Clear after reading
            self._battle_start_opponent_monster = None
            return (opponent, monster)

    def was_challenge_declined(self) -> bool:
        """Check if our challenge was declined."""
        with self._lock:
            declined = self._battle_declined
            self._battle_declined = False  # Clear after reading
            return declined