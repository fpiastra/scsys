from dataclasses import (dataclass, asdict)
from pathlib import Path
import socket
import json

from .alarm_base import (AlarmEvent)


@dataclass
class AlarmClientConfig:
    runtime_dir: Path
    timeout: float = 1.0
    retries: int = 0
    retry_delay: float = 0.1

class AlarmClient:
    def __init__(self, cfg:AlarmClientConfig):
        self.cfg = cfg
        self.socket_path = self.cfg.runtime_dir / 'sockets' / 'alarmd.sock'
    #

    def send_event(self, event:AlarmEvent) -> bool:
        return self._send_message(
            "event",
            asdict(event)
        )
    
    def _send_message(self, msg_type: str, payload: dict | None = None) -> dict[str, Any]:

        with socket.socket(
                socket.AF_UNIX,
                socket.SOCK_STREAM
            ) as sock:
            try:
                sock.settimeout(self.cfg.timeout)
                sock.connect(str(self.socket_path))

                sock.sendall(
                    json.dumps(
                        self._build_message(
                            msg_type=msg_type,
                            payload=payload
                        )
                    ).encode('utf-8')
                )

                reply = self._parse_reply(sock.recv(4096))
            except (OSError, TypeError, ValueError, RuntimeError) as err:
                return {'success': False,
                        'error': str(err)}
        
        return reply

    def _build_message(
        self,
        msg_type: str,
        payload: dict | None = None
    ):
        if payload is None:
            return {"command": msg_type}
        #
        return {
            "type": msg_type,
            "payload": payload
        }

    def _parse_reply(self, reply: bytes):
        if not reply:
            raise RuntimeError("Connection closed by alarmd.")

        if not "success" in reply:
            raise RuntimeError(f"Malformed reply from alarmd (\n    {str(reply)}\n)")
        
        return json.loads(reply.decode('utf-8'))