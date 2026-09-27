from pathlib import Path
from dataclasses import dataclass
import argparse

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
            self.runtime_dir / "locks" / "alarmd.lock"
        )

        self.socket_path = self.runtime_dir / 'sockets' / 'alarmd.sock'
        
        self.alarm_manager = AlarmManager( config.alarmd )

        self.server = None
        self.running = False
    #

    def run(self):
        print("[alarmd] Starting alarm daemon...")

        self.lock.acquire()
        print(f"[alarmd] Lock acquired: {self.lock.lock_path}")

        self._setup_socket()
        print(f"[alarmd] Listening on socket: {self.socket_path}")

        # Install signals
        signal.signal(
            signal.SIGTERM,
            self.sigterm_handler
        )

        signal.signal(
            signal.SIGINT,
            self.sigterm_handler
        )

        self.running = True
        print("[alarmd] Alarm daemon is running.")

        try:
            self.event_loop()
        finally:
            print("[alarmd] Cleaning up...")
            self.cleanup()
            print("[alarmd] Alarm daemon stopped.")
        #
    #

    def event_loop(self):

        while self.running:
            self._poll_socket()
    #

    def _poll_socket(self):
        try:
            conn, _ = self.server.accept()
        except BlockingIOError:
            # There is currently no connection
            return
    
        print("[alarmd] Received connection.")
    
        try:
            try:
                data = conn.recv(4096)
            except BlockingIOError:
                #There is a client connected but has not yet sent anything
                return
    
            if not data:
                print("[alarmd] Empty request received.")
                return
    
            print(f"[alarmd] Received request: {data.decode('utf-8', errors='replace')}")
    
            try:
                request = json.loads(
                    data.decode()
                )
            except json.JSONDecodeError:
                decoded = data.decode("utf-8", errors="replace")
    
                print("[alarmd] ERROR: Invalid JSON request.")
    
                response = {
                    "success": False,
                    "message": (
                        f"Invalid JSON request: \n"
                        f"    {decoded}"
                    )
                }
            else:
                print(
                    f"[alarmd] Request type: "
                    f"{request.get('msg_type')}"
                )
    
                try:
                    response = self._handle_request(request)
                except Exception as err:
                    print(
                        f"[alarmd] ERROR while handling request: "
                        f"{type(err).__name__}: {err}"
                    )
    
                    response = {
                        "success": False,
                        "message": f"Request error: {err}"
                    }
    
            print(f"[alarmd] Sending response: {response}")
    
            conn.sendall(
                json.dumps(response).encode()
            )
    
        finally:
            conn.close()
        #
    #

        
    def _handle_request(self, request):
        request_type = request.get("msg_type")
        if request_type is None:
            print("[alarmd] ERROR: Request type missing.")
            #Probably I shall raise here, because this is a protocol error
            return {
                "success": False,
                "message": f'Request type missing'
            }
        #

        print(f"[alarmd] DEBUG: Handling request type '{request_type}'.")

        if request_type == "event":
            print("[alarmd] DEBUG: Forwarding alarm event to AlarmManager.")
            return self.alarm_manager.process_event_request(request.get('payload'))
        elif request_type == "shutdown":
            print("[alarmd] INFO: Shutdown request received.")
            self.shutdown()
            return {'success': True}

        print(f"[alarmd] ERROR: Unknown request type '{request_type}'.")
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
        print("[alarmd] INFO: Shutdown requested.")
        self.running = False
    #

    def sigterm_handler(self, signum, frame):
        self.shutdown()
    #

def main():

    parser = argparse.ArgumentParser(
        prog="scd",
        description="Slow Control Alarm Daemon"
    )

    parser.add_argument(
        "config_file",
        help="Path to the daemon configuration file"
    )

    args = parser.parse_args()

    daemon = None
    fail = False

    try:

        daemon = AlarmDaemon(
            args.config_file
        )

        daemon.run()

    except KeyboardInterrupt:

        print("Stopping daemon...")

    except Exception as e:

        print(f"ERROR: {e}")
        fail = True

    finally:

        if daemon is not None:
            daemon.cleanup()

    return int(fail)


if __name__ == "__main__":
    raise SystemExit(main())