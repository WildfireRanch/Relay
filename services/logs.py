# ─────────────────────────────────────────────────────────────────────────────
# File: logs.py
# Directory: services
# Purpose: # Purpose: Manage logging of application activities and exceptions, and provide access to recent log data.
#
# Upstream:
#   - ENV: —
#   - Imports: datetime, json, pathlib, requests, traceback
#
# Downstream:
#   - routes.context
#   - routes.logs
#
# Contents:
#   - get_recent_logs()
#   - log_and_refresh()
#   - log_entry()
#   - log_exception()
# ─────────────────────────────────────────────────────────────────────────────

from datetime import datetime
import json
import pathlib
import requests
import traceback

LOG_PATH = pathlib.Path("logs/session_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def log_entry(source: str, message: str, level: str = "INFO", extra: dict = None):
    """
    Write a new line to the session log, optionally with level and extra fields.
    """
    entry = {
        "time": datetime.utcnow().isoformat(),
        "source": source,
        "level": level,
        "message": message,
    }
    if extra:
        entry.update(extra)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def log_exception(source: str, exc: Exception, context: str = ""):
    """
    Log an exception with stack trace and context.
    """
    stack = traceback.format_exc()
    log_entry(
        source=source,
        message=f"Exception: {exc} | Context: {context}",
        level="ERROR",
        extra={"stack_trace": stack}
    )

def get_recent_logs(n=100, level_filter=None):
    """
    Retrieve the last n log entries, optionally filtering by log level.
    """
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
    logs = [json.loads(line) for line in lines[-n:]]
    if level_filter:
        logs = [log for log in logs if log.get("level") == level_filter]
    return logs

def log_and_refresh(source: str, message: str):
    log_entry(source, message)
    try:
        requests.post("http://localhost:8000/context/update", timeout=2)
    except Exception as e:
        log_exception("log_and_refresh", e, "Failed to auto-refresh context")
