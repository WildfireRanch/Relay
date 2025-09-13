# services/github_app.py
import os, time, json, httpx, jwt
from typing import Dict, Any, Optional

GITHUB_API = "https://api.github.com"
APP_ID = os.environ["GITHUB_APP_ID"]
INSTALLATION_ID = os.environ["GITHUB_INSTALLATION_ID"]
PRIVATE_KEY = os.environ["GITHUB_APP_PRIVATE_KEY"]

_token_cache: Dict[str, Any] = {"token": None, "exp": 0}

def _make_app_jwt() -> str:
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 9 * 60, "iss": APP_ID}
    return jwt.encode(payload, PRIVATE_KEY, algorithm="RS256")

def get_installation_token() -> str:
    # refresh if < 2 min remaining
    if _token_cache["token"] and _token_cache["exp"] - time.time() > 120:
        return _token_cache["token"]

    app_jwt = _make_app_jwt()
    url = f"{GITHUB_API}/app/installations/{INSTALLATION_ID}/access_tokens"
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
    }
    with httpx.Client(timeout=20) as c:
        r = c.post(url, headers=headers)
        r.raise_for_status()
        data = r.json()
    _token_cache["token"] = data["token"]
    # expires_at example: "2025-09-12T19:22:54Z"
    _token_cache["exp"] = int(time.mktime(time.strptime(data["expires_at"], "%Y-%m-%dT%H:%M:%SZ")))
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
