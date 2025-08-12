# File: routes/webhooks_github.py
# Purpose: Verified, hardened GitHub webhook intake with background dispatch
# Notes:
# - Verifies X-Hub-Signature-256 (sha256=...) or legacy X-Hub-Signature (sha1=...)
# - Returns 2xx quickly; heavy work runs in BackgroundTasks
# - In-memory de-dupe on X-GitHub-Delivery to avoid reprocessing retries
# - Dispatches common events (pull_request, issue_comment, push)
# - Queues a Control action via /control/queue_action if available, else logs to logs/events.log
# - Does NOT execute repo writes; that’s Step 4 (/gh action endpoints)

from __future__ import annotations

import os
import hmac
import json
import hashlib
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger("webhooks.github")

# Config
CONTROL_BASE_URL = os.getenv("CONTROL_BASE_URL", "http://127.0.0.1:8080")
API_KEY = os.getenv("API_KEY", "")
EVENT_LOG_PATH = os.getenv("EVENT_LOG_PATH", "logs/events.log")

# ────────────────────────── Helpers ──────────────────────────

@router.get("/github")
async def github_probe():
    return {"ok": True, "msg": "github webhook endpoint is up (GET probe)"}

@router.get("/github/debug")
async def github_debug():
    # Do not return the actual secret, just its presence.
    return {
        "ok": True,
        "has_secret": bool(os.getenv("GITHUB_WEBHOOK_SECRET")),
        "env": os.getenv("ENV", "local"),
    }

def _verify_sig(req: Request, body: bytes, secret: str):
    if not secret:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    sig256 = req.headers.get("X-Hub-Signature-256")  # sha256=...
    sig1   = req.headers.get("X-Hub-Signature")      # sha1=...

    if sig256:
        expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, sig256):
            return
        raise HTTPException(status_code=401, detail="Bad signature (sha256)")

    if sig1:
        expected = "sha1=" + hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
        if hmac.compare_digest(expected, sig1):
            return
        raise HTTPException(status_code=401, detail="Bad signature (sha1)")

    raise HTTPException(status_code=400, detail="Missing signature header")

_seen: set[str] = set()
def _already_seen(delivery_id: str) -> bool:
    if not delivery_id:
        return False
    if delivery_id in _seen:
        return True
    if len(_seen) > 2048:
        _seen.clear()
    _seen.add(delivery_id)
    return False

def _safe_json_loads(raw: bytes) -> dict[str, Any]:
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

def _extract_fenced_block(text: str, lang_hint: str = "") -> Optional[str]:
    fence = "```"
    if fence not in text:
        return None
    parts = text.split(fence)
    # search fenced sections; odd indexes are inside code fences
    for i in range(1, len(parts), 2):
        header_and_body = parts[i].strip().splitlines()
        if not header_and_body:
            continue
        first = header_and_body[0].strip().lower()
        body = "\n".join(header_and_body[1:]) if len(header_and_body) > 1 else ""
        if not lang_hint or lang_hint in first:
            return body.strip() or None
    return None

def _append_event_log(record: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(EVENT_LOG_PATH), exist_ok=True)
        with open(EVENT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        log.warning("Failed to write event log: %s", e)

def _queue_control_action(kind: str, payload: dict[str, Any]) -> bool:
    """Try to hand off to your Control ActionQueue; fall back to logfile."""
    url = f"{CONTROL_BASE_URL.rstrip('/')}/control/queue_action"
    body = json.dumps({
        "action_type": kind,
        "source": "github_webhook",
        "payload": payload,
        "queued_at": datetime.now(timezone.utc).isoformat()
    }).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}" if API_KEY else "",
    }
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()  # drain
        return True
    except Exception as e:
        log.info("Control queue not available, logging instead: %s", e)
        _append_event_log({"kind": kind, "payload": payload, "note": "queued_to_log"})
        return False

# ────────────────────────── Route ──────────────────────────

@router.post("/github")
async def github(req: Request, bg: BackgroundTasks):
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    body = await req.body()

    _verify_sig(req, body, secret)

    event    = req.headers.get("X-GitHub-Event", "unknown")
    delivery = req.headers.get("X-GitHub-Delivery", "")

    if _already_seen(delivery):
        return {"ok": True, "event": event, "delivery": delivery, "deduped": True}

    payload = _safe_json_loads(body)
    # process async; keep GitHub happy with a fast 2xx
    bg.add_task(_dispatch_event, event, payload, delivery)
    return {"ok": True, "event": event, "delivery": delivery, "queued": True}

# ────────────────────────── Dispatcher ──────────────────────────

def _dispatch_event(event: str, p: dict[str, Any], delivery: str):
    try:
        if event == "pull_request":
            _on_pull_request(p, delivery)
        elif event == "issue_comment":
            _on_issue_comment(p, delivery)
        elif event == "push":
            _on_push(p, delivery)
        else:
            log.info("Unhandled GH event=%s delivery=%s", event, delivery)
            _append_event_log({"event": event, "delivery": delivery, "unhandled": True})
    except Exception as ex:
        log.exception("Webhook dispatch failed: %s", ex)
        _append_event_log({"event": event, "delivery": delivery, "error": str(ex)})

def _on_pull_request(p: dict[str, Any], delivery: str):
    action = p.get("action")
    repo = p.get("repository", {}).get("full_name")
    pr = p.get("pull_request", {}) or {}
    number = pr.get("number")
    head_branch = (pr.get("head", {}) or {}).get("ref", "")
    data = {"repo": repo, "number": number, "branch": head_branch, "action": action, "delivery": delivery}

    # Example triage: label/notify for branches created by our bot
    if head_branch.startswith("echo/") and action in {"opened", "reopened", "synchronize"}:
        _queue_control_action("pr_triage", data)
    else:
        _append_event_log({"event": "pull_request", **data})

def _on_issue_comment(p: dict[str, Any], delivery: str):
    if p.get("action") != "created":
        return
    repo = p.get("repository", {}).get("full_name")
    issue = p.get("issue", {}) or {}
    number = issue.get("number")
    comment_body = (p.get("comment", {}) or {}).get("body", "") or ""
    data = {"repo": repo, "number": number, "delivery": delivery}

    # Command: /echo apply-diff with a ```diff fenced block
    if comment_body.strip().startswith("/echo apply-diff"):
        diff = _extract_fenced_block(comment_body, lang_hint="diff")
        if not diff:
            _queue_control_action("comment_error", {**data, "msg": "No ```diff block found"})
            return
        _queue_control_action("apply_diff_request", {**data, "diff": diff})
    else:
        _append_event_log({"event": "issue_comment", **data})

def _on_push(p: dict[str, Any], delivery: str):
    repo = p.get("repository", {}).get("full_name")
    ref = p.get("ref", "")
    data = {"repo": repo, "ref": ref, "delivery": delivery}
    _append_event_log({"event": "push", **data})
