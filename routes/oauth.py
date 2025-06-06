# File: routes/oauth.py
# Purpose: Handles Google OAuth redirect and token persistence

from fastapi import APIRouter, Request
from pathlib import Path
from google_auth_oauthlib.flow import Flow, InstalledAppFlow
import os
import base64

router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly"
]
CREDENTIALS_PATH = Path("/tmp/credentials.json")
TOKEN_PATH = Path("frontend/sync/token.json")

@router.get("/google/auth")
def start_oauth():
    if not CREDENTIALS_PATH.exists():
        raw = os.getenv("GOOGLE_CREDS_JSON")
        if not raw:
            return {"error": "Missing GOOGLE_CREDS_JSON in env"}
        decoded = base64.b64decode(raw.encode()).decode()
        CREDENTIALS_PATH.write_text(decoded)

    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_PATH),
        scopes=SCOPES,
        redirect_uri="https://relay.wildfireranch.us/google/callback",
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline', include_granted_scopes='true')
    return {"redirect": auth_url}

@router.get("/google/callback")
def oauth_callback(code: str):
    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_PATH), SCOPES
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(creds.to_json())
    print(f"✅ token.json written to: {TOKEN_PATH}")

    return {"status": "✅ Auth successful", "token_path": str(TOKEN_PATH)}
