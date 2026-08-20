from pathlib import Path
from datetime import datetime, timezone

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

from .base import ScStorage
from ..devices import MeasurementRecord

def read_token(token_path):

    token_path = Path(token_path)

    if not token_path.exists():
        raise RuntimeError(
            f'InfluxDB token file "{token_path}" '
            f'does not exist.'
        )

    try:
        token = token_path.read_text().strip()

    except OSError as err:
        raise RuntimeError(
            f'Failed to read InfluxDB token file '
            f'"{token_path}": {err}'
        ) from err

    if not token:
        raise RuntimeError(
            f'InfluxDB token file "{token_path}" '
            f'is empty.'
        )

    return token
#

class InfluxStorage(ScStorage):

    STORAGE_TYPE = 'influxdb'

    def __init__(self, device_name:str, device_type:str, config:dict):
        super().__init__(device_name, device_type, config)

        self.url = config["url"] #This must be declared otherwise it fails
        self.token = read_token(config["token_path"]) #This must be declared otherwise it fails
        self.org = config["org"] #This must be declared otherwise it fails
        self.bucket = config.get("bucket", "slowcontrol") #This has a default
        self.measurement = config["measurement"] #This must be declared otherwise it fails

        self.client = None
        self.write_api = None
        self.is_connected = False
        self.connect()
    #

    def connect(self):

        if self.is_connected:
            return

        #
        # Defensive cleanup in case we are reconnecting
        #
        if self.client is not None:

            try:
                self.client.close()
            except Exception:
                pass

            self.client = None
            self.write_api = None
        #

        try:

            self.client = InfluxDBClient(
                url=self.url,
                token=self.token,
                org=self.org
            )

            if not self.client.ping():

                raise RuntimeError(
                    f"InfluxDB server '{self.url}' "
                    f"is not responding."
                )

            self.write_api = self.client.write_api(
                write_options=SYNCHRONOUS
            )

            self.is_connected = True

        except Exception as err:

            if self.client is not None:

                try:
                    self.client.close()
                except Exception:
                    pass

            self.client = None
            self.write_api = None
            self.is_connected = False

            raise RuntimeError(
                f"Failed to connect to InfluxDB "
                f"at '{self.url}': {err}"
            ) from err
    #

    def write_measurement(self, meas:MeasurementRecord):

        if meas.value is None:
            return True #This is a trick to not publish it and at the same time removeit from the queue

        point = (
            Point(self.measurement)
            .tag("device", self.device_name)
            .tag("type", self.device_type)
            .field(meas.varname, meas.value)
            .time(meas.timestamp)
        )

        try:
            self.connect()

        except Exception as err:

            print(
                f"InfluxDB reconnection failed "
                f"for device '{self.device_name}': "
                f"{err}"
            )
            return False
        #

        try:
            self.write_api.write(
                bucket=self.bucket,
                org=self.org,
                record=point
            )

            return True

        except Exception as err:
            self.is_connected = False
            print(
                f"InfluxDB write failed "
                f"for device '{self.device_name}': "
                f"{err}"
            )   
            return False
        #
    #

    def close(self):
        if self.client is not None:
            self.client.close()
            self.client = None
            self.write_api = None
            self.is_connected = False
        #
    #
#   



