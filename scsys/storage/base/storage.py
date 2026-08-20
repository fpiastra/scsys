from abc import ABC, abstractmethod
from collections import deque

class ScStorage(ABC):
    def __init__(self, device_name:str, device_type:str, config:dict):
        self.device_name = device_name
        self.device_type = device_type
        self.cfg = config
        self.meas_queue = deque() #This contains the queue of the measurements to be written
        self.is_connected = True # This is the default as not every storage type needs to be connected

    def connect(self):
        """
        Optional initialization.
        """
        pass
    
    @abstractmethod
    def write_measurement(self, meas):
        """
        Write a snapshot of the device measurements.
        """
        pass

    def close(self):
        """
        Optional cleanup.
        """
        pass

    def enqueue(self, meas_record):
        self.meas_queue.append(meas_record)
    
    def write(self):
        if not len(self.meas_queue):
            return
        #
        while self.meas_queue:
            meas_record = self.meas_queue[0]

            if not self.write_measurement(meas_record):
                return
            
            self.meas_queue.popleft()
        #
    #
#