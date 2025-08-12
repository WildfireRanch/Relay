# File: services/action_queue.py
from __future__ import annotations
import json, os, time
from datetime import datetime, timezone
from typing import Any, Dict

LOG_PATH = os.getenv("ACTION_LOG_PATH", "logs/actions.log")

def enqueue_action(kind: str, payload: Dict[str, Any]) -> None:
    """Simple local queue stub. Replace with DB/Redis later."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "payload": payload,
        "id": f"{int(time.time()*1000)}-{kind}"
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
