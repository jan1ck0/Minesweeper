import struct
import json
import socket

UDP_PORT = 50000
HTTP_PORT = 50001
TCP_PORT = 50002

DISCOVER_MSG = b"MINESWEEPER_DISCOVER"
OFFER_PREFIX = "MINESWEEPER_OFFER"

def recv_exact(sock: socket.socket, n: int) -> bytes | None:
    """Helper function to recv exactly n bytes or return None if EOF is reached."""
    data = b""
    while len(data) < n:
        try:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        except (socket.error, ConnectionResetError):
            return None
    return data

def recv_msg(sock: socket.socket) -> dict | None:
    """Receives a length-prefixed JSON message from the TCP socket."""
    raw_msglen = recv_exact(sock, 4)
    if not raw_msglen:
        return None
    msglen = struct.unpack(">I", raw_msglen)[0]
    data = recv_exact(sock, msglen)
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except json.JSONDecodeError:
        return None

def send_msg(sock: socket.socket, data: dict) -> bool:
    """Sends a length-prefixed JSON message over the TCP socket."""
    try:
        serialized = json.dumps(data).encode("utf-8")
        sock.sendall(struct.pack(">I", len(serialized)) + serialized)
        return True
    except (socket.error, ConnectionResetError):
        return False
