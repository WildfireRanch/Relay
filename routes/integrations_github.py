# File: routes/integrations_github.py
# Purpose: GitHub App integration endpoints (JWT auth → installation token),
#          diagnostics, branch/status helpers, READ endpoints (contents/tree/search),
#          and optional WRITE endpoints (put file, open PR) behind strict guards.
#
# Env (required):
#   GITHUB_APP_ID                      # integer App ID
#   GITHUB_APP_INSTALLATION_ID         # installation id
#   GITHUB_APP_PRIVATE_KEY_BASE64      # base64 of PEM (-----BEGIN PRIVATE KEY----- ... )
#   GITHUB_OWNER=WildfireRanch
#   GITHUB_REPO=Relay
#
# Env (optional / write-safety):
#   ECHO_GH_WRITE_ENABLED=false        # flip to true to enable write/PR routes
#   INTERNAL_API_KEY=...               # required header: X-Api-Key for write routes
#
# Notes:
# - Installation tokens expire ~60m. We parse 'expires_at' and refresh with guard.
# - All routes are allowlisted to OWNER/REPO (no external repos).
# - Write routes require BOTH the env gate + API key header.
# - Errors bubble as HTTP errors (prevents Railway 502 masks).

from __future__ import annotations
import os, time, base64, calendar, json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel

router = APIRouter(prefix="/integrations/github", tags=["github"])

# ── Config ────────────────────────────────────────────────────────────────────
REQUIRED_ENVS = [
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_APP_PRIVATE_KEY_BASE64",
    "GITHUB_OWNER",
    "GITHUB_REPO",
]
HTTP_TIMEOUT = 20.0
UA = {"User-Agent": "Relay-Echo/1.1 (+https://relay.wildfireranch.us)"}
GITHUB_API = "https://api.github.com"

OWNER = os.getenv("GITHUB_OWNER", "")
REPO  = os.getenv("GITHUB_REPO", "")

WRITE_ENABLED = os.getenv("ECHO_GH_WRITE_ENABLED", "false").lower() == "true"
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

# in-memory cache for installation token
_token_cache: Dict[str, Any] = {"token": None, "exp_unix": 0}

# ── Helpers ───────────────────────────────────────────────────────────────────
def _require_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise HTTPException(500, f"Missing required env: {name}")
    return v

def _allowlisted(owner: str, repo: str) -> None:
    if owner != OWNER or repo != REPO:
        raise HTTPException(403, "repo not allowlisted")

def _parse_expires_at_iso(iso: str) -> int:
    # Example: "2025-09-12T19:22:54Z"
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())

def _make_app_jwt() -> str:
    app_id_raw = _require_env("GITHUB_APP_ID")
    try:
        app_id = int(app_id_raw)
    except ValueError:
        raise HTTPException(500, f"GITHUB_APP_ID must be an integer (got {app_id_raw})")

    key_b64 = _require_env("GITHUB_APP_PRIVATE_KEY_BASE64")
    try:
        private_key = base64.b64decode(key_b64)
    except Exception as e:
        raise HTTPException(500, f"Failed to b64-decode GITHUB_APP_PRIVATE_KEY_BASE64: {e}")

    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": app_id}  # slack + short TTL
    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except Exception as e:
        raise HTTPException(500, f"JWT encode failed: {e}")

async def _get_installation_token() -> str:
    # refresh if less than 2 minutes remaining
    now = int(time.time())
    if _token_cache["token"] and (_token_cache["exp_unix"] - now) > 120:
        return _token_cache["token"]

    inst_id = _require_env("GITHUB_APP_INSTALLATION_ID")
    headers = {"Authorization": f"Bearer {_make_app_jwt()}",
               "Accept": "application/vnd.github+json", **UA}
    url = f"{GITHUB_API}/app/installations/{inst_id}/access_tokens"

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
        r = await x.post(url, headers=headers)
    if r.status_code >= 300:
        raise HTTPException(r.status_code, f"/access_tokens failed: {r.text}")

    data = r.json()
    token = data.get("token")
    expires_at = data.get("expires_at")
    if not token or not expires_at:
        raise HTTPException(500, "Invalid /access_tokens response (missing token/expires_at)")

    _token_cache["token"] = token
    _token_cache["exp_unix"] = _parse_expires_at_iso(expires_at)
    return token

async def _gh_headers(raw: bool = False) -> Dict[str, str]:
    tok = await _get_installation_token()
    accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    return {"Authorization": f"Bearer {tok}", "Accept": accept, **UA}

# ── Diagnostics ───────────────────────────────────────────────────────────────
@router.get("/ping")
async def ping() -> Dict[str, bool]:
    return {"ok": True}

@router.get("/diag")
async def diag() -> Dict[str, Any]:
    presence = {k: bool(os.getenv(k)) for k in REQUIRED_ENVS}
    lengths = {k: (len(os.getenv(k, "")) if os.getenv(k) else 0) for k in REQUIRED_ENVS}
    # fetch default_branch for convenience
    owner, repo = _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")
    try:
        headers = await _gh_headers()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=headers)
        rb = r.json() if "application/json" in r.headers.get("content-type","") else {}
        default_branch = (rb or {}).get("default_branch")
    except Exception:
        default_branch = None
    return {"ok": all(presence.values()), "presence": presence, "lengths": lengths, "default_branch": default_branch}

@router.get("/app")
async def app_info() -> Dict[str, Any]:
    try:
        headers = {"Authorization": f"Bearer {_make_app_jwt()}",
                   "Accept": "application/vnd.github+json", **UA}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(f"{GITHUB_API}/app", headers=headers)
        body: Any = r.json() if "application/json" in r.headers.get("content-type","") else r.text
        return {"status": r.status_code, "body": body}
    except Exception as e:
        raise HTTPException(500, f"/app probe failed: {e}")

@router.get("/installations")
async def list_installations() -> Dict[str, Any]:
    try:
        headers = {"Authorization": f"Bearer {_make_app_jwt()}",
                   "Accept": "application/vnd.github+json", **UA}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(f"{GITHUB_API}/app/installations", headers=headers)
        body: Any = r.json() if "application/json" in r.headers.get("content-type","") else r.text
        return {"status": r.status_code, "body": body}
    except Exception as e:
        raise HTTPException(500, f"/installations probe failed: {e}")

@router.get("/status")
async def status(branch: str = "main") -> Any:
    owner, repo = _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")
    try:
        headers = await _gh_headers()
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(f"{GITHUB_API}/repos/{owner}/{repo}/commits/{branch}/status", headers=headers)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"status call failed: {e}")

# ── Repository READ ───────────────────────────────────────────────────────────
@router.get("/tree")
async def get_tree(ref: str = "HEAD", recursive: bool = True) -> Any:
    """Return the git tree for a ref (branch or SHA). Use ?recursive=1 for full listing."""
    owner, repo = _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")
    try:
        headers = await _gh_headers()
        url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}"
        if recursive:
            url += "?recursive=1"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(url, headers=headers)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"tree failed: {e}")

@router.get("/contents")
async def get_contents(path: str = "", ref: str = "main", raw: bool = False) -> Any:
    """
    List a directory or read a file from the repository.
    - Directories → {type:'dir', entries:[{name,path,type,size}]}
    - Files (raw=false) → {type:'file', path, sha, size, content:text}
    - Files (raw=true)  → {path, ref, raw:true, content: <string> }
    """
    owner, repo = _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")
    try:
        headers = await _gh_headers(raw=raw)
        url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
        params = {"ref": ref}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(url, headers=headers, params=params)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)

        if raw:
            # Raw returns the file content body directly
            text = r.text
            return {"path": path, "ref": ref, "raw": True, "content": text}

        data = r.json()
        if isinstance(data, list):
            return {
                "type": "dir",
                "entries": [
                    {"name": i["name"], "path": i["path"], "type": i["type"], "size": i.get("size")}
                    for i in data
                ],
            }
        # file with base64 payload
        if data.get("encoding") == "base64" and "content" in data:
            try:
                decoded = base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            except Exception:
                decoded = ""
            return {"type": "file", "path": data.get("path"), "sha": data.get("sha"),
                    "size": data.get("size"), "content": decoded}
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"contents failed: {e}")

@router.get("/search/code")
async def search_code(
    q: str = Query(..., description="GitHub code search query (without repo: filter)"),
    per_page: int = 30, page: int = 1
) -> Any:
    """Search code within the allowlisted repo. Example: q='ContextEngine language:python'"""
    owner, repo = _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")
    try:
        headers = await _gh_headers()
        query = f"{q} repo:{owner}/{repo}"
        params = {"q": query, "per_page": per_page, "page": page}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(f"{GITHUB_API}/search/code", headers=headers, params=params)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        data = r.json()
        items = [
            {"path": i.get("path"), "sha": i.get("sha"),
             "score": i.get("score"), "html_url": i.get("html_url")}
            for i in data.get("items", [])
        ]
        return {"total": data.get("total_count", 0), "items": items}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"search failed: {e}")

# ── Optional WRITE (guarded) ──────────────────────────────────────────────────
class PutFile(BaseModel):
    path: str
    branch: str = "main"
    message: str
    content_b64: str
    sha: Optional[str] = None  # include when updating an existing file

def _require_write(x_api_key: Optional[str]):
    if not WRITE_ENABLED:
        raise HTTPException(403, "write disabled")
    if not x_api_key or x_api_key != INTERNAL_API_KEY:
        raise HTTPException(401, "invalid api key")

@router.put("/contents")
async def put_contents(body: PutFile, x_api_key: Optional[str] = Header(default=None, convert_underscores=False)):
    """Create/update a file in a feature branch. Requires ECHO_GH_WRITE_ENABLED + X-Api-Key."""
    _require_write(x_api_key)
    owner, repo = _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")
    try:
        headers = await _gh_headers()
        payload = {"message": body.message, "content": body.content_b64, "branch": body.branch}
        if body.sha:
            payload["sha"] = body.sha
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.put(f"{GITHUB_API}/repos/{owner}/{repo}/contents/{body.path}",
                            headers=headers, json=payload)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        data = r.json()
        return {"content": data.get("content", {}), "commit": data.get("commit", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"put contents failed: {e}")

class NewPR(BaseModel):
    title: str
    head: str
    base: str = "main"
    body: Optional[str] = None

@router.post("/pulls")
async def create_pr(body: NewPR, x_api_key: Optional[str] = Header(default=None, convert_underscores=False)):
    """Open a pull request from 'head' → 'base'. Requires write gate + API key."""
    _require_write(x_api_key)
    owner, repo = _require_env("GITHUB_OWNER"), _require_env("GITHUB_REPO")
    try:
        headers = await _gh_headers()
        payload = {"title": body.title, "head": body.head, "base": body.base, "body": body.body}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.post(f"{GITHUB_API}/repos/{owner}/{repo}/pulls", headers=headers, json=payload)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        data = r.json()
        return {"number": data["number"], "title": data["title"],
                "head": data["head"]["ref"], "base": data["base"]["ref"]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"create pr failed: {e}")
