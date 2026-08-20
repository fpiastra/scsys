from pathlib import Path
import importlib
import inspect

from .base import ScStorage
from .csv_storage import CsvStorage
from .influxdb_storage import InfluxStorage

STORAGE_CLASSES = {}

def discover_storages(search_dir=None):

    global STORAGE_CLASSES

    STORAGE_CLASSES.clear()

    if search_dir is None:
        search_dir = Path(__file__).parent
    #

    for pyfile in search_dir.glob("*.py"):

        module_name = (
            f"{__package__}."
            f"{pyfile.stem}"
        )

        try:
            module = importlib.import_module(
                module_name
            )
        except Exception as err:
            print(
                f'ERROR loading storage module '
                f'"{module_name}": {err}'
            )
            continue

        for _, obj in inspect.getmembers( module, inspect.isclass):
            
            if (issubclass(obj, ScStorage)
                and obj is not ScStorage
                ):
                if obj.STORAGE_TYPE in STORAGE_CLASSES:
                    raise RuntimeError(
                        f'Duplicate STORAGE_TYPE '
                        f'"{obj.STORAGE_TYPE}"'
                    )
                if obj.STORAGE_TYPE == "generic":
                    raise RuntimeError(
                        f'{obj.__name__} does not define '
                        f'STORAGE_TYPE'
                    )
                STORAGE_CLASSES[obj.STORAGE_TYPE] = obj
            #
        #
    #
#

def get_storage_class(storage_type:str):
    return STORAGE_CLASSES.get(
        storage_type
    )
#