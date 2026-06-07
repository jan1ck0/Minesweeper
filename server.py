import socket
import threading
import json
import uuid
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from dataclasses import dataclass, asdict
import random

from network import UDP_PORT, HTTP_PORT, TCP_PORT, DISCOVER_MSG, OFFER_PREFIX, send_msg, recv_msg
from engine import Difficulty, MinesweeperEngine, ScoreManager

DIFFICULTIES = {
    "Easy": Difficulty("Easy", 9, 9, 10),
    "Medium": Difficulty("Medium", 16, 16, 40),
    "Hard": Difficulty("Hard", 16, 30, 99),
}


@dataclass
class Player:
    id: str
    nickname: str
    color: str
    score: int
    stunned_until: float
    is_host: bool
    connected: bool


class Lobby:
    def __init__(self, lobby_id: str, difficulty_name: str):
        self.id = lobby_id
        self.diff_name = difficulty_name
        self.diff = DIFFICULTIES.get(difficulty_name, DIFFICULTIES["Easy"])

        self.state = "waiting"
        self.players: dict[str, Player] = {}
        self.sockets: dict[str, socket.socket] = {}

        self.rows = self.diff.rows
        self.cols = self.diff.cols
        self.mines_total = self.diff.mines
        self.mines = set()
        self.adj = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        self.revealed = [[False for _ in range(self.cols)] for _ in range(self.rows)]
        self.flags = {}

        self.first_click = True
        self.game_over = False
        self.won = False
        self.game_start_time = None
        self.game_duration = 0

        self.chat_log = []
        self.lock = threading.Lock()

    def get_neighbors(self, r: int, c: int):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.rows and 0 <= nc < self.cols:
                    yield nr, nc

    def _place_mines(self, safe_r: int, safe_c: int):
        forbidden = {(safe_r, safe_c)} | set(self.get_neighbors(safe_r, safe_c))
        candidates = [(r, c) for r in range(self.rows) for c in range(self.cols) if (r, c) not in forbidden]
        if len(candidates) < self.mines_total:
            forbidden = {(safe_r, safe_c)}
            candidates = [(r, c) for r in range(self.rows) for c in range(self.cols) if (r, c) not in forbidden]
        self.mines = set(random.sample(candidates, self.mines_total))

        for r in range(self.rows):
            for c in range(self.cols):
                if (r, c) in self.mines:
                    self.adj[r][c] = -1
                else:
                    self.adj[r][c] = sum((nr, nc) in self.mines for nr, nc in self.get_neighbors(r, c))

    def elapsed_seconds(self) -> int:
        if self.game_start_time is None:
            return 0
        if self.game_over:
            return int(self.game_duration)
        return int(time.time() - self.game_start_time)

    def to_dict(self) -> dict:
        """Returns the public state of the lobby, hiding unrevealed mine positions."""
        revealed_cells = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.revealed[r][c]:
                    revealed_cells.append([r, c, self.adj[r][c]])
                elif self.game_over and (r, c) in self.mines:
                    revealed_cells.append([r, c, -1])

        players_list = []
        now = time.time()
        for p in self.players.values():
            stunned_secs = max(0.0, p.stunned_until - now)
            players_list.append({
                "id": p.id,
                "nickname": p.nickname,
                "color": p.color,
                "score": p.score,
                "stunned_seconds": stunned_secs,
                "is_host": p.is_host,
                "connected": p.connected
            })

        players_list.sort(key=lambda x: x["score"], reverse=True)

        flags_list = [[r, c, pid] for (r, c), pid in self.flags.items()]

        return {
            "lobby_id": self.id,
            "difficulty": self.diff_name,
            "rows": self.rows,
            "cols": self.cols,
            "mines_total": self.mines_total,
            "state": self.state,
            "revealed_cells": revealed_cells,
            "flags": flags_list,
            "game_over": self.game_over,
            "won": self.won,
            "elapsed_seconds": self.elapsed_seconds(),
            "players": players_list,
            "chat": self.chat_log[-30:]
        }

    def broadcast_state(self):
        state = self.to_dict()
        msg = {"event": "state_update", "lobby": state}
        for player_id, sock in list(self.sockets.items()):
            if self.players[player_id].connected:
                success = send_msg(sock, msg)
                if not success:
                    print(f"Failed to send to player {player_id}, disconnecting them.")
                    self.players[player_id].connected = False

    def add_chat(self, sender: str, text: str):
        self.chat_log.append({"sender": sender, "text": text, "timestamp": time.time()})

    def check_win(self) -> bool:
        revealed_count = sum(1 for r in range(self.rows) for c in range(self.cols) if self.revealed[r][c])
        if revealed_count == self.rows * self.cols - self.mines_total:
            self.game_over = True
            self.won = True
            self.game_duration = time.time() - self.game_start_time
            self.state = "finished"

            ScoreManager.add_score(self.diff_name, int(self.game_duration))
            self.add_chat("System", f"Game Won in {int(self.game_duration)} seconds!")
            return True
        return False

    def reveal(self, player_id: str, r: int, c: int):
        if self.game_over or self.state != "playing":
            return
        player = self.players.get(player_id)
        if not player or player.stunned_until > time.time():
            return
        if (r, c) in self.flags or self.revealed[r][c]:
            return

        if self.first_click:
            self._place_mines(r, c)
            self.first_click = False
            self.game_start_time = time.time()

        if (r, c) in self.mines:
            player.score -= 10
            player.stunned_until = time.time() + 3.0
            self.revealed[r][c] = True
            self.add_chat("System", f"[!] {player.nickname} hit a mine (-10 pts, 3s stun)!")
            self.check_win()
            return

        revealed_cells = set()
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            if self.revealed[cr][cc] or (cr, cc) in self.flags or (cr, cc) in self.mines:
                continue
            self.revealed[cr][cc] = True
            revealed_cells.add((cr, cc))
            if self.adj[cr][cc] == 0:
                for nr, nc in self.get_neighbors(cr, cc):
                    if not self.revealed[nr][nc] and (nr, nc) not in self.mines:
                        stack.append((nr, nc))

        points = len(revealed_cells)
        player.score += points

        self.check_win()

    def toggle_flag(self, player_id: str, r: int, c: int):
        if self.game_over or self.state != "playing":
            return
        player = self.players.get(player_id)
        if not player or player.stunned_until > time.time():
            return
        if self.revealed[r][c]:
            return

        if (r, c) in self.flags:
            owner_id = self.flags[(r, c)]
            if owner_id == player_id:
                del self.flags[(r, c)]
                if (r, c) in self.mines:
                    player.score -= 5
                else:
                    player.score += 5
        else:
            self.flags[(r, c)] = player_id
            if (r, c) in self.mines:
                player.score += 5
            else:
                player.score -= 5

    def chord(self, player_id: str, r: int, c: int):
        if self.game_over or self.state != "playing" or self.first_click:
            return
        player = self.players.get(player_id)
        if not player or player.stunned_until > time.time():
            return
        if not self.revealed[r][c] or self.adj[r][c] <= 0:
            return

        n = self.adj[r][c]
        flagged_around = sum((nr, nc) in self.flags for nr, nc in self.get_neighbors(r, c))
        if flagged_around != n:
            return

        revealed_safe = 0
        hit_mines = 0

        for nr, nc in list(self.get_neighbors(r, c)):
            if (nr, nc) in self.flags or self.revealed[nr][nc]:
                continue
            if (nr, nc) in self.mines:
                hit_mines += 1
                self.revealed[nr][nc] = True
            else:
                stack = [(nr, nc)]
                while stack:
                    cr, cc = stack.pop()
                    if self.revealed[cr][cc] or (cr, cc) in self.flags or (cr, cc) in self.mines:
                        continue
                    self.revealed[cr][cc] = True
                    revealed_safe += 1
                    if self.adj[cr][cc] == 0:
                        for nnr, nnc in self.get_neighbors(cr, cc):
                            if not self.revealed[nnr][nnc] and (nnr, nnc) not in self.mines:
                                stack.append((nnr, nnc))

        if hit_mines > 0:
            player.score -= 10 * hit_mines
            player.stunned_until = time.time() + 3.0
            self.add_chat("System",
                          f"[!] {player.nickname} hit {hit_mines} mine(s) during chord (-{10 * hit_mines} pts, 3s stun)!")

        if revealed_safe > 0:
            player.score += revealed_safe

        self.check_win()

    def restart(self):
        self.state = "playing"
        self.first_click = True
        self.game_over = False
        self.won = False
        self.game_start_time = None
        self.game_duration = 0
        self.mines.clear()
        self.flags.clear()
        self.adj = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        self.revealed = [[False for _ in range(self.cols)] for _ in range(self.rows)]
        for p in self.players.values():
            p.score = 0
            p.stunned_until = 0
        self.add_chat("System", "Game restarted! Play when ready.")


lobbies: dict[str, Lobby] = {}
lobbies_lock = threading.Lock()

PLAYER_COLORS = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"]


def get_random_color():
    return random.choice(PLAYER_COLORS)


class MinesweeperHTTPHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/lobbies":
            with lobbies_lock:
                lobby_list = []
                for lobby in lobbies.values():
                    with lobby.lock:
                        lobby_list.append({
                            "lobby_id": lobby.id,
                            "difficulty": lobby.diff_name,
                            "player_count": sum(1 for p in lobby.players.values() if p.connected),
                            "state": lobby.state,
                            "rows": lobby.rows,
                            "cols": lobby.cols,
                        })
            self.send_json(200, lobby_list)
        elif path == "/api/highscores":
            scores = ScoreManager.load()
            self.send_json(200, scores)
        else:
            self.send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/lobbies":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            try:
                body = json.loads(post_data.decode("utf-8"))
            except Exception:
                body = {}

            difficulty_name = body.get("difficulty", "Easy")
            if difficulty_name not in DIFFICULTIES:
                difficulty_name = "Easy"

            lobby_id = str(uuid.uuid4())[:8]
            lobby = Lobby(lobby_id, difficulty_name)

            with lobbies_lock:
                lobbies[lobby_id] = lobby

            self.send_json(201, {
                "lobby_id": lobby_id,
                "difficulty": difficulty_name,
                "rows": lobby.rows,
                "cols": lobby.cols,
                "mines": lobby.mines_total,
            })
        else:
            self.send_json(404, {"error": "Not Found"})


def handle_tcp_client(client_sock: socket.socket, addr):
    print(f"[TCP] New connection from {addr}")
    player_id = None
    lobby_id = None

    try:
        while True:
            msg = recv_msg(client_sock)
            if not msg:
                break

            action = msg.get("action")

            if action == "join":
                req_lobby_id = msg.get("lobby_id")
                nickname = msg.get("nickname", "Anonymous")[:12]

                with lobbies_lock:
                    lobby = lobbies.get(req_lobby_id)

                if not lobby:
                    send_msg(client_sock, {"error": "Lobby not found"})
                    continue

                with lobby.lock:
                    player_id = str(uuid.uuid4())[:6]
                    lobby_id = req_lobby_id

                    is_host = (sum(1 for p in lobby.players.values() if p.connected) == 0)
                    color = get_random_color()
                    existing_colors = [p.color for p in lobby.players.values() if p.connected]
                    for col in PLAYER_COLORS:
                        if col not in existing_colors:
                            color = col
                            break

                    player = Player(
                        id=player_id,
                        nickname=nickname,
                        color=color,
                        score=0,
                        stunned_until=0.0,
                        is_host=is_host,
                        connected=True
                    )
                    lobby.players[player_id] = player
                    lobby.sockets[player_id] = client_sock

                    lobby.add_chat("System", f"[+] {nickname} joined the game!")

                    send_msg(client_sock, {"event": "join_success", "player_id": player_id})
                    lobby.broadcast_state()

            elif action == "leave":
                break

            elif action == "chat":
                if not lobby_id or not player_id:
                    continue
                with lobbies_lock:
                    lobby = lobbies.get(lobby_id)
                if lobby:
                    with lobby.lock:
                        player = lobby.players.get(player_id)
                        chat_text = msg.get("message", "").strip()[:80]
                        if player and chat_text:
                            lobby.add_chat(player.nickname, chat_text)
                            lobby.broadcast_state()

            elif action == "start_game":
                if not lobby_id or not player_id:
                    continue
                with lobbies_lock:
                    lobby = lobbies.get(lobby_id)
                if lobby:
                    with lobby.lock:
                        player = lobby.players.get(player_id)
                        if player and player.is_host:
                            lobby.state = "playing"
                            lobby.first_click = True
                            lobby.game_over = False
                            lobby.won = False
                            lobby.mines.clear()
                            lobby.flags.clear()
                            lobby.revealed = [[False for _ in range(lobby.cols)] for _ in range(lobby.rows)]
                            lobby.adj = [[0 for _ in range(lobby.cols)] for _ in range(lobby.rows)]
                            for p in lobby.players.values():
                                p.score = 0
                                p.stunned_until = 0.0
                            lobby.add_chat("System", "🎮 Game started! Reveal tiles to earn points.")
                            lobby.broadcast_state()

            elif action in ("reveal", "flag", "chord"):
                if not lobby_id or not player_id:
                    continue
                r = msg.get("row")
                c = msg.get("col")
                if r is None or c is None:
                    continue

                with lobbies_lock:
                    lobby = lobbies.get(lobby_id)
                if lobby:
                    with lobby.lock:
                        if 0 <= r < lobby.rows and 0 <= c < lobby.cols:
                            if action == "reveal":
                                lobby.reveal(player_id, r, c)
                            elif action == "flag":
                                lobby.toggle_flag(player_id, r, c)
                            elif action == "chord":
                                lobby.chord(player_id, r, c)
                            lobby.broadcast_state()

            elif action == "restart":
                if not lobby_id or not player_id:
                    continue
                with lobbies_lock:
                    lobby = lobbies.get(lobby_id)
                if lobby:
                    with lobby.lock:
                        player = lobby.players.get(player_id)
                        if player and lobby.game_over:
                            lobby.restart()
                            lobby.broadcast_state()

    except ConnectionError:
        pass
    finally:
        client_sock.close()
        print(f"[TCP] Connection closed with {addr}")

        if lobby_id and player_id:
            with lobbies_lock:
                lobby = lobbies.get(lobby_id)
            if lobby:
                with lobby.lock:
                    player = lobby.players.get(player_id)
                    if player:
                        player.connected = False
                        lobby.add_chat("System", f"[-] {player.nickname} disconnected.")
                        if player.is_host:
                            player.is_host = False
                            active_players = [p for p in lobby.players.values() if p.connected]
                            if active_players:
                                active_players[0].is_host = True
                                lobby.add_chat("System", f"[Host] {active_players[0].nickname} is now the host.")

                        if player_id in lobby.sockets:
                            del lobby.sockets[player_id]

                        active_count = sum(1 for p in lobby.players.values() if p.connected)
                        if active_count == 0:
                            print(f"[Lobby] Lobby {lobby_id} is now empty. Deleting lobby.")
                            with lobbies_lock:
                                if lobby_id in lobbies:
                                    del lobbies[lobby_id]
                        else:
                            lobby.broadcast_state()


def run_udp_discovery_server(server_name: str):
    print(f"[UDP] Server starting discovery on port {UDP_PORT}...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", UDP_PORT))
    except Exception as e:
        print(f"[UDP] Failed to bind to port {UDP_PORT}: {e}")
        return

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if data == DISCOVER_MSG:
                response = f"{OFFER_PREFIX}:{server_name}:{TCP_PORT}:{HTTP_PORT}"
                sock.sendto(response.encode("utf-8"), addr)
        except Exception as e:
            print(f"[UDP] Error: {e}")
            break


def run_http_server():
    server = HTTPServer(("", HTTP_PORT), MinesweeperHTTPHandler)
    print(f"[HTTP] REST API running on port {HTTP_PORT}...")
    server.serve_forever()


def run_tcp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", TCP_PORT))
    sock.listen(10)
    print(f"[TCP] Server listening on port {TCP_PORT}...")

    while True:
        try:
            client_sock, addr = sock.accept()
            t = threading.Thread(target=handle_tcp_client, args=(client_sock, addr), daemon=True)
            t.start()
        except Exception as e:
            print(f"[TCP] Accept error: {e}")
            break


def start_all_servers(server_name="Local Minesweeper Server"):
    udp_thread = threading.Thread(target=run_udp_discovery_server, args=(server_name,), daemon=True)
    udp_thread.start()

    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    run_tcp_server()


if __name__ == "__main__":
    import sys

    name = "Central Server"
    if len(sys.argv) > 1:
        name = sys.argv[1]
    try:
        start_all_servers(name)
    except KeyboardInterrupt:
        print("\n[Server] Shutting down.")