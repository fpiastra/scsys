import os
import psutil
import signal
from pathlib import Path
from dataclasses import (dataclass, field)
from datetime import datetime
import yaml
import socket
import json
import time

from ...storage import get_storage_class
from ...scd.device_info import DeviceInfo
from ...alarms.alarm_engine import AlarmEngine
from ...alarms.alarm_client import (AlarmClient, AlarmClientConfig)

@dataclass
class Measurement:
    value: int | float | bool | None
    timestamp: datetime | None
    valid: bool = False #This indicates that the last readout failed and the fields above are outdated (the last good readout)

@dataclass
class MeasurementRecord:
    varname: str
    value: int | float | bool
    timestamp: datetime

@dataclass
class RuntimeConfig:
    polling_interval: float = 5.0
    variables_map: dict = field(
        default_factory=dict
    )
    storage: dict = field(
        default_factory=dict
    )
#

class ScDevice:

    DEVICE_TYPE = "generic"

    VARIABLES = ()

    def __init__(self, cfg:DeviceInfo, runtime_dir:str):

        self.cfg = cfg
        self.name = cfg.name
        self.device_cfg = cfg.device_config
        self.runtime_dir = Path(runtime_dir)
        self.measurements = {}
        self.storages = []
        self.variables_map = {}
        self.variables_map_reverse = {}
        self.socket_path = self.runtime_dir / "sockets" / f"{self.name}.sock"
        self.runtime_file =  self.runtime_dir / "devices" / f"{self.name}.json"
        self.alarm_engine = None
        self.alarm_client = None
        self.server = None
        self.running = False
    #
    
    def run(self):
        
        proc = psutil.Process(os.getpid())

        self._update_runtime_info(
            pid=proc.pid,
            process_started=proc.create_time()
        )

        self.initialize()
        
        signal.signal(
            signal.SIGTERM,
            self._sigterm_handler
        )

        signal.signal(
            signal.SIGINT,
            self._sigterm_handler
        )
        
        self.running = True

        try:
            while self.running:
                self._update_runtime_info(heartbeat=datetime.now().isoformat())

                self._poll_socket()

                self.read_measurements()

                self._process_alarm_events()

                self._publish_measurements()

                time.sleep(
                    self.runtime_cfg.polling_interval
                )
            #
        finally:
            self.cleanup()
    #

    def initialize(self):
        self._setup_variables_mapping()
        self._setup_alarm_engine()
        self._setup_storage()
        self._setup_socket()
        self._setup_alarm_client()
        self.connect()
    #
    

    def connect(self):
        raise NotImplementedError
    #

    def disconnect(self):
        raise NotImplementedError
    #

    def _resolve_name(self, name):
        if name in self.VARIABLES:
            return name
        return self.variables_map.get(name)
    #

    def _export_name(self, canonical):
        #This is the inverse helper function than resolve_name
        return self.variables_map_reverse.get(
            canonical,
            canonical
        )
    #

    def get(self, varname):
        canonical = self._resolve_name(varname)
        if canonical is None:
            return {
                "success": False,
                "message": f'Unknown variable "{varname}"'
            }
        val = self.get_value(canonical)
        if val is None:
            return {
                "success": False,
                "message": f'No measurement for "{varname}"'
            }
        return {
            "success": True,
            "name": varname,
            "value": val
        }
    #

    def set(self, varname, value):
        canonical = self._resolve_name(varname)
        if canonical is None:
            return {
                "success": False,
                "message": f'Unknown variable "{varname}"'
            }
        if self.set_value(canonical, value):
            return{
                "success": True
            }
        return {
            "success": False,
            "name": varname,
            "message": f"Failed to set parameter '{varname}' to '{value}'"
        }
    #

    def get_value(
        self,
        varname
    ):
        raise NotImplementedError
    #

    def set_value(
        self,
        varname,
        value
    ):
        """
        Returns:
            True  -> success
            False -> failure
        """
        raise NotImplementedError
    #

    def add_measurement(
        self,
        varname,
        initial_value:int|float|bool|None=None,
        initial_timestamp:datetime|None=None 
    ):
        self.measurements[varname] =  Measurement(
            value = initial_value,
            timestamp = initial_timestamp
        )
    #
        

    def update_measurement(
            self,
            varname,
            value,
            timestamp
    ):
        self.measurements[varname] = Measurement(
            value = value,
            timestamp = timestamp,
            valid = True
        )
    #

    def _invalidate_measurement(
        self,
        varname
    ):

        meas = self.measurements.get(varname)

        if meas is None:
            return

        meas.valid = False
    #   

    def read_measurements(self):
        raise NotImplementedError
    #

    def _publish_measurements(self):
        for varname, meas in self.measurements:
            if not meas.valid:
                continue

            for storage in self.storages:
                storage.enque(
                    MeasurementRecord(
                        varname=varname,
                        value=meas.value,
                        timestamp=meas.timestamp
                    )
                )
            #
        #
        for storage in self.storages:
            storage.write() #This is a command to actually write the variables in the queue
    #

    def _process_alarm_events(self):

        events = self.alarm_engine.evaluate(self.measurements)

        if not events:
            return

        for event in events:
            reply = self.alarm_client.send_event(event)
            if not reply["success"]:
                #logger.warning(f'Failed to send alarm {event.name}: {reply['error']}')
                pass


    def shutdown(self):
        self.running = False
    #

    def status(self):
        return {
            "device": self.name,
            "type": self.DEVICE_TYPE,
            "running": self.running
        }
    #

    def _handle_command(self, request):
        command = request.get(
            "command"
        )

        if command == "status":
            return {
                "success": True,
                "status": self.status()
            }
        elif command == "get":
            return self.get( request["varname"] )
        elif command == "set":

            return self.set(
                request["varname"],
                request["value"]
            )
        elif command == "shutdown":
            self.shutdown()
            return {
                "success": True
            }
        return {
            "success": False,
            "message": f"Unknown command '{command}'"
        }
    #

    def _setup_variables_mapping(self):
        for canonical, varname in self.runtime_cfg.variables_map.items():
            if canonical not in self.VARIABLES:
                raise RuntimeError(
                    f'Unknown variable "{canonical}" '
                    f'for device type "{self.DEVICE_TYPE}"'
                )
            self.variables_map[varname] = canonical
            self.variables_map_reverse[canonical] = varname
    #

    def _setup_alarm_engine(self):
        self.alarm_engine = AlarmEngine(dev_name=self.name, rules=self.get("alarms", []))

    def _setup_alarm_client(self):
        self.alarm_client = AlarmClient(
            AlarmClientConfig(runtime_dir=Path(self.runtime_dir))
        )
        self.alarm_client
    
    def _setup_storage(self):

        if self.runtime_cfg.storage is None:
            return
        
        for cfg in self.runtime_cfg.storage:

            storage_type = cfg["type"]

            storage_cls = get_storage_class(
                storage_type
            )

            if storage_cls is None:
                print(
                    f'{self.name}: Unknown storage type "{storage_type}"'
                )
                continue

            storage = storage_cls(
                self.name,
                self.DEVICE_TYPE,
                cfg
            )

            self.storages.append(storage)
        #
    #

    def _setup_socket(self):
        self.socket_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

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

    def _poll_socket(self):

        try:
            conn, _ = self.server.accept()
        except BlockingIOError:
            #TODO: log a message of error
            return

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
                response = {
                    "success": False,
                    "message": f"Invalid JSON request:\n({request})"
                }
            else:
                try:
                    response = self._handle_command(
                        request
                    )
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

    def _cleanup_socket(self):
        if self.server is not None:
            self.server.close()
        #
        if self.socket_path.exists():
            self.socket_path.unlink()
        #
    #

    def cleanup(self):
        try:
            self._cleanup_socket()
        finally:
            self.disconnect()
    #

    def _sigterm_handler(self, signum, frame):
        self.shutdown()
    #

    def _read_runtime_info(self):
        try:
            with self.runtime_file.open("r") as f:
                return json.load(f)

        except Exception as err:
            print(f'ERROR failed to load runtime info from "{str(self.runtime_file)}": {err}')
            return None
    #

    def _write_runtime_info(self, runtime_info:dict):
        with self.runtime_file.open("w") as f:
            json.dump(
                runtime_info,
                f,
                indent=4
            )
        #
    #

    def _update_runtime_info(self, **kwargs):
        runtime_info = self._read_runtime_info()

        if runtime_info is None:
            return False

        runtime_info.update(kwargs)

        self._write_runtime_info(runtime_info)

        return True