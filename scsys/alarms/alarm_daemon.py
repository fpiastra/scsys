from pathlib import Path
from dataclasses import dataclass

import socket
import signal
import json

from .alarm_manager import AlarmManager

from ..scd.config_manager import ConfigManager
from ..scd.lock import LockManager

class AlarmDaemon:
    def __init__(self, config_file:str):
        cfgmgr = ConfigManager(config_file)

        config = cfgmgr.load() #From here I will just need the runtime directory and the few things needed for the alarm system

        self.runtime_dir = Path(config.runtime_dir)
        self.lock = LockManager(
            self.runtime_dir / 'alarmd.lock'
        )

        self.socket_path = self.runtime_dir / 'sockets' / 'alarmd.sock'
        
        self.alarm_manager = AlarmManager()

        self.server = None
        self.running = False
    #

    def run(self):
        self.lock.acquire()

        self._setup_socket()

        #Install signals
        signal.signal(
            signal.SIGTERM,
            self.sigterm_handler
        )
        
        signal.signal(
            signal.SIGINT,
            self.sigterm_handler
        )

        self.running = True

        try:
            self.event_loop()
        finally:
            self.cleanup()
    #

    def event_loop(self):

        while self.running:
            self._poll_socket()
    #

    def _poll_socket(self):
        try:
            conn, _ = self.server.accept()
        except BlockingIOError:
            #There is currently no connection
            return
        #
        
        try:
            data = conn.recv(4096)
            if not data:
                return
            #
            try:
                request = json.loads(
                    data.decode()
                )
            except json.JSONDecodeError:
                decoded = data.decode("utf-8", errors="replace")

                response = {
                    "success": False,
                    "message": (
                        f"Invalid JSON request: \n"
                        f"    {decoded}"
                    )
                }
            else:
                try:
                    response = self._handle_request(request)
                except Exception as err:
                    response = {
                        "success": False,
                        "message": f"Request error: {err}"
                    }
                #
            #
            conn.sendall(
                json.dumps(response).encode()
            )
        finally:
            conn.close()
        #
    #

        
    def _handle_request(self, request):
        request_type = request.get("command")
        if request_type is None:
            #Probably I shall raise here, because this is a protocol error
            return {
                "success": False,
                "message": f'Request type missing'
            }
        #

        if request_type == "event":
            return self.alarm_manager.process_event_request(request.get('payload'))
        elif request_type == "shutdown":
            self.shutdown()
            return {'success': True}

        return {
            "success": False,
            "message": f'Unknown request type ({request_type})'
        }

    def _setup_socket(self):
        self.socket_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )
        #
        if self.socket_path.exists():
            self.socket_path.unlink()
        #
        self.server = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM
        )
        #
        self.server.bind(
            str(self.socket_path)
        )
        #
        self.server.listen(5)
        self.server.setblocking(False)
    #

    def cleanup(self):
        if self.server is not None:
            self.server.close()
        #
        self.lock.release()
        if self.socket_path.exists():
            self.socket_path.unlink()
        #
    #

    def shutdown(self):
        self.running = False
    #

    def sigterm_handler(self, signum, frame):
        self.shutdown()
    #

