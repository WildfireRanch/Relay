import os, time, base64, httpx, jwt

def _app_jwt() -> str:
    app_id = os.getenv("GITHUB_APP_ID")
    key_b64 = os.getenv("GITHUB_APP_PRIVATE_KEY_BASE64")
    if not app_id or not key_b64:
        raise RuntimeError("Missing GITHUB_APP_ID / GITHUB_APP_PRIVATE_KEY_BASE64")
    key = base64.b64decode(key_b64)
    now = int(time.time())
    payload = {"iat": now - 60, "exp": now + 540, "iss": app_id}
    return jwt.encode(payload, key, algorithm="RS256")

async def installation_token() -> str:
    inst_id = os.getenv("GITHUB_APP_INSTALLATION_ID")
    if not inst_id:
        raise RuntimeError("Missing GITHUB_APP_INSTALLATION_ID")
    headers = {"Authorization": f"Bearer {_app_jwt()}",
               "Accept": "application/vnd.github+json"}
    url = f"https://api.github.com/app/installations/{inst_id}/access_tokens"
    async with httpx.AsyncClient(timeout=30) as x:
        r = await x.post(url, headers=headers)
        r.raise_for_status()
        return r.json()["token"]
