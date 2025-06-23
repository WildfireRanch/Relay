# File: routes/oauth.py
# Directory: /routes
# Purpose: Provide Google OAuth endpoints for both development (Codespaces) and production.
# Supports dynamic and environment-overridden redirect URIs, robust logging, and token persistence.

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
# Default post-auth landing page (relative path)
DEFAULT_POST_REDIRECT = "/status/summary"
# Optional overrides (full URIs)
OVERRIDE_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI")
OVERRIDE_POST_REDIRECT = os.getenv("POST_AUTH_REDIRECT_URI")

@router.get("/google/auth")
async def start_oauth(request: Request):
    """
    Initiates the OAuth flow:
    1. Ensure client secrets in /tmp/credentials.json from GOOGLE_CREDS_JSON.
    2. Determine redirect URI (override or based on request.base_url).
    3. Redirect browser to Google consent screen.
    """
    # 1. Write client secrets if missing
    if not CREDENTIALS_PATH.exists():
        raw = os.getenv("GOOGLE_CREDS_JSON")
        if not raw:
            raise HTTPException(500, detail="Missing GOOGLE_CREDS_JSON environment variable.")
        try:
            creds_json = base64.b64decode(raw).decode()
            CREDENTIALS_PATH.write_text(creds_json)
            print(f"✅ Wrote client secrets to {CREDENTIALS_PATH}")
        except Exception as e:
            raise HTTPException(500, detail=f"Error decoding GOOGLE_CREDS_JSON: {e}")

    # 2. Determine redirect URI
    if OVERRIDE_REDIRECT_URI:
        redirect_uri = OVERRIDE_REDIRECT_URI
        print(f"🔧 Using override redirect URI: {redirect_uri}")
    else:
        base = str(request.base_url).rstrip("/")
        redirect_uri = f"{base}/google/callback"
        print(f"🔧 Using dynamic redirect URI: {redirect_uri}")

    # 3. Create flow and authorization URL
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
    Handles the OAuth callback:
    1. Validate 'code'.
    2. Exchange code for credentials using redirect URI.
    3. Persist token.json.
    4. Redirect to post-auth landing (relative path).
    """
    if not code:
        raise HTTPException(400, detail="Missing authorization code in callback.")

    if not CREDENTIALS_PATH.exists():
        raise HTTPException(500, detail="Client secrets not found.")

    # Determine redirect URI for token exchange
    if OVERRIDE_REDIRECT_URI:
        redirect_uri = OVERRIDE_REDIRECT_URI
        print(f"🔧 Exchanging token with override redirect URI: {redirect_uri}")
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
        print(f"❌ Token exchange failed: {e}")
        raise HTTPException(500, detail=f"Token exchange failed: {e}")

    # Persist token.json
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"✅ Saved token.json to {TOKEN_PATH}")
    except Exception as e:
        print(f"❌ Could not save token.json: {e}")
        raise HTTPException(500, detail=f"Could not write token.json: {e}")

    # Redirect to post-auth page (use relative path to avoid port issues)
    if OVERRIDE_POST_REDIRECT:
        post_redirect = OVERRIDE_POST_REDIRECT
        print(f"🔄 Redirecting to override post-auth: {post_redirect}")
    else:
        post_redirect = DEFAULT_POST_REDIRECT
        print(f"🔄 Redirecting to relative post-auth path: {post_redirect}")
    return RedirectResponse(post_redirect)
