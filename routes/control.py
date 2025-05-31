# === Standard library imports ===
import os
import json
from uuid import uuid4
from pathlib import Path
from datetime import datetime

# === FastAPI framework imports ===
from fastapi import APIRouter, Depends, Header, HTTPException, Body

router = APIRouter(prefix="/control", tags=["control"])

# === Auth header check ===
def auth(key: str = Header(..., alias="X-API-Key")):
    if key != os.getenv("API_KEY"):
        raise HTTPException(401, "bad key")

# === Paths and data files ===
ACTIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "pending_actions.json"
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "actions.log"

# === Ensure directories and files exist ===
ACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

if not ACTIONS_PATH.exists():
    ACTIONS_PATH.write_text("[]")

# === Utility: Load / save action queue ===
def load_actions():
    return json.loads(ACTIONS_PATH.read_text())

def save_actions(actions):
    ACTIONS_PATH.write_text(json.dumps(actions, indent=2))

# === Utility: Append to persistent action log ===
def append_log(entry: dict):
    line = json.dumps(entry)
    print(f"[log] Writing log e
