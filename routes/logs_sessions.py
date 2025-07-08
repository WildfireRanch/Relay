# ──────────────────────────────────────────────────────────────────────────────
# Directory: routes
# Purpose: # Purpose: Manage and retrieve logs of user sessions within the application.
#
# Upstream:
#   - ENV: —
#   - Imports: fastapi, json, pathlib
#
# Downstream:
#   - —
#
# Contents:
#   - list_all_sessions()

# ──────────────────────────────────────────────────────────────────────────────

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
