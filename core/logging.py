# File: logging.py
# Directory: core
# Purpose: Structured JSON logging helper for all agents/routes. Ensures payloads
#          are always serializable and timestamped.
#
# Upstream:
#   - Imports: datetime, json
#   - Callers: agents.*, routes.ask, services.*, tests.*
#
# Downstream:
#   - stdout (log aggregation / container logs)
#
# Contents:
#   - log_event(event_type: str, payload: dict)

import datetime
import json
from typing import Any, Dict


def _safe(obj: Any) -> Any:
    """
    Ensure object is JSON-serializable.
    If not, fall back to str() wrapped in a dict.
    """
    try:
        json.dumps(obj)
        return obj
    except Exception:
        try:
            return {"_repr": str(obj)}
        except Exception:
            return {"_repr": "<unserializable>"}


def log_event(event_type: str, payload: Dict[str, Any]) -> None:
    """
    Emit a structured log line to stdout.
    Example:
      {"timestamp":"2025-08-28T20:11:02.123Z","event":"ask_received","details":{...}}
    """
    ts = datetime.datetime.utcnow().isoformat() + "Z"
    record = {
        "timestamp": ts,
        "event": event_type,
        "details": _safe(payload),
    }
    try:
        print(json.dumps(record, ensure_ascii=False))
    except Exception:
        # Last resort: print a minimal fallback
        print(f'{{"timestamp":"{ts}","event":"{event_type}","details":"<logging failure>"}}')
