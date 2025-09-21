# ──────────────────────────────────────────────────────────────────────────────
# File: control.py
# Directory: routes
# Purpose: # Purpose: Manages action control flows including authentication, logging, queuing, and approval processes within the application.
#
# Upstream:
#   - ENV: API_KEY
#   - Imports: agents, agents.control_agent, datetime, fastapi, json, os, pathlib, services, uuid
#
# Downstream:
#   - main
#
# Contents:
#   - append_log()
#   - approve_action()
#   - auth()
#   - control_test()
#   - deny_action()
#   - list_log()
#   - list_queue()
#   - load_actions()
#   - queue_action()
#   - save_actions()
#   - update_action_history()
#   - write_file()

# ──────────────────────────────────────────────────────────────────────────────

import os, json
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Body, Request

from services import gmail
from agents import codex_agent, docs_agent, echo_agent
try:
    from agents.control_agent import control_agent
except Exception as e:
    raise RuntimeError("control router disabled: missing control_agent export") from e

router = APIRouter(prefix="/control", tags=["control"])

# === Auth Middleware ===
def auth(key: str = Header(None, alias="X-API-Key")):
    expected = os.getenv("API_KEY")
    if not key or key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return "admin"

# === File paths ===
ACTIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "pending_actions.json"
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "actions.log"
ACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
if not ACTIONS_PATH.exists():
    ACTIONS_PATH.write_text("[]")

# === Utils ===
def load_actions():
    return json.loads(ACTIONS_PATH.read_text())

def save_actions(actions):
    ACTIONS_PATH.write_text(json.dumps(actions, indent=2))

def append_log(entry: dict):
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def update_action_history(action, status, user, comment=""):
    action.setdefault("history", []).append({
        "timestamp": datetime.utcnow().isoformat(),
        "status": status,
        "user": user,
        "comment": comment
    })

# === Agent Dispatch Map ===
AGENT_DISPATCH = {
    "codex": codex_agent.handle,
    "control": control_agent.run,
    "docs": docs_agent.analyze,
    "echo": echo_agent.run,
}

# === /queue_action ===
@router.post("/queue_action")
def queue_action(data: dict = Body(...), user=Depends(auth)):
    action_id = str(uuid4())
    queued = {
        "id": action_id,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "pending",
        "action": data,
        "history": [{
            "timestamp": datetime.utcnow().isoformat(),
            "status": "pending",
            "user": user,
            "comment": data.get("rationale", "")
        }]
    }
    actions = load_actions()
    actions.append(queued)
    save_actions(actions)
    return {"status": "queued", "id": action_id}

# === /list_queue ===
@router.get("/list_queue")
def list_queue(user=Depends(auth)):
    try:
        return {"actions": load_actions()}
    except Exception as e:
        raise HTTPException(500, f"Failed to load queue: {e}")

# === /approve_action ===
@router.post("/approve_action")
async def approve_action(data: dict = Body(...), user=Depends(auth)):
    action_id = data.get("id")
    comment = data.get("comment", "")
    if not action_id:
        raise HTTPException(400, "Missing action ID")

    actions = load_actions()
    updated = []
    approved = None

    for a in actions:
        if a["id"] == action_id and a["status"] == "pending":
            approved = a
            a["status"] = "approved"
            a["approved_at"] = datetime.utcnow().isoformat()
            update_action_history(a, "approved", user, comment)
        updated.append(a)

    if not approved:
        raise HTTPException(404, "No matching pending action found")

    save_actions(updated)
    action_data = approved["action"]

    route = action_data.get("type")
    handler = AGENT_DISPATCH.get(route)

    if handler:
        result = await handler(
            query=action_data.get("query", ""),
            context=action_data.get("context", {}),
            user_id=user
        )
        append_log({
            "id": action_id,
            "type": route,
            "timestamp": datetime.utcnow().isoformat(),
            "status": "executed",
            "result": result,
            "user": user,
            "comment": comment
        })
        return result

    # Optional: file write fallback
    if action_data.get("type") == "write_file":
        result = write_file(action_data, user=user)
        append_log({
            "id": action_id,
            "type": "write_file",
            "path": action_data.get("path"),
            "timestamp": datetime.utcnow().isoformat(),
            "status": "executed",
            "result": result,
            "user": user,
            "comment": comment
        })
        return result

    append_log({
        "id": action_id,
        "type": action_data.get("type"),
        "timestamp": datetime.utcnow().isoformat(),
        "status": "approved",
        "user": user,
        "comment": comment
    })

    return {"status": "approved"}

# === /deny_action ===
@router.post("/deny_action")
def deny_action(data: dict = Body(...), user=Depends(auth)):
    action_id = data.get("id")
    comment = data.get("comment", "")
    if not action_id:
        raise HTTPException(400, "Missing action ID")

    actions = load_actions()
    updated = []
    denied = None

    for a in actions:
        if a["id"] == action_id and a["status"] == "pending":
            denied = a
            a["status"] = "denied"
            a["denied_at"] = datetime.utcnow().isoformat()
            update_action_history(a, "denied", user, comment)
        updated.append(a)

    if not denied:
        raise HTTPException(404, "No matching pending action found")

    save_actions(updated)
    append_log({
        "id": action_id,
        "type": denied["action"].get("type"),
        "timestamp": datetime.utcnow().isoformat(),
        "status": "denied",
        "user": user,
        "comment": comment
    })
    return {"status": "denied"}

# === /list_log ===
@router.get("/list_log")
def list_log(user=Depends(auth)):
    try:
        if not LOG_PATH.exists():
            return {"log": []}
        with LOG_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        return {"log": [json.loads(line) for line in lines if line.strip()]}
    except Exception as e:
        raise HTTPException(500, f"Failed to read log: {e}")

# === /write_file ===
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

# === /test (ControlAgent direct test) ===
@router.post("/test")
async def control_test(request: Request, user=Depends(auth)):
    payload = await request.json()
    query = payload.get("query", "")
    context = payload.get("context", {})

    result = await control_agent.run(query=query, context=context, user_id=user)
    append_log({
        "id": f"manual-{datetime.utcnow().isoformat()}",
        "type": "control_test",
        "timestamp": datetime.utcnow().isoformat(),
        "status": "executed",
        "user": user,
        "query": query,
        "context": context,
        "result": result
    })
    return result
