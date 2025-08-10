# routes/webhooks_github.py
import os, hmac, hashlib, json
from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

@router.get("/github")   # simple GET so you can probe with curl
async def github_probe():
    return {"ok": True, "msg": "github webhook endpoint is up (GET probe)"}

def verify(sig_hdr: str | None, body: bytes, secret: str):
    if not sig_hdr:
        raise HTTPException(400, "Missing signature")
    mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(f"sha256={mac}", sig_hdr):
        raise HTTPException(401, "Bad signature")

@router.post("/github")
async def github(req: Request):
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    body = await req.body()
    verify(req.headers.get("X-Hub-Signature-256"), body, secret)
    event = req.headers.get("X-GitHub-Event", "unknown")
    payload = json.loads(body.decode("utf-8") or "{}")
    # TODO: log -> memory / queue actions here
    return {"ok": True, "event": event}
