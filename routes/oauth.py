# File: routes/oauth.py
# Directory: /routes
# Purpose: Define Google OAuth endpoints for initiating user authorization and handling callbacks,
#          persist tokens for use by the `services/google_docs_sync.py` workflow.

import os
import base64
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow, InstalledAppFlow

router = APIRouter()

# === Configuration ===
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]
CREDENTIALS_PATH = Path("/tmp/credentials.json")
TOKEN_PATH = Path("frontend/sync/token.json")
# Redirect URIs
PROD_REDIRECT = "https://relay.wildfireranch.us/google/callback"
POST_AUTH_REDIRECT = "https://relay.wildfireranch.us/status/summary"

@router.get("/google/auth")
async def start_oauth(request: Request):
    """
    1. Ensure client secrets are on disk (write from env if needed).
    2. Build an OAuth2 Flow and redirect the browser to Google's consent screen.
    """
    # Step 1: Write client secrets if missing
    if not CREDENTIALS_PATH.exists():
        raw = os.getenv("GOOGLE_CREDS_JSON")
        if not raw:
            raise HTTPException(status_code=500, detail="Missing GOOGLE_CREDS_JSON environment variable.")
        try:
            decoded = base64.b64decode(raw.encode()).decode()
            CREDENTIALS_PATH.write_text(decoded)
            print(f"✅ Wrote client secrets to {CREDENTIALS_PATH} (length={len(decoded)})")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to decode GOOGLE_CREDS_JSON: {e}")

    # Step 2: Create flow and get the authorization URL
    flow = Flow.from_client_secrets_file(
        client_secrets_file=str(CREDENTIALS_PATH),
        scopes=SCOPES,
        redirect_uri=PROD_REDIRECT,
    )
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    # Save state in session if needed (omitted for simplicity)
    print(f"🌐 Redirecting user to Google consent screen: {auth_url}")
    return RedirectResponse(auth_url)

@router.get("/google/callback")
async def oauth_callback(request: Request, code: str = None, state: str = None):
    """
    1. Exchange the authorization code for tokens.
    2. Persist tokens to disk for later use by sync workflows.
    3. Redirect user to a post-auth landing page.
    """
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code in callback request.")

    # Ensure credentials.json is present
    if not CREDENTIALS_PATH.exists():
        raise HTTPException(status_code=500, detail="Missing client secrets file.")

    # Exchange code for credentials
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_file=str(CREDENTIALS_PATH),
            scopes=SCOPES,
            redirect_uri=PROD_REDIRECT,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
    except Exception as e:
        print(f"❌ Failed to fetch token: {e}")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {e}")

    # Persist the token.json
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        print(f"✅ token.json written to: {TOKEN_PATH} (expires_in: {creds.expiry})")
    except Exception as e:
        print(f"❌ Failed to write token file: {e}")
        raise HTTPException(status_code=500, detail=f"Could not write token.json: {e}")

    # Redirect user to status summary
    return RedirectResponse(POST_AUTH_REDIRECT)
