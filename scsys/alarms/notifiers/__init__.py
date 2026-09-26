NOTIFIER_CLASSES: dict[str, AlarmNotifier] = {}

def discover_notifiers():
    pass
#

def get_notifier(name):
    return NOTIFIER_CLASSES.get(name)
#