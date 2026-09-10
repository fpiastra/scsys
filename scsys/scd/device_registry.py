from pathlib import Path
import json
from dataclasses import dataclass
from ..devices import (get_device_class, DeviceInfo, RuntimeConfig)


class DeviceRegistry:
    def __init__(self, setup_file):

        self.setup_file = Path(setup_file)
        self.devices = {}
    #
        
    def load(self):
        self.devices.clear()
        
        with self.setup_file.open("r") as f:
            cfg = json.safe_load(f)
        #

        for dev_cfg in cfg["devices"]:

            name = dev_cfg["name"]
            if not name:
                print("ERROR: Device without a name. Ignoring device.")
                continue
            #

            type_name = dev_cfg.get("type")

            if type_name is None:
                print(
                    f'ERROR: No device type for device "{name}". Ignoring device.'
                )
                continue #Maybe raise here or print an error
            #
            
            dev_cls = get_device_class(type_name)
            if dev_cls is None:
                print(
                    f'ERROR: Unknown device type "{type_name}" '
                    f'for device "{name}". Ignoring device.'
                )
                continue
            #

            device_config = dev_cfg.get("config")
            if device_config is None:
                print(
                    f'ERROR: No config specified for device "{name}". Ignoring device.'
                )
                continue
            #

            runtime_config = dev_cfg.get("runtime",{})
            watchdog_config = dev_cfg.get("watchdog", {})

            self.devices[name] = DeviceInfo(
                name=name,
                type_name=type_name,
                device_class=dev_cls,
                enabled=dev_cfg.get("enabled", True),
                autostart=dev_cfg.get("autostart", False),
                device_config=device_config,
                runtime_config=runtime_config,
                watchdog_config=watchdog_config,
                process_name=name
            )
        #
    #

    def get(self, name):
        return self.devices.get(name)
    #

    def exists(self, name):
        return name in self.devices
    #

    def enabled_devices(self):
        return [
            dev
            for dev in self.devices.values()
            if dev.enabled
        ]
    #

    def autostart_devices(self):
        return [
            dev
            for dev in self.devices.values()
            if dev.enabled and dev.autostart
        ]
    #

    def get_info_dict(self):
        return {
            name: {
                "type": dev.type_name,
                "enabled": dev.enabled,
                "autostart": dev.autostart
            }
            for name, dev in self.devices.items()
        }
    #
#