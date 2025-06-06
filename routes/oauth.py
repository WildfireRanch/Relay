# File: routes/oauth.py

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import os
import json
import base64
from google_auth_oauthlib.flow import Flow

router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly"
]

REDIRECT_URI = "https://relay.wildfireranch.us/google/callback"

@router.get("/google/auth")
def start_auth():
    creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
    if not creds_b64:
        return {"error": "Missing GOOGLE_CREDS_JSON in env"}

    client_config = json.loads(base64.b64decode(creds_b64).decode())
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)

@router.get("/google/callback")
def oauth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return {"error": "No code in callback"}

    creds_b64 = os.getenv("GOOGLE_CREDS_JSON")
    client_config = json.loads(base64.b64decode(creds_b64).decode())

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(code=code)

    creds = flow.credentials
    token_path = "frontend/sync/token.json"
    with open(token_path, "w") as f:
        f.write(creds.to_json())

    return {"status": "✅ Auth successful", "token_path": token_path}
