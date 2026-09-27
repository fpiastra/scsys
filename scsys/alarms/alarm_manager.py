import json
from dataclasses import dataclass
from enum import Enum, auto
from datetime import datetime
import time

from .alarm_base import (AlarmEvent, AlarmEventType, AlarmSeverity)
from .alarm_storage import AlarmStorage
from .notification_manager import AlarmNotificationManager


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
    def __init__(self, cfg:dict):
        print("[alarmd] DEEBUG: Initializing AlarmManager...")

        self.active_alarms: dict[tuple[str, str], ActiveAlarm] = {}

        self.notification_manager = AlarmNotificationManager(
            cfg.get("notifiers", [])
        )

        print(
            f"[alarmd] INFO: Notification manager configured with "
            f"{len(self.notification_manager.notifiers)} notifier(s)."
        )
        
        self.storage = AlarmStorage(
            cfg.get("storage", {})
        )

        print("[alarmd] DEBUG: AlarmManager initialized.")

    def process_event_request(self, ev_dict: dict) -> bool:
        print(f"[alarmd] DEBUG: Processing alarm event request: {ev_dict}")
        try:
            event_data = dict(ev_dict)

            #Reconstructing the Enum and IntEnum types from the JSON serialization to rebuild the AlarmEvent
            if event_data.get("severity") is not None:
                event_data["severity"] = AlarmSeverity(event_data["severity"])
            #
            if event_data.get("evtype") is not None:
                event_data["evtype"] = AlarmEventType[event_data["evtype"].upper()]
            #
            event = AlarmEvent(**event_data)
        except Exception as err:
            print(
                "[alarmd] ERROR: Failed to create AlarmEvent: "
                f"{type(err).__name__}: {err}"
            )
            
            return{
                'success': False,
                'message': f"Failed to make an AlarmEvent object from dictionary:\n {json.dumps(ev_dict)}",
                'error': f"{type(err)}: {str(err)}" #This is optional in the protocol
            }

        print(
            f"[alarmd] DETAIL: AlarmEvent created:\n    "
            f"{event.source}.{event.name} "
            f"(active={event.active}, "
            f"severity={event.severity}, "
            f"evtype={event.evtype})"
        )

        try:
            self._process_event(event)

            print(
                f"[alarmd] DEBUG: Alarm event processed successfully: "
                f"{event.source}.{event.name}"
            )
            
            return {'success': True}
        except Exception as err:
            print(
                "[alarmd] ERROR: failed to process AlarmEvent: "
                f"{type(err).__name__}: {err}"
            )

            return {
                'success': False,
                'message': f"Failed to process AlarmEvent",
                'error': f"{type(err)}: {str(err)}" #This is optional in the IPC protocol
            }
        #
    
    def _process_event(self, event:AlarmEvent):

        now = time.time()
        ev_id = event.identity

        print(
            f"[alarmd] Event: {event.source}.{event.name} "
            f"active={event.active}, evtype={event.evtype}"
        )

        self.storage.store(event) #Store always the reception of an event regardless it is active or not and generates notifications or not

        active_alarm = self.active_alarms.get(ev_id)

        if event.active:

            if active_alarm is None:

                print(
                    f"[alarmd] DEBUG: Alarm ACTIVATED: "
                    f"{event.source}.{event.name}"
                )
                
                self.notification_manager.notify(event)
                self.active_alarms[ev_id] = ActiveAlarm(
                    event=event,
                    first_seen=now,
                    last_update = now,
                    last_notification=now
                )

                print(
                    f"[alarmd] DEBUG: Active alarm registered: "
                    f"{event.source}.{event.name}"
                )
                
            else:
                print(
                    f"[alarmd] DEBUG: Alarm updated: "
                    f"{event.source}.{event.name}"
                )

                active_alarm.event = event

                if event.evtype==AlarmEventType.UPDATED:
                    active_alarm.last_update = now

                    print(
                        f"[alarmd] DEBUG: Alarm updated: "
                        f"{event.source}.{event.name}"
                    )
                #
            #
        else:
            
            #Clear the corresponding alarm entry from the active alarms
            if active_alarm is None:
                print(
                    f"[alarmd] DETAIL: Clearing event received for inactive alarm: "
                    f"{event.source}.{event.name}"
                )

            else:

                print(
                    f"[alarmd] DEBUG: Alarm CLEARED: "
                    f"{event.source}.{event.name}"
                )

                if event.evtype != AlarmEventType.SUPPRESSED:

                    print(
                        f"[alarmd] DEBUG: Sending clear notification: "
                        f"{event.source}.{event.name}"
                    )

                    self.notification_manager.notify(event)

                else:

                    print(
                        f"[alarmd] DETAIL: Alarm SUPPRESSED: "
                        f"{event.source}.{event.name}"
                    )

                self.active_alarms.pop(ev_id)

                print(
                    f"[alarmd] DEBUG: Active alarm removed: "
                    f"{event.source}.{event.name}"
                )
        #
    #

    def get_active_alarm(self, id):
        return self.active_alarms.get(id)
    #

    def is_active(self, id):
        return id in self.active_alarms