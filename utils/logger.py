# File: utils/logger.py
from datetime import datetime

def log_event(event_type: str, payload: dict):
    timestamp = datetime.utcnow().isoformat()
    print(f"[{timestamp}] {event_type.upper()} → {payload}")
