from dataclasses import dataclass

@dataclass
class RuntimeConfig:
    polling_interval: float
    variables_map: dict
    storage: dict

    @classmethod
    def from_dict(cls, runtime_cfg:dict) -> "RuntimeConfig":
        return cls(
            polling_interval=runtime_cfg.get("polling_interval", 5),
            variables_map=runtime_cfg.get("variables_map", {}),
            storage=runtime_cfg.get("storage", {})
        )
    #
#
