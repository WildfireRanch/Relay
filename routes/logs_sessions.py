# File: routes/logs_sessions.py
# Directory: routes/
# Purpose: API route for listing user session memory logs from /logs/sessions/*.jsonl

from fastapi import APIRouter, Request
from pathlib import Path
import json

router = APIRouter(prefix="/logs/sessions", tags=["logs", "memory"])

SESSION_LOG_DIR = Path("./logs/sessions")

@router.get("/all")
def list_all_sessions():
    entries = []
    for path in SESSION_LOG_DIR.glob("*.jsonl"):
        with open(path) as f:
            for line in f:
                try:
                    parsed = json.loads(line)
                    entries.append(parsed)
                except json.JSONDecodeError:
                    continue
    return {"entries": sorted(entries, key=lambda x: x.get("timestamp", ""), reverse=True)}
