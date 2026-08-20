import argparse
from argparse import Namespace

from .client import send
from .formatter import print_response


def handle_scd(action):
    if action != "status":
        #TODO: figure out which othe commands make sense for the scd inquire and control
        return
    #
    request = {
        "object": "scd",
        "action": action
    }

    response = send(request)

    print_response(response)
#

def handle_devices_list():

    request = {
        'object': 'device',
        "action": "device_list"
    }

    response = send(request)

    print_response(response)
#

def handle_device(args:Namespace):
    if args.action == "status":
        handle_device_status(args.device)
        #
    elif args.action == "start":
        handle_device_start(args.device)
    #
    elif args.action == "stop":
        handle_device_stop(args.device)
    #
    elif args.action == "restart":
        handle_device_restart(args.device)
    #
    elif args.action == "get":
        if len(args.extra) != 1:
            raise RuntimeError(
                "get requires a variable name"
            )
        handle_device_get(
            args.device,
            args.extra[0]
        )
    #
    elif args.action == "set":
        if len(args.extra) != 2:
            raise RuntimeError(
                "set requires a variable name and a value"
            )
        handle_device_set(
            args.device,
            args.extra[0],
            args.extra[1]
        )
    #

def handle_device_status(device):

    request = {
        'object': 'device',
        "action": "status",
        "device": device
    }

    response = send(request)

    print_response(response)
#

def handle_device_start(device):

    request = {
        'object': 'device',
        "action": "start",
        "device": device
    }

    response = send(request)

    print_response(response)
#

def handle_device_get(
    device,
    varname
):
    request = {
        'object': 'device',
        "action": "get",
        "device": device,
        "varname": varname
    }

    response = send(request)
    print_response(response)
#

def handle_device_set(
    device,
    varname,
    value
):
    request = {
        'object': 'device',
        "action": "set",
        "device": device,
        "varname": varname,
        "value": value
    }

    response = send(request)
    print_response(response)
#

def handle_device_stop(device):

    request = {
        'object': 'device',
        "action": "stop",
        "device": device
    }

    response = send(request)

    print_response(response)
#

def handle_device_restart(device):

    request = {
        'object': 'device',
        "action": "restart",
        "device": device
    }

    response = send(request)

    print_response(response)
#

def dispatch(args):

    if args.object == "scd":
        handle_scd(args.action)
    elif args.object == "devices":
        handle_devices_list()
    elif args.object == "device":
        handle_device(args)
    #
#

def main():
    
    parser = argparse.ArgumentParser(
        prog="scctl",
        description="General Slow Control System CLI"
    )

    subparsers = parser.add_subparsers(
        dest="object",
        required=True
    )

    scd_parser = subparsers.add_parser("scd")
    scd_parser.add_argument(
        "action",
        choices=[
            "status"
        ]
    )
    
    status_parser = subparsers.add_parser("status")
    devices_parser = subparsers.add_parser("devices")
    device_parser = subparsers.add_parser("device")
    alarm_parser  = subparsers.add_parser("alarm")
    config_parser = subparsers.add_parser("config")

    #Device subparsers
    device_parser.add_argument("device")
    device_parser.add_argument(
        "action",
        choices=[
            "status",
            "get",
            "set",
            "start",
            "stop",
            "restart"
        ]
    )

    device_parser.add_argument(
        "extra",
        nargs="*"
    )

    
    
    args = parser.parse_args()

    print(f"Request to be sent:\n {args}")

    dispatch(args)
#

if __name__ == '__main__':
    main()