# File: routes/control.py
# Directory: routes/
# Purpose: Relay Action Queue & Audit API (human-in-the-loop, max context, audit log)
# - Queue, approve, deny, and execute agent-proposed actions (with rationale/context)
# - Every action has history/audit trail and persistent logs
# - Supports comments, diff/context, operator identity, timeline
# - Gmail integration: send/list/get email with admin auth

import os
import json
from uuid import uuid4
from pathlib import Path
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException, Body

from services import gmail  # Gmail utility, see services/gmail.py

router = APIRouter(prefix="/control", tags=["control"])

# === Authentication: Require correct API key in header ===
def auth(key: str = Header(..., alias="X-API-Key")):
    if key != os.getenv("API_KEY"):
        raise HTTPException(401, "bad key")

# === File paths for queue and audit log ===
ACTIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "pending_actions.json"
LOG_PATH = Path(__file__).resolve().parents[1] / "logs" / "actions.log"
ACTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# === Ensure initial empty file exists ===
if not ACTIONS_PATH.exists():
    ACTIONS_PATH.write_text("[]")

# === Utility functions to load/save/append actions ===
def load_actions():
    """Load the full action queue from disk."""
    return json.loads(ACTIONS_PATH.read_text())

def save_actions(actions):
    """Write the full action queue to disk."""
    ACTIONS_PATH.write_text(json.dumps(actions, indent=2))

def append_log(entry: dict):
    """Append an event to the persistent audit log."""
    line = json.dumps(entry)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as f:
        f.write(line + "\n")

def update_action_history(action, status, user, comment=""):
    """Add a status change event to an action's timeline/history."""
    if "history" not in action:
        action["history"] = []
    action["history"].append({
        "timestamp": datetime.utcnow().isoformat(),
        "status": status,
        "user": user,
        "comment": comment
    })

# === Route: Write a file to disk ===
@router.post("/write_file")
def write_file(data: dict = Body(...), user=Depends(auth)):
    """
    Immediately write a file to disk. (Mostly used internally by approved actions.)
    """
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

# === Route: Queue a new agent-proposed action ===
@router.post("/queue_action")
def queue_action(data: dict = Body(...), user=Depends(auth)):
    """
    Queue a new action for human approval. Supports rationale/context/diff.
    """
    try:
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
        # Optionally add context, rationale, diff for transparency
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
    except Exception as e:
        raise HTTPException(500, f"Failed to queue action: {e}")

# === Route: List all actions in the queue (for review/approval) ===
@router.get("/list_queue")
def list_queue(user=Depends(auth)):
    """
    Return the full queue of pending/approved/denied actions (with all metadata).
    """
    try:
        return {"actions": load_actions()}
    except Exception as e:
        raise HTTPException(500, f"Failed to load queue: {e}")

# === Route: Approve a pending action (logs and executes if type is write_file) ===
@router.post("/approve_action")
def approve_action(data: dict = Body(...), user=Depends(auth)):
    """
    Approve and (if applicable) execute a pending action. Operator can leave a comment.
    Sends an email notification if configured.
    """
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

    # === Email notification (if ADMIN_EMAIL env var is set) ===
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

    # If action is file write, execute it now and log
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

    # Log all other approvals as well
    append_log({
        "id": action_id,
        "type": action_data.get("type"),
        "timestamp": datetime.utcnow().isoformat(),
        "status": "approved",
        "user": user,
        "comment": comment
    })

    return {"status": "approved"}

# === Route: Deny a pending action (with comment/audit log) ===
@router.post("/deny_action")
def deny_action(data: dict = Body(...), user=Depends(auth)):
    """
    Deny a pending action, recording operator comment and updating history/log.
    Sends an email notification if configured.
    """
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

    # === Email notification (if ADMIN_EMAIL env var is set) ===
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

# === Route: List all action log entries (full audit trail) ===
@router.get("/list_log")
def list_log(user=Depends(auth)):
    """
    Return the persistent action audit log (all approvals, denials, executions, with who/when/comments).
    """
    try:
        if not LOG_PATH.exists():
            return {"log": []}
        with LOG_PATH.open("r") as f:
            lines = f.readlines()
        return {"log": [json.loads(line) for line in lines if line.strip()]}
    except Exception as e:
        raise HTTPException(500, f"Failed to read log: {e}")

# === Route: Send an email via Gmail (admin/debug) ===
@router.post("/send_email")
def api_send_email(data: dict = Body(...), user=Depends(auth)):
    """
    Send an email (admin/debug/ops use). Required fields: to_email, subject, body.
    """
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

# === Route: List recent inbox emails via Gmail API ===
@router.get("/list_email")
def api_list_email(query: str = "", max_results: int = 10, user=Depends(auth)):
    """
    List recent emails matching a query (inbox audit/debug).
    """
    try:
        emails = gmail.list_emails(query=query, max_results=max_results)
        return {"emails": emails}
    except Exception as e:
        raise HTTPException(500, f"Gmail list failed: {e}")

# === Route: Fetch full details of a specific email ===
@router.get("/get_email")
def api_get_email(email_id: str, user=Depends(auth)):
    """
    Fetch full details of a specific email by its Gmail ID.
    """
    try:
        email = gmail.get_email(email_id)
        return {"email": email}
    except Exception as e:
        raise HTTPException(500, f"Gmail get failed: {e}")
