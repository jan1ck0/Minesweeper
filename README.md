# Minesweeper Multiplayer

## O projekte

Minesweeper Multiplayer je implementácia klasickej hry Minesweeper vytvorená v jazyku Python pomocou knižnice Pygame. Hra podporuje režim pre jedného hráča aj multiplayer cez lokálnu sieť (LAN).

## Funkcie

- Singleplayer režim
- Multiplayer LAN režim
- Automatické vyhľadávanie serverov
- Lobby systém
- Integrovaný chat
- Bodovací systém
- Rekordy a najlepšie časy
- Bezpečný prvý klik
- Označovanie mín vlajkami
- Automatické odkrývanie prázdnych polí
- Chording (rýchle odkrývanie susedných polí)

## Obtiažnosti

- Easy (9×9, 10 mín)
- Medium (16×16, 40 mín)
- Hard (16×30, 99 mín)

## Použité technológie

- Python
- Pygame
- TCP komunikácia
- UDP komunikácia
- HTTP server
- JSON

## Spustenie

### Klient

```bash
python main.py
```

### Server

```bash
python main.py --server
```

## Súbory projektu

- `main.py` – spustenie hry alebo servera
- `engine.py` – herná logika
- `ui.py` – grafické rozhranie
- `network.py` – sieťová komunikácia
- `server.py` – multiplayer server

## Cieľ hry

Cieľom hry je odkryť všetky polia, ktoré neobsahujú mínu. Hráč prehrá po kliknutí na mínu a vyhrá po odkrytí všetkých bezpečných polí.