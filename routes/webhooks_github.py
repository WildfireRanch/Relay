# ──────────────────────────────────────────────────────────────────────────────
# File: routes/webhooks_github.py
# Purpose: Verified, hardened GitHub webhook intake with background dispatch
#
# Notes:
#  - Verifies X-Hub-Signature-256 (sha256=...) or legacy X-Hub-Signature (sha1=...)
#  - Returns 2xx quickly; heavy work runs in BackgroundTasks
#  - In-memory de-dupe on X-GitHub-Delivery to avoid reprocessing retries
#  - Dispatches common events (pull_request, issue_comment, push, ping)
#  - Queues a Control action via in-process queue first; falls back to HTTP; else logs
#  - Does NOT execute repo writes; those live in /control endpoints or GH Actions
#  - Quiet on client disconnects (returns 204, no stacktrace)
# ──────────────────────────────────────────────────────────────────────────────

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

from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Response
from starlette.requests import ClientDisconnect

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = logging.getLogger("webhooks.github")

# ────────────────────────── Configuration ──────────────────────────

CONTROL_BASE_URL = os.getenv("CONTROL_BASE_URL", "http://127.0.0.1:8080")
API_KEY = os.getenv("API_KEY", "")
EVENT_LOG_PATH = os.getenv("EVENT_LOG_PATH", "logs/events.log")
MAX_EVENT_BYTES = int(os.getenv("GITHUB_WEBHOOK_MAX_BYTES", "1048576"))  # 1 MiB
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")

# De-dup cache (process-local)
_seen: set[str] = set()
_SEEN_MAX = 2048  # simple cap to avoid unbounded growth


# ────────────────────────── Utilities ──────────────────────────

def _append_event_log(record: dict[str, Any]) -> None:
    """Best-effort JSONL append (never raises)."""
    try:
        os.makedirs(os.path.dirname(EVENT_LOG_PATH), exist_ok=True)
        with open(EVENT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("Failed to write event log: %s", e)


def _queue_control_action(kind: str, payload: dict[str, Any]) -> bool:
    """
    Prefer in-process queue (Codespaces-safe). Fallback to HTTP; else write to log.
    Returns True if enqueued via local or HTTP; False if only logged.
    """
    # 1) In-process queue
    try:
        from services.action_queue import enqueue_action  # type: ignore
        enqueue_action(kind, payload)
        return True
    except Exception as e:
        log.info("Local control queue unavailable (%s); trying HTTP fallback", e.__class__.__name__)

    # 2) HTTP fallback (works when Control runs as a separate service)
    url = f"{CONTROL_BASE_URL.rstrip('/')}/control/queue_action"
    body = json.dumps({
        "action_type": kind,
        "source": "github_webhook",
        "payload": payload,
        "queued_at": datetime.now(timezone.utc).isoformat()
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            _ = resp.read()  # drain
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
        log.info("HTTP queue fallback failed: %s", getattr(e, "reason", e))
        _append_event_log({"kind": kind, "payload": payload, "note": "queued_to_log"})
        return False


def _already_seen(delivery_id: str) -> bool:
    """Return True if this delivery was already processed; record if new."""
    if not delivery_id:
        return False
    if delivery_id in _seen:
        return True
    if len(_seen) >= _SEEN_MAX:
        _seen.clear()
    _seen.add(delivery_id)
    return False


def _safe_json_loads(raw: bytes) -> dict[str, Any]:
    """Decode JSON with clear 400 on bad payloads."""
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")


def _verify_sig(req: Request, body: bytes, secret: str) -> None:
    """
    Verify GitHub HMAC signatures.
    - Prefer X-Hub-Signature-256 (sha256=...)
    - Accept legacy X-Hub-Signature (sha1=...)
    """
    if not secret:
        # Treat as server misconfig; do not process unsigned webhook in prod.
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    sig256 = req.headers.get("X-Hub-Signature-256")  # sha256=...
    sig1 = req.headers.get("X-Hub-Signature")        # sha1=...

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


def _extract_fenced_block(text: str, lang_hint: str = "") -> Optional[str]:
    """
    Extract first ```<lang> fenced code block body. Returns None if none found.
    """
    fence = "```"
    if fence not in text:
        return None
    parts = text.split(fence)
    # Odd indices are inside code fences: [text, block, text, block, ...]
    for i in range(1, len(parts), 2):
        header_and_body = parts[i].strip().splitlines()
        if not header_and_body:
            continue
        first = header_and_body[0].strip().lower()
        body = "\n".join(header_and_body[1:]) if len(header_and_body) > 1 else ""
        if not lang_hint or lang_hint in first:
            body = body.strip()
            return body or None
    return None


# ────────────────────────── Probes ──────────────────────────

@router.get("/github")
async def github_probe():
    return {"ok": True, "msg": "github webhook endpoint is up (GET probe)"}


@router.get("/github/debug")
async def github_debug():
    # Do not return the secret; just presence & cache stats.
    return {
        "ok": True,
        "has_secret": bool(WEBHOOK_SECRET),
        "delivery_cache_size": len(_seen),
        "max_event_bytes": MAX_EVENT_BYTES,
    }


# ────────────────────────── Route (POST) ──────────────────────────

@router.post("/github")
async def github(req: Request, bg: BackgroundTasks):
    """
    Hardened webhook ingress:
      • 204 on ClientDisconnect (quiet)
      • payload size guard
      • HMAC verification
      • in-memory de-dup on X-GitHub-Delivery
      • enqueue background dispatch, return 2xx immediately
    """
    # 1) ClientDisconnect is not an error (quiet 204)
    try:
        body = await req.body()
    except ClientDisconnect:
        return Response(status_code=204)

    # 2) Body size guard
    if len(body) > MAX_EVENT_BYTES:
        raise HTTPException(status_code=413, detail="Payload too large")

    # 3) Verify HMAC signatures
    _verify_sig(req, body, WEBHOOK_SECRET)

    # 4) Event headers
    event = req.headers.get("X-GitHub-Event", "unknown")
    delivery = req.headers.get("X-GitHub-Delivery", "")

    # 5) De-duplicate
    if _already_seen(delivery):
        return {"ok": True, "event": event, "delivery": delivery, "deduped": True}

    # 6) Parse JSON (400 if invalid)
    payload = _safe_json_loads(body)

    # 7) Dispatch asynchronously; keep GitHub happy with quick 2xx
    bg.add_task(_dispatch_event, event, payload, delivery)
    return {"ok": True, "event": event, "delivery": delivery, "queued": True}


# ────────────────────────── Dispatcher ──────────────────────────

def _dispatch_event(event: str, p: dict[str, Any], delivery: str) -> None:
    """
    Background dispatcher — never raises up the stack.
    """
    try:
        if event == "ping":
            _append_event_log({"event": "ping", "delivery": delivery})
            return

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


def _on_pull_request(p: dict[str, Any], delivery: str) -> None:
    action = p.get("action")
    repo = p.get("repository", {}).get("full_name")
    pr = p.get("pull_request", {}) or {}
    number = pr.get("number")
    head_branch = (pr.get("head", {}) or {}).get("ref", "")
    data = {"repo": repo, "number": number, "branch": head_branch, "action": action, "delivery": delivery}

    # Example triage: label/notify for branches created by our bot
    if head_branch and head_branch.startswith("echo/") and action in {"opened", "reopened", "synchronize"}:
        _queue_control_action("pr_triage", data)
    else:
        _append_event_log({"event": "pull_request", **data})


def _on_issue_comment(p: dict[str, Any], delivery: str) -> None:
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


def _on_push(p: dict[str, Any], delivery: str) -> None:
    repo = p.get("repository", {}).get("full_name")
    ref = p.get("ref", "")
    data = {"repo": repo, "ref": ref, "delivery": delivery}
    _append_event_log({"event": "push", **data})
