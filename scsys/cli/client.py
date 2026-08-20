import os
from pathlib import Path
import socket
import json

DEFAULT_RUNTIME_DIR = Path("/run/scsys")

RUNTIME_DIR = Path(
    os.environ.get(
        "SCSYS_RUNTIME_DIR",
        DEFAULT_RUNTIME_DIR
    )
)

SOCKET_PATH = RUNTIME_DIR / "scd.sock"

def send(request:dict):

    print(f"DEBUG: sending {request}")

    payload = json.dumps(request)

    with socket.socket(
        socket.AF_UNIX,
        socket.SOCK_STREAM
    ) as sock:
        try:
            sock.connect(str(SOCKET_PATH))
        except FileNotFoundError:
            return {
                "success": False,
                "error": "mxlscd is not running"
            }

        sock.sendall(payload.encode())

        response = sock.recv(4096)
    #

    return json.loads(response.decode())
#