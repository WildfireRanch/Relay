# File: routes/integrations_github.py
# Purpose: GitHub App integration endpoints (JWT auth, installation token, status,
#          repository dispatch, and read-only repo access for contents/tree).
#
# Notes:
# - Requires env vars: GITHUB_APP_ID, GITHUB_APP_INSTALLATION_ID,
#   GITHUB_APP_PRIVATE_KEY_BASE64, GITHUB_OWNER, GITHUB_REPO
# - Permissions needed on the GitHub App (at minimum):
#     Contents: Read (Write if you want to commit later)
#     Pull requests: Read/Write (if you want to open PRs)
#     Issues: Read/Write (if you want to open issues)
#     Commit statuses: Read/Write (optional for setting statuses)
# - Errors are raised as HTTPException with the upstream message to avoid Railway 502s.x

from __future__ import annotations

import os
import time
import base64
import httpx
import jwt
import base64 as b64
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/integrations/github", tags=["github"])

# ──────────────────────────────────────────────────────────────────────────────
# Config & constants
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_ENVS = [
    "GITHUB_APP_ID",
    "GITHUB_APP_INSTALLATION_ID",
    "GITHUB_APP_PRIVATE_KEY_BASE64",
    "GITHUB_OWNER",
    "GITHUB_REPO",
]

HTTP_TIMEOUT = 10.0  # seconds
UA = {"User-Agent": "Relay-Echo/1.0 (+https://relay.wildfireranch.us)"}

# Simple in-memory cache for installation token (token, expires_at=unix ts)
_installation_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0}


# ──────────────────────────────────────────────────────────────────────────────
# Utilities: JWT + installation token
# ──────────────────────────────────────────────────────────────────────────────

def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise HTTPException(500, f"Missing required env: {name}")
    return val


def _app_jwt() -> str:
    """
    Build a short-lived JWT for GitHub App auth.
    GitHub requires 'iss' (App ID) to be an INTEGER.
    """
    app_id_raw = _require_env("GITHUB_APP_ID")
    try:
        app_id = int(app_id_raw)
    except ValueError:
        raise HTTPException(500, f"GITHUB_APP_ID must be numeric, got: {app_id_raw}")

    key_b64 = _require_env("GITHUB_APP_PRIVATE_KEY_BASE64")
    try:
        private_key = base64.b64decode(key_b64)
    except Exception as e:
        raise HTTPException(500, f"Failed to decode GITHUB_APP_PRIVATE_KEY_BASE64: {e}")

    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": app_id}  # skew +9m expiry

    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except Exception as e:
        raise HTTPException(500, f"JWT encode failed: {e}")


async def _installation_headers() -> Dict[str, str]:
    """
    Return Bearer headers with a cached Installation Access Token.
    Token is refreshed if missing or within 60s of expiry.
    """
    # Reuse token if valid
    now = int(time.time())
    cached = _installation_token_cache
    if cached["token"] and cached["expires_at"] - now > 60:
        return {"Authorization": f"Bearer {cached['token']}", "Accept": "application/vnd.github+json", **UA}

    inst_id = _require_env("GITHUB_APP_INSTALLATION_ID")
    jwt_token = _app_jwt()
    headers = {"Authorization": f"Bearer {jwt_token}", "Accept": "application/vnd.github+json", **UA}
    url = f"https://api.github.com/app/installations/{inst_id}/access_tokens"

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
        r = await x.post(url, headers=headers)

    if r.status_code >= 300:
        raise HTTPException(r.status_code, f"/access_tokens failed: {r.text}")

    data = r.json()
    token = data.get("token")
    expires_at_iso = data.get("expires_at")  # ISO8601
    if not token or not expires_at_iso:
        raise HTTPException(500, "Invalid /access_tokens response (missing token/expires_at)")

    # Parse expires_at (YYYY-MM-DDTHH:MM:SSZ)
    # Safe approximation: convert to unix by time.strptime + timegm, or trust 8m TTL default
    # Here we just cache for 8 minutes safely.
    cached["token"] = token
    cached["expires_at"] = now + 8 * 60  # 8 minutes
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", **UA}


# ──────────────────────────────────────────────────────────────────────────────
# Diagnostics
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/ping")
async def ping() -> Dict[str, bool]:
    return {"ok": True}


@router.get("/diag")
async def diag() -> Dict[str, Any]:
    """
    Report presence/length of required envs (without leaking values).
    """
    presence = {k: bool(os.getenv(k)) for k in REQUIRED_ENVS}
    lengths = {k: (len(os.getenv(k, "")) if os.getenv(k) else 0) for k in REQUIRED_ENVS}
    return {"ok": all(presence.values()), "presence": presence, "lengths": lengths}


@router.get("/app")
async def app_info() -> Dict[str, Any]:
    """
    Verify App JWT by calling the /app endpoint.
    """
    try:
        headers = {"Authorization": f"Bearer {_app_jwt()}", "Accept": "application/vnd.github+json", **UA}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get("https://api.github.com/app", headers=headers)
        body: Any = r.json() if "application/json" in r.headers.get("content-type", "") else r.text
        return {"status": r.status_code, "body": body}
    except Exception as e:
        raise HTTPException(500, f"/app probe failed: {e}")


@router.get("/installations")
async def list_installations() -> Dict[str, Any]:
    """
    List installations visible to this App JWT (helps confirm permissions).
    """
    try:
        headers = {"Authorization": f"Bearer {_app_jwt()}", "Accept": "application/vnd.github+json", **UA}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get("https://api.github.com/app/installations", headers=headers)
        body: Any = r.json() if "application/json" in r.headers.get("content-type", "") else r.text
        return {"status": r.status_code, "body": body}
    except Exception as e:
        raise HTTPException(500, f"/installations probe failed: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Status & dispatch
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/status")
async def status(branch: str = "main", owner: Optional[str] = None, repo: Optional[str] = None) -> Any:
    """
    Fetch combined commit status for a branch (Railway/Vercel status contexts will appear here).
    """
    owner = owner or _require_env("GITHUB_OWNER")
    repo = repo or _require_env("GITHUB_REPO")

    try:
        headers = await _installation_headers()
        url = f"https://api.github.com/repos/{owner}/{repo}/commits/{branch}/status"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(url, headers=headers)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        return r.json()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"status call failed: {e}")


@router.post("/dispatch")
async def dispatch(event_type: str, payload: Dict[str, Any] = {}) -> Dict[str, bool]:
    """
    Trigger a repository_dispatch event (useful for custom workflows, reindex, etc.).
    """
    owner = _require_env("GITHUB_OWNER")
    repo = _require_env("GITHUB_REPO")
    try:
        headers = await _installation_headers()
        url = f"https://api.github.com/repos/{owner}/{repo}/dispatches"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.post(url, json={"event_type": event_type, "client_payload": payload}, headers=headers)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"dispatch failed: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# Repo read endpoints (require Contents: Read)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/contents")
async def get_contents(path: str = "", ref: str = "main") -> Any:
    """
    List a directory or read a file from the repository.
    - For directories: returns {type:'dir', entries:[{name, path, type, size}]}
    - For files: returns {type:'file', path, sha, size, content:text}
    """
    owner = _require_env("GITHUB_OWNER")
    repo = _require_env("GITHUB_REPO")

    try:
        headers = await _installation_headers()
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as x:
            r = await x.get(url, headers=headers)
        if r.status_code >= 300:
            raise HTTPException(r.status_code, r.text)

        data = r.json()
        # Directory listing
        if isinstance(data, list):
            return {
                "type": "dir",
                "entries": [
                    {"name": i["name"], "path": i["path"], "type": i["type"], "size": i.get("size")}
                    for i in data
                ],
            }

        # Single file
        if data.get("encoding") == "base64" and "content" in data:
            try:
                text = b64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            except Exception:
                text = ""  # fallback
            return {
                "type": "file",
                "path": data.get("path"),
                "sha": data.get("sha"),
                "size": data.get("size"),
                "content": text,
            }

        # Pass through any other GitHub response shape
        return data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"contents failed: {e}")


@router.get("/tree")
async def get_tree(ref: str = "main", recursive: bool = True) -> Any:
    """
    Return the git tree for a ref (branch or SHA). With recursive=1 this lists full repo tree.
    """
    owner = _require_env("GITHUB_OWNER")
    repo = _require_env("GITHUB_REPO")

    try:
        headers = await _installation_headers()
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}"
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
