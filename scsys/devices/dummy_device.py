from .base import (ScDevice, Measurement)
from datetime import datetime
from random import random

class DummyDevice(ScDevice):

    DEVICE_TYPE = "dummy"

    VARIABLES = (
        "dummyvar",
        "setpoint"
    )

    def __init__(self, name, config_file, runtime_dir):
        super().__init__(name, config_file, runtime_dir)

        self.internal_setpoint = 0.0
        ts = datetime.now()

        #The class must be fixed as 
        for var in self.VARIABLES:

            self.add_measurement(
                var,
                initial_value=0.0,
                initial_timestamp=datetime.now()
            )
        #
    #

    def connect(self):
        self.connected = True

        print(
            f"Dummy device "
            f"{self.name} connected"
        )
    #
    
    def disconnect(self):
        self.connected = False

        print(
            f"Dummy device "
            f"{self.name} disconnected"
        )
    #
    
    def get_value(
        self,
        varname
    ):
        meas = self.measurements.get(varname)
        if meas is None:
            return None #This happens when the value was asked before the measurement was ever made
        return meas.value
    #

    def set_value(
        self,
        varname,
        value
    ):
        """
        Returns:
            True  -> success
            False -> failure
        """
        if varname != 'setpoint':
            print(f'{self.name}:'
                  f"The variable '{varname}' is read only!"
                  )
            return False
        #
        print(
            f"{self.name}: "
            f"{varname} <- {value}"
        )
        self.internal_setpoint = value #This is set only in this dummy class, but this should not happen in a real device. The measurement value must be changed only for the read_measurements function
        return True
    #

    def read_measurements(self):

        self.update_measurement(
            varname   = 'dummyvar',
            value     = random(),
            timestamp = datetime.now()
        )
        
        self.update_measurement(
            varname   = 'setpoint',
            value     = self.internal_setpoint,
            timestamp = datetime.now()
        )
    #
#