import importlib
import inspect
from pathlib import Path

from .notifier_base import AlarmNotifier

NOTIFIER_CLASSES: dict[str, AlarmNotifier] = {}

def discover_notifiers():
    """
    Discover all AlarmNotifier subclasses in this package.

    Each notifier class must define a `type_name` class attribute,
    which is used as the configuration identifier.
    """
    global NOTIFIER_CLASSES

    NOTIFIER_CLASSES.clear()

    package_dir = Path(__file__).parent

    for path in package_dir.glob("*.py"):

        if path.name == "notifier_base.py":
            continue
        #

        module_name = f"{__name__}.{path.stem}"

        try:
            module = importlib.import_module(module_name)
        except Exception as err:
            print(
                f'WARNING: Failed to import notifier module '
                f'"{module_name}": {err}'
            )
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):

            if (
                not issubclass(obj, AlarmNotifier)
                or obj is AlarmNotifier
            ):
                continue

            type_name = getattr(obj, "type_name", None)

            if not type_name:
                print(
                    f'WARNING: Notifier class "{obj.__name__}" '
                    f'does not define "type_name".'
                )
                continue

            if type_name in NOTIFIER_CLASSES:
                raise RuntimeError(
                    f'Duplicate notifier type "{type_name}": '
                    f'{NOTIFIER_CLASSES[type_name]} and {obj}'
                )

            NOTIFIER_CLASSES[type_name] = obj
        #
    #
#

def get_notifier(name):
    return NOTIFIER_CLASSES.get(name)
#