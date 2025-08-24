import os, httpx
from fastapi import APIRouter, HTTPException
from services.github_app import installation_token

router = APIRouter(prefix="/integrations/github", tags=["github"])

@router.get("/ping")
async def ping():
    return {"ok": True}

async def _h():
    return {"Authorization": f"Bearer {await installation_token()}",
            "Accept": "application/vnd.github+json"}

@router.get("/status")
async def status(branch: str = "main"):
    owner, repo = os.getenv("GITHUB_OWNER"), os.getenv("GITHUB_REPO")
    if not owner or not repo:
        raise HTTPException(500, "Missing GITHUB_OWNER/GITHUB_REPO")
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}/status"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.get(url, headers=await _h())
    if r.status_code >= 300:
        raise HTTPException(r.status_code, r.text)
    return r.json()

@router.post("/dispatch")
async def dispatch(event_type: str, payload: dict = {}):
    owner, repo = os.getenv("GITHUB_OWNER"), os.getenv("GITHUB_REPO")
    url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.post(url, json={"event_type": event_type,
                                    "client_payload": payload},
                         headers=await _h())
    if r.status_code >= 300:
        raise HTTPException(r.status_code, r.text)
    return {"ok": True}
