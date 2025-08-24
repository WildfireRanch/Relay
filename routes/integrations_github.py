# routes/integrations_github.py
import os, time, base64, httpx, jwt
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/integrations/github", tags=["github"])

REQUIRED_ENVS = [
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_APP_PRIVATE_KEY_BASE64",
    "GITHUB_OWNER",
    "GITHUB_REPO",
]

@router.get("/ping")
async def ping():
    return {"ok": True}

@router.get("/diag")
async def diag():
    # Don’t leak values—only presence and lengths
    presence = {k: bool(os.getenv(k)) for k in REQUIRED_ENVS}
    lengths  = {k: (len(os.getenv(k,"")) if os.getenv(k) else 0) for k in REQUIRED_ENVS}
    return {"ok": all(presence.values()), "presence": presence, "lengths": lengths}

def _app_jwt() -> str:
    app_id = os.getenv("GITHUB_APP_ID")
    key_b64 = os.getenv("GITHUB_APP_PRIVATE_KEY_BASE64","")
    if not app_id or not key_b64:
        raise HTTPException(500, "Missing GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY_BASE64")
    try:
        key = base64.b64decode(key_b64)
        now = int(time.time())
        return jwt.encode({"iat": now-60, "exp": now+540, "iss": app_id}, key, algorithm="RS256")
    except Exception as e:
        raise HTTPException(500, f"JWT build failed: {e}")

async def _headers():
    inst = os.getenv("GITHUB_APP_INSTALLATION_ID")
    if not inst:
        raise HTTPException(500, "Missing GITHUB_APP_INSTALLATION_ID")
    tok_headers = {"Authorization": f"Bearer {_app_jwt()}", "Accept": "application/vnd.github+json"}
    async with httpx.AsyncClient(timeout=10) as x:
        r = await x.post(f"https://api.github.com/app/installations/{inst}/access_tokens", headers=tok_headers)
    if r.status_code >= 300:
        # surface exact error so Railway won't wrap it as 502
        raise HTTPException(r.status_code, f"/access_tokens failed: {r.text}")
    token = r.json().get("token")
    if not token:
        raise HTTPException(500, "No token in access_tokens response")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

@router.get("/app")
async def app_info():
    try:
        headers = {"Authorization": f"Bearer {_app_jwt()}", "Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(timeout=10) as x:
            r = await x.get("https://api.github.com/app", headers=headers)
        return {"status": r.status_code, "body": r.json() if "application/json" in r.headers.get("content-type","") else r.text}
    except Exception as e:
        raise HTTPException(500, f"/app probe failed: {e}")

@router.get("/installations")
async def list_installations():
    try:
        headers = {"Authorization": f"Bearer {_app_jwt()}", "Accept": "application/vnd.github+json"}
        async with httpx.AsyncClient(timeout=10) as x:
            r = await x.get("https://api.github.com/app/installations", headers=headers)
        return {"status": r.status_code, "body": r.json() if "application/json" in r.headers.get("content-type","") else r.text}
    except Exception as e:
        raise HTTPException(500, f"/installations probe failed: {e}")

@router.get("/status")
async def status(branch: str = "main", owner: str | None = None, repo: str | None = None):
    owner = owner or os.getenv("GITHUB_OWNER")
    repo  = repo  or os.getenv("GITHUB_REPO")
    if not owner or not repo:
        raise HTTPException(500, f"Missing owner/repo (owner={owner}, repo={repo})")
    try:
        headers = await _headers()
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}/status"
        async with httpx.AsyncClient(timeout=10) as x:
            r = await x.get(url, headers=headers)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        # don’t let exceptions bubble into Railway 502—return a 500 with detail
        raise HTTPException(500, f"status call failed: {e}")

@router.post("/dispatch")
async def dispatch(event_type: str, payload: dict = {}):
    owner, repo = os.getenv("GITHUB_OWNER"), os.getenv("GITHUB_REPO")
    if not owner or not repo:
        raise HTTPException(500, "Missing GITHUB_OWNER/GITHUB_REPO")
    try:
        headers = await _headers()
        url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
        async with httpx.AsyncClient(timeout=10) as x:
            r = await x.post(url, json={"event_type": event_type, "client_payload": payload}, headers=headers)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"dispatch failed: {e}")
