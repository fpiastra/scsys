NOTIFIERS: dict[str, AlarmNotifier] = {}

def discover_notifiers():
    pass
#

def get_notifier(name):
    return NOTIFIERS.get(name)
#