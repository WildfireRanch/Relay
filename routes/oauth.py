# File: routes/oauth.py
# Directory: /routes
# Purpose: Provide Google OAuth endpoints for both development (Codespaces) and production environments.
#          Dynamic redirect URIs are derived from the incoming request to support dev previews.

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
# Optional override for post-auth landing page in production
DEFAULT_POST_AUTH_REDIRECT = "/status/summary"

@router.get("/google/auth")
async def start_oauth(request: Request):
    """
    Initiates the OAuth flow:
    1. Ensure client secrets are written to /tmp/credentials.json from GOOGLE_CREDS_JSON.
    2. Build an OAuth2 Flow with a redirect URI based on request.base_url.
    3. Redirect the browser to Google's consent screen.
    """
    # 1. Write client secrets if missing
    if not CREDENTIALS_PATH.exists():
        raw = os.getenv("GOOGLE_CREDS_JSON")
        if not raw:
            raise HTTPException(status_code=500, detail="Missing GOOGLE_CREDS_JSON environment variable.")
        try:
            decoded = base64.b64decode(raw.encode()).decode()
            CREDENTIALS_PATH.write_text(decoded)
            print(f"✅ Wrote client secrets to {CREDENTIALS_PATH} (length={len(decoded)})")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to decode/write client secrets: {e}")

    # 2. Build dynamic redirect URI
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/google/callback"
    print(f"🔧 Using redirect URI: {redirect_uri}")

    # 3. Create OAuth2 flow and authorization URL
    flow = Flow.from_client_secrets_file(
        client_secrets_file=str(CREDENTIALS_PATH),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    print(f"🌐 Redirecting user to Google consent screen: {auth_url}")
    return RedirectResponse(auth_url)

@router.get("/google/callback")
async def oauth_callback(request: Request, code: str = None, state: str = None):
    """
    Handles the OAuth callback:
    1. Validates the authorization code.
    2. Exchanges code for credentials using the same dynamic redirect URI.
    3. Persists token.json for subsequent API calls.
    4. Redirects user to a post-auth landing page.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code in callback request.")

    # Ensure client secrets exist
    if not CREDENTIALS_PATH.exists():
        raise HTTPException(status_code=500, detail="Client secrets file not found.")

    # Reconstruct redirect URI for token exchange
    base = str(request.base_url).rstrip("/")
    redirect_uri = f"{base}/google/callback"
    print(f"🔧 Exchanging token with redirect URI: {redirect_uri}")

    # Exchange the authorization code for credentials
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_file=str(CREDENTIALS_PATH),
            scopes=SCOPES,
            redirect_uri=redirect_uri,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        print("✅ Fetched OAuth tokens successfully.")
    except Exception as e:
        print(f"❌ Token exchange failed: {e}")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {e}")

    # Persist token.json
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"✅ token.json written to: {TOKEN_PATH} (expiry: {creds.expiry})")
    except Exception as e:
        print(f"❌ Failed to write token.json: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to write token.json: {e}")

    # Determine post-auth redirect target
    post_auth = os.getenv("POST_AUTH_REDIRECT_URI") or f"{base}{DEFAULT_POST_AUTH_REDIRECT}"
    print(f"🔄 Redirecting user to post-auth page: {post_auth}")
    return RedirectResponse(post_auth)
