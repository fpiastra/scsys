from dataclasses import dataclass

@dataclass
class DeviceInfo:

    name: str

    type_name: str

    device_class: type

    enabled: bool

    autostart: bool

    device_config: dict

    process_name: str

    def create_device(self, runtime_dir:str):
        return self.device_class(
            cfg=self,
            runtime_dir=str(runtime_dir)
        )
    #
#