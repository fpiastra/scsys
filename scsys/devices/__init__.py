from pathlib import Path
import importlib
import inspect
from .base import (ScDevice, Measurement, MeasurementRecord)

DEVICE_CLASSES = {}

def discover_devices(search_dir=None):
    global DEVICE_CLASSES

    DEVICE_CLASSES.clear()

    builtin_dir = Path(__file__).parent

    # Load built-in devices first
    discover_directory(
        builtin_dir,
        builtin=True
    )

    # Then load user devices, overriding if needed
    if search_dir is not None:
        discover_directory(
            search_dir=search_dir,
            builtin=False
        )
    #
#

def discover_directory(search_dir:str, builtin:bool):
    global DEVICE_CLASSES

    search_dir = Path(search_dir)

    if not search_dir.is_dir():
        raise RuntimeError(
            f'"{search_dir}" is not a directory.'
        )
    #

    for pyfile in search_dir.glob("*.py"):
        #
        # Ignore package helpers
        #
        if pyfile.name == "__init__.py":
            continue
        #
        try:
            if builtin:
                module_name = f"{__package__}.{pyfile.stem}"
                module = importlib.import_module(module_name)
            else:
                #
                # Load module directly from file
                #
                module_name = (
                    f"user_device_{pyfile.stem}"
                )

                spec = (
                    importlib.util.spec_from_file_location(
                        module_name,
                        pyfile
                    )
                )

                if spec is None or spec.loader is None:
                    raise RuntimeError(
                        "Cannot create module spec."
                    )
                #

                module = (
                    importlib.util.module_from_spec(spec)
                )

                spec.loader.exec_module(module)

        except Exception as err:
            print(
                f'ERROR loading device module '
                f'"{pyfile}": {err}'
            )
            continue

        for _, obj in inspect.getmembers( module, inspect.isclass):
            
            if (not issubclass(obj, ScDevice)
                or obj is ScDevice
                ):
                continue

            if obj.DEVICE_TYPE == "generic":
                raise RuntimeError(
                    f'{obj.__name__} does not define '
                    f'DEVICE_TYPE'
                )
            #

            if obj.DEVICE_TYPE in DEVICE_CLASSES:
                if builtin:
                    raise RuntimeError(
                        f'Duplicate DEVICE_TYPE '
                        f'"{obj.DEVICE_TYPE}"'
                    )
                else:
                    print(
                        f'Overriding device type "{obj.DEVICE_TYPE}" '
                        f'with "{module_name}"'
                    )
                #
            #
            DEVICE_CLASSES[obj.DEVICE_TYPE] = obj
        #
    #
#

def get_device_class(device_type:str):
    global DEVICE_CLASSES
    return DEVICE_CLASSES.get(
        device_type
    )
#
