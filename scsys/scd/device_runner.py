import argparse
from argparse import Namespace

from pathlib import Path
import pickle

from ..devices import get_device_class
from .process_manager import DeviceInfo

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("device_image")

    args = parser.parse_args()

    #
    # Load all available device classes.
    #
    with open(args.device_image, "rb") as f:
        device_info = pickle.load(f)
    #
    
    device_info.device.run()

#

if __name__ == "__main__":
    raise SystemExit(main())