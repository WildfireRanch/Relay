# File: routes/oauth.py
# Directory: /routes
# Purpose: Provide Google OAuth endpoints for both development (Codespaces) and production.
#          Supports dynamic and environment-overridden redirect URIs, robust logging, and token persistence.

import os
import base64
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

router = APIRouter()

# === OAuth Configuration ===
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]
CREDENTIALS_PATH = Path("/tmp/credentials.json")
TOKEN_PATH = Path("frontend/sync/token.json")
# Post-auth landing page (path on the same host), can override with POST_AUTH_REDIRECT_URI
default_post_redirect = "/status/summary"
# Optional override for full OAuth callback URI
OVERRIDE_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")
# Optional override for post-auth redirect URI
OVERRIDE_POST_REDIRECT = os.getenv("POST_AUTH_REDIRECT_URI")

@router.get("/google/auth")
async def start_oauth(request: Request):
    """
    1. Ensure client secrets in /tmp/credentials.json from GOOGLE_CREDS_JSON.
    2. Determine redirect URI (env override or based on request.base_url).
    3. Redirect user to Google's OAuth consent screen.
    """
    # 1. Write client secrets if missing
    if not CREDENTIALS_PATH.exists():
        raw = os.getenv("GOOGLE_CREDS_JSON")
        if not raw:
            raise HTTPException(500, detail="Missing GOOGLE_CREDS_JSON environment variable.")
        try:
            creds_json = base64.b64decode(raw).decode()
            CREDENTIALS_PATH.write_text(creds_json)
            print(f"✅ Wrote client secrets to {CREDENTIALS_PATH} ({len(creds_json)} bytes)")
        except Exception as e:
            raise HTTPException(500, detail=f"Error decoding GOOGLE_CREDS_JSON: {e}")

    # 2. Determine redirect URI
    if OVERRIDE_REDIRECT_URI:
        redirect_uri = OVERRIDE_REDIRECT_URI
        print(f"🔧 Using OVERRIDE redirect URI: {redirect_uri}")
    else:
        base = str(request.base_url).rstrip("/")
        redirect_uri = f"{base}/google/callback"
        print(f"🔧 Using dynamic redirect URI: {redirect_uri}")

    # 3. Create OAuth2 flow
    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent"
    )
    print(f"🌐 Redirecting to Google consent: {auth_url}")
    return RedirectResponse(auth_url)

@router.get("/google/callback")
async def oauth_callback(request: Request, code: str = None, state: str = None):
    """
    1. Validate 'code' parameter.
    2. Exchange code for credentials using same redirect URI logic.
    3. Persist token.json.
    4. Redirect user to post-auth page.
    """
    if not code:
        raise HTTPException(400, detail="Missing authorization code in callback.")

    # Ensure client secrets exist
    if not CREDENTIALS_PATH.exists():
        raise HTTPException(500, detail="Client secrets not found.")

    # 2. Determine redirect URI for token exchange
    if OVERRIDE_REDIRECT_URI:
        redirect_uri = OVERRIDE_REDIRECT_URI
        print(f"🔧 Exchanging token with OVERRIDE redirect URI: {redirect_uri}")
    else:
        base = str(request.base_url).rstrip("/")
        redirect_uri = f"{base}/google/callback"
        print(f"🔧 Exchanging token with dynamic redirect URI: {redirect_uri}")

    # Exchange code for credentials
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_PATH),
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        print(f"✅ Obtained credentials (expires: {creds.expiry})")
    except Exception as e:
        print(f"❌ Token exchange error: {e}")
        raise HTTPException(500, detail=f"Token exchange failed: {e}")

    # 3. Persist token.json
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"✅ Saved token.json to {TOKEN_PATH}")
    except Exception as e:
        print(f"❌ Failed to save token.json: {e}")
        raise HTTPException(500, detail=f"Failed to write token.json: {e}")

    # 4. Redirect to post-auth page
    if OVERRIDE_POST_REDIRECT:
        post_redirect = OVERRIDE_POST_REDIRECT
        print(f"🔄 Redirecting user to OVERRIDE post-auth: {post_redirect}")
    else:
        base = str(request.base_url).rstrip("/")
        post_redirect = f"{base}{default_post_redirect}"
        print(f"🔄 Redirecting user to dynamic post-auth: {post_redirect}")
    return RedirectResponse(post_redirect)
