# File: routes/webhooks_github.py
# Purpose: GitHub webhook endpoint with GET probe and HMAC verification

import os
import hmac
import hashlib
import json
import logging
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# ── Probe endpoint for curl tests ────────────────────────────────────────────
@router.get("/github")
async def github_probe():
    return {"ok": True, "msg": "GitHub webhook endpoint is up (GET probe)"}

# ── Signature verification helper ───────────────────────────────────────────
def verify_signature(sig_hdr: str | None, body: bytes, secret: str):
    if not secret:
        raise HTTPException(500, "Webhook secret not configured")
    if not sig_hdr:
        raise HTTPException(400, "Missing signature")

    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    # Optional debug logging
    if os.getenv("WEBHOOK_DEBUG", "").lower() in ("1", "true", "yes"):
        logging.info(f"Webhook sig header: {sig_hdr}")
        logging.info(f"Webhook sig expected: {expected}")

    # Constant-time comparison
    if not hmac.compare_digest(expected, sig_hdr):
        raise HTTPException(401, "Bad signature")

# ── Main webhook handler ─────────────────────────────────────────────────────
@router.post("/github")
async def github_webhook(req: Request):
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    body = await req.body()

    # Verify signature before doing any work
    verify_signature(req.headers.get("X-Hub-Signature-256"), body, secret)

    event = req.headers.get("X-GitHub-Event", "unknown")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    # TODO: log to memory system / ActionQueue integration
    logging.info(f"Received GitHub event: {event}")
    # Example: logging.debug(json.dumps(payload, indent=2))

    return {"ok": True, "event": event}

