import math
import time
import socket
import threading
import json
import random
import urllib.request
import urllib.parse
import pygame

from engine import Difficulty, MinesweeperEngine, ScoreManager
from network import UDP_PORT, HTTP_PORT, TCP_PORT, DISCOVER_MSG, OFFER_PREFIX, send_msg, recv_msg
import server


class _Button:
    def __init__(self, rect: pygame.Rect, text: str, font: pygame.font.Font):
        self.rect = rect
        self.text = text
        self.font = font

    def draw(self, screen: pygame.Surface, *, bg: str, fg: str, border: str, hover: bool):
        color = pygame.Color(bg)
        if hover:
            color = color.lerp(pygame.Color("#ffffff"), 0.08)
        pygame.draw.rect(screen, color, self.rect, border_radius=8)
        pygame.draw.rect(screen, pygame.Color(border), self.rect, width=1, border_radius=8)

        surf = self.font.render(self.text, True, pygame.Color(fg))
        screen.blit(surf, surf.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.rect.collidepoint(pos)


class _Overlay:
    def __init__(self, kind: str, title: str, lines: list[str]):
        self.kind = kind
        self.title = title
        self.lines = lines
        self.closed = False
        self.scroll = 0
        self._max_scroll = 0
        self._visible_lines = 0

    def layout(self, screen_size: tuple[int, int]):
        w, h = screen_size
        box_w = min(520, w - 40)
        box_h = min(420, h - 40)
        box = pygame.Rect(0, 0, box_w, box_h)
        box.center = (w // 2, h // 2)

        ok_rect = pygame.Rect(0, 0, 110, 40)
        ok_rect.bottomright = (box.right - 18, box.bottom - 18)
        return box, ok_rect

    def handle_event(self, e: pygame.event.Event, ok_rect: pygame.Rect):
        if e.type == pygame.KEYDOWN and e.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.closed = True
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_UP:
                self.scroll = max(0, self.scroll - 1)
            elif e.key == pygame.K_DOWN:
                self.scroll = min(self._max_scroll, self.scroll + 1)
            elif e.key == pygame.K_PAGEUP:
                step = max(1, self._visible_lines)
                self.scroll = max(0, self.scroll - step)
            elif e.key == pygame.K_PAGEDOWN:
                step = max(1, self._visible_lines)
                self.scroll = min(self._max_scroll, self.scroll + step)
            elif e.key == pygame.K_HOME:
                self.scroll = 0
            elif e.key == pygame.K_END:
                self.scroll = self._max_scroll

        if e.type == pygame.MOUSEWHEEL:
            step = 3
            self.scroll = max(0, min(self._max_scroll, self.scroll - e.y * step))

        if e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 4:
                self.scroll = max(0, self.scroll - 3)
            elif e.button == 5:
                self.scroll = min(self._max_scroll, self.scroll + 3)
        if e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            if ok_rect.collidepoint(e.pos):
                self.closed = True

    def draw(
        self,
        screen: pygame.Surface,
        *,
        palette: dict,
        title_font: pygame.font.Font,
        text_font: pygame.font.Font,
        ok_font: pygame.font.Font,
    ) -> pygame.Rect:
        w, h = screen.get_size()
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 140))
        screen.blit(dim, (0, 0))

        box, ok_rect = self.layout((w, h))

        pygame.draw.rect(screen, pygame.Color(palette["panel"]), box, border_radius=14)
        pygame.draw.rect(screen, pygame.Color(palette["panel_edge"]), box, width=1, border_radius=14)

        y = box.y + 18
        title_surf = title_font.render(self.title, True, pygame.Color(palette["text"]))
        screen.blit(title_surf, (box.x + 18, y))
        y += title_surf.get_height() + 14

        line_h = text_font.get_linesize()
        content_left = box.x + 22
        content_right = box.right - 22
        content_top = y
        content_bottom = ok_rect.top - 14
        content_h = max(1, content_bottom - content_top)

        self._visible_lines = max(1, content_h // max(1, line_h))
        self._max_scroll = max(0, len(self.lines) - self._visible_lines)
        self.scroll = max(0, min(self._max_scroll, self.scroll))

        show_scrollbar = self._max_scroll > 0
        bar_w = 8
        if show_scrollbar:
            content_right -= bar_w + 10

        start = self.scroll
        end = min(len(self.lines), start + self._visible_lines)
        draw_y = content_top
        for line in self.lines[start:end]:
            surf = text_font.render(line, True, pygame.Color(palette["text"]))
            screen.blit(surf, (content_left, draw_y))
            draw_y += line_h

        if show_scrollbar:
            track = pygame.Rect(box.right - 22 - bar_w, content_top, bar_w, content_h)
            pygame.draw.rect(screen, pygame.Color(palette["panel_edge"]), track, border_radius=6)

            total = max(1, len(self.lines))
            visible = max(1, self._visible_lines)
            thumb_h = max(24, int(track.height * (visible / total)))
            if self._max_scroll == 0:
                thumb_y = track.y
            else:
                thumb_y = track.y + int((track.height - thumb_h) * (self.scroll / self._max_scroll))
            thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
            pygame.draw.rect(screen, pygame.Color(palette["tile_hidden_hover"]), thumb, border_radius=6)

        is_hover = ok_rect.collidepoint(pygame.mouse.get_pos())
        ok_bg = pygame.Color(palette["panel_edge"])
        if is_hover:
            ok_bg = ok_bg.lerp(pygame.Color("#ffffff"), 0.08)
        pygame.draw.rect(screen, ok_bg, ok_rect, border_radius=10)
        ok_surf = ok_font.render("OK", True, pygame.Color(palette["text"]))
        screen.blit(ok_surf, ok_surf.get_rect(center=ok_rect.center))

        return ok_rect


class MinesweeperPygameApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Minesweeper Multiplayer")

        self.palette = {
            "bg": "#0b1220",
            "panel": "#0f172a",
            "panel_edge": "#1f2937",
            "text": "#e5e7eb",
            "subtext": "#cbd5e1",
            "tile_hidden": "#334155",
            "tile_hidden_hover": "#3f516d",
            "tile_hidden_pressed": "#2b3a50",
            "tile_revealed": "#e5e7eb",
            "tile_revealed_edge": "#cbd5e1",
            "mine": "#111827",
            "mine_bg": "#fee2e2",
            "mine_bg_trigger": "#fecaca",
            "flag": "#ef4444",
            "wrong": "#ef4444",
            "shadow": "#020617",
        }

        self.difficulties = [
            Difficulty("Easy", 9, 9, 10),
            Difficulty("Medium", 16, 16, 40),
            Difficulty("Hard", 16, 30, 99),
        ]
        self.difficulty_index = 0

        self.tile = 26
        self.pad = 10
        self.panel_h = 64

        self.app_state = "menu"
        self.nickname = f"Player{random.randint(100, 999)}"
        self.editing_nick = False
        
        self.discovered_servers = []
        self.selected_server = None  # {ip, name, tcp_port, http_port}
        self.manual_ip = "127.0.0.1"
        self.editing_ip = False
        
        self.discovered_lobbies = []
        self.tcp_sock = None
        self.tcp_connected = False
        self.lobby_state = None  # Receives full dict update from server
        self.player_id = None
        self.chat_input = ""
        self.editing_chat = False

        self.engine: MinesweeperEngine | None = None

        self._start_time: float | None = None
        self._mouse_down = {1: False, 2: False, 3: False}
        self._hover_cell: tuple[int, int] | None = None
        self._pressed_cells: set[tuple[int, int]] = set()
        self._smiley_state = "idle"

        self._overlay: _Overlay | None = None
        self._overlay_ok_rect: pygame.Rect | None = None

        self._smiley_rect_cache: pygame.Rect | None = None
        self._mine_rect_cache: pygame.Rect | None = None
        self._timer_rect_cache: pygame.Rect | None = None

        self.clock = pygame.time.Clock()

        # Fonts
        self.font_ui = pygame.font.SysFont("segoeui", 16) or pygame.font.Font(None, 16)
        self.font_counter = pygame.font.SysFont("consolas", 24, bold=True) or pygame.font.Font(None, 24)
        self.font_num = pygame.font.SysFont("segoeui", 14, bold=True) or pygame.font.Font(None, 14)
        self.font_title = pygame.font.SysFont("segoeui", 22, bold=True) or pygame.font.Font(None, 22)
        self.font_title_large = pygame.font.SysFont("segoeui", 32, bold=True) or pygame.font.Font(None, 32)
        self.font_chat = pygame.font.SysFont("segoeui", 12) or pygame.font.Font(None, 12)

        self.screen = pygame.display.set_mode((640, 480))
        self._layout_static()

    def _layout_static(self):
        panel_y = self.pad
        panel_x = self.pad
        btn_h = 34

        self.diff_buttons: list[_Button] = []
        x = panel_x
        for d in self.difficulties:
            rect = pygame.Rect(x, panel_y + 14, 110, btn_h)
            self.diff_buttons.append(_Button(rect, d.name, self.font_ui))
            x += rect.width + 10

        self.highscores_btn = _Button(pygame.Rect(x, panel_y + 14, 130, btn_h), "Highscores", self.font_ui)

    def _layout_panel_dynamic(self):
        w, _ = self.screen.get_size()
        inner = pygame.Rect(self.pad, self.pad, w - 2 * self.pad, self.panel_h)

        left_pad = 14
        gap = 8
        btn_h = 34
        btn_y = inner.y + (inner.height - btn_h) // 2

        mine_w, mine_h = 84, 36
        timer_w, timer_h = 84, 36

        x = inner.x + left_pad

        diff_w = 96
        for b in self.diff_buttons:
            b.rect = pygame.Rect(x, btn_y, diff_w, btn_h)
            x = b.rect.right + gap

        self.highscores_btn.rect = pygame.Rect(x, btn_y, 120, btn_h)
        x = self.highscores_btn.rect.right + 16

        mine_rect = pygame.Rect(x, inner.y + (inner.height - mine_h) // 2, mine_w, mine_h)
        x = mine_rect.right + 12

        smiley_rect = pygame.Rect(x, inner.y + (inner.height - 44) // 2, 44, 44)
        x = smiley_rect.right + 12

        timer_rect = pygame.Rect(x, inner.y + (inner.height - timer_h) // 2, timer_w, timer_h)

        max_right = inner.right - left_pad

        overflow = max(0, timer_rect.right - max_right)
        if overflow:
            mine_rect.x -= overflow
            smiley_rect.x -= overflow
            timer_rect.x -= overflow

        self._mine_rect_cache = mine_rect
        self._smiley_rect_cache = smiley_rect
        self._timer_rect_cache = timer_rect

    def _board_origin(self):
        if self.app_state == "playing_sp":
            if self.engine is None:
                return self.pad, self.panel_h + self.pad
            w, _ = self.screen.get_size()
            board_w = self.engine.cols * self.tile
            x = max(self.pad, (w - board_w) // 2)
            return x, self.panel_h + self.pad
        else:
            # Multiplayer
            if self.lobby_state is None:
                return self.pad, self.panel_h + self.pad
            return self.pad, self.panel_h + self.pad

    def _window_size_for_engine(self):
        if self.engine is None:
            return 640, 480
        board_w = self.engine.cols * self.tile + 2 * self.pad
        board_h = self.panel_h + self.engine.rows * self.tile + 2 * self.pad
        min_w = 760
        min_h = 480
        return max(min_w, board_w), max(min_h, board_h)

    def _window_size_for_mp(self):
        if self.lobby_state is None:
            return 800, 500
        board_w = self.lobby_state["cols"] * self.tile
        board_h = self.lobby_state["rows"] * self.tile
        # 320px for sidebar, plus padding
        width = max(800, board_w + 360)
        height = max(520, self.panel_h + board_h + 30)
        return width, height

    def new_game(self, difficulty: Difficulty):
        self.app_state = "playing_sp"
        self.engine = MinesweeperEngine(difficulty.rows, difficulty.cols, difficulty.mines)
        self._start_time = None
        self._smiley_state = "idle"
        self._mouse_down = {1: False, 2: False, 3: False}
        self._hover_cell = None
        self._pressed_cells = set()
        self._overlay = None
        self._overlay_ok_rect = None

        self._smiley_rect_cache = None
        self._mine_rect_cache = None
        self._timer_rect_cache = None

        self.screen = pygame.display.set_mode(self._window_size_for_engine())

    def _elapsed_seconds(self) -> int:
        if self.app_state == "playing_sp":
            if self._start_time is None:
                return 0
            return max(0, min(999, int(time.time() - self._start_time)))
        else:
            if self.lobby_state is None:
                return 0
            return self.lobby_state.get("elapsed_seconds", 0)

    def _ensure_timer_started(self):
        if self._start_time is None:
            self._start_time = time.time()

    def _mine_counter_text(self) -> str:
        if self.app_state == "playing_sp":
            if self.engine is None:
                return "000"
            left = self.engine.mines_total - len(self.engine.flags)
        else:
            if self.lobby_state is None:
                return "000"
            left = self.lobby_state["mines_total"] - len(self.lobby_state["flags"])

        left = max(-99, min(999, left))
        sign = "-" if left < 0 else ""
        return f"{sign}{abs(left):03d}"[-3:]

    def _cell_from_pos(self, pos):
        ox, oy = self._board_origin()
        x, y = pos
        x -= ox
        y -= oy
        if x < 0 or y < 0:
            return None
        c = x // self.tile
        r = y // self.tile
        
        if self.app_state == "playing_sp" and self.engine:
            if 0 <= r < self.engine.rows and 0 <= c < self.engine.cols:
                return int(r), int(c)
        elif self.app_state == "playing_mp" and self.lobby_state:
            if 0 <= r < self.lobby_state["rows"] and 0 <= c < self.lobby_state["cols"]:
                return int(r), int(c)
        return None

    def _num_color(self, n: int) -> str:
        return {
            1: "#2563eb",
            2: "#16a34a",
            3: "#dc2626",
            4: "#7c3aed",
            5: "#b45309",
            6: "#0f766e",
            7: "#111827",
            8: "#374151",
        }.get(n, self.palette["mine"])

    def _smiley_rect(self):
        if self._smiley_rect_cache is None:
            self._layout_panel_dynamic()
        return self._smiley_rect_cache

    def _mine_counter_rect(self):
        if self._mine_rect_cache is None:
            self._layout_panel_dynamic()
        return self._mine_rect_cache

    def _timer_rect(self):
        if self._timer_rect_cache is None:
            self._layout_panel_dynamic()
        return self._timer_rect_cache

    def _open_highscores(self):
        lines: list[str] = ["Top 15 best times", ""]
        for diff in self.difficulties:
            scores = ScoreManager.get_top_scores(diff.name)
            lines.append(f"{diff.name}:")
            if not scores:
                lines.append("  No scores yet")
            else:
                for i, s in enumerate(scores[:15], start=1):
                    lines.append(f"  {i:>2}. {s} s")
            lines.append("")
        self._overlay = _Overlay("highscores", "Highscores", lines)

    def _show_message(self, title: str, message: str):
        self._overlay = _Overlay("message", title, [message])

    def trigger_udp_discovery(self):
        self.discovered_servers = []
        
        def run_discover():
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0.8)
            try:
                sock.sendto(DISCOVER_MSG, ("255.255.255.255", UDP_PORT))
            except Exception:
                pass
            
            start = time.time()
            servers = []
            while time.time() - start < 0.8:
                try:
                    data, addr = sock.recvfrom(1024)
                    msg = data.decode("utf-8")
                    if msg.startswith(OFFER_PREFIX):
                        parts = msg.split(":")
                        if len(parts) >= 4:
                            srv = {
                                "ip": addr[0],
                                "name": parts[1],
                                "tcp_port": int(parts[2]),
                                "http_port": int(parts[3]),
                            }
                            # Deduplicate
                            if srv["ip"] not in [s["ip"] for s in servers]:
                                servers.append(srv)
                    break
                except Exception:
                    break
            self.discovered_servers = servers

        t = threading.Thread(target=run_discover, daemon=True)
        t.start()

    def fetch_lobbies_via_http(self):
        if not self.selected_server:
            return
        ip = self.selected_server["ip"]
        port = self.selected_server["http_port"]
        url = f"http://{ip}:{port}/api/lobbies"
        
        def run_fetch():
            try:
                with urllib.request.urlopen(url, timeout=1.0) as resp:
                    if resp.status == 200:
                        self.discovered_lobbies = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"Failed to fetch lobbies: {e}")
                self.discovered_lobbies = []

        t = threading.Thread(target=run_fetch, daemon=True)
        t.start()

    def create_lobby_via_http(self, difficulty_name):
        if not self.selected_server:
            return
        ip = self.selected_server["ip"]
        port = self.selected_server["http_port"]
        url = f"http://{ip}:{port}/api/lobbies"
        
        data = json.dumps({"difficulty": difficulty_name}).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        
        try:
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status in (200, 201):
                    res = json.loads(resp.read().decode("utf-8"))
                    lobby_id = res.get("lobby_id")
                    if lobby_id:
                        self.join_lobby_via_tcp(lobby_id)
        except Exception as e:
            print(f"Failed to create lobby: {e}")

    def join_lobby_via_tcp(self, lobby_id):
        self.disconnect_tcp()

        ip = self.selected_server["ip"]
        port = self.selected_server["tcp_port"]
        
        self.tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_sock.settimeout(3.0)
        
        try:
            self.tcp_sock.connect((ip, port))
            self.tcp_sock.settimeout(None)
            self.tcp_connected = True
            
            send_msg(self.tcp_sock, {
                "action": "join",
                "lobby_id": lobby_id,
                "nickname": self.nickname
            })
            
            t = threading.Thread(target=self._tcp_recv_loop, daemon=True)
            t.start()
            
            self.app_state = "playing_mp"
        except Exception as e:
            print(f"Failed to connect TCP: {e}")
            self.disconnect_tcp()
            self._show_message("Error", "Could not connect to lobby.")

    def _tcp_recv_loop(self):
        while self.tcp_connected:
            try:
                msg = recv_msg(self.tcp_sock)
                if not msg:
                    break
                event = msg.get("event")
                if event == "join_success":
                    self.player_id = msg.get("player_id")
                elif event == "state_update":
                    self.lobby_state = msg.get("lobby")
            except Exception as e:
                print(f"TCP connection lost: {e}")
                break
        
        self.disconnect_tcp()

    def disconnect_tcp(self):
        self.tcp_connected = False
        if self.tcp_sock:
            try:
                send_msg(self.tcp_sock, {"action": "leave"})
                self.tcp_sock.close()
            except Exception:
                pass
            self.tcp_sock = None
        self.lobby_state = None
        self.player_id = None
        
        if self.app_state in ("playing_mp",):
            self.app_state = "lobby_room"
            pygame.display.set_mode((640, 480))

    def host_local_server(self):
        def run_srv():
            try:
                server.start_all_servers("Local Host")
            except Exception:
                pass
        t = threading.Thread(target=run_srv, daemon=True)
        t.start()
        
        time.sleep(0.2)  # Give server a moment to start
        self.selected_server = {
            "ip": "127.0.0.1",
            "name": "Local Host",
            "tcp_port": TCP_PORT,
            "http_port": HTTP_PORT
        }
        self.app_state = "lobby_room"
        self.fetch_lobbies_via_http()

    def _handle_board_mouse_down(self, button: int, pos):
        if self.app_state == "playing_sp":
            if self.engine is None or self.engine.game_over:
                return
            self._mouse_down[button] = True
            cell = self._cell_from_pos(pos)
            self._pressed_cells = set()
            if cell is None:
                return
            r, c = cell
            chord_intent = (button == 2) or (self._mouse_down[1] and self._mouse_down[3])
            if chord_intent:
                self._pressed_cells = set(self.engine.neighbors(r, c))
            else:
                self._pressed_cells = {(r, c)}
        else:
            if not self.lobby_state or self.lobby_state["game_over"]:
                return
            
            # Check if local player is stunned
            me = next((p for p in self.lobby_state["players"] if p["id"] == self.player_id), None)
            if me and me["stunned_seconds"] > 0:
                return

            self._mouse_down[button] = True
            cell = self._cell_from_pos(pos)
            self._pressed_cells = set()
            if cell is None:
                return
            r, c = cell
            chord_intent = (button == 2) or (self._mouse_down[1] and self._mouse_down[3])
            if chord_intent:
                self._pressed_cells = set(self.get_neighbors_mp(r, c))
            else:
                self._pressed_cells = {(r, c)}

    def get_neighbors_mp(self, r: int, c: int):
        rows = self.lobby_state["rows"]
        cols = self.lobby_state["cols"]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    yield nr, nc

    def _handle_board_mouse_up(self, button: int, pos):
        if self.app_state == "playing_sp":
            if self.engine is None:
                return
            chord_intent = False
            if button == 2:
                chord_intent = True
            elif button in (1, 3):
                other = 3 if button == 1 else 1
                chord_intent = self._mouse_down.get(other, False)

            self._mouse_down[button] = False
            cell = self._cell_from_pos(pos)
            action = None

            if cell is not None and not self.engine.game_over:
                r, c = cell
                if button == 3:
                    self.engine.toggle_flag(r, c)
                else:
                    action = self.engine.chord(r, c) if chord_intent else self.engine.reveal(r, c)
                    if action is not None and action.get("type") != "noop" and self._start_time is None and not self.engine.first_click:
                        self._ensure_timer_started()

            self._pressed_cells = set()

            if action is not None:
                if action.get("type") == "boom":
                    self._smiley_state = "lose"
                    self._show_message("Minesweeper", "Boom! You hit a mine.")
                elif action.get("type") == "win":
                    elapsed = self._elapsed_seconds()
                    diff_name = self.difficulties[self.difficulty_index].name
                    for d in self.difficulties:
                        if d.rows == self.engine.rows and d.cols == self.engine.cols and d.mines == self.engine.mines_total:
                            diff_name = d.name
                            break
                    ScoreManager.add_score(diff_name, elapsed)

                    self.engine.flags = set(self.engine.mines)
                    self._smiley_state = "win"
                    self._show_message("Minesweeper", "You win!")
        else:
            if not self.lobby_state or not self.tcp_connected:
                return
            
            # Check if local player is stunned
            me = next((p for p in self.lobby_state["players"] if p["id"] == self.player_id), None)
            if me and me["stunned_seconds"] > 0:
                self._pressed_cells = set()
                self._mouse_down[button] = False
                return

            chord_intent = False
            if button == 2:
                chord_intent = True
            elif button in (1, 3):
                other = 3 if button == 1 else 1
                chord_intent = self._mouse_down.get(other, False)

            self._mouse_down[button] = False
            cell = self._cell_from_pos(pos)

            if cell is not None and not self.lobby_state["game_over"]:
                r, c = cell
                if button == 3:
                    send_msg(self.tcp_sock, {"action": "flag", "row": r, "col": c})
                else:
                    if chord_intent:
                        send_msg(self.tcp_sock, {"action": "chord", "row": r, "col": c})
                    else:
                        send_msg(self.tcp_sock, {"action": "reveal", "row": r, "col": c})

            self._pressed_cells = set()

    def _draw_menu(self):
        self.screen.fill(pygame.Color(self.palette["bg"]))
        w, h = self.screen.get_size()
        
        title = self.font_title_large.render("MINESWEEPER", True, pygame.Color(self.palette["text"]))
        self.screen.blit(title, title.get_rect(center=(w // 2, 80)))
        
        sub = self.font_ui.render("Multiplayer Cooperative & Competitive", True, pygame.Color(self.palette["subtext"]))
        self.screen.blit(sub, sub.get_rect(center=(w // 2, 120)))
        
        nick_lbl = self.font_ui.render("Your Nickname (click to edit):", True, pygame.Color(self.palette["subtext"]))
        self.screen.blit(nick_lbl, (w // 2 - 130, 160))
        
        nick_box = pygame.Rect(w // 2 - 130, 185, 260, 36)
        box_bg = self.palette["tile_hidden_pressed"] if self.editing_nick else self.palette["panel"]
        border_color = "#3b82f6" if self.editing_nick else self.palette["panel_edge"]
        pygame.draw.rect(self.screen, pygame.Color(box_bg), nick_box, border_radius=8)
        pygame.draw.rect(self.screen, pygame.Color(border_color), nick_box, width=2, border_radius=8)
        
        nick_txt = self.font_ui.render(self.nickname, True, pygame.Color(self.palette["text"]))
        self.screen.blit(nick_txt, nick_txt.get_rect(center=nick_box.center))
        
        mouse = pygame.mouse.get_pos()
        btn_y = 250
        btn_w, btn_h = 260, 42
        
        self.menu_sp_btn = _Button(pygame.Rect(w // 2 - 130, btn_y, btn_w, btn_h), "Singleplayer Mode", self.font_ui)
        self.menu_mp_btn = _Button(pygame.Rect(w // 2 - 130, btn_y + 50, btn_w, btn_h), "Connect to Server", self.font_ui)
        self.menu_host_btn = _Button(pygame.Rect(w // 2 - 130, btn_y + 100, btn_w, btn_h), "Host Local Server", self.font_ui)
        self.menu_scores_btn = _Button(pygame.Rect(w // 2 - 130, btn_y + 150, btn_w, btn_h), "Highscores", self.font_ui)
        
        for btn in (self.menu_sp_btn, self.menu_mp_btn, self.menu_host_btn, self.menu_scores_btn):
            btn.draw(self.screen, bg=self.palette["panel"], fg=self.palette["text"], border=self.palette["panel_edge"], hover=btn.hit(mouse))

    def _draw_browser(self):
        self.screen.fill(pygame.Color(self.palette["bg"]))
        w, h = self.screen.get_size()
        
        title = self.font_title.render("LAN Server Browser", True, pygame.Color(self.palette["text"]))
        self.screen.blit(title, (30, 30))
        
        sub = self.font_ui.render("Searching for servers via UDP Broadcast...", True, pygame.Color(self.palette["subtext"]))
        self.screen.blit(sub, (30, 60))
        
        # List discovered servers
        list_rect = pygame.Rect(30, 95, 360, 240)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel"]), list_rect, border_radius=10)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel_edge"]), list_rect, width=1, border_radius=10)
        
        if not self.discovered_servers:
            empty_txt = self.font_ui.render("No local servers found. Click Refresh.", True, pygame.Color(self.palette["subtext"]))
            self.screen.blit(empty_txt, empty_txt.get_rect(center=list_rect.center))
        else:
            y_offset = list_rect.y + 10
            mouse = pygame.mouse.get_pos()
            for i, s in enumerate(self.discovered_servers):
                srv_rect = pygame.Rect(list_rect.x + 10, y_offset, list_rect.width - 20, 45)
                bg = self.palette["tile_hidden_hover"] if srv_rect.collidepoint(mouse) else self.palette["panel_edge"]
                pygame.draw.rect(self.screen, pygame.Color(bg), srv_rect, border_radius=6)
                
                srv_name = self.font_ui.render(s["name"], True, pygame.Color(self.palette["text"]))
                srv_ip = self.font_chat.render(f"{s['ip']}:{s['tcp_port']}", True, pygame.Color(self.palette["subtext"]))
                
                self.screen.blit(srv_name, (srv_rect.x + 10, srv_rect.y + 6))
                self.screen.blit(srv_ip, (srv_rect.x + 10, srv_rect.y + 24))
                
                y_offset += 55
                if y_offset > list_rect.bottom - 50:
                    break  # Simple limit to avoid overflow

        # Right control panel (manual IP)
        lbl_manual = self.font_ui.render("Connect to IP manually:", True, pygame.Color(self.palette["subtext"]))
        self.screen.blit(lbl_manual, (410, 95))
        
        ip_box = pygame.Rect(410, 120, 200, 36)
        box_bg = self.palette["tile_hidden_pressed"] if self.editing_ip else self.palette["panel"]
        border_color = "#3b82f6" if self.editing_ip else self.palette["panel_edge"]
        pygame.draw.rect(self.screen, pygame.Color(box_bg), ip_box, border_radius=8)
        pygame.draw.rect(self.screen, pygame.Color(border_color), ip_box, width=2, border_radius=8)
        
        ip_txt = self.font_ui.render(self.manual_ip, True, pygame.Color(self.palette["text"]))
        self.screen.blit(ip_txt, ip_txt.get_rect(center=ip_box.center))
        
        mouse = pygame.mouse.get_pos()
        self.manual_conn_btn = _Button(pygame.Rect(410, 165, 200, 36), "Connect Manual IP", self.font_ui)
        self.manual_conn_btn.draw(self.screen, bg=self.palette["panel_edge"], fg=self.palette["text"], border=self.palette["panel_edge"], hover=self.manual_conn_btn.hit(mouse))
        
        self.browser_refresh_btn = _Button(pygame.Rect(30, 360, 150, 40), "Refresh Discovery", self.font_ui)
        self.browser_back_btn = _Button(pygame.Rect(460, 360, 150, 40), "Back to Menu", self.font_ui)
        
        for btn in (self.browser_refresh_btn, self.browser_back_btn):
            btn.draw(self.screen, bg=self.palette["panel"], fg=self.palette["text"], border=self.palette["panel_edge"], hover=btn.hit(mouse))

    def _draw_lobby(self):
        self.screen.fill(pygame.Color(self.palette["bg"]))
        w, h = self.screen.get_size()
        
        srv_name = self.selected_server["name"] if self.selected_server else "Local Host"
        title = self.font_title.render(f"Server Lobbies ({srv_name})", True, pygame.Color(self.palette["text"]))
        self.screen.blit(title, (30, 30))
        
        list_rect = pygame.Rect(30, 80, 360, 260)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel"]), list_rect, border_radius=10)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel_edge"]), list_rect, width=1, border_radius=10)
        
        if not self.discovered_lobbies:
            empty_txt = self.font_ui.render("No active rooms. Create one!", True, pygame.Color(self.palette["subtext"]))
            self.screen.blit(empty_txt, empty_txt.get_rect(center=list_rect.center))
        else:
            y_offset = list_rect.y + 10
            mouse = pygame.mouse.get_pos()
            for i, l in enumerate(self.discovered_lobbies):
                lob_rect = pygame.Rect(list_rect.x + 10, y_offset, list_rect.width - 20, 45)
                bg = self.palette["tile_hidden_hover"] if lob_rect.collidepoint(mouse) else self.palette["panel_edge"]
                pygame.draw.rect(self.screen, pygame.Color(bg), lob_rect, border_radius=6)
                
                lob_info = self.font_ui.render(f"Room {l['lobby_id']} ({l['difficulty']})", True, pygame.Color(self.palette["text"]))
                lob_state = self.font_chat.render(f"Players: {l['player_count']} | State: {l['state']}", True, pygame.Color(self.palette["subtext"]))
                
                self.screen.blit(lob_info, (lob_rect.x + 10, lob_rect.y + 6))
                self.screen.blit(lob_state, (lob_rect.x + 10, lob_rect.y + 24))
                
                y_offset += 55
                if y_offset > list_rect.bottom - 50:
                    break

        lbl_create = self.font_ui.render("Create New Room:", True, pygame.Color(self.palette["subtext"]))
        self.screen.blit(lbl_create, (410, 80))
        
        mouse = pygame.mouse.get_pos()
        self.create_easy_btn = _Button(pygame.Rect(410, 110, 200, 36), "Easy Difficulty", self.font_ui)
        self.create_medium_btn = _Button(pygame.Rect(410, 155, 200, 36), "Medium Difficulty", self.font_ui)
        self.create_hard_btn = _Button(pygame.Rect(410, 200, 200, 36), "Hard Difficulty", self.font_ui)
        
        for btn in (self.create_easy_btn, self.create_medium_btn, self.create_hard_btn):
            btn.draw(self.screen, bg=self.palette["panel_edge"], fg=self.palette["text"], border=self.palette["panel_edge"], hover=btn.hit(mouse))

        # Bottom controls
        self.lobby_refresh_btn = _Button(pygame.Rect(30, 360, 150, 40), "Refresh Lobbies", self.font_ui)
        self.lobby_disconnect_btn = _Button(pygame.Rect(460, 360, 150, 40), "Disconnect", self.font_ui)
        
        for btn in (self.lobby_refresh_btn, self.lobby_disconnect_btn):
            btn.draw(self.screen, bg=self.palette["panel"], fg=self.palette["text"], border=self.palette["panel_edge"], hover=btn.hit(mouse))

    def _draw_panel(self):
        w, _ = self.screen.get_size()
        panel_rect = pygame.Rect(0, 0, w, self.panel_h + self.pad)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["bg"]), panel_rect)

        # Calculate appropriate width of the upper bar
        inner_w = w - 2 * self.pad

        inner = pygame.Rect(self.pad, self.pad, inner_w, self.panel_h)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel"]), inner, border_radius=14)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel_edge"]), inner, width=1, border_radius=14)

        self._layout_panel_dynamic()

        if self.app_state == "playing_sp":
            # Original difficulty selector buttons in SP
            for i, b in enumerate(self.diff_buttons):
                selected = i == self.difficulty_index
                bg = self.palette["tile_hidden_hover"] if selected else self.palette["panel_edge"]
                b.draw(
                    self.screen,
                    bg=bg,
                    fg=self.palette["text"],
                    border=self.palette["panel_edge"],
                    hover=b.hit(mouse),
                )
            self.highscores_btn.draw(
                self.screen,
                bg=self.palette["panel_edge"],
                fg=self.palette["text"],
                border=self.palette["panel_edge"],
                hover=self.highscores_btn.hit(mouse),
            )
        else:
            srv_info = self.font_ui.render(f"Server: {self.selected_server['name'] if self.selected_server else 'Local'}", True, pygame.Color(self.palette["text"]))
            lobby_info = self.font_ui.render(f"Room: {self.lobby_state['lobby_id'] if self.lobby_state else ''}", True, pygame.Color(self.palette["subtext"]))
            self.screen.blit(srv_info, (self.pad + 14, self.pad + 12))
            self.screen.blit(lobby_info, (self.pad + 14, self.pad + 32))

        mine_rect = self._mine_counter_rect()
        pygame.draw.rect(self.screen, pygame.Color("#000000"), mine_rect, border_radius=8)
        mine_text = self.font_counter.render(self._mine_counter_text(), True, pygame.Color("#ef4444"))
        self.screen.blit(mine_text, mine_text.get_rect(center=mine_rect.center))

        timer_rect = self._timer_rect()
        pygame.draw.rect(self.screen, pygame.Color("#000000"), timer_rect, border_radius=8)
        timer_text = self.font_counter.render(f"{self._elapsed_seconds():03d}", True, pygame.Color("#ef4444"))
        self.screen.blit(timer_text, timer_text.get_rect(center=timer_rect.center))

        self._draw_smiley()

    def _draw_smiley(self):
        rect = self._smiley_rect()
        
        # Decide smiley state based on game mode
        state = self._smiley_state
        if self.app_state == "playing_mp" and self.lobby_state:
            # Derive MP smiley state
            if self.lobby_state["game_over"]:
                state = "win" if self.lobby_state["won"] else "lose"
            else:
                state = "idle"
            fill = pygame.Color("#fbbf24")
        else:
            fill = pygame.Color("#22c55e") if state == "win" else pygame.Color("#ef4444")

        pygame.draw.ellipse(self.screen, fill, rect)
        pygame.draw.ellipse(self.screen, pygame.Color(self.palette["panel_edge"]), rect, width=2)

        cx, cy = rect.center
        if state == "pressed":
            inner = rect.inflate(-20, -20)
            pygame.draw.ellipse(self.screen, pygame.Color(self.palette["panel_edge"]), inner, width=1)
            return

        eye_color = pygame.Color("#111827")
        pygame.draw.circle(self.screen, eye_color, (cx - 8, cy - 6), 2)
        pygame.draw.circle(self.screen, eye_color, (cx + 8, cy - 6), 2)

        mouth_rect = pygame.Rect(0, 0, 20, 14)
        mouth_rect.center = (cx, cy + 6)
        if state == "lose":
            pygame.draw.arc(self.screen, eye_color, mouth_rect, math.radians(20), math.radians(160), 2)
            for dx in (-8, 8):
                pygame.draw.line(self.screen, eye_color, (cx + dx - 2, cy - 8), (cx + dx + 2, cy - 4), 2)
                pygame.draw.line(self.screen, eye_color, (cx + dx + 2, cy - 8), (cx + dx - 2, cy - 4), 2)
        elif state == "win":
            pygame.draw.arc(self.screen, eye_color, mouth_rect, math.radians(200), math.radians(340), 2)
        else:
            pygame.draw.arc(self.screen, eye_color, mouth_rect, math.radians(200), math.radians(340), 2)

    def _draw_tile(self, r: int, c: int, trigger=None):
        if self.app_state == "playing_sp":
            if self.engine is None:
                return

            ox, oy = self._board_origin()
            x0 = ox + c * self.tile
            y0 = oy + r * self.tile
            rect = pygame.Rect(x0, y0, self.tile, self.tile)

            is_revealed = self.engine.revealed[r][c]
            is_flag = (r, c) in self.engine.flags
            is_mine = (r, c) in self.engine.mines
            is_trigger = trigger is not None and trigger.get("type") == "boom" and trigger.get("trigger") == (r, c)

            if self.engine.game_over and is_mine:
                bg = self.palette["mine_bg_trigger"] if is_trigger else self.palette["mine_bg"]
            elif is_revealed:
                bg = self.palette["tile_revealed"]
            else:
                bg = self.palette["tile_hidden"]
                if self._hover_cell == (r, c):
                    bg = self.palette["tile_hidden_hover"]
                if (r, c) in self._pressed_cells:
                    bg = self.palette["tile_hidden_pressed"]

            pygame.draw.rect(self.screen, pygame.Color(bg), rect)
            pygame.draw.rect(self.screen, pygame.Color(self.palette["shadow"]), rect, width=1)

            if self.engine.game_over and is_mine:
                pygame.draw.circle(self.screen, pygame.Color(self.palette["mine"]), rect.center, 6)
                pygame.draw.line(self.screen, pygame.Color(self.palette["mine"]), (rect.left + 6, rect.centery), (rect.right - 6, rect.centery), 2)
                pygame.draw.line(self.screen, pygame.Color(self.palette["mine"]), (rect.centerx, rect.top + 6), (rect.centerx, rect.bottom - 6), 2)
                return

            if not is_revealed and is_flag:
                pole_color = pygame.Color(self.palette["mine"])
                flag_color = pygame.Color(self.palette["flag"])
                pygame.draw.polygon(
                    self.screen,
                    flag_color,
                    [(rect.left + 9, rect.top + 19), (rect.left + 9, rect.top + 7), (rect.left + 19, rect.top + 11)],
                )
                pygame.draw.line(self.screen, pole_color, (rect.left + 9, rect.top + 7), (rect.left + 9, rect.top + 21), 2)
                pygame.draw.line(self.screen, pole_color, (rect.left + 6, rect.top + 21), (rect.left + 14, rect.top + 21), 2)
                return

            if is_revealed:
                n = self.engine.adj[r][c]
                if n > 0:
                    surf = self.font_num.render(str(n), True, pygame.Color(self._num_color(n)))
                    self.screen.blit(surf, surf.get_rect(center=(rect.centerx, rect.centery + 1)))
        
        else:
            if self.lobby_state is None:
                return

            ox, oy = self._board_origin()
            x0 = ox + c * self.tile
            y0 = oy + r * self.tile
            rect = pygame.Rect(x0, y0, self.tile, self.tile)

            val = None
            is_revealed = False
            for rcval in self.lobby_state["revealed_cells"]:
                if rcval[0] == r and rcval[1] == c:
                    is_revealed = True
                    val = rcval[2]
                    break

            flag_pid = None
            for flag in self.lobby_state["flags"]:
                if flag[0] == r and flag[1] == c:
                    flag_pid = flag[2]
                    break

            
            flag_color_hex = "#ef4444"
            if flag_pid:
                for player in self.lobby_state["players"]:
                    if player["id"] == flag_pid:
                        flag_color_hex = player["color"]
                        break

            if is_revealed and val == -1:
                bg = self.palette["mine_bg_trigger"]
            elif is_revealed:
                bg = self.palette["tile_revealed"]
            else:
                bg = self.palette["tile_hidden"]
                if self._hover_cell == (r, c):
                    bg = self.palette["tile_hidden_hover"]
                if (r, c) in self._pressed_cells:
                    bg = self.palette["tile_hidden_pressed"]

            pygame.draw.rect(self.screen, pygame.Color(bg), rect)
            pygame.draw.rect(self.screen, pygame.Color(self.palette["shadow"]), rect, width=1)

            if is_revealed and val == -1:
                pygame.draw.circle(self.screen, pygame.Color(self.palette["mine"]), rect.center, 6)
                pygame.draw.line(self.screen, pygame.Color(self.palette["mine"]), (rect.left + 6, rect.centery), (rect.right - 6, rect.centery), 2)
                pygame.draw.line(self.screen, pygame.Color(self.palette["mine"]), (rect.centerx, rect.top + 6), (rect.centerx, rect.bottom - 6), 2)
                return

            if not is_revealed and flag_pid:
                pole_color = pygame.Color(self.palette["mine"])
                f_color = pygame.Color(flag_color_hex)
                pygame.draw.polygon(
                    self.screen,
                    f_color,
                    [(rect.left + 9, rect.top + 19), (rect.left + 9, rect.top + 7), (rect.left + 19, rect.top + 11)],
                )
                pygame.draw.line(self.screen, pole_color, (rect.left + 9, rect.top + 7), (rect.left + 9, rect.top + 21), 2)
                pygame.draw.line(self.screen, pole_color, (rect.left + 6, rect.top + 21), (rect.left + 14, rect.top + 21), 2)
                return

            if is_revealed and val is not None and val > 0:
                surf = self.font_num.render(str(val), True, pygame.Color(self._num_color(val)))
                self.screen.blit(surf, surf.get_rect(center=(rect.centerx, rect.centery + 1)))

    def _draw_board(self):
        if self.app_state == "playing_sp":
            if self.engine is None:
                return
            for r in range(self.engine.rows):
                for c in range(self.engine.cols):
                    self._draw_tile(r, c)
        else:
            if self.lobby_state is None:
                return
            for r in range(self.lobby_state["rows"]):
                for c in range(self.lobby_state["cols"]):
                    self._draw_tile(r, c)

    def _draw_sidebar(self):
        """Draws the multiplayer sidebar containing Player List, Chat logs, and input boxes."""
        if not self.lobby_state:
            return

        w, h = self.screen.get_size()
        board_w = self.lobby_state["cols"] * self.tile
        sidebar_x = self.pad * 2 + board_w
        sidebar_w = w - sidebar_x - self.pad
        sidebar_h = h - self.pad * 2
        
        sidebar_rect = pygame.Rect(sidebar_x, self.pad, sidebar_w, sidebar_h)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel"]), sidebar_rect, border_radius=14)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel_edge"]), sidebar_rect, width=1, border_radius=14)

        # Draw Lobby details
        y = sidebar_rect.y + 14
        room_title = self.font_title.render("MULTIPLAYER", True, pygame.Color(self.palette["text"]))
        self.screen.blit(room_title, (sidebar_rect.x + 14, y))
        y += 30

        room_state = self.font_chat.render(f"Lobby State: {self.lobby_state['state'].upper()}", True, pygame.Color(self.palette["subtext"]))
        self.screen.blit(room_state, (sidebar_rect.x + 14, y))
        y += 20

        if self.lobby_state["state"] == "waiting":
            me_player = next((p for p in self.lobby_state["players"] if p["id"] == self.player_id), None)
            is_host = me_player and me_player.get("is_host", False)
            if is_host:
                lbl_start = self.font_ui.render("Press 'S' or click button to START", True, pygame.Color("#fbbf24"))
                self.screen.blit(lbl_start, (sidebar_rect.x + 14, y))
            else:
                lbl_start = self.font_ui.render("Waiting for Host to start...", True, pygame.Color(self.palette["subtext"]))
                self.screen.blit(lbl_start, (sidebar_rect.x + 14, y))
            y += 24

        y = max(y, sidebar_rect.y + 80)
        lbl_scores = self.font_ui.render("SCOREBOARD:", True, pygame.Color(self.palette["text"]))
        self.screen.blit(lbl_scores, (sidebar_rect.x + 14, y))
        pygame.draw.line(self.screen, pygame.Color(self.palette["panel_edge"]), (sidebar_rect.x + 14, y + 22), (sidebar_rect.right - 14, y + 22), 1)
        y += 28

        for p in self.lobby_state["players"]:
            # Draw color bullet
            bullet_rect = pygame.Rect(sidebar_x + 16, y + 4, 10, 10)
            pygame.draw.ellipse(self.screen, pygame.Color(p["color"]), bullet_rect)
            
            # Form display string
            name_str = p["nickname"]
            if p["id"] == self.player_id:
                name_str += " (You)"
            if p["is_host"]:
                name_str += " [Host]"
            if not p["connected"]:
                name_str += " [OUT]"

            color = self.palette["text"]
            if p["stunned_seconds"] > 0:
                color = "#f87171"
                name_str += f" (Stun {math.ceil(p['stunned_seconds'])}s)"
            elif not p["connected"]:
                color = "#4b5563"

            p_surf = self.font_ui.render(name_str, True, pygame.Color(color))
            self.screen.blit(p_surf, (sidebar_x + 32, y))

            score_surf = self.font_ui.render(str(p["score"]), True, pygame.Color(self.palette["text"]))
            self.screen.blit(score_surf, (sidebar_rect.right - 16 - score_surf.get_width(), y))

            y += 24
            if y > sidebar_rect.bottom - 220:
                break

        # CHAT BOX (Height: 120px)
        y = sidebar_rect.bottom - 190
        lbl_chat = self.font_ui.render("Lobby Chat:", True, pygame.Color(self.palette["subtext"]))
        self.screen.blit(lbl_chat, (sidebar_rect.x + 14, y))
        y += 20

        chat_box_rect = pygame.Rect(sidebar_rect.x + 10, y, sidebar_rect.width - 20, 105)
        pygame.draw.rect(self.screen, pygame.Color("#050911"), chat_box_rect, border_radius=8)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel_edge"]), chat_box_rect, width=1, border_radius=8)

        chat_y = chat_box_rect.y + 6
        messages = self.lobby_state["chat"][-6:]  # Show last 6 messages
        for msg in messages:
            sender = msg["sender"]
            text = msg["text"]
            
            if sender == "System":
                col = "#fbbf24"
                full_msg = f"{text}"
            else:
                col = self.palette["text"]
                full_msg = f"{sender}: {text}"
                
            msg_surf = self.font_chat.render(full_msg, True, pygame.Color(col))
            self.screen.blit(msg_surf, (chat_box_rect.x + 8, chat_y))
            chat_y += 16

        # Chat Input Box
        y = chat_box_rect.bottom + 8
        chat_input_box = pygame.Rect(sidebar_rect.x + 10, y, sidebar_rect.width - 20, 28)
        input_bg = self.palette["tile_hidden_pressed"] if self.editing_chat else self.palette["panel"]
        input_border = "#3b82f6" if self.editing_chat else self.palette["panel_edge"]
        pygame.draw.rect(self.screen, pygame.Color(input_bg), chat_input_box, border_radius=6)
        pygame.draw.rect(self.screen, pygame.Color(input_border), chat_input_box, width=1, border_radius=6)

        if self.chat_input:
            in_text = self.chat_input
        else:
            in_text = "Press Enter to chat..." if not self.editing_chat else "Typing..."
        
        in_color = self.palette["text"] if self.chat_input else self.palette["subtext"]
        in_surf = self.font_chat.render(in_text, True, pygame.Color(in_color))
        self.screen.blit(in_surf, (chat_input_box.x + 8, chat_input_box.y + 6))

        mouse = pygame.mouse.get_pos()
        y = chat_input_box.bottom + 8
        
        me = next((p for p in self.lobby_state["players"] if p["id"] == self.player_id), None)
        is_host = me and me["is_host"]

        self.mp_leave_btn = _Button(pygame.Rect(sidebar_rect.x + 10, y, 90, 24), "Leave Room", self.font_chat)
        self.mp_leave_btn.draw(self.screen, bg=self.palette["panel_edge"], fg=self.palette["text"], border=self.palette["panel_edge"], hover=self.mp_leave_btn.hit(mouse))
        
        if self.lobby_state["state"] == "waiting" and is_host:
            self.mp_start_btn = _Button(pygame.Rect(sidebar_rect.right - 110, y, 100, 24), "Start Game", self.font_chat)
            self.mp_start_btn.draw(self.screen, bg="#16a34a", fg="#ffffff", border=self.palette["panel_edge"], hover=self.mp_start_btn.hit(mouse))
        elif self.lobby_state["game_over"]:
            self.mp_restart_btn = _Button(pygame.Rect(sidebar_rect.right - 110, y, 100, 24), "Restart Game", self.font_chat)
            self.mp_restart_btn.draw(self.screen, bg="#16a34a", fg="#ffffff", border=self.palette["panel_edge"], hover=self.mp_restart_btn.hit(mouse))

    def _draw_overlay(self):
        if self._overlay is None:
            return
        ok_rect = self._overlay.draw(
            self.screen,
            palette=self.palette,
            title_font=self.font_title,
            text_font=self.font_ui,
            ok_font=self.font_ui,
        )
        self._overlay_ok_rect = ok_rect

    def _draw_stun_overlay(self):
        """Draws a red screen outline overlay if the local player is stunned."""
        if not self.lobby_state:
            return
        me = next((p for p in self.lobby_state["players"] if p["id"] == self.player_id), None)
        if not me or me["stunned_seconds"] <= 0:
            return

        w, h = self.screen.get_size()
        border_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(border_surf, (239, 68, 68, 40), (0, 0, w, h), width=8)
        self.screen.blit(border_surf, (0, 0))

        stun_msg = f"EXPLODED! STUNNED: {math.ceil(me['stunned_seconds'])}s"
        surf = self.font_title.render(stun_msg, True, pygame.Color("#ef4444"))
        
        ox, oy = self._board_origin()
        board_w = self.lobby_state["cols"] * self.tile
        board_h = self.lobby_state["rows"] * self.tile
        
        box_rect = pygame.Rect(ox + (board_w - surf.get_width()) // 2 - 10, oy + board_h // 2 - 20, surf.get_width() + 20, 40)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel"]), box_rect, border_radius=8)
        pygame.draw.rect(self.screen, pygame.Color("#ef4444"), box_rect, width=1, border_radius=8)
        
        self.screen.blit(surf, surf.get_rect(center=box_rect.center))

    def _handle_event(self, e: pygame.event.Event):
        if e.type == pygame.QUIT:
            self.disconnect_tcp()
            raise SystemExit

        if self._overlay is not None:
            if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
                ok_rect = self._overlay_ok_rect
                if ok_rect is None:
                    _, ok_rect = self._overlay.layout(self.screen.get_size())
                self._overlay.handle_event(e, ok_rect)
            return

        if self.app_state == "menu":
            self._handle_event_menu(e)
        elif self.app_state == "browser":
            self._handle_event_browser(e)
        elif self.app_state == "lobby_room":
            self._handle_event_lobby(e)
        elif self.app_state == "playing_sp":
            self._handle_event_sp(e)
        elif self.app_state == "playing_mp":
            self._handle_event_mp(e)

    def _handle_event_menu(self, e: pygame.event.Event):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            pos = e.pos
            w, h = self.screen.get_size()
            nick_box = pygame.Rect(w // 2 - 130, 185, 260, 36)
            if nick_box.collidepoint(pos):
                self.editing_nick = True
            else:
                self.editing_nick = False
                
            if self.menu_sp_btn.hit(pos):
                self.new_game(self.difficulties[0])
            elif self.menu_mp_btn.hit(pos):
                self.app_state = "browser"
                self.trigger_udp_discovery()
            elif self.menu_host_btn.hit(pos):
                self.host_local_server()
            elif self.menu_scores_btn.hit(pos):
                self._open_highscores()

        elif e.type == pygame.KEYDOWN and self.editing_nick:
            if e.key == pygame.K_RETURN:
                self.editing_nick = False
            elif e.key == pygame.K_BACKSPACE:
                self.nickname = self.nickname[:-1]
            else:
                if e.unicode and len(self.nickname) < 12:
                    self.nickname += e.unicode

    def _handle_event_browser(self, e: pygame.event.Event):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            pos = e.pos
            
            ip_box = pygame.Rect(410, 120, 200, 36)
            if ip_box.collidepoint(pos):
                self.editing_ip = True
            else:
                self.editing_ip = False
                
            # Manual IP connect button
            if self.manual_conn_btn.hit(pos):
                self.selected_server = {
                    "ip": self.manual_ip,
                    "name": "Manual IP Server",
                    "tcp_port": TCP_PORT,
                    "http_port": HTTP_PORT
                }
                self.app_state = "lobby_room"
                self.fetch_lobbies_via_http()
                return

            if self.browser_back_btn.hit(pos):
                self.app_state = "menu"
            elif self.browser_refresh_btn.hit(pos):
                self.trigger_udp_discovery()
            
            list_rect = pygame.Rect(30, 95, 360, 240)
            if list_rect.collidepoint(pos) and self.discovered_servers:
                y_offset = list_rect.y + 10
                for s in self.discovered_servers:
                    srv_rect = pygame.Rect(list_rect.x + 10, y_offset, list_rect.width - 20, 45)
                    if srv_rect.collidepoint(pos):
                        self.selected_server = s
                        self.app_state = "lobby_room"
                        self.fetch_lobbies_via_http()
                        break
                    y_offset += 55

        elif e.type == pygame.KEYDOWN and self.editing_ip:
            if e.key == pygame.K_RETURN:
                self.editing_ip = False
            elif e.key == pygame.K_BACKSPACE:
                self.manual_ip = self.manual_ip[:-1]
            else:
                if e.unicode and (e.unicode.isdigit() or e.unicode in "."):
                    self.manual_ip += e.unicode

    def _handle_event_lobby(self, e: pygame.event.Event):
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            pos = e.pos
            
            if self.create_easy_btn.hit(pos):
                self.create_lobby_via_http("Easy")
            elif self.create_medium_btn.hit(pos):
                self.create_lobby_via_http("Medium")
            elif self.create_hard_btn.hit(pos):
                self.create_lobby_via_http("Hard")
            
            elif self.lobby_refresh_btn.hit(pos):
                self.fetch_lobbies_via_http()
            elif self.lobby_disconnect_btn.hit(pos):
                self.selected_server = None
                self.app_state = "browser"
                self.trigger_udp_discovery()
            
            list_rect = pygame.Rect(30, 80, 360, 260)
            if list_rect.collidepoint(pos) and self.discovered_lobbies:
                y_offset = list_rect.y + 10
                for l in self.discovered_lobbies:
                    lob_rect = pygame.Rect(list_rect.x + 10, y_offset, list_rect.width - 20, 45)
                    if lob_rect.collidepoint(pos):
                        self.join_lobby_via_tcp(l["lobby_id"])
                        break
                    y_offset += 55

    def _handle_event_sp(self, e: pygame.event.Event):
        if e.type == pygame.KEYDOWN:
            if e.key in (pygame.K_ESCAPE, pygame.K_F2):
                self.new_game(self.difficulties[self.difficulty_index])
            elif e.key in (pygame.K_1, pygame.K_KP1):
                self.difficulty_index = 0
                self.new_game(self.difficulties[0])
            elif e.key in (pygame.K_2, pygame.K_KP2) and len(self.difficulties) >= 2:
                self.difficulty_index = 1
                self.new_game(self.difficulties[1])
            elif e.key in (pygame.K_3, pygame.K_KP3) and len(self.difficulties) >= 3:
                self.difficulty_index = 2
                self.new_game(self.difficulties[2])

        if e.type == pygame.MOUSEMOTION:
            self._hover_cell = self._cell_from_pos(e.pos)

        if e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 1:
                pos = e.pos
                if self.highscores_btn.hit(pos):
                    self._open_highscores()
                    return
                for i, b in enumerate(self.diff_buttons):
                    if b.hit(pos):
                        self.difficulty_index = i
                        self.new_game(self.difficulties[i])
                        return
                if self._smiley_rect().collidepoint(pos):
                    self._smiley_state = "pressed"
                    return

            if e.button in (1, 2, 3):
                self._handle_board_mouse_down(e.button, e.pos)

        if e.type == pygame.MOUSEBUTTONUP:
            if e.button == 1 and self._smiley_state == "pressed":
                if self._smiley_rect().collidepoint(e.pos):
                    self.new_game(self.difficulties[self.difficulty_index])
                else:
                    self._smiley_state = "idle"
                return

            if e.button in (1, 2, 3):
                self._handle_board_mouse_up(e.button, e.pos)

    def _handle_event_mp(self, e: pygame.event.Event):
        if not self.lobby_state:
            return

        if e.type == pygame.KEYDOWN:
            if self.editing_chat:
                if e.key == pygame.K_RETURN:
                    # Send message to server
                    msg_text = self.chat_input.strip()
                    if msg_text:
                        send_msg(self.tcp_sock, {"action": "chat", "message": msg_text})
                    self.chat_input = ""
                    self.editing_chat = False
                elif e.key == pygame.K_ESCAPE:
                    self.editing_chat = False
                elif e.key == pygame.K_BACKSPACE:
                    self.chat_input = self.chat_input[:-1]
                else:
                    if e.unicode and len(self.chat_input) < 80:
                        self.chat_input += e.unicode
            else:
                if e.key in (pygame.K_RETURN, pygame.K_t):
                    self.editing_chat = True
                elif e.key == pygame.K_s:
                    send_msg(self.tcp_sock, {"action": "start_game"})
                elif e.key == pygame.K_r:
                    send_msg(self.tcp_sock, {"action": "restart"})

        if e.type == pygame.MOUSEMOTION:
            self._hover_cell = self._cell_from_pos(e.pos)

        if e.type == pygame.MOUSEBUTTONDOWN:
            pos = e.pos
            
            if self._smiley_rect().collidepoint(pos) and self.lobby_state["game_over"]:
                send_msg(self.tcp_sock, {"action": "restart"})
                return

            w, h = self.screen.get_size()
            board_w = self.lobby_state["cols"] * self.tile
            sidebar_x = self.pad * 2 + board_w
            
            y = h - self.pad - 28
            leave_rect = pygame.Rect(sidebar_x + 10, y + 8, 90, 24)
            if leave_rect.collidepoint(pos):
                self.disconnect_tcp()
                return

            action_rect = pygame.Rect(w - self.pad - 110, y + 8, 100, 24)
            if action_rect.collidepoint(pos):
                me_player = next((p for p in self.lobby_state["players"] if p["id"] == self.player_id), None)
                if self.lobby_state["state"] == "waiting" and me_player and me_player["is_host"]:
                    send_msg(self.tcp_sock, {"action": "start_game"})
                elif self.lobby_state["game_over"]:
                    send_msg(self.tcp_sock, {"action": "restart"})
                return

            chat_input_rect = pygame.Rect(sidebar_x + 10, h - self.pad - 28 - 36, w - sidebar_x - self.pad - 20, 28)
            if chat_input_rect.collidepoint(pos):
                self.editing_chat = True
            else:
                self.editing_chat = False

            if e.button in (1, 2, 3):
                self._handle_board_mouse_down(e.button, e.pos)

        if e.type == pygame.MOUSEBUTTONUP:
            if e.button in (1, 2, 3):
                self._handle_board_mouse_up(e.button, e.pos)

    def run(self):
        while True:
            self.clock.tick(60)

            for e in pygame.event.get():
                self._handle_event(e)

            if self._overlay is not None and self._overlay.closed:
                self._overlay = None
                self._overlay_ok_rect = None

            if self.app_state == "menu":
                self._draw_menu()
            elif self.app_state == "browser":
                self._draw_browser()
            elif self.app_state == "lobby_room":
                self._draw_lobby()
            elif self.app_state == "playing_sp":
                if self.engine is not None and self.engine.game_over and self._smiley_state == "idle":
                    self._smiley_state = "win" if self.engine.won else "lose"

                self.screen.fill(pygame.Color(self.palette["bg"]))
                self._draw_panel()
                self._draw_board()
            elif self.app_state == "playing_mp":
                # Multiplayer Gameplay state
                self.screen.fill(pygame.Color(self.palette["bg"]))
                if self.lobby_state is None:
                    lbl_load = self.font_title.render("Loading room state...", True, pygame.Color(self.palette["text"]))
                    self.screen.blit(lbl_load, lbl_load.get_rect(center=self.screen.get_rect().center))
                else:
                    expected_w, expected_h = self._window_size_for_mp()
                    curr_w, curr_h = self.screen.get_size()
                    if curr_w != expected_w or curr_h != expected_h:
                        self.screen = pygame.display.set_mode((expected_w, expected_h))
                    self._draw_panel()
                    self._draw_board()
                    self._draw_sidebar()
                    self._draw_stun_overlay()

            if self._overlay is not None:
                self._draw_overlay()

            pygame.display.flip()


def run():
    MinesweeperPygameApp().run()