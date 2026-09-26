from .alarm_base import *
from .notifiers.notifier_base import AlarmNotifier
from .notifiers import (discover_notifiers, get_notifier)
from .notifiers.console_notifier import ConsoleNotifier

class AlarmNotificationManager:
    def __init__(self, notifiers_lst:list[dict]):
        discover_notifiers()

        self.notifiers: list[AlarmNotifier] = []

    def add_notifier(self, notifier:AlarmNotifier)  -> None:
        self.notifiers.append(notifier)

    def notify(self, event: AlarmEvent)  -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(event)
            except Exception:
                
                #logger.exception(f"Notifier {notifier.__class__.__name__} failed")
                pass