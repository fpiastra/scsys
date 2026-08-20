from abc import (ABC, abstractmethod)
from datetime import datetime

from .alarm_base import (AlarmEvent, AlarmSeverity)

class AlarmNotifier(ABC):
    @abstractmethod
    def notify(self, event: AlarmEvent)  -> None:
        pass


class AlarmNotificationManager:
    def __init__(self):
        self.notifiers: list[AlarmNotifier] = []

    def add_notifier(self, notifier:AlarmNotifier)  -> None:
        self.notifiers.append(AlarmNotifier())

    def notify(self, event: AlarmEvent)  -> None:
        for notifier in self.notifiers:
            try:
                notifier.notify(event)
            except Exception:
                #logger.exception(f"Notifier {notifier.__class__.__name__} failed")
                pass



class ConsoleNotifier(AlarmNotifier):
    def __init__(self, severity:AlarmSeverity=AlarmSeverity.INFO):
        self.severity = severity
    #

    def notify(self, event:AlarmEvent) -> None:
        if event.severity<self.severity:
            return

        time_str = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"{time_str} {event.severity.name<8}:\n"
            f"[{event.source}.{event.name}]\n"
            f"{event.message}\n"
        )