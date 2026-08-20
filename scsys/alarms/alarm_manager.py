import json
from dataclasses import dataclass
from enum import Enum, auto
from datetime import datetime
import time

from .alarm_base import (AlarmEvent, AlarmEventType)
from .alarm_storage import AlarmStorage
from .alarm_notifier import AlarmNotifier


class AlarmState(Enum):
    ACTIVE = auto()
    ACKNOWLEDGED = auto()

@dataclass
class ActiveAlarm:
    event: AlarmEvent
    state: AlarmState = AlarmState.ACTIVE
    first_seen: float = None
    last_update: float = None
    last_notification: float = None

class AlarmManager:
    def __init__(self):
        self.active_alarms: dict[tuple[str, str], ActiveAlarm] = {}

        self.notifier = AlarmNotifier()
        
        self.storage = AlarmStorage()

    def process_event_request(self, ev_dict: dict) -> bool:
        try:
            event = AlarmEvent(**ev_dict)
        except Exception as err:
            return{
                'success': False,
                'message': f"Failed to make an AlarmEvent object from dictionary:\n {json.dumps(ev_dict)}",
                'error': f"{type(err)}: {str(err)}" #This is optional in the protocol
            }

        try:
            self._process_event(event)

            return {'success': True}
        except Exception as err:
            return {
                'success': False,
                'message': f"Failed to process AlarmEvent",
                'error': f"{type(err)}: {str(err)}" #This is optional in the IPC protocol
            }
        #
    
    def _process_event(self, event:AlarmEvent):

        now = time.time()

        self.storage.store(event) #Store always the reception of an event regardless it is active or not and generates notifications or not

        ev_id = event.identity
        active_alarm = self.active_alarms.get(ev_id)

        if event.active:
            if active_alarm is None:
                self.notifier.notify(event)
                self.active_alarms[ev_id] = ActiveAlarm(
                    event=event,
                    first_seen=now,
                    last_update = now,
                    last_notification=now
                )
            else:
                active_alarm.event = event
                if event.evtype==AlarmEventType.UPDATED:
                    active_alarm.last_update = now
                #
            #
        else:
            #Clear the corresponding alarm entry from the active alarms
            if not active_alarm is None:
                if event.evtype!=AlarmEventType.SUPPRESSED:
                    self.notifier.notify(event)
                self.active_alarms.pop(ev_id)
            #
        #
    #

    def get_active_alarm(self, id):
        return self.active_alarms.get(id)
    #

    def is_active(self, id):
        return id in self.active_alarms