import os
from pathlib import Path

class LockManager:
    def __init__(self, lock_path):
        self.lock_path = Path(lock_path)
    #

    def acquire(self):

        if self.lock_path.exists():

            pid = int(
                self.lock_path.read_text().strip()
            )
            
            try:
                os.kill(pid, 0) #Ask the kernel if the pid exist and if I am allowed to send signals
            except ProcessLookupError:
                print(
                    f"Removing stale lock "
                    f"for PID {pid}"
                )
                self.lock_path.unlink()

            except PermissionError:
                raise RuntimeError(
                    f"Lock file points to PID {pid}, "
                    f"which belongs to another user. "
                    f"Refusing startup."
                )
            else:
                raise RuntimeError(
                    f"mxlscd already running "
                    f"(PID {pid})"
                )
        #

        self.lock_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.lock_path.write_text(
            str(os.getpid())
        )
    #
    
    def release(self):

        if self.lock_path.exists():

            self.lock_path.unlink()
    #

    def is_locked(self):

        if not self.lock_path.exists():
            return False

        try:
            pid = int(
                self.lock_path.read_text().strip()
            )
        except (ValueError, OSError):
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        else:
            return True
    #

