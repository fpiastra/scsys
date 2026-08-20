import argparse
import signal
import socket
import time

from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from enum import Enum, IntEnum

from .config_manager import ConfigManager
from .device_registry import DeviceRegistry
from .devs_state import DevsState
from .process_manager import ProcessManager
from .lock import LockManager
from ..devices import discover_devices
from ..alarms.alarm_base import (AlarmSeverity, AlarmEvent, AlarmEventType)
from ..alarms.alarm_client import (AlarmClient, AlarmClientConfig)

class WatchdogAlarmType(Enum):
    #
    # Runtime integrity
    #
    MISSING_RUNTIME = "missing_runtime"

    #
    # Process health
    #
    PROCESS_DEAD = "process_dead"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    UNEXPECTED_RUNNING = "unexpected_running"

    #
    # Lifecycle (future)
    #
    RESTART_FAILED = "restart_failed"
    STARTUP_FAILED = "startup_failed"
    RESTART_STORM = "restart_storm"

    def __str__(self):
        return self.value

@dataclass
class WatchdogAlarmState:
    active: bool = False

class Watchdog:

    def __init__(self, config_file):

        cfgman = ConfigManager(config_file)
        cfgman.load()

        self.runtime_dir = Path(cfgman.config.runtime_dir)
        self.lock_path = self.runtime_dir / "locks" / "watchdog.lock"
        self.socket_path = self.runtime_dir / "sockets" / "watchdog.sock"

        self.config = cfgman.config.watchdog

        discover_devices(
            cfgman.config.devs_defs_dir
        )

        self.lock = LockManager(
            self.lock_path
        )

        self.registry = DeviceRegistry(
            self.config.setup_file
        )

        self.pm = ProcessManager(
            runtime_dir=self.runtime_dir
        )

        self.devs_state = DevsState(
            Path(self.config.runtime_dir)
        )

        self.running = False

        self.alarm_client = AlarmClient(
            AlarmClientConfig(runtime_dir=self.runtime_dir)
        )
        self.alarm_states:dict[str,dict[WatchdogAlarmType,WatchdogAlarmState]] = {}

        #
        # Future
        #
        self.server = None
    #

    def run(self):

        self.lock.acquire()

        self.registry.load()

        #
        # Future
        #
        # self.setup_socket()

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
            self.check_devices()

            #
            # Future:
            # poll watchdog socket
            #

            time.sleep(
                self.config.heartbeat_interval
            )
        #
    #

    def check_devices(self):
        for dev in self.registry.enabled_devices():
            self.check_device(dev)
        #
    #

    def check_device(self, device_info):

        state = self.devs_state.get(device_info.name)

        if state == DevsState.RUNNING:
            self.check_running(device_info)

        elif state == DevsState.STOPPED:
            self.check_stopped(device_info)

        else:
            print(
                f'Unknown state "{state}" '
                f'for device "{device_info.name}".'
            )
        #
    #

    def check_running(self, device_info):
        
        runtime_info = self.pm.status(device_info.name)

        #
        # No runtime info (or file).
        #
        if runtime_info is None:
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.MISSING_RUNTIME,
                severity=AlarmSeverity.WARNING,
                message=f'No runtime information.',
                active=True
            )
            print(
                f'Device "{device_info.name}" '
                f'has no runtime information. Restarting.'
            )

            self.pm.restart(device_info)
            return
        else:
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.MISSING_RUNTIME,
                severity=AlarmSeverity.INFO,
                message=f'Runtime information ok.',
                active=False
            )
        #

        #
        # Runtime file exists but process does not.
        #
        if not self.pm.is_running(device_info.name):
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.PROCESS_DEAD,
                severity=AlarmSeverity.WARNING,
                message=f'Process dead.',
                active=True
            )
            print(
                f'Device "{device_info.name}" '
                f'is not running. Restarting.'
            )

            self.pm.restart(device_info)
            return
        else:
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.PROCESS_DEAD,
                severity=AlarmSeverity.INFO,
                message=f'Process found alive (ok).',
                active=False
            )
        #

        if not self.heartbeat_ok(runtime_info=runtime_info):
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.HEARTBEAT_TIMEOUT,
                severity=AlarmSeverity.WARNING,
                message=f'Heartbeat timeout.',
                active=True
            )
            print(
                f'Device "{device_info.name}" '
                f'Heartbeat timeout. Restarting.'
            )

            self.pm.restart(device_info)
            return
        else:
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.HEARTBEAT_TIMEOUT,
                severity=AlarmSeverity.INFO,
                message=f'Heartbeat ok.',
                active=False
            )
        #
    #

    def check_stopped(self, device_info):

        if self.pm.is_running(device_info.name):
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.PROCESS_DEAD,
                severity=AlarmSeverity.WARNING,
                message=f'Process running (unexpected).',
                active=True
            )

            print(
                f'Device "{device_info.name}" '
                f'should be stopped.'
            )
            
            self.pm.stop(device_info.name)
            return
        else:
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.PROCESS_DEAD,
                severity=AlarmSeverity.INFO,
                message=f'Process has stopped (ok).',
                active=False
            )

        #
        # Future:
        # cleanup stale files
        #
    #

    def runtime_is_valid(self, device_info):
        return self.pm.status(device_info.name) is not None
    #

    def heartbeat_ok(self, runtime_info):
        hb = runtime_info.get("heartbeat")
        if hb is None:
            return False
        
        hb = datetime.fromisoformat(hb)

        age = (datetime.now() - hb).total_seconds()

        return age <= 2 * self.config.heartbeat_interval
    #

    def _emit_alarm(
        self,
        device: str,
        alarm: WatchdogAlarmType,
        severity: AlarmSeverity,
        message: str,
        active: bool,
    ):
        if device not in self.alarm_states:
            self.alarm_states[device] = {}

        states = self.alarm_states[device]

        if alarm not in states:
            states[alarm] = WatchdogAlarmState()

        state = states[alarm]

        #
        # Determine whether an event must be emitted and its semantic.
        #
        if state.active == active:
            if active:
                # Alarm still active -> refresh.
                evtype = AlarmEventType.UPDATED
            else:
                # Alarm already inactive -> nothing to do.
                return
        else:
            if active:
                # Alarm just activated.
                evtype = AlarmEventType.ACTIVATED
            else:
                # Alarm just cleared.
                evtype = None

        #
        # Update the internal state.
        #
        state.active = active

        #
        # Build the event.
        #
        alarm_event = AlarmEvent(
            source=device,
            name=alarm.value,
            severity=severity,
            active=active,
            message=message,
            timestamp=time.time(),
            evtype=evtype,
        )

        #
        # Send the event.
        #
        reply = self.alarm_client.send_event(event=alarm_event)

        if not reply["success"]:
            # logger.warning(
            #     f"Failed to send alarm '{alarm.value}': {reply['error']}"
            # )
            pass
        #
    #

    def shutdown(self):
        self.running = False
    #

    def sigterm_handler(
        self,
        signum,
        frame
    ):
        self.shutdown()
    #

    def cleanup(self):
        if self.server is not None:
            self.server.close()

        if self.socket_path.exists():
            self.socket_path.unlink()

        self.lock.release()
    #

    #
    # Future
    #
    def setup_socket(self):
        pass

    def handle_connection(self, conn):
        pass

    def handle_request(self, request):
        pass

    def status(self):
        pass
    #
#


def main():

    parser = argparse.ArgumentParser(
        prog="scwatchdog",
        description="Slow Control Watchdog"
    )

    parser.add_argument(
        "config_file",
        required=True
    )

    args = parser.parse_args()

    watchdog = None

    fail = False

    try:
        watchdog = Watchdog(args.config_file)

        watchdog.run()

    except KeyboardInterrupt:
        print("Stopping watchdog...")

    except Exception as err:
        print(f"ERROR: {err}")
        fail = True

    finally:

        if watchdog is not None:
            watchdog.cleanup()

    return int(fail)
#

if __name__ == "__main__":
    raise SystemExit(main())