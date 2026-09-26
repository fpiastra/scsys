from abc import (ABC, abstractmethod)
from datetime import datetime

from ..alarm_base import (AlarmEvent, AlarmSeverity)
from .notifier_base import AlarmNotifier

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