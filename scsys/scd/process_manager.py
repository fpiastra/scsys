import os
import signal
import psutil
from datetime import (datetime, timezone)
import time
from pathlib import Path

import socket

import subprocess
import sys

import json
import pickle

from dataclasses import dataclass

from ..devices.base import ScDevice
from .device_info import DeviceInfo

@dataclass
class LaunchInfo:
    device: ScDevice

class ProcessManager:

    def __init__(self, runtime_dir: Path):
        self.runtime_dir = Path(runtime_dir)
    #

    def start(self, device_info: DeviceInfo):

        if self.is_running(device_info.name):
            return False
        #

        #Create the launch directory inside the runtime directory
        launch_dir = self.runtime_dir / "launch"
        launch_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        devices_dir = self.runtime_dir / "devices"
        devices_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        sockets_dir = self.runtime_dir / "sockets"
        sockets_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        runtime_info = {
            "name": device_info.name,
            "type": device_info.type_name,
            "config": device_info.device_config,
            "rconfig": device_info.runtime_config,
            "watchdog": device_info.watchdog_config,
            "pid": None,
            "process_started": None,
            "heartbeat": None
        }

        with self.runtime_file(device_info.name).open("w") as f:
            json.dump(
                runtime_info,
                f,
                indent=4
            )
        #

        device = device_info.create_device(
            runtime_dir=self.runtime_dir
        )
        
        with self.launch_file(device_info.name).open("wb") as f:
            pickle.dump(
                LaunchInfo(device=device),
                f
            )
        #

        try:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "scsys.device_runner",
                    str(self.launch_file(device_info.name))
                ],
                start_new_session=True,
            )
        #
        except Exception as err:
            print(f'ERROR: failed to launch the process for device "{device_info.name}": {err}')
            self.launch_file(device_info.name).unlink(missing_ok=True)
            self.runtime_file(device_info.name).unlink(missing_ok=True)
            return False
        #

        #
        # Wait up to 5 seconds for the device to start.
        #
        timeout = 5.0
        poll_interval = 0.1

        t0 = time.monotonic()

        while True:
            # Check whether the child process has terminated.
            # poll() returns None if it is still running,
            # otherwise it returns the process exit code.   
            if proc.poll() is not None:
                
                print(
                    f'Process for device "{device_info.name}" '
                    f'terminated during startup with code {proc.poll()}.'
                )

                self.launch_file(device_info.name).unlink(missing_ok=True)
                self.runtime_file(device_info.name).unlink(missing_ok=True)

                return False
            #
            
            runtime_info = self.load_runtime_info(device_info.name)
            if runtime_info is None:
                self.launch_file(device_info.name).unlink(missing_ok=True)
                self.runtime_file(device_info.name).unlink(missing_ok=True)
                return False

            if runtime_info.get("process_started") is not None:
                print(
                    f'Process for device "{device_info.name}" '
                    f'started successfully at '
                    f'{runtime_info.get("process_started")} '
                    f'with PID={runtime_info.get("pid")}.'
                )

                self.devices_infos[device_info.name] = device_info

                self.launch_file(device_info.name).unlink(missing_ok=True)
                return True

            if time.monotonic() - t0 >= timeout:
                print(
                    f'Process for device "{device_info.name}" '
                    f'failed to start within {timeout} s.'
                )
                
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=2)
                #
                self.launch_file(device_info.name).unlink(missing_ok=True)
                self.runtime_file(device_info.name).unlink(missing_ok=True)
                return False

            time.sleep(poll_interval)
        #
    #

    def stop(self, name, timeout=5):

        pid = self.get_pid(name)

        #
        # If there is no runtime information (or no PID),
        # simply cleanup any stale files.
        #
        if pid is None:
            self.cleanup_files(name)
            return True

        #
        # The device process is already gone
        # (PID missing or PID reused).
        #
        if not self.is_running(name):
            self.cleanup_files(name)
            return True
        
        #
        # Try a graceful shutdown through the device socket.
        #
        self.send_shutdown_command(name)

        time.sleep(timeout)

        #
        # The device exited cleanly.
        #
        if not self.pid_exists(pid):
            self.cleanup_files(name)
            return True

        #
        # Graceful shutdown failed.
        # Try SIGTERM.
        #
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

        time.sleep(timeout)

        if not self.pid_exists(pid):
            self.cleanup_files(name)
            return True

        print(
            f'Device "{name}" did not stop gracefully. '
            f'Sending SIGKILL.'
        )

        #
        # Last resort.
        #
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass

        time.sleep(1)

        if not self.pid_exists(pid):
            self.cleanup_files(name)
            return True

        #
        # The process still exists.
        # Do not remove the runtime information,
        # since it still corresponds to a live process.
        #
        print(
            f'Failed to terminate process of device "{name}".'
        )

        return False
    #

    def send_shutdown_command(self, name):
        self.socket_file(name)
        
        payload = json.dumps({"command": "shutdown"})

        with socket.socket(
            socket.AF_UNIX,
            socket.SOCK_STREAM
        ) as sock:
            try:
                sock.connect(str(self.socket_file(name)))
            except (FileNotFoundError, ConnectionRefusedError, OSError) as err:
                print(f"ERROR: Socket of device '{name}' not found or connection was refused: {err}")
                return False
            sock.sendall(payload.encode())
        return True  
    #

    def restart(self, device_info:DeviceInfo):

        self.stop(device_info.name)

        return self.start(device_info)
    #
    
    def is_running(self, name):
        runtime_info = self.load_runtime_info(name)
        if runtime_info is None:
            return False

        pid = runtime_info.get("pid")
        if pid is None:
            return False

        if not self.pid_exists(pid):
            return False
        
        #
        # Verify that the PID still belongs to the
        # same process.
        #
        try:
            proc = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return False
        #
        return proc.create_time() == runtime_info.get("process_started")
    #

    def pid_exists(self, pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def get_pid(self, name):
        runtime_info = self.load_runtime_info(name)
        if runtime_info is None:
            return None
        #
        
        return runtime_info.get('pid')
    #

    def status(self, name):

        runtime_info = self.load_runtime_info(name)

        if runtime_info is None:
            return None
        #
        
        status = {
            k:v for k,v in runtime_info.items()
            if k!= "config"
        }
        status["running"] = self.is_running(name)

        return status
    #

    def all_status(self):
        ret = {}
        for runtime_file in (self.runtime_dir / "devices").glob("*.json"):
            name = runtime_file.name[:-5]
            runtime_info = self.status(name)
            if runtime_info:
                ret[name] = runtime_info
            #
        #
        return ret
    #

    def load_runtime_info(self, name):

        runtime_file = (
            self.runtime_dir /
            "devices" /
            f"{name}.json"
        )

        try:
            with runtime_file.open("r") as f:
                return json.load(f)

        except Exception:
            return None
    #

    def require_runtime_info(self, name):

        runtime_info = self.load_runtime_info(name)

        if runtime_info is None:
            raise RuntimeError(
                f'No runtime information for device "{name}".'
            )

        return runtime_info

    def runtime_file(self, name):
        return (
            self.runtime_dir /
            "devices" /
            f"{name}.json"
        )
    #

    def socket_file(self, name):
        return (
            self.runtime_dir /
            "sockets" /
            f"{name}.sock"
        )
    #

    def launch_file(self, name):
        #This is the file where there is the class device class initialized and serialized ready to be run in an independent process
        return (
            self.runtime_dir /
            "launch" /
            f"{name}.pkl"
        )
    #

    def cleanup_files(self, name):
        self.runtime_file(name).unlink(missing_ok=True)
        self.launch_file(name).unlink(missing_ok=True)
        self.socket_file(name).unlink(missing_ok=True)
    #
#
