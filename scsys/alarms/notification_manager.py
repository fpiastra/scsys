from .alarm_base import *
from .notifiers.notifier_base import AlarmNotifier
from .notifiers import (discover_notifiers, get_notifier, NOTIFIER_CLASSES)
from .notifiers.console_notifier import ConsoleNotifier

class AlarmNotificationManager:
    def __init__(self, notifiers_lst:list[dict]):
        print("[alarmd] DEBUG: Initializing AlarmNotificationManager...")

        discover_notifiers()

        print(
            f"[alarmd] DEBUG: Discovered notifiers: "
            f"{list(NOTIFIER_CLASSES.keys())}"
        )

        self.notifiers: list[AlarmNotifier] = []

        for cfg in notifiers_lst:

            notifier_type = cfg.get("type")

            if notifier_type is None:
                print(
                    "[alarmd] WARNING: Notifier configuration has no "
                    "'type' field."
                )
                continue

            print(
                f"[alarmd] INFO: Configuring notifier '{notifier_type}'."
            )

            notifier_class = get_notifier(notifier_type)

            if notifier_class is None:
                print(
                    f"[alarmd] WARNING: Unknown notifier type "
                    f"'{notifier_type}'."
                )
                continue

            kwargs = {
                key: value
                for key, value in cfg.items()
                if key != "type"
            }

            try:
                notifier = notifier_class(**kwargs)

            except Exception as err:

                print(
                    f"[alarmd] ERROR: Failed to initialize notifier "
                    f"'{notifier_type}': "
                    f"{type(err).__name__}: {err}"
                )
                continue

            self.add_notifier(notifier)

            print(
                f"[alarmd] DEBUG: Notifier '{notifier_type}' initialized."
            )

        print(
            f"[alarmd] DETAIL: AlarmNotificationManager ready with "
            f"{len(self.notifiers)} notifier(s)."
        )

    def add_notifier(self, notifier:AlarmNotifier)  -> None:
        print(
            f"[alarmd] DEBUG: Adding notifier: "
            f"{notifier.__class__.__name__}"
        )
        self.notifiers.append(notifier)

    def notify(self, event: AlarmEvent)  -> None:
        print(
            f"[alarmd] DEBUG: Dispatching notification for "
            f"{event.source}.{event.name} "
            f"to {len(self.notifiers)} notifier(s)."
        )
        for notifier in self.notifiers:
            print(
                f"[alarmd] DEBUG: -> {notifier.__class__.__name__}"
            )
            try:
                notifier.notify(event)
            except Exception as err:
                print(
                    f"[alarmd] ERROR: Notifier "
                    f"'{notifier.__class__.__name__}' failed: "
                    f"{type(err).__name__}: {err}"
                )
                #logger.exception(f"Notifier {notifier.__class__.__name__} failed")