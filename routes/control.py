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
    print(f"[log] Writing to: {LOG_PATH}")
    print(f"[log] Entry: {line}")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)  # ensure logs/ exists
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")

# === Route: Write a file to disk ===
@router.post("/write_file")
def write_file(data: dict = Body(...), user=Depends(auth)):
    path = data.get("path")
    content = data.get("content")

    if not path or not content:
        raise HTTPException(400, "Missing path or content")

    base = Path(__file__).resolve().parents[1]
    full_path = base / path
    full_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        full_path.write_text(content)
        return {
            "status": "success",
            "path": str(full_path.relative_to(base)),
            "size": len(content)
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to write file: {e}")

# === Route: Queue a proposed action (e.g. write_file) ===
@router.post("/queue_action")
def queue_action(data: dict = Body(...), user=Depends(auth)):
    try:
        action_id = str(uuid4())
        queued = {
            "id": action_id,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "queued",
            "action": data,
        }
        actions = load_actions()
        actions.append(queued)
        save_actions(actions)
        return {"status": "queued", "id": action_id}
    except Exception as e:
        raise HTTPException(500, f"Failed to queue action: {e}")

# === Route: View the current action queue ===
@router.get("/list_queue")
def list_queue(user=Depends(auth)):
    try:
        return {"actions": load_actions()}
    except Exception as e:
        raise HTTPException(500, f"Failed to load queue: {e}")

# === Route: Approve and execute a queued action ===
@router.post("/approve_action")
def approve_action(data: dict = Body(...), user=Depends(auth)):
    action_id = data.get("id")
    if not action_id:
        raise HTTPException(400, "Missing action ID")

    actions = load_actions()
    updated = []
    approved = None

    for a in actions:
        if a["id"] == action_id and a["status"] == "queued":
            approved = a
            a["status"] = "approved"
            a["approved_at"] = datetime.utcnow().isoformat()
        updated.append(a)

    if not approved:
        raise HTTPException(404, "No matching queued action found")

    save_actions(updated)

    action_data = approved["action"]
    if action_data["type"] == "write_file":
        result = write_file(action_data, user=user)
        print(f"[approve] About to log write_file result: {result}")
        print(f"[approve] Executing and logging action: {action_id}")
        append_log({
            "id": action_id,
            "type": action_data["type"],
            "path": action_data.get("path"),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "executed",
            "result": result
        })
        return result

    return {"status": "approved", "note": "No executable logic for this action type"}

# === Route: View the executed action log ===
@router.get("/list_log")
def list_log(user=Depends(auth)):
    """Return the list of executed/logged actions."""
    try:
        if not LOG_PATH.exists():
            return {"log": []}
        with LOG_PATH.open("r") as f:
            lines = f.readlines()
        return {"log": [json.loads(line) for line in lines if line.strip()]}
    except Exception as e:
        raise HTTPException(500, f"Failed to read log: {e}")