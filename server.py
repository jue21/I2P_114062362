import asyncio
import json
import time
import threading
from typing import Dict, Set, Any
from dataclasses import dataclass, asdict
from server.playerHandler import PlayerHandler

from websockets.asyncio.server import serve

PORT = 8989

PLAYER_HANDLER = PlayerHandler()
PLAYER_HANDLER.start()

# ------------------------------
# Simple in-memory chat storage
# ------------------------------
class ChatStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._next_id = 1
        self._messages: list[dict] = []

    def add(self, sender_id: int, text: str) -> dict:
        # Sanitize
        t = (text or "").strip()
        if len(t) > 200:
            t = t[:200]
        if not t:
            raise ValueError("empty")
        with self._lock:
            msg = {
                "id": self._next_id,
                "from": sender_id,
                "text": t,
                "ts": time.time(),
            }
            self._messages.append(msg)
            self._next_id += 1
            # Keep only the last N to avoid unbounded growth
            if len(self._messages) > 1000:
                self._messages = self._messages[-800:]
            return msg

    def list_since(self, since_id: int) -> list[dict]:
        with self._lock:
            if since_id <= 0:
                return list(self._messages[-100:])  # cap response size
            # Find first index with id > since_id
            # Messages are appended in increasing id order
            out: list[dict] = []
            for m in self._messages:
                if int(m.get("id", 0)) > since_id:
                    out.append(m)
            # Cap size
            if len(out) > 200:
                out = out[-200:]
            return out

CHAT = ChatStore()

# Track connected clients
CONNECTED_CLIENTS: Set[Any] = set()
CLIENTS_LOCK = asyncio.Lock()


async def broadcast_player_update():
    """Broadcast player list to all connected clients periodically"""
    while True:
        await asyncio.sleep(0.0167)  # 60 updates per second
        players = PLAYER_HANDLER.list_players()
        message = {
            "type": "players_update",
            "players": players,
            "timestamp": time.time()
        }
        msg_json = json.dumps(message)
        # Broadcast to all connected clients
        disconnected = set()
        async with CLIENTS_LOCK:
            for client in CONNECTED_CLIENTS:
                try:
                    await client.send(msg_json)
                except Exception:
                    disconnected.add(client)
            # Remove disconnected clients
            CONNECTED_CLIENTS.difference_update(disconnected)


async def handle_client(websocket: Any):
    """Handle a WebSocket client connection"""
    player_id = -1
    
    async with CLIENTS_LOCK:
        CONNECTED_CLIENTS.add(websocket)
    
    try:
        # Register player on connection - server assigns ID
        player_id = PLAYER_HANDLER.register()
        await websocket.send(json.dumps({
            "type": "registered",
            "id": player_id
        }))
        
        # Send initial player list
        players = PLAYER_HANDLER.list_players()
        await websocket.send(json.dumps({
            "type": "players_update",
            "players": players,
            "timestamp": time.time()
        }))
        
        # Send recent chat messages
        recent_chat = CHAT.list_since(0)
        await websocket.send(json.dumps({
            "type": "chat_update",
            "messages": recent_chat
        }))
        
        # Handle incoming messages
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get("type")
                
                if msg_type == "player_update":
                    # Update player position - use server-assigned ID, ignore client ID
                    x = float(data.get("x", 0))
                    y = float(data.get("y", 0))
                    map_name = str(data.get("map", ""))
                    direction = str(data.get("direction", "down"))
                    is_moving = bool(data.get("is_moving", False))
                    
                    # Use the server-assigned player_id, not client-provided
                    PLAYER_HANDLER.update(player_id, x, y, map_name, direction, is_moving)
                    
                elif msg_type == "chat_send":
                    # Send chat message - use server-assigned ID
                    text = str(data.get("text", ""))
                    if text:
                        try:
                            msg = CHAT.add(player_id, text)  # Use server-assigned ID
                            # Broadcast to all clients
                            chat_msg = {
                                "type": "chat_update",
                                "messages": [msg]
                            }
                            chat_json = json.dumps(chat_msg)
                            async with CLIENTS_LOCK:
                                disconnected = set()
                                for client in CONNECTED_CLIENTS:
                                    try:
                                        await client.send(chat_json)
                                    except Exception:
                                        disconnected.add(client)
                                CONNECTED_CLIENTS.difference_update(disconnected)
                        except ValueError:
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": "empty_message"
                            }))
                            
            except json.JSONDecodeError:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "invalid_json"
                }))
            except Exception as e:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": str(e)
                }))
                
    except Exception:
        pass
    finally:
        # Unregister player on disconnect
        if player_id >= 0:
            PLAYER_HANDLER.unregister(player_id)
        async with CLIENTS_LOCK:
            CONNECTED_CLIENTS.discard(websocket)


async def main():
    print(f"[Server] Running WebSocket server on ws://0.0.0.0:{PORT}")
    # Start broadcast task
    asyncio.create_task(broadcast_player_update())
    # Start server
    async with serve(handle_client, "0.0.0.0", PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())