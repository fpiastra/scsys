from abc import (ABC, abstractmethod)
from datetime import datetime

from ..alarm_base import (AlarmEvent)

class AlarmNotifier(ABC):
    @abstractmethod
    def notify(self, event: AlarmEvent)  -> None:
        pass