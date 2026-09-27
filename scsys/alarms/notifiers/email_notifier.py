from datetime import datetime

from ..alarm_base import (AlarmEvent, AlarmSeverity)
from .notifier_base import AlarmNotifier

class EmailNotifier(AlarmNotifier):
    type_name = "email"

    def __init__(self, severity:AlarmSeverity=AlarmSeverity.INFO):
        pass
