import os
import argparse
from pathlib import Path
import socket
import json
import yaml
import signal

from .process_manager import ProcessManager
from .device_registry import DeviceRegistry
from .config_manager import ConfigManager
from .devs_state import DevsState
from .lock import LockManager
from ..devices import discover_devices


class SlowControlDaemon:

    def __init__(self, config_file):

        cfgmgr = ConfigManager(config_file)

        self.config = cfgmgr.load()

        self.runtime_dir = self.config.runtime_dir

        discover_devices(
            self.config.devices_dir
        )
        
        self.socket_path = self.config.socket_path

        self.lock_path = self.config.lock_path

        self.lock = LockManager(
            self.config.lock_path
        )

        self.registry = DeviceRegistry(
            self.config.setup_file
        )

        self.pm = ProcessManager(
            runtime_dir=self.config.runtime_dir
        )

        self.devs_state = DevsState(
            self.runtime_dir
        )

        self.running = False
    #

    def run(self):

        self.lock.acquire()

        self.registry.load()

        self.initialize_devs_state()

        self.setup_socket()

        self.autostart_devices()

        signal.signal(
            signal.SIGTERM,
            self.sigterm_handler
        )

        signal.signal(
            signal.SIGINT,
            self.sigterm_handler
        )

        self.running = True

        self.event_loop()
    #

    def event_loop(self):
        while self.running:
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                continue
            
            self.handle_connection(conn)
        #
    #

    def setup_socket(self):

        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        if self.socket_path.exists():
            self.socket_path.unlink()

        self.server = socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM
        )

        self.server.bind(str(self.socket_path))
        self.server.settimeout(1.0)
        self.server.listen(5)

        print(
            f"Listening on {str(self.socket_path)}"
        )
    #

    def initialize_devs_state(self):
        for dev in self.registry.enabled_devices():

            if self.devs_state.get(dev.name) is not None:
                continue
            #
            if dev.autostart:
                self.devs_state.set(
                    dev.name,
                    DevsState.RUNNING
                )
            else:
                self.devs_state.set(
                    dev.name,
                    DevsState.STOPPED
                )
            #
        #
    #

    def autostart_devices(self):
        for dev in self.registry.autostart_devices():
            self.pm.start(dev)
        #
    #

    def handle_connection(self, conn):

        data = conn.recv(4096)

        request = json.loads(data.decode())

        print(f"Received: {request}")

        response = self.handle_request(request)

        conn.sendall(
            json.dumps(response).encode()
        )

        conn.close()
    #

    def handle_request(self, request):
        if request["object"] == "scd":
            return self.handle_scd(request)

        elif request["object"] == "device":
            return self.handle_device(request)
        #
        return {
            "success": False,
            "message": f"Unknown object '{request['object']}'"
        }
    #

    def handle_scd(self, request):
        # This method actually returns the status of each known device, so we have to request a list of them beforehand
        if request['action'] == 'status':
            return self.handle_scd_status()
        #
        act = request["action"]
        return {
            "success": False,
            "message": f"Unknown action '{act}' for the scd."
        }
    #

    def handle_scd_status(self):
        devices = []

        for name in self.registry.devices:
            runtime_info = self.pm.status(name)

            devices.append(
                {
                    "name": name,
                    "requested_state": self.devs_state.get(name),
                    **(runtime_info or {})
                }
            )

        return {
            "success": True,
            "pid": os.getpid(),
            "devices": devices
        }
    #

    def handle_device(self, request):
        if request['action'] == 'start':
            return self.start_device(request['device'])
        #
        elif request['action'] == 'stop':
            return self.stop_device(request['device'])
        #
        elif request['action'] == 'restart':
            return self.restart_device(request['device'])
        #
        elif request['action'] == 'status':
            return self.device_status(request['device'])
        #
        elif request['action'] == 'device_list':
            return self.device_list()
        #
        elif request["action"] == "get":
            return self.send_to_device(
                request["device"],
                {
                    "command": "get",
                    "varname": request["varname"]
                }
            )
        #
        elif request["action"] == "set":
            return self.send_to_device(
                request["device"],
                {
                    "command": "set",
                    "varname": request["varname"],
                    "value": request["value"]
                }
            )
        #

        action = request["action"]
        return {
            "success": False,
            "message": f'Unknown device action "{action}"'
        }
    #

    def start_device(self, device):
        devinfo = self.registry.get(device)
        if devinfo is None:
            return {
                "success": False,
                "message": f'Unknown device "{device}"'
            }
        #

        self.devs_state.set(device, DevsState.RUNNING)

        ok = self.pm.start(devinfo)

        return {
            "success": ok
        }
    #

    def stop_device(self, device):

        self.devs_state.set(device, DevsState.STOPPED)

        ok = self.pm.stop(device)
        
        return {
            "success": ok
        }
    #

    def restart_device(self, device):
        device_info = self.registry.get(device)
        ok = self.pm.restart(device_info)
        
        return {
            "success": ok
        }
    #

    def send_to_device(
            self,
            device,
            request
    ):
        #Check if the device exists and is active
        if not self.pm.is_running(device):
            return{
                "success": False,
                "message": f'Device "{device}" not running.'
            }
        #

        payload = json.dumps(request)
        socket_path = Path(self.config.runtime_dir) / "sockets" / (str(device)+'.sock')
        
        with socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM
        ) as sock:
            try:
                sock.connect(str(socket_path))
            except (FileNotFoundError, ConnectionRefusedError):
                return {
                    "success": False,
                    "message": f'Socket of device "{device}" not found or connection was refused.'
                }
            #
            sock.sendall(payload.encode())
            response = sock.recv(4096)
        #
        try:
            ret = json.loads(response.decode())
        except json.JSONDecodeError as err:
            return{
                "success": False,
                "message": f'Invalid JSON response from device "{device}": {err}.'
            }
        except Exception as err:
            return{
                "success": False,
                "message": f'Error in the response from device "{device}": {err}.'
            }
        return ret
    #
        

    def device_status(self, device):
        devinfo = self.registry.get(device)
        if devinfo is None:
            return {
                "success": False,
                "message": f'Unknown device "{device}"'
            }
        
        runtime_info = self.pm.status(device)
        if runtime_info is None:
            return {
                "success": False,
                "message": f'Failed to get runtime status of device "{device}"'
            }
        

        response = {
            "success": True,
            "requested_state": self.devs_state.get(device)
            **runtime_info
        }
        
        if not response["running"]:
            return response
        
        device_status = self.send_to_device(
            device,
            {
                "command": "status"
            }
        )
        
        response['device_status'] = device_status
        return response
    #

    def device_list(self):
        return {
            "success": True,
            "devices": list(
                self.registry.devices.keys()
            )
        }
    #

    def get_pid(self):
        return -1 #Do it properly
    #

    def sigterm_handler(self, signum, frame):
        self.shutdown()

    def shutdown(self):
        self.running = False

    def cleanup(self):
        self.lock.release()
        if self.socket_path.exists():
            self.socket_path.unlink()
    #


def main():

    parser = argparse.ArgumentParser(
        prog="scd",
        description="Slow Control Daemon"
    )

    parser.add_argument(
        "config_file",
        help="Path to the daemon configuration file"
    )

    args = parser.parse_args()

    daemon = None
    fail = False

    try:

        daemon = SlowControlDaemon(
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