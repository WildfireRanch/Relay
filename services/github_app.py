# File: services/github_app.py
# Purpose: Handle GitHub App authentication (App JWT + Installation tokens)

import os
import time
import base64
import httpx
import jwt  # PyJWT

def _app_jwt() -> str:
    """
    Build a short-lived JWT for GitHub App authentication.
    Requires:
      - GITHUB_APP_ID (must be numeric string)
      - GITHUB_APP_PRIVATE_KEY_BASE64 (base64 of PEM file)
    """
    app_id_raw = os.getenv("GITHUB_APP_ID")
    if not app_id_raw:
        raise RuntimeError("Missing GITHUB_APP_ID")
    try:
        app_id = int(app_id_raw)  # GitHub requires iss to be an integer
    except ValueError:
        raise RuntimeError(f"GITHUB_APP_ID must be numeric, got: {app_id_raw}")

    key_b64 = os.getenv("GITHUB_APP_PRIVATE_KEY_BASE64")
    if not key_b64:
        raise RuntimeError("Missing GITHUB_APP_PRIVATE_KEY_BASE64")

    try:
        key = base64.b64decode(key_b64)
    except Exception as e:
        raise RuntimeError(f"Failed to decode base64 private key: {e}")

    now = int(time.time())
    payload = {
        "iat": now - 60,   # issued-at, backdated 1 min for clock skew
        "exp": now + 540,  # expires in ~9 minutes
        "iss": app_id,
    }
    try:
        return jwt.encode(payload, key, algorithm="RS256")
    except Exception as e:
        raise RuntimeError(f"JWT encode failed: {e}")

async def installation_token() -> str:
    """
    Exchange the App JWT for an Installation Access Token.
    Requires:
      - GITHUB_APP_INSTALLATION_ID
    """
    inst_id = os.getenv("GITHUB_APP_INSTALLATION_ID")
    if not inst_id:
        raise RuntimeError("Missing GITHUB_APP_INSTALLATION_ID")

    headers = {
        "Authorization": f"Bearer {_app_jwt()}",
        "Accept": "application/vnd.github+json",
    }
    url = f"https://api.github.com/app/installations/{inst_id}/access_tokens"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers)

    if resp.status_code >= 300:
        raise RuntimeError(
            f"GitHub access_tokens failed {resp.status_code}: {resp.text}"
        )

    token = resp.json().get("token")
    if not token:
        raise RuntimeError("No token in GitHub /access_tokens response")
    return token
