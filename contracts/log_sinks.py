import json
import logging
from datetime import datetime, timezone
from urllib.request import Request, urlopen


class HttpJsonLogHandler(logging.Handler):
    """
    Best-effort JSON log forwarder.
    Failures are intentionally swallowed to avoid impacting request paths.
    """

    def __init__(self, sink_url: str, timeout_seconds: float = 2.0):
        super().__init__()
        self.sink_url = sink_url
        self.timeout_seconds = timeout_seconds

    def emit(self, record):
        try:
            payload = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'level': record.levelname,
                'logger': record.name,
                'message': record.getMessage(),
                'request_id': getattr(record, 'request_id', '-'),
                'user_id': getattr(record, 'request_user_id', '-'),
                'org_id': getattr(record, 'request_org_id', '-'),
                'path': getattr(record, 'request_path', '-'),
            }
            body = json.dumps(payload).encode('utf-8')
            request = Request(
                self.sink_url,
                data=body,
                headers={'Content-Type': 'application/json'},
                method='POST',
            )
            with urlopen(request, timeout=self.timeout_seconds):
                pass
        except Exception:
            return
