from dataclasses import dataclass
import time

from .alarm_base import *
from ..devices import Measurement

@dataclass
class AlarmState:
    active: bool = False

class AlarmEngine:
    def __init__(self, dev_name:str, rules:list[dict] | None=None):
        self.dev_name = dev_name
        self.rules: list[AlarmRule] = []
        if rules is not None: 
            self.rules = [AlarmRule.from_dict(rule_cfg) for rule_cfg in rules]
        self.states: dict[str, AlarmState] = {}
    #

    def evaluate(
        self,
        measurements: dict[str, Measurement]
    ) -> list[AlarmEvent]:

        events: list[AlarmEvent] = []

        now = time.time()

        for rule in self.rules:

            if not rule.enabled:
                continue

            meas = measurements.get(rule.var_name)
            if meas is None:
                continue

            rule_state = self.states.setdefault(
                rule.name,
                AlarmState()
            )

            invalid_name = f"{rule.name}:invalid"

            invalid_state = self.states.setdefault(
                invalid_name,
                AlarmState()
            )

            #
            # INVALID MEASUREMENT
            #
            if not meas.valid:

                #
                # Suppress threshold alarm if active
                #
                if rule_state.active:

                    rule_state.active = False

                    events.append(
                        AlarmEvent(
                            source=self.dev_name,
                            name=rule.name,
                            severity=rule.severity,
                            active=False,
                            message=f"Suppressed because measurement '{meas.name}' is invalid.",
                            timestamp=now,
                            evtype=AlarmEventType.SUPPRESSED,
                        )
                    )

                #
                # Optionally raise invalid-measurement alarm
                #
                if (
                    rule.invalid_policy == InvalidValuePolicy.ALARM
                    and not invalid_state.active
                ):

                    invalid_state.active = True

                    events.append(
                        AlarmEvent(
                            source=self.dev_name,
                            name=invalid_name,
                            severity=rule.severity,
                            active=True,
                            message=f"Device {self.dev_name}: measurement '{meas.name}' is invalid.",
                            timestamp=now,
                            evtype=AlarmEventType.ACTIVATED,
                        )
                    )

                continue

            #
            # VALID MEASUREMENT
            #

            #
            # Clear invalid-measurement alarm
            #
            if invalid_state.active:

                invalid_state.active = False

                events.append(
                    AlarmEvent(
                        source=self.dev_name,
                        name=invalid_name,
                        severity=rule.severity,
                        active=False,
                        message=f"Device {self.dev_name}: measurement '{meas.name}' is valid again.",
                        timestamp=now
                    )
                )

            #
            # Evaluate threshold rule
            #
            condition = self._compare(
                meas.value,
                rule.operator,
                rule.threshold
            )

            if condition:

                evtype = (
                    AlarmEventType.UPDATED
                    if rule_state.active
                    else AlarmEventType.ACTIVATED
                )

                rule_state.active = True

                events.append(
                    AlarmEvent(
                        source=self.dev_name,
                        name=rule.name,
                        severity=rule.severity,
                        active=True,
                        message=(
                            f"Device {self.dev_name}: "
                            f"{meas.name}={meas.value} "
                            f"violates rule "
                            f"{rule.operator}{rule.threshold}"
                        ),
                        timestamp=now,
                        evtype=evtype,
                    )
                )

            elif rule_state.active:

                rule_state.active = False

                events.append(
                    AlarmEvent(
                        source=self.dev_name,
                        name=rule.name,
                        severity=rule.severity,
                        active=False,
                        message=(
                            f"Device {self.dev_name}: "
                            f"{meas.name}={meas.value} "
                            f"returned in range."
                        ),
                        timestamp=now,
                    )
                )

        return events
    #
        
        


    def _compare(
            self,
            value: float,
            operator: ComparisonOperator,
            threshold: float
        ) -> bool:
        
        if operator == ComparisonOperator.LT:
            return value < threshold
        elif operator == ComparisonOperator.LE:
            return value <= threshold
        elif operator == ComparisonOperator.EQ:
            return value == threshold
        elif operator == ComparisonOperator.NE:
            return value != threshold
        elif operator == ComparisonOperator.GE:
            return value >= threshold
        elif operator == ComparisonOperator.GT:
            return value > threshold

        raise RuntimeError(f"Unknown comparison operator {operator}")
