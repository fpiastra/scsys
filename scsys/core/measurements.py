from datetime import datetime

from dataclasses import (dataclass, field)

@dataclass
class Measurement:
    value: int | float | bool | None
    timestamp: datetime | None
    valid: bool = False #This indicates that the last readout failed and the fields above are outdated (the last good readout)

@dataclass
class MeasurementRecord:
    varname: str
    value: int | float | bool
    timestamp: datetime