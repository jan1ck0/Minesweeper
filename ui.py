import time
import tkinter as tk
from tkinter import messagebox
from engine import Difficulty, MinesweeperEngine, ScoreManager


class MinesweeperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Minesweeper")
        self.resizable(False, False)

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
        self.configure(bg=self.palette["bg"])

        self.difficulties = [
            Difficulty("Easy", 9, 9, 10),
            Difficulty("Medium", 16, 16, 40),
            Difficulty("Hard", 16, 30, 99),
        ]

        self.tile = 26
        self.pad = 10

        self.engine = None
        self._timer_job = None
        self._start_time = None

        self._mouse_down = {1: False, 2: False, 3: False}
        self._hover_cell = None
        self._pressed_cells = set()
        self._smiley_state = "idle"

        self._build_ui()
        self.new_game(self.difficulties[0])

    def _build_ui(self):
        self.panel = tk.Frame(self, bg=self.palette["panel"], padx=self.pad, pady=self.pad)
        self.panel.grid(row=0, column=0, sticky="ew")

        self.diff_var = tk.StringVar(value=self.difficulties[0].name)
        self.diff_menu = tk.OptionMenu(self.panel, self.diff_var, *[d.name for d in self.difficulties], command=self._on_diff_change)
        self.diff_menu.config(
            width=10,
            bg=self.palette["panel_edge"],
            fg=self.palette["text"],
            activebackground=self.palette["panel_edge"],
            activeforeground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
        )
        self.diff_menu.grid(row=0, column=0, padx=(0, 10))

        self.highscores_btn = tk.Button(
            self.panel,
            text="Highscores",
            command=self._show_highscores,
            bg=self.palette["panel_edge"],
            fg=self.palette["text"],
            activebackground=self.palette["panel_edge"],
            activeforeground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
        )
        self.highscores_btn.grid(row=0, column=1, padx=(0, 10))

        self.mine_counter = tk.Label(
            self.panel,
            text="000",
            width=5,
            anchor="center",
            bg="#000000",
            fg="#ef4444",
            font=("Consolas", 18, "bold"),
        )
        self.mine_counter.grid(row=0, column=2, padx=(0, 10))

        self.smiley = tk.Canvas(self.panel, width=44, height=44, bg=self.palette["panel"], highlightthickness=0)
        self.smiley.grid(row=0, column=3, padx=(0, 10))
        self.smiley.bind("<Button-1>", lambda e: self._smiley_press())
        self.smiley.bind("<ButtonRelease-1>", lambda e: self._smiley_release())

        self.timer = tk.Label(
            self.panel,
            text="000",
            width=5,
            anchor="center",
            bg="#000000",
            fg="#ef4444",
            font=("Consolas", 18, "bold"),
        )
        self.timer.grid(row=0, column=4)

        self.board_frame = tk.Frame(self, bg=self.palette["bg"], padx=self.pad, pady=self.pad)
        self.board_frame.grid(row=1, column=0)

        self.canvas = tk.Canvas(self.board_frame, bg=self.palette["bg"], highlightthickness=0)
        self.canvas.grid(row=0, column=0)

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_button_down)
        self.canvas.bind("<Button-2>", self._on_button_down)
        self.canvas.bind("<Button-3>", self._on_button_down)
        self.canvas.bind("<ButtonRelease-1>", self._on_button_up)
        self.canvas.bind("<ButtonRelease-2>", self._on_button_up)
        self.canvas.bind("<ButtonRelease-3>", self._on_button_up)

        self.bind("<Escape>", lambda e: self._safe_new_game())
        self.bind("<F2>", lambda e: self._safe_new_game())

    def _on_diff_change(self, _):
        d = next((x for x in self.difficulties if x.name == self.diff_var.get()), self.difficulties[0])
        self.new_game(d)

    def _safe_new_game(self):
        d = next((x for x in self.difficulties if x.name == self.diff_var.get()), self.difficulties[0])
        self.new_game(d)

    def new_game(self, difficulty: Difficulty):
        if self._timer_job is not None:
            try:
                self.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None

        self.engine = MinesweeperEngine(difficulty.rows, difficulty.cols, difficulty.mines)
        self._start_time = None
        self.timer.config(text="000")
        self._smiley_state = "idle"

        w = self.engine.cols * self.tile
        h = self.engine.rows * self.tile
        self.canvas.config(width=w, height=h)

        self._mouse_down = {1: False, 2: False, 3: False}
        self._hover_cell = None
        self._pressed_cells = set()

        self._update_mine_counter()
        self._redraw_all()

    def _update_mine_counter(self):
        left = self.engine.mines_total - len(self.engine.flags)
        left = max(-99, min(999, left))
        sign = "-" if left < 0 else ""
        self.mine_counter.config(text=f"{sign}{abs(left):03d}"[-3:])

    def _tick_timer(self):
        if self.engine is None or self.engine.game_over:
            return
        if self._start_time is None:
            self.timer.config(text="000")
            return
        elapsed = int(time.time() - self._start_time)
        elapsed = min(999, max(0, elapsed))
        self.timer.config(text=f"{elapsed:03d}")
        self._timer_job = self.after(250, self._tick_timer)

    def _ensure_timer_started(self):
        if self._start_time is not None:
            return
        self._start_time = time.time()
        self._tick_timer()

    def _smiley_press(self):
        self._smiley_state = "pressed"
        self._draw_smiley()

    def _smiley_release(self):
        self._safe_new_game()

    def _cell_from_xy(self, x: int, y: int):
        if self.engine is None:
            return None
        c = x // self.tile
        r = y // self.tile
        if 0 <= r < self.engine.rows and 0 <= c < self.engine.cols:
            return r, c
        return None

    def _on_motion(self, e):
        cell = self._cell_from_xy(e.x, e.y)
        if cell != self._hover_cell:
            self._hover_cell = cell
            self._redraw_all()

    def _on_leave(self, _):
        if self._hover_cell is not None:
            self._hover_cell = None
            self._redraw_all()

    def _on_button_down(self, e):
        if self.engine is None:
            return
        if self.engine.game_over:
            return

        self._mouse_down[e.num] = True
        cell = self._cell_from_xy(e.x, e.y)
        self._pressed_cells = set()

        if cell is not None:
            r, c = cell
            if (e.num == 2) or (self._mouse_down[1] and self._mouse_down[3]) or (self._mouse_down[3] and self._mouse_down[1]):
                self._pressed_cells = set(self.engine.neighbors(r, c))
            else:
                self._pressed_cells = {(r, c)}

        self._redraw_all()

    def _on_button_up(self, e):
        if self.engine is None:
            return

        chord_intent = False
        if e.num == 2:
            chord_intent = True
        elif e.num in (1, 3):
            other = 3 if e.num == 1 else 1
            chord_intent = self._mouse_down.get(other, False)

        self._mouse_down[e.num] = False
        cell = self._cell_from_xy(e.x, e.y)

        action = None
        if cell is not None and not self.engine.game_over:
            r, c = cell
            if e.num == 3:
                self.engine.toggle_flag(r, c)
                self._update_mine_counter()
            else:
                if chord_intent:
                    action = self.engine.chord(r, c)
                else:
                    action = self.engine.reveal(r, c)

                if action is not None and action.get("type") != "noop" and self._start_time is None and not self.engine.first_click:
                    self._ensure_timer_started()

        self._pressed_cells = set()
        self._redraw_all(trigger=action)

        if action is not None:
            if action.get("type") == "boom":
                self._smiley_state = "lose"
                self._draw_smiley()
                messagebox.showerror("Minesweeper", "Boom! You hit a mine.")
            elif action.get("type") == "win":
                elapsed = int(time.time() - self._start_time) if self._start_time else 0
                diff_name = self.diff_var.get()
                for d in self.difficulties:
                    if d.rows == self.engine.rows and d.cols == self.engine.cols and d.mines == self.engine.mines_total:
                        diff_name = d.name
                        break
                ScoreManager.add_score(diff_name, elapsed)

                self.engine.flags = set(self.engine.mines)
                self._update_mine_counter()
                self._redraw_all(trigger=action)
                self._smiley_state = "win"
                self._draw_smiley()
                messagebox.showinfo("Minesweeper", "You win!")

    def _redraw_all(self, trigger=None):
        self.canvas.delete("all")
        self._draw_board(trigger=trigger)
        self._draw_smiley()

    def _draw_smiley(self):
        self.smiley.delete("all")
        x0, y0, x1, y1 = 4, 4, 40, 40
        fill = "#fbbf24" if self._smiley_state not in ("lose", "win") else ("#22c55e" if self._smiley_state == "win" else "#ef4444")
        outline = self.palette["panel_edge"]
        self.smiley.create_oval(x0, y0, x1, y1, fill=fill, outline=outline, width=2)

        cx, cy = 22, 22
        if self._smiley_state == "pressed":
            self.smiley.create_oval(cx - 10, cy - 10, cx + 10, cy + 10, outline=outline)
            return

        self.smiley.create_oval(14, 16, 18, 20, fill="#111827", outline="")
        self.smiley.create_oval(26, 16, 30, 20, fill="#111827", outline="")

        if self._smiley_state == "lose":
            self.smiley.create_line(14, 16, 18, 20, fill="#111827", width=2)
            self.smiley.create_line(18, 16, 14, 20, fill="#111827", width=2)
            self.smiley.create_line(26, 16, 30, 20, fill="#111827", width=2)
            self.smiley.create_line(30, 16, 26, 20, fill="#111827", width=2)
            self.smiley.create_arc(14, 26, 30, 38, start=20, extent=140, style="arc", outline="#111827", width=2)
        elif self._smiley_state == "win":
            self.smiley.create_arc(14, 22, 30, 38, start=200, extent=140, style="arc", outline="#111827", width=2)
        else:
            self.smiley.create_arc(14, 22, 30, 36, start=200, extent=140, style="arc", outline="#111827", width=2)

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

    def _draw_tile(self, r: int, c: int, trigger=None):
        x0 = c * self.tile
        y0 = r * self.tile
        x1 = x0 + self.tile
        y1 = y0 + self.tile

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

        self.canvas.create_rectangle(x0, y0, x1, y1, fill=bg, outline=self.palette["shadow"], width=1)

        if self.engine.game_over and is_mine:
            self.canvas.create_oval(x0 + 7, y0 + 7, x1 - 7, y1 - 7, fill=self.palette["mine"], outline="")
            self.canvas.create_line(x0 + 6, y0 + 13, x1 - 6, y0 + 13, fill=self.palette["mine"], width=2)
            self.canvas.create_line(x0 + 13, y0 + 6, x0 + 13, y1 - 6, fill=self.palette["mine"], width=2)
            return

        if not is_revealed and is_flag:
            self.canvas.create_polygon(
                x0 + 9,
                y0 + 19,
                x0 + 9,
                y0 + 7,
                x0 + 19,
                y0 + 11,
                fill=self.palette["flag"],
                outline="",
            )
            self.canvas.create_line(x0 + 9, y0 + 7, x0 + 9, y0 + 21, fill=self.palette["mine"], width=2)
            self.canvas.create_line(x0 + 6, y0 + 21, x0 + 14, y0 + 21, fill=self.palette["mine"], width=2)
            return

        if is_revealed:
            n = self.engine.adj[r][c]
            if n > 0:
                self.canvas.create_text(
                    x0 + self.tile // 2,
                    y0 + self.tile // 2 + 1,
                    text=str(n),
                    fill=self._num_color(n),
                    font=("Segoe UI", 12, "bold"),
                )

    def _draw_board(self, trigger=None):
        for r in range(self.engine.rows):
            for c in range(self.engine.cols):
                self._draw_tile(r, c, trigger=trigger)

    def _show_highscores(self):
        top = tk.Toplevel(self)
        top.title("Highscores")
        top.resizable(False, False)
        top.configure(bg=self.palette["bg"])

        tk.Label(
            top,
            text="Top 15 best times",
            bg=self.palette["bg"],
            fg=self.palette["text"],
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(10, 5))

        row = 1
        for diff in self.difficulties:
            scores = ScoreManager.get_top_scores(diff.name)
            tk.Label(
                top,
                text=f"{diff.name}",
                bg=self.palette["bg"],
                fg=self.palette["subtext"],
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            ).grid(row=row, column=0, sticky="w", padx=(20, 10), pady=(8, 0))
            row += 1

            if not scores:
                tk.Label(
                    top,
                    text="No scores yet",
                    bg=self.palette["bg"],
                    fg=self.palette["text"],
                    font=("Consolas", 10),
                    anchor="w",
                ).grid(row=row, column=0, columnspan=2, sticky="w", padx=(35, 20), pady=(2, 0))
                row += 1
                continue

            for i, s in enumerate(scores[:15], start=1):
                tk.Label(
                    top,
                    text=f"{i:>2}.",
                    bg=self.palette["bg"],
                    fg=self.palette["text"],
                    font=("Consolas", 10),
                    anchor="e",
                    width=3,
                ).grid(row=row, column=0, sticky="e", padx=(35, 0), pady=(2, 0))
                tk.Label(
                    top,
                    text=f"{s} s",
                    bg=self.palette["bg"],
                    fg=self.palette["text"],
                    font=("Consolas", 10),
                    anchor="w",
                ).grid(row=row, column=1, sticky="w", padx=(10, 20), pady=(2, 0))
                row += 1

        tk.Button(
            top,
            text="Close",
            command=top.destroy,
            bg=self.palette["panel_edge"],
            fg=self.palette["text"],
            activebackground=self.palette["panel_edge"],
            activeforeground=self.palette["text"],
            relief="flat",
            highlightthickness=0,
        ).grid(row=row, column=0, columnspan=2, pady=(10, 10))