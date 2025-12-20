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
# Battle Challenge Storage
# ------------------------------
class BattleChallengeStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending_challenges: Dict[int, dict] = {}  # target_id -> challenge info

    def add_challenge(self, from_id: int, to_id: int, monster_data: dict = None) -> dict:
        with self._lock:
            challenge = {
                "from": from_id,
                "to": to_id,
                "timestamp": time.time(),
                "challenger_monster": monster_data  # Store challenger's monster data
            }
            self._pending_challenges[to_id] = challenge
            return challenge

    def get_challenge(self, to_id: int) -> dict | None:
        with self._lock:
            return self._pending_challenges.get(to_id)

    def remove_challenge(self, to_id: int) -> None:
        with self._lock:
            if to_id in self._pending_challenges:
                del self._pending_challenges[to_id]

BATTLE_CHALLENGES = BattleChallengeStore()

# Map player_id to websocket for direct messaging
PLAYER_WEBSOCKETS: Dict[int, Any] = {}
PLAYER_WS_LOCK = asyncio.Lock()

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
        
        # Store websocket for direct messaging
        async with PLAYER_WS_LOCK:
            PLAYER_WEBSOCKETS[player_id] = websocket
        
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
                
                elif msg_type == "battle_challenge":
                    # Player is challenging another player to battle
                    target_id = int(data.get("target_id", -1))
                    monster_data = data.get("monster_data", None)  # Challenger's monster
                    monster_name = monster_data.get('name', 'None') if monster_data else 'None'
                    print(f"[SERVER] battle_challenge: player {player_id} challenges {target_id}, monster: {monster_name}")
                    if target_id >= 0 and target_id != player_id:
                        BATTLE_CHALLENGES.add_challenge(player_id, target_id, monster_data)
                        # Send challenge notification to target player with challenger's monster
                        challenge_msg = json.dumps({
                            "type": "battle_challenge_received",
                            "from": player_id,
                            "opponent_monster": monster_data
                        })
                        async with PLAYER_WS_LOCK:
                            target_ws = PLAYER_WEBSOCKETS.get(target_id)
                            if target_ws:
                                try:
                                    await target_ws.send(challenge_msg)
                                    print(f"[SERVER] Sent challenge to player {target_id}")
                                except Exception as e:
                                    print(f"[SERVER] Failed to send challenge: {e}")
                
                elif msg_type == "battle_accept":
                    # Player accepts a battle challenge
                    challenger_id = int(data.get("challenger_id", -1))
                    accepter_monster = data.get("monster_data", None)  # Accepter's monster
                    accepter_name = accepter_monster.get('name', 'None') if accepter_monster else 'None'
                    print(f"[SERVER] battle_accept: player {player_id} accepts from {challenger_id}, their monster: {accepter_name}")
                    if challenger_id >= 0:
                        print(f"[SERVER DEBUG] Preparing to send battle_start to challenger {challenger_id} and accepter {player_id}")
                        # Get challenger's monster from stored challenge
                        challenge = BATTLE_CHALLENGES.get_challenge(player_id)
                        challenger_monster = challenge.get("challenger_monster") if challenge else None
                        challenger_name = challenger_monster.get('name', 'None') if challenger_monster else 'None'
                        print(f"[SERVER] Retrieved stored challenger monster: {challenger_name}")
                        BATTLE_CHALLENGES.remove_challenge(player_id)
                        # Notify both players to start battle with opponent's monster data
                        start_msg_challenger = json.dumps({
                            "type": "battle_start",
                            "opponent_id": player_id,
                            "opponent_monster": accepter_monster  # Challenger receives accepter's monster
                        })
                        start_msg_accepter = json.dumps({
                            "type": "battle_start",
                            "opponent_id": challenger_id,
                            "opponent_monster": challenger_monster  # Accepter receives challenger's monster
                        })
                        print(f"[SERVER] Sending battle_start to challenger {challenger_id} with monster: {accepter_name}")
                        print(f"[SERVER] Sending battle_start to accepter {player_id} with monster: {challenger_name}")
                        async with PLAYER_WS_LOCK:
                            challenger_ws = PLAYER_WEBSOCKETS.get(challenger_id)
                            if challenger_ws:
                                try:
                                    await challenger_ws.send(start_msg_challenger)
                                except Exception as e:
                                    print(f"[SERVER] Failed to send to challenger: {e}")
                            # Also confirm to the accepter
                            try:
                                await websocket.send(start_msg_accepter)
                            except Exception as e:
                                print(f"[SERVER] Failed to send to accepter: {e}")
                
                elif msg_type == "battle_decline":
                    # Player declines a battle challenge
                    challenger_id = int(data.get("challenger_id", -1))
                    if challenger_id >= 0:
                        BATTLE_CHALLENGES.remove_challenge(player_id)
                        # Notify challenger that battle was declined
                        decline_msg = json.dumps({
                            "type": "battle_declined",
                            "by": player_id
                        })
                        async with PLAYER_WS_LOCK:
                            challenger_ws = PLAYER_WEBSOCKETS.get(challenger_id)
                            if challenger_ws:
                                try:
                                    await challenger_ws.send(decline_msg)
                                except Exception:
                                    pass
                    
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
            BATTLE_CHALLENGES.remove_challenge(player_id)
        async with PLAYER_WS_LOCK:
            if player_id in PLAYER_WEBSOCKETS:
                del PLAYER_WEBSOCKETS[player_id]
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