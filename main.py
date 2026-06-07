import sys
from ui import run
from server import start_all_servers

if __name__ == "__main__":
    if "--server" in sys.argv:
        name = "Minesweeper LAN Server"
        try:
            idx = sys.argv.index("--server")
            if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("-"):
                name = sys.argv[idx + 1]
        except ValueError:
            pass
        
        print(f"Starting Minesweeper server: '{name}'")
        try:
            start_all_servers(name)
        except KeyboardInterrupt:
            print("\nServer shut down.")
    else:
        run()
