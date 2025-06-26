# File: core/logging.py
# Purpose: Centralized event logging for agents and system-level tracking

import datetime
import json

def log_event(event_type: str, payload: dict):
    """Log key events to stdout or later to file/db/analytics."""
    timestamp = datetime.datetime.utcnow().isoformat()
    print(json.dumps({
        "timestamp": timestamp,
        "event": event_type,
        "details": payload
    }))
