import os, hmac, hashlib, json, logging
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.get("/github")
async def github_probe():
    return {"ok": True, "msg": "github webhook endpoint is up (GET probe)"}

@router.get("/github/debug")
async def github_debug():
    # Do NOT print the secret; just indicate presence.
    return {
        "ok": True,
        "has_secret": bool(os.getenv("GITHUB_WEBHOOK_SECRET")),
        "env": os.getenv("ENV", "local"),
    }

def verify_sig(req: Request, body: bytes, secret: str):
    if not secret:
        # Explicit 500 so you immediately see misconfig vs bad sig.
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    sig256 = req.headers.get("X-Hub-Signature-256")  # e.g. sha256=deadbeef...
    sig1   = req.headers.get("X-Hub-Signature")      # e.g. sha1=deadbeef...

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

# Simple in-memory dedupe to prevent retries from reprocessing
_seen = set()
def already_seen(delivery_id: str) -> bool:
    if delivery_id in _seen:
        return True
    if len(_seen) > 2048:
        _seen.clear()
    _seen.add(delivery_id)
    return False

@router.post("/github")
async def github(req: Request, bg: BackgroundTasks):
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    body = await req.body()

    # Verify signature first
    verify_sig(req, body, secret)

    event    = req.headers.get("X-GitHub-Event", "unknown")
    delivery = req.headers.get("X-GitHub-Delivery", "unknown")

    if already_seen(delivery):
        return {"ok": True, "event": event, "delivery": delivery, "deduped": True}

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # For now just log & ack; Step 3 will dispatch in background
    logging.info("GH webhook %s delivery=%s", event, delivery)
    return {"ok": True, "event": event, "delivery": delivery, "queued": True}
