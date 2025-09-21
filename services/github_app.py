"""
services/github_app.py
Purpose: Helper for GitHub App JWT and installation token using consistent envs.

Env (preferred):
  - GITHUB_APP_ID                       (int)
  - GITHUB_APP_INSTALLATION_ID         (int/id)
  - GITHUB_APP_PRIVATE_KEY_BASE64      (base64 PEM: -----BEGIN PRIVATE KEY----- ...)

Back-compat fallbacks supported:
  - GITHUB_INSTALLATION_ID
  - GITHUB_APP_PRIVATE_KEY             (raw PEM)
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, Optional

import httpx
import jwt

GITHUB_API = "https://api.github.com"

_token_cache: Dict[str, Any] = {"token": None, "exp": 0}


def _env_installation_id() -> str:
    return os.getenv("GITHUB_APP_INSTALLATION_ID") or os.getenv("GITHUB_INSTALLATION_ID") or ""


def _env_app_id() -> str:
    return os.getenv("GITHUB_APP_ID") or ""


def _env_private_key_pem() -> bytes:
    # Preferred: base64 of PEM
    b64 = os.getenv("GITHUB_APP_PRIVATE_KEY_BASE64")
    if b64:
        try:
            return base64.b64decode(b64)
        except Exception:
            pass
    raw = os.getenv("GITHUB_APP_PRIVATE_KEY") or ""
    return raw.encode("utf-8") if raw else b""


def _make_app_jwt() -> str:
    app_id = _env_app_id()
    key = _env_private_key_pem()
    if not app_id or not key:
        raise RuntimeError("GitHub App env not configured (need APP_ID and PRIVATE_KEY)")
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": int(app_id)}
    return jwt.encode(payload, key, algorithm="RS256")


def get_installation_token() -> str:
    # refresh if < 2 min remaining
    if _token_cache["token"] and _token_cache["exp"] - time.time() > 120:
        return _token_cache["token"]

    inst_id = _env_installation_id()
    if not inst_id:
        raise RuntimeError("GITHUB_APP_INSTALLATION_ID is not set")

    app_jwt = _make_app_jwt()
    url = f"{GITHUB_API}/app/installations/{inst_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    with httpx.Client(timeout=20) as c:
        r = c.post(url, headers=headers)
        r.raise_for_status()
        data = r.json()

    _token_cache["token"] = data.get("token")
    # expires_at example: "2025-09-12T19:22:54Z"
    expires_at = data.get("expires_at", "1970-01-01T00:00:00Z")
    _token_cache["exp"] = int(time.mktime(time.strptime(expires_at, "%Y-%m-%dT%H:%M:%SZ")))
    return _token_cache["token"]


def gh_headers(raw: bool = False) -> Dict[str, str]:
    tok = get_installation_token()
    accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    return {"Authorization": f"Bearer {tok}", "Accept": accept}


def gh_get(path: str, params: Optional[Dict[str, Any]] = None, raw: bool = False):
    with httpx.Client(timeout=30) as c:
        r = c.get(f"{GITHUB_API}{path}", headers=gh_headers(raw), params=params)
        r.raise_for_status()
        return r.text if raw else r.json()


def gh_post(path: str, json_body: Dict[str, Any]):
    with httpx.Client(timeout=30) as c:
        r = c.post(f"{GITHUB_API}{path}", headers=gh_headers(), json=json_body)
        r.raise_for_status()
        return r.json()


def gh_put(path: str, json_body: Dict[str, Any]):
    with httpx.Client(timeout=30) as c:
        r = c.put(f"{GITHUB_API}{path}", headers=gh_headers(), json=json_body)
        r.raise_for_status()
        return r.json()
