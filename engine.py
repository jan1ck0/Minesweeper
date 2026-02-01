import json
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Difficulty:
    name: str
    rows: int
    cols: int
    mines: int


class MinesweeperEngine:
    def __init__(self, rows: int, cols: int, mines: int):
        self.rows = rows
        self.cols = cols
        self.mines_total = mines
        self.reset()

    def reset(self):
        self.first_click = True
        self.game_over = False
        self.won = False

        self.mines = set()
        self.adj = [[0 for _ in range(self.cols)] for _ in range(self.rows)]
        self.revealed = [[False for _ in range(self.cols)] for _ in range(self.rows)]
        self.flags = set()

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def neighbors(self, r: int, c: int):
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = r + dr, c + dc
                if self.in_bounds(nr, nc):
                    yield nr, nc

    def _place_mines(self, safe_r: int, safe_c: int):
        forbidden = {(safe_r, safe_c)} | set(self.neighbors(safe_r, safe_c))
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
                    self.adj[r][c] = sum((nr, nc) in self.mines for nr, nc in self.neighbors(r, c))

    def toggle_flag(self, r: int, c: int):
        if self.game_over or self.revealed[r][c]:
            return
        if (r, c) in self.flags:
            self.flags.remove((r, c))
        else:
            self.flags.add((r, c))

    def reveal(self, r: int, c: int):
        if self.game_over:
            return {"type": "noop"}
        if (r, c) in self.flags or self.revealed[r][c]:
            return {"type": "noop"}

        if self.first_click:
            self._place_mines(r, c)
            self.first_click = False

        if (r, c) in self.mines:
            self.game_over = True
            self.won = False
            return {"type": "boom", "trigger": (r, c)}

        revealed = self._flood_reveal(r, c)
        if self._check_win():
            return {"type": "win", "revealed": revealed}
        return {"type": "reveal", "revealed": revealed}

    def chord(self, r: int, c: int):
        if self.game_over or self.first_click:
            return {"type": "noop"}
        if not self.revealed[r][c]:
            return {"type": "noop"}
        n = self.adj[r][c]
        if n <= 0:
            return {"type": "noop"}

        flagged_around = sum((nr, nc) in self.flags for nr, nc in self.neighbors(r, c))
        if flagged_around != n:
            return {"type": "noop"}

        revealed_total = set()
        for nr, nc in self.neighbors(r, c):
            if (nr, nc) in self.flags or self.revealed[nr][nc]:
                continue
            if (nr, nc) in self.mines:
                self.game_over = True
                self.won = False
                return {"type": "boom", "trigger": (nr, nc)}
            revealed_total |= self._flood_reveal(nr, nc)

        if self._check_win():
            return {"type": "win", "revealed": revealed_total}
        return {"type": "reveal", "revealed": revealed_total}

    def _flood_reveal(self, r: int, c: int):
        revealed = set()
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            if self.revealed[cr][cc] or (cr, cc) in self.flags:
                continue
            if (cr, cc) in self.mines:
                continue
            self.revealed[cr][cc] = True
            revealed.add((cr, cc))
            if self.adj[cr][cc] == 0:
                for nr, nc in self.neighbors(cr, cc):
                    if not self.revealed[nr][nc] and (nr, nc) not in self.mines:
                        stack.append((nr, nc))
        return revealed

    def _check_win(self) -> bool:
        if self.game_over:
            return self.won
        revealed_count = sum(1 for r in range(self.rows) for c in range(self.cols) if self.revealed[r][c])
        if revealed_count == self.rows * self.cols - self.mines_total:
            self.game_over = True
            self.won = True
            return True
        return False


class ScoreManager:
    FILE = "scores.json"
    TOP_N = 15

    @staticmethod
    def load():
        try:
            with open(ScoreManager.FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    @staticmethod
    def save(scores):
        with open(ScoreManager.FILE, "w", encoding="utf-8") as f:
            json.dump(scores, f, indent=2, ensure_ascii=False)

    @staticmethod
    def add_score(difficulty_name: str, seconds: int):
        scores = ScoreManager.load()
        if difficulty_name not in scores:
            scores[difficulty_name] = []
        scores[difficulty_name].append(seconds)
        scores[difficulty_name] = sorted(set(scores[difficulty_name]))[: ScoreManager.TOP_N]
        ScoreManager.save(scores)

    @staticmethod
    def get_top_scores(difficulty_name: str):
        scores = ScoreManager.load()
        return scores.get(difficulty_name, [])
