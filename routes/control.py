# File: routes/control.py
# Directory: routes/
# Purpose: Relay Action Queue & Audit API
# - Queue, approve, deny, and execute agent-proposed actions
# - Maintains audit log and Gmail notifications
# - CORS-safe, with strong error handling and API key auth

import os
import json
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Body

from services import gmail  # Gmail utility, see services/gmail.py

router = APIRouter(prefix="/control", tags=["control"])

# === Auth Middleware: Require valid API key ===
def auth(key: str = Header(None, alias="X-API-Key")):
    expected = os.getenv("API_KEY")
    if not key:
        raise HTTPException(status_code=401, detail="Missing API key")
    if key != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return "admin"  # For now just one user

# === File paths ===
ACTIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "pending_actions.json"
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "actions.log"
ACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

if not ACTIONS_PATH.exists():
    ACTIONS_PATH.write_text("[]")

# === Util: queue/load/log ===
def load_actions():
    return json.loads(ACTIONS_PATH.read_text())

def save_actions(actions):
    ACTIONS_PATH.write_text(json.dumps(actions, indent=2))

def append_log(entry: dict):
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def update_action_history(action, status, user, comment=""):
    if "history" not in action:
        action["history"] = []
    action["history"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "status": status,
        "user": user,
        "comment": comment
    })

# === POST /queue_action ===
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
    if data.get("context"):
        queued["action"]["context"] = data["context"]
    if data.get("rationale"):
        queued["action"]["rationale"] = data["rationale"]
    if data.get("diff"):
        queued["action"]["diff"] = data["diff"]

    actions = load_actions()
    actions.append(queued)
    save_actions(actions)
    return {"status": "queued", "id": action_id}

# === GET /list_queue ===
@router.get("/list_queue")
def list_queue(user=Depends(auth)):
    try:
        return {"actions": load_actions()}
    except Exception as e:
        raise HTTPException(500, f"Failed to load queue: {e}")

# === POST /approve_action ===
@router.post("/approve_action")
def approve_action(data: dict = Body(...), user=Depends(auth)):
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

    # Email notify
    try:
        to_addr = os.getenv("ADMIN_EMAIL")
        if to_addr:
            subject = f"[Relay] Action Approved (#{action_id[:8]})"
            body = (
                f"Action ID: {action_id}\n"
                f"Status: approved\n"
                f"User: {user}\n"
                f"Type: {action_data.get('type')}\n"
                f"Path: {action_data.get('path')}\n"
                f"Comment: {comment}\n\n"
                f"Timeline:\n{json.dumps(approved.get('history', []), indent=2)}"
            )
            gmail.send_email(to_addr, subject, body)
    except Exception as e:
        print(f"[Email] Approval notification failed: {e}")

    if action_data["type"] == "write_file":
        result = write_file(action_data, user=user)
        append_log({
            "id": action_id,
            "type": action_data["type"],
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

# === POST /deny_action ===
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

    try:
        to_addr = os.getenv("ADMIN_EMAIL")
        if to_addr:
            subject = f"[Relay] Action Denied (#{action_id[:8]})"
            body = (
                f"Action ID: {action_id}\n"
                f"Status: denied\n"
                f"User: {user}\n"
                f"Type: {denied['action'].get('type')}\n"
                f"Path: {denied['action'].get('path')}\n"
                f"Comment: {comment}\n\n"
                f"Timeline:\n{json.dumps(denied.get('history', []), indent=2)}"
            )
            gmail.send_email(to_addr, subject, body)
    except Exception as e:
        print(f"[Email] Denial notification failed: {e}")

    append_log({
        "id": action_id,
        "type": denied["action"].get("type"),
        "timestamp": datetime.utcnow().isoformat(),
        "status": "denied",
        "user": user,
        "comment": comment
    })

    return {"status": "denied"}

# === GET /list_log ===
@router.get("/list_log")
def list_log(user=Depends(auth)):
    try:
        if not LOG_PATH.exists():
            return {"log": []}
        with LOG_PATH.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        log_entries = [json.loads(line) for line in lines if line.strip()]
        return {"log": log_entries}
    except Exception as e:
        print(f"[list_log] Failed to read: {e}")
        raise HTTPException(500, f"Failed to read log: {e}")

# === POST /write_file ===
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

# === Gmail: send, list, get ===
@router.post("/send_email")
def api_send_email(data: dict = Body(...), user=Depends(auth)):
    to_email = data.get("to_email")
    subject = data.get("subject")
    body = data.get("body")
    if not (to_email and subject and body):
        raise HTTPException(400, "Missing fields")
    try:
        result = gmail.send_email(to_email, subject, body)
        return {"status": "sent", "id": result["id"]}
    except Exception as e:
        raise HTTPException(500, f"Gmail send failed: {e}")

@router.get("/list_email")
def api_list_email(query: str = "", max_results: int = 10, user=Depends(auth)):
    try:
        emails = gmail.list_emails(query=query, max_results=max_results)
        return {"emails": emails}
    except Exception as e:
        raise HTTPException(500, f"Gmail list failed: {e}")

@router.get("/get_email")
def api_get_email(email_id: str, user=Depends(auth)):
    try:
        email = gmail.get_email(email_id)
        return {"email": email}
    except Exception as e:
        raise HTTPException(500, f"Gmail get failed: {e}")
from fastapi import Request
from agents.control_agent import control_agent

@router.post("/test")
async def control_test(request: Request, user=Depends(auth)):
    """
    Test ControlAgent directly with a structured context payload.
    Expects:
    {
      "query": "restart backend",
      "context": {
        "action": "restart_service"
      }
    }
    """
    payload = await request.json()
    query = payload.get("query", "")
    context = payload.get("context", {})

    result = await control_agent.run(query=query, context=context, user_id=user)
    return result
