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
    #
#

@dataclass
class WatchdogAlarmState:
    active: bool = False
#
@dataclass
class WatchdogConfig:
    autostart: bool
    cycle_time_interval: float
    startup_timeout: float
    heartbeat_timeout: float
    restart_on_failure: bool

class Watchdog:

    def __init__(self, config_file):

        cfgman = ConfigManager(config_file)
        cfgman.load()

        self.runtime_dir = Path(cfgman.config.runtime_dir)
        self.lock_path = self.runtime_dir / "locks" / "watchdog.lock"
        self.socket_path = self.runtime_dir / "sockets" / "watchdog.sock"
        self.setup_file = Path(cfgman.config.setup_file)

        cfg = cfgman.config.watchdog

        self.config = WatchdogConfig(
            autostart = cfg.get("autostart", True),
            cycle_time_interval = cfg.get("cycle_time_interval", 10),
            startup_timeout = cfg.get("startup_timeout", 5),
            heartbeat_timeout = cfg.get("heartbeat_timeout", 30),
            restart_on_failure = cfg.get("restart_on_failure", False)
        )

        self.lock = LockManager(
            self.lock_path
        )

        self.registry = DeviceRegistry(
            self.setup_file
        )

        self.pm = ProcessManager(
            runtime_dir=self.runtime_dir
        )

        self.devs_state = DevsState(
            Path(self.runtime_dir)
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

    def watchdog_config_for(self, device_info, runtime_info):
        """
        Build the effective watchdog configuration for one device.

        Precedence is:

            1) global watchdog config
            2) device watchdog config from setup.json
            3) watchdog config from the runtime JSON

        The runtime configuration is deliberately the final authority because operational commands may change watchdog behaviour without modifying setup.json.
        """

        cfg = {
            "enabled": True,
            "heartbeat_timeout": self.config.heartbeat_timeout,
            "restart_on_failure": self.config.restart_on_failure,
            "startup_timeout": self.config.startup_timeout,
        }

        #
        # Static per-device override from setup.json.
        #
        cfg.update(device_info.watchdog_config or {})

        #
        # Runtime override is authoritative when a runtime file exists.
        #
        if runtime_info is not None:
            runtime_wdg = runtime_info.get("watchdog", {})
            if isinstance(runtime_wdg, dict):
                cfg.update(runtime_wdg)

        return cfg


    def run(self):
        """
        Acquire exclusive Watchdog ownership, load the configured device
        universe, and start supervision.
        """

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
        """
        Periodically supervise all configured devices.

        The socket server will later be integrated into this loop. For now,
        sleeping between supervision cycles avoids consuming a CPU core.
        """

        next_check = time.monotonic()

        while self.running:
            now = time.monotonic()
            #
            # Future:
            # poll watchdog socket
            #
            if now >= next_check:
                self.check_devices()
                next_check = (
                    now + self.config.cycle_time_interval
                )
            #
            time.sleep(0.1) #TODO: Remove this once the Watchdog socket is implementeed
        #
    #

    def check_devices(self):
        for dev in self.registry.enabled_devices():
            self.check_device(dev)
        #
    #

    def check_device(self, device_info):
        """
        Check one configured device.

        setup.json defines which devices exist. The runtime JSON, when present, supplies the authoritative runtime state and watchdog overrides.
        Runtime files belonging to unknown devices are therefore never examined.
        """

        #
        # Read the runtime state. This may be None when the device has not
        # produced a runtime file yet.
        #
        runtime_info = self.pm.status(device_info.name)

        #
        # Build the effective watchdog configuration.
        #
        wdg = self.watchdog_config_for(
            device_info=device_info,
            runtime_info=runtime_info
        )

        #
        # A runtime command may disable watchdog supervision completely.
        #
        if not wdg.get("enabled", True):
            return
        #

        state = self.devs_state.get(device_info.name)

        if state == DevsState.RUNNING:
            self.check_running(
                device_info=device_info,
                runtime_info=runtime_info,
                watchdog_config=wdg
            )

        elif state == DevsState.STOPPED:
            self.check_stopped(
                device_info=device_info,
                watchdog_config=wdg
            )

        else:
            print(
                f'Unknown state "{state}" '
                f'for device "{device_info.name}".'
            )
        #
    #

    def check_running(
            self,
            device_info,
            runtime_info,
            watchdog_config
    ):
        """
        Check a device that is expected to be running.

        The checks are deliberately ordered from basic runtime integrity to
        process health and finally heartbeat health.
        """
        
        runtime_info = self.pm.status(device_info.name)

        #
        # The runtime file is the device's live state. If it is missing,
        # the process cannot be considered healthy.
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
        # Runtime file exists, but the process itself is gone.
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

        #
        # Finally check that the device process is still communicating.
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
        """
        Check a device that is expected to be stopped.

        A running process in this state is an unexpected condition and is
        stopped by the Watchdog.
        """

        if self.pm.is_running(device_info.name):
            self._emit_alarm(
                device=device_info.name,
                alarm=WatchdogAlarmType.UNEXPECTED_RUNNING,
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
                alarm=WatchdogAlarmType.UNEXPECTED_RUNNING,
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

    def heartbeat_ok(self, runtime_info, watchdog_config):
        hb = runtime_info.get("heartbeat")

        if hb is None:
            return False

        try:
            hb = datetime.fromisoformat(hb)

            # Runtime timestamps are currently expected to be local/naive
            # datetimes. Keep this consistent with the existing runtime format.
            
            age = (datetime.now() - hb).total_seconds()
        except (TypeError, ValueError):
            return False
        #

        timeout = watchdog_config.get(
            "heartbeat_timeout",
            self.config.heartbeat_timeout
        )


        return age <= timeout
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