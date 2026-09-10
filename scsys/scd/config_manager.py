import os
import json

from pathlib import Path
from dataclasses import dataclass, field

import yaml

from ..devices import discover_devices


DEFAULT_RUNTIME_DIR = Path("/run/scsys")


@dataclass
class ScdConfig:
    """
    Configuration shared by the slow-control daemons.

    The watchdog and alarmd sections are kept as dictionaries.
    Their contents are validated by the corresponding daemon.
    """

    setup_file: Path

    runtime_dir: Path

    log_level: str = "INFO"

    watchdog: dict = field(
        default_factory=dict
    )

    alarmd: dict = field(
        default_factory=dict
    )
#


class ConfigManager:

    def __init__(self, config_file):
        self.config_file = Path(config_file)
        self.config = None
        self.setup = None
    #

    def load(self) -> ScdConfig:

        #
        # Load main YAML configuration.
        #
        try:
            with self.config_file.open("r") as f:
                cfg = yaml.safe_load(f) or {}
        except OSError as err:
            raise RuntimeError(
                f'Failed to read configuration file '
                f'"{self.config_file}": {err}'
            ) from err
        except yaml.YAMLError as err:
            raise RuntimeError(
                f'Invalid YAML in configuration file '
                f'"{self.config_file}": {err}'
            ) from err
        #

        self.validate(cfg)

        #
        # Load and validate the setup file.
        #
        setup_file = Path(
            cfg["setup_file"]
        ).expanduser()

        #
        # Keep paths in the configuration relative to the
        # current working directory, as in the previous
        # ConfigManager implementation.
        #
        setup_file = setup_file.resolve()

        self.setup = self._load_setup_file(
            setup_file
        )

        #
        # Runtime directory precedence:
        #
        #   1. SCSYS_RUNTIME_DIR environment variable
        #   2. runtime_dir in configuration
        #   3. DEFAULT_RUNTIME_DIR
        #
        runtime_dir = Path(
            cfg.get(
                "runtime_dir",
                os.environ.get(
                    "SCSYS_RUNTIME_DIR",
                    DEFAULT_RUNTIME_DIR
                )
            )
        ).expanduser().resolve()

        devs_defs_dir = cfg.get(
            "devs_dir",
            os.environ.get( "SCSYS_DEVS_DIR")
        )

        if not devs_defs_dir is None:
            devs_defs_dir = Path(devs_defs_dir).expanduser().resolve()
        #
        discover_devices(devs_defs_dir)

        #
        # Build the common configuration object.
        #
        self.config = ScdConfig(
            setup_file=setup_file,
            runtime_dir=runtime_dir,
            devs_defs_dir=devs_defs_dir,
            log_level=cfg.get(
                "log_level",
                "INFO"
            ),
            #
            # These are deliberately kept as raw dictionaries.
            # The Watchdog and AlarmDaemon are responsible for
            # validating their own sections.
            #
            watchdog=cfg.get(
                "watchdog",
                {}
            ),
            alarmd=cfg.get(
                "alarmd",
                {}
            )
        )

        return self.config
    #

    def validate(self, cfg: dict):
        """
        Validate the common/global YAML configuration.

        This method deliberately does not validate the internal
        configuration of watchdog or alarmd.
        """

        if not isinstance(cfg, dict):
            raise RuntimeError(
                f'Configuration file "{self.config_file}" '
                f'does not contain a YAML mapping.'
            )

        #
        # setup_file is mandatory.
        #
        if "setup_file" not in cfg:
            raise RuntimeError(
                f'Configuration file "{self.config_file}" '
                f'does not define the mandatory key '
                f'"setup_file".'
            )

        if not isinstance(cfg["setup_file"], (str, os.PathLike)):
            raise ValueError(
                f'Invalid setup_file={cfg["setup_file"]!r}. '
                f'The value must be a path.'
            )

        #
        # Runtime directory, if explicitly supplied, must at
        # least be path-like.
        #
        if "runtime_dir" in cfg:
            if not isinstance(
                cfg["runtime_dir"],
                (str, os.PathLike)
            ):
                raise ValueError(
                    f'Invalid runtime_dir={cfg["runtime_dir"]!r}. '
                    f'The value must be a path.'
                )

        #
        # Log level is a global setting and therefore belongs here.
        #
        log_level = cfg.get(
            "log_level",
            "INFO"
        )

        allowed_levels = (
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL"
        )

        if log_level not in allowed_levels:
            raise ValueError(
                f'Invalid log_level="{log_level}". '
                f'Allowed values are: '
                f'{", ".join(allowed_levels)}.'
            )
    #

    def _load_setup_file(
        self,
        setup_file: Path
    ) -> dict:

        #
        # Read JSON.
        #
        try:
            with setup_file.open("r") as f:
                setup = json.load(f)

        except OSError as err:
            raise RuntimeError(
                f'Failed to read setup file '
                f'"{setup_file}": {err}'
            ) from err

        except json.JSONDecodeError as err:
            raise RuntimeError(
                f'Invalid JSON in setup file '
                f'"{setup_file}": '
                f'{err}'
            ) from err
        #

        self._validate_setup_structure(
            setup,
            setup_file
        )

        return setup
    #

    def _validate_setup_structure(
        self,
        setup: dict,
        setup_file: Path
    ):
        """
        Validate only the global structure of setup.json.

        Device-specific configuration is deliberately not
        validated here.
        """

        #
        # Top-level object.
        #
        if not isinstance(setup, dict):
            raise ValueError(
                f'Setup file "{setup_file}" '
                f'must contain a JSON object at the top level.'
            )

        #
        # devices is mandatory.
        #
        if "devices" not in setup:
            raise ValueError(
                f'Setup file "{setup_file}" '
                f'does not define the mandatory key "devices".'
            )

        devices = setup["devices"]

        if not isinstance(devices, list):
            raise ValueError(
                f'Setup file "{setup_file}" '
                f'key "devices" must contain a JSON list.'
            )

        #
        # These are the fields which every device must have.
        #
        required_device_keys = (
            "name",
            "type",
            "enabled",
            "autostart",
            "runtime",
            "config",
            "watchdog",
            "alarms",
        )

        device_names = set()

        for index, device in enumerate(devices):

            if not isinstance(device, dict):
                raise ValueError(
                    f'Setup file "{setup_file}": '
                    f'device at index {index} '
                    f'must be a JSON object.'
                )

            #
            # Check mandatory device fields.
            #
            for key in required_device_keys:

                if key not in device:
                    raise ValueError(
                        f'Setup file "{setup_file}": '
                        f'device at index {index} '
                        f'does not define the mandatory '
                        f'key "{key}".'
                    )

            #
            # The name is part of the global device identity,
            # so it is checked here.
            #
            name = device["name"]

            if not isinstance(name, str):
                raise ValueError(
                    f'Setup file "{setup_file}": '
                    f'device at index {index} '
                    f'has a non-string name: {name!r}.'
                )

            if not name:
                raise ValueError(
                    f'Setup file "{setup_file}": '
                    f'device at index {index} '
                    f'has an empty name.'
                )

            if name in device_names:
                raise ValueError(
                    f'Setup file "{setup_file}" '
                    f'defines the device name "{name}" '
                    f'more than once.'
                )

            device_names.add(name)
        #
    #
#