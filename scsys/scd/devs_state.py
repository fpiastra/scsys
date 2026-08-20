from pathlib import Path
import json


class DevsState:

    RUNNING = "running"
    STOPPED = "stopped"

    def __init__(self, runtime_dir):
        self.runtime_dir = Path(runtime_dir)
        self.devsstate_file = self.runtime_dir / "devs_state.json"

        self.devs_state = {}

        self.load()

    def exists(self, device):
        return self.get(device) is not None
    #

    def get(self, device):
        return self.devs_state.get(device)

    def set(self, device, state):
        self.devs_state[device] = state
        self.save()

    def all(self):
        return self.devs_state.copy()

    def save(self):
        self.devsstate_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with self.devsstate_file.open("w") as f:
            json.dump(
                self.devs_state,
                f,
                indent=4
            )
        #

    def load(self):
        if not self.devsstate_file.exists():
            self.devs_state = {}
            return

        try:
            with self.devsstate_file.open("r") as f:
                self.devs_state = json.load(f)

        except Exception:
            #
            # Corrupted file:
            # start from an empty state.
            #
            self.devs_state = {}
    #