
import asyncio
import json
import random
import string
import time
from typing import Dict, Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

MAX_PLAYERS = 10

def gen_id(n=8):
    return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(n))

# Sample deck for "carta" (tema/palabra/clue). Replace/expand as needed.
CARD_DECK = [
    "Castillo",
    "Arena de batalla",
    "Torre",
    "Elixir",
    "Hechizo",
    "Mosquetera",
    "Arquera",
    "Gigante",
    "Montapuercos",
    "Dragón",
]

class Player:
    def __init__(self, pid: str, name: str):
        self.id = pid
        self.name = name
        self.alive = True
        self.role = "crew"      # or "impostor"
        self.ws: WebSocket | None = None
        self.card: str | None = None  # carta para tripulantes (la misma para todos)

    def to_public(self):
        return {
            "id": self.id,
            "name": self.name,
            "alive": self.alive,
        }

class Room:
    def __init__(self, code: str):
        self.code = code
        self.players: Dict[str, Player] = {}
        self.sockets: Dict[str, WebSocket] = {}
        self.state = "lobby"  # lobby | discussion | voting | ended
        self.impostor_ids: List[str] = []
        self.created_at = time.time()

        # Rondas/turnos
        self.turn_order: List[str] = []          # lista de ids
        self.current_turn_index: int = 0
        self.rounds_completed: int = 0
        self.require_two_rounds_before_first_vote = True
        self.first_vote_done = False

        # Votos
        self.votes: Dict[str, str | None] = {}   # voter_id -> target_id or None (skip)

        # Carta compartida para tripulación
        self.shared_card: str | None = None

        # Config
        self.impostor_count: int = 1

    # ---------- helpers ----------
    def alive_counts(self):
        crew = sum(1 for p in self.players.values() if p.alive and p.role == "crew")
        imps = sum(1 for p in self.players.values() if p.alive and p.role == "impostor")
        return crew, imps

    def check_win(self):
        if self.state not in ("discussion", "voting"):
            return None
        crew, imps = self.alive_counts()
        if imps == 0:
            self.state = "ended"
            return {"winner": "crew"}
        if imps >= crew:
            self.state = "ended"
            return {"winner": "impostor"}
        return None

    def advance_turn(self):
        # Avanza al siguiente jugador vivo; si cierra una vuelta, incrementa rondas
        if not self.turn_order:
            return
        n = len(self.turn_order)
        # Detectar si estamos al final y volver al inicio suma ronda
        next_index = (self.current_turn_index + 1) % n
        if next_index == 0:
            self.rounds_completed += 1
        # Saltar eliminados
        for _ in range(n):
            pid = self.turn_order[next_index]
            if self.players.get(pid) and self.players[pid].alive:
                self.current_turn_index = next_index
                break
            next_index = (next_index + 1) % n

    def sanitize_turn_order(self):
        # Quita ids inexistentes
        self.turn_order = [pid for pid in self.turn_order if pid in self.players]

    def public_state(self, for_id: str | None = None) -> Dict[str, Any]:
        # Estado visible para cliente
        data_players = [p.to_public() for p in self.players.values()]
        start_pid = self.turn_order[0] if self.turn_order else None
        current_pid = self.turn_order[self.current_turn_index] if self.turn_order else None
        can_vote = self.state in ("voting",) or (
            self.state == "discussion" and (
                (not self.require_two_rounds_before_first_vote) or
                (self.rounds_completed >= 2) or
                self.first_vote_done
            )
        )
        # Información privada (rol + carta) se envía por mensaje "secret"
        return {
            "type": "state",
            "room": self.code,
            "state": self.state,
            "players": data_players,
            "turn_order": self.turn_order,
            "start_player_id": start_pid,
            "current_turn_id": current_pid,
            "rounds_completed": self.rounds_completed,
            "can_open_voting": can_vote,
            "impostor_count": self.impostor_count,
            "max_players": MAX_PLAYERS,
        }

# -----------------------------
# FastAPI + WebSockets
# -----------------------------

app = FastAPI()
rooms: Dict[str, Room] = {}


@app.get("/play")
async def play_redirect():
    return HTMLResponse("""<!doctype html><meta charset='utf-8'>
    <script>location.href='/static/index.html'+location.search;</script>""")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    try:
        with open('static/landing.html', 'r', encoding='utf-8') as f:
            return HTMLResponse(f.read())
    except Exception:
        return HTMLResponse("<!doctype html><meta charset='utf-8'><title>Impostor Royale</title><p>Servidor activo. Abre <a href='/static/index.html'>/static/index.html</a> para jugar.</p>")

async def broadcast(room: Room):
    for pid, ws in list(room.sockets.items()):
        try:
            await ws.send_text(json.dumps(room.public_state(for_id=pid)))
        except Exception:
            pass

async def send_secret(player: Player):
    # Mensaje privado con rol y carta (si crew)
    data = {
        "type": "secret",
        "role": player.role,
        "card": player.card if (player.role == "crew") else None
    }
    try:
        if player.ws:
            await player.ws.send_text(json.dumps(data))
    except Exception:
        pass

# ------------- Handlers -------------

async def handle_join(ws: WebSocket, data: Dict[str, Any]):
    name = data.get("name", "Player")[:16]
    code = data.get("room", "").upper()
    if not code or len(code) > 8:
        code = "".join(random.choice(string.ascii_uppercase) for _ in range(4))

    room = rooms.get(code) or Room(code)
    rooms[code] = room

    # Max players in room (connected sockets)
    connected = [p for p in room.players.values() if p.ws is not None]
    if len(connected) >= MAX_PLAYERS:
        await ws.send_text(json.dumps({"type": "error", "message": "Sala llena (máximo 10)."}))
        return

    pid = gen_id()
    p = Player(pid, name)
    p.ws = ws
    room.players[pid] = p
    room.sockets[pid] = ws

    await ws.send_text(json.dumps({"type": "joined", "room": code, "player_id": pid}))
    await broadcast(room)

async def handle_start(ws: WebSocket, data: Dict[str, Any]):
    code = data.get("room", "").upper()
    impostor_count = int(data.get("impostors", 1))
    impostor_count = max(1, min(2, impostor_count))

    room = rooms.get(code)
    if not room:
        return
    if room.state != "lobby":
        return

    # mínimo 3 jugadores conectados
    connected = [p for p in room.players.values() if p.ws is not None]
    if len(connected) < 3:
        await ws.send_text(json.dumps({"type": "error", "message": "Se requieren mínimo 3 jugadores para iniciar."}))
        return

    # Roles
    alive_players = list(connected)
    for p in alive_players:
        p.role = "crew"
        p.alive = True
        p.card = None

    random.shuffle(alive_players)
    room.impostor_count = impostor_count
    room.impostor_ids = [p.id for p in alive_players[:impostor_count]]
    for pid in room.impostor_ids:
        room.players[pid].role = "impostor"

    # Carta compartida (crew)
    room.shared_card = random.choice(CARD_DECK)
    for p in room.players.values():
        if p.ws is None:  # omit disconnected
            continue
        if p.role == "crew":
            p.card = room.shared_card

    # Turnos: usar solo conectados para iniciar
    order = [p.id for p in connected]
    random.shuffle(order)
    room.turn_order = order
    room.current_turn_index = 0
    room.rounds_completed = 0
    room.first_vote_done = False
    room.votes.clear()

    # Estado
    room.state = "discussion"

    # Enviar secretos a cada jugador
    for p in connected:
        await send_secret(p)

    await broadcast(room)

async def handle_next_turn(ws: WebSocket, data: Dict[str, Any]):
    code = data.get("room", "").upper()
    room = rooms.get(code)
    if not room or room.state not in ("discussion",):
        return
    room.sanitize_turn_order()
    if not room.turn_order:
        return
    # Avanzar turno
    room.advance_turn()
    await broadcast(room)

async def handle_open_voting(ws: WebSocket, data: Dict[str, Any]):
    code = data.get("room", "").upper()
    room = rooms.get(code)
    if not room:
        return
    # Permitir votar solo si: después de 2 rondas o si ya hubo la primera votación
    if room.state != "discussion":
        return
    if room.require_two_rounds_before_first_vote and not room.first_vote_done and room.rounds_completed < 2:
        await ws.send_text(json.dumps({"type": "error", "message": "La primera votación solo se habilita tras 2 rondas completas."}))
        return
    room.state = "voting"
    room.votes.clear()
    await broadcast(room)

async def handle_vote(ws: WebSocket, data: Dict[str, Any]):
    code = data.get("room", "").upper()
    voter = data.get("player_id")
    target = data.get("target_id")  # None para saltar
    room = rooms.get(code)
    if not room or room.state != "voting":
        return
    if voter not in room.players or not room.players[voter].alive:
        return
    if target is not None and target not in room.players:
        return
    room.votes[voter] = target
    await broadcast(room)

async def finalize_voting(room: Room):
    # Conteo simple: mayoría elimina; empate = nadie sale
    tally: Dict[str, int] = {}
    for v in room.votes.values():
        if v is None:
            continue
        tally[v] = tally.get(v, 0) + 1
    eliminated_id = None
    if tally:
        max_votes = max(tally.values())
        top = [pid for pid, c in tally.items() if c == max_votes]
        if len(top) == 1:
            eliminated_id = top[0]
            if eliminated_id in room.players and room.players[eliminated_id].alive:
                room.players[eliminated_id].alive = False
    # Marcar que ya hubo primera votación
    if not room.first_vote_done:
        room.first_vote_done = True
    # Volver a discusión si no hay victoria
    win = room.check_win()
    if win:
        # Revelar quiénes eran impostores al terminar
        for ws in list(room.sockets.values()):
            try:
                await ws.send_text(json.dumps({"type": "end", "winner": win["winner"], "impostors": room.impostor_ids}))
            except Exception:
                pass
        return
    room.state = "discussion"
    room.votes.clear()
    await broadcast(room)

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    await websocket.accept()
    try:
        while True:
            text = await websocket.receive_text()
            try:
                data = json.loads(text)
            except Exception:
                await websocket.send_text(json.dumps({"type": "error", "message": "JSON inválido"}))
                continue

            msg_type = data.get("type")
            if msg_type == "join":
                await handle_join(websocket, data)
            elif msg_type == "start":
                await handle_start(websocket, data)
            elif msg_type == "next_turn":
                await handle_next_turn(websocket, data)
            elif msg_type == "open_voting":
                await handle_open_voting(websocket, data)
            elif msg_type == "vote":
                await handle_vote(websocket, data)
            elif msg_type == "finalize_voting":
                code = data.get("room", "").upper()
                room = rooms.get(code)
                if room and room.state == "voting":
                    await finalize_voting(room)
            else:
                await websocket.send_text(json.dumps({"type": "error", "message": "Tipo de mensaje no soportado"}))

    except WebSocketDisconnect:
        pass
    finally:
        # Cleanup: mark socket as disconnected
        for room in rooms.values():
            for pid, ws in list(room.sockets.items()):
                if ws is websocket:
                    room.sockets.pop(pid, None)
                    p = room.players.get(pid)
                    if p:
                        p.ws = None
                    break

# Broadcast heartbeat cada segundo
async def ticker():
    while True:
        await asyncio.sleep(1)
        for room in list(rooms.values()):
            try:
                await broadcast(room)
            except Exception:
                pass

@app.on_event("startup")
async def on_start():
    asyncio.create_task(ticker())
