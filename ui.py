import math
import time

import pygame

from engine import Difficulty, MinesweeperEngine, ScoreManager


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
        pygame.display.set_caption("Minesweeper")

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

        self.font_ui = pygame.font.SysFont("segoeui", 16) or pygame.font.Font(None, 16)
        self.font_counter = pygame.font.SysFont("consolas", 24, bold=True) or pygame.font.Font(None, 24)
        self.font_num = pygame.font.SysFont("segoeui", 14, bold=True) or pygame.font.Font(None, 14)
        self.font_title = pygame.font.SysFont("segoeui", 22, bold=True) or pygame.font.Font(None, 22)

        self.screen = pygame.display.set_mode((640, 480))

        self._layout_static()
        self.new_game(self.difficulties[self.difficulty_index])

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
        if self.engine is None:
            return self.pad, self.panel_h + self.pad
        w, _ = self.screen.get_size()
        board_w = self.engine.cols * self.tile
        x = max(self.pad, (w - board_w) // 2)
        return x, self.panel_h + self.pad

    def _window_size_for_engine(self):
        if self.engine is None:
            return 640, 480
        board_w = self.engine.cols * self.tile + 2 * self.pad
        board_h = self.panel_h + self.engine.rows * self.tile + 2 * self.pad
        min_w = 760
        min_h = 480
        return max(min_w, board_w), max(min_h, board_h)

    def new_game(self, difficulty: Difficulty):
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
        if self._start_time is None:
            return 0
        return max(0, min(999, int(time.time() - self._start_time)))

    def _ensure_timer_started(self):
        if self._start_time is None:
            self._start_time = time.time()

    def _mine_counter_text(self) -> str:
        if self.engine is None:
            return "000"
        left = self.engine.mines_total - len(self.engine.flags)
        left = max(-99, min(999, left))
        sign = "-" if left < 0 else ""
        return f"{sign}{abs(left):03d}"[-3:]

    def _cell_from_pos(self, pos):
        if self.engine is None:
            return None
        ox, oy = self._board_origin()
        x, y = pos
        x -= ox
        y -= oy
        if x < 0 or y < 0:
            return None
        c = x // self.tile
        r = y // self.tile
        if 0 <= r < self.engine.rows and 0 <= c < self.engine.cols:
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

    def _handle_board_mouse_down(self, button: int, pos):
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

    def _handle_board_mouse_up(self, button: int, pos):
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

    def _handle_event(self, e: pygame.event.Event):
        if e.type == pygame.QUIT:
            raise SystemExit

        if self._overlay is not None:
            if e.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL):
                ok_rect = self._overlay_ok_rect
                if ok_rect is None:
                    _, ok_rect = self._overlay.layout(self.screen.get_size())
                self._overlay.handle_event(e, ok_rect)
            return

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

    def _draw_panel(self):
        w, _ = self.screen.get_size()
        panel_rect = pygame.Rect(0, 0, w, self.panel_h + self.pad)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["bg"]), panel_rect)

        inner = pygame.Rect(self.pad, self.pad, w - 2 * self.pad, self.panel_h)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel"]), inner, border_radius=14)
        pygame.draw.rect(self.screen, pygame.Color(self.palette["panel_edge"]), inner, width=1, border_radius=14)

        self._layout_panel_dynamic()

        mouse = pygame.mouse.get_pos()

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
        if self._smiley_state not in ("lose", "win"):
            fill = pygame.Color("#fbbf24")
        else:
            fill = pygame.Color("#22c55e") if self._smiley_state == "win" else pygame.Color("#ef4444")

        pygame.draw.ellipse(self.screen, fill, rect)
        pygame.draw.ellipse(self.screen, pygame.Color(self.palette["panel_edge"]), rect, width=2)

        cx, cy = rect.center
        if self._smiley_state == "pressed":
            inner = rect.inflate(-20, -20)
            pygame.draw.ellipse(self.screen, pygame.Color(self.palette["panel_edge"]), inner, width=1)
            return

        eye_color = pygame.Color("#111827")
        pygame.draw.circle(self.screen, eye_color, (cx - 8, cy - 6), 2)
        pygame.draw.circle(self.screen, eye_color, (cx + 8, cy - 6), 2)

        mouth_rect = pygame.Rect(0, 0, 20, 14)
        mouth_rect.center = (cx, cy + 6)
        if self._smiley_state == "lose":
            pygame.draw.arc(self.screen, eye_color, mouth_rect, math.radians(20), math.radians(160), 2)
            for dx in (-8, 8):
                pygame.draw.line(self.screen, eye_color, (cx + dx - 2, cy - 8), (cx + dx + 2, cy - 4), 2)
                pygame.draw.line(self.screen, eye_color, (cx + dx + 2, cy - 8), (cx + dx - 2, cy - 4), 2)
        elif self._smiley_state == "win":
            pygame.draw.arc(self.screen, eye_color, mouth_rect, math.radians(200), math.radians(340), 2)
        else:
            pygame.draw.arc(self.screen, eye_color, mouth_rect, math.radians(200), math.radians(340), 2)

    def _draw_tile(self, r: int, c: int, trigger=None):
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

    def _draw_board(self):
        if self.engine is None:
            return
        for r in range(self.engine.rows):
            for c in range(self.engine.cols):
                self._draw_tile(r, c)

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

    def run(self):
        while True:
            self.clock.tick(60)

            for e in pygame.event.get():
                self._handle_event(e)

            if self._overlay is not None and self._overlay.closed:
                self._overlay = None
                self._overlay_ok_rect = None
                if self._smiley_state == "pressed":
                    self._smiley_state = "idle"

            if self.engine is not None and self.engine.game_over and self._smiley_state == "idle":
                self._smiley_state = "win" if self.engine.won else "lose"

            self.screen.fill(pygame.Color(self.palette["bg"]))
            self._draw_panel()
            self._draw_board()

            if self._overlay is not None:
                self._draw_overlay()

            pygame.display.flip()


def run():
    MinesweeperPygameApp().run()