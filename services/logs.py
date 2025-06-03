# services/logs.py
from datetime import datetime
import json
import pathlib
import requests

LOG_PATH = pathlib.Path("logs/session_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# === Basic logging ===
def log_entry(source: str, message: str):
    """
    Write a new line to the session log.
    """
    entry = {
        "time": datetime.utcnow().isoformat(),
        "source": source,
        "message": message,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

# === Retrieve recent logs ===
def get_recent_logs(n=100):
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-n:]]

# === Smart logger: log and auto-update context ===
def log_and_refresh(source: str, message: str):
    log_entry(source, message)
    try:
        requests.post("http://localhost:8000/context/update", timeout=2)
    except Exception:
        pass  # fail silently if context update fails
