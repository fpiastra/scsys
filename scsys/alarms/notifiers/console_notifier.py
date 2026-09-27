from datetime import datetime

from ..alarm_base import (AlarmEvent, AlarmSeverity)
from .notifier_base import AlarmNotifier

class ConsoleNotifier(AlarmNotifier):
    type_name:str = "console" #This is the class member used for the automatic discovery as a key in the NOTIFIERS_CLASSES dictionary

    def __init__(self, severity:str="INFO"):
        self.severity = AlarmSeverity[severity.upper()]
        print(
            f"[alarmd] DEBUG: ConsoleNotifier initialized "
            f"(severity={self.severity.name})."
        )
    #

    def notify(self, event:AlarmEvent) -> None:
        print(
            f"[alarmd] DEBUG: ConsoleNotifier received event:\n"
            f"   {event.source}.{event.name} "
            f"   (severity={event.severity.name})."
        )

        if event.severity<self.severity:
            print(
                f"[alarmd] DEBUG: ConsoleNotifier: event suppressed "
                f"because severity {event.severity.name} < "
                f"{self.severity.name}."
            )
            return

        time_str = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        print(
            ""
            f"[{time_str}] -> {event.severity.name:<8} alarm:\n"
            f"  [{event.source}.{event.name}]\n"
            f"  {event.message}\n"
        )