# ──────────────────────────────────────────────────────────────────────────────
# File: google_docs_sync.py
# Directory: services
# Purpose: # Purpose: Synchronize documents from Google Docs to local storage, handling authentication, retrieval, and conversion to markdown.
#
# Upstream:
#   - ENV: ENV, GOOGLE_CREDS_JSON, GOOGLE_TOKEN_JSON
#   - Imports: base64, google.auth.transport.requests, google.oauth2.credentials, google_auth_oauthlib.flow, googleapiclient.discovery, markdownify, os, pathlib
#
# Downstream:
#   - routes.context
#   - routes.docs
#
# Contents:
#   - fetch_and_save_doc()
#   - find_folder_id()
#   - get_docs_in_folder()
#   - get_google_service()
#   - sync_google_docs()
# ──────────────────────────────────────────────────────────────────────────────

import os
import base64
from pathlib import Path

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from markdownify import markdownify as md

# === Configuration Constants ===
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]
CREDENTIALS_PATH = Path("/tmp/credentials.json")
TOKEN_PATH = Path("frontend/sync/token.json")
IMPORT_PATH = Path("docs/imported")
IMPORT_PATH.mkdir(parents=True, exist_ok=True)
COMMAND_CENTER_FOLDER_NAME = "COMMAND_CENTER"

# === Authentication and Service Setup ===
def get_google_service():
    """
    Ensure we have valid Google API credentials, then build Drive and Docs services.
    - Writes out credentials.json from GOOGLE_CREDS_JSON if missing
    - Bootstraps token.json from GOOGLE_TOKEN_JSON env var or runs interactive OAuth
    """
    creds = None

    # Write out credentials.json if not already present
    if not CREDENTIALS_PATH.exists():
        raw = os.getenv("GOOGLE_CREDS_JSON")
        if not raw:
            raise FileNotFoundError("Missing GOOGLE_CREDS_JSON environment variable.")
        decoded = base64.b64decode(raw.encode()).decode()
        CREDENTIALS_PATH.write_text(decoded)
        print(f"✅ Wrote client secrets to {CREDENTIALS_PATH}")

    # Bootstrap token.json from env, if provided
    if not TOKEN_PATH.exists() and os.getenv("GOOGLE_TOKEN_JSON"):
        token_raw = os.getenv("GOOGLE_TOKEN_JSON")
        try:
            TOKEN_PATH.write_text(base64.b64decode(token_raw).decode())
            print(f"✅ Bootstrapped token.json to {TOKEN_PATH}")
        except Exception as e:
            print(f"❌ Failed to decode GOOGLE_TOKEN_JSON: {e}")

    # Load existing credentials
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or start OAuth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Interactive login only allowed in local dev
            if os.getenv("ENV") == "local":
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
                creds = flow.run_local_server(port=0)
                TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
                TOKEN_PATH.write_text(creds.to_json())
                print(f"✅ Saved new token.json to {TOKEN_PATH}")
            else:
                raise RuntimeError(
                    "Missing valid credentials and interactive login is disabled in production."
                )

    # Build and return API clients
    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)
    return drive_service, docs_service

# === Google Docs Fetching Utilities ===
def find_folder_id(drive_service, folder_name: str) -> str:
    """
    Find the Drive folder ID by name.
    Returns folder ID or raises if not found.
    """
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'"
    result = (
        drive_service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    files = result.get("files", [])
    if not files:
        raise RuntimeError(f"Folder '{folder_name}' not found in Drive.")
    return files[0]["id"]


def get_docs_in_folder(drive_service, folder_id: str) -> list:
    """
    List all Google Docs files within the given folder ID.
    """
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'"
    result = (
        drive_service.files()
        .list(q=query, fields="files(id, name)")
        .execute()
    )
    return result.get("files", [])


def fetch_and_save_doc(docs_service, file: dict) -> str:
    """
    Fetch a Google Doc by ID, convert its content to Markdown, and save locally.
    Returns the filename of the saved Markdown file.
    """
    doc = docs_service.documents().get(documentId=file["id"]).execute()
    # Build plain-text HTML-like content
    elements = doc.get("body", {}).get("content", [])
    html = ""
    for element in elements:
        if "paragraph" in element:
            for part in element["paragraph"].get("elements", []):
                html += part.get("textRun", {}).get("content", "")
            html += "\n"
    # Convert to Markdown
    markdown = md(html)
    # Prepare output filename
    title_slug = file["name"].replace(" ", "_").lower()
    out_path = IMPORT_PATH / f"{title_slug}.md"
    out_path.write_text(markdown, encoding="utf-8")
    return out_path.name

# === Main Entry Point ===
def sync_google_docs() -> list:
    """
    Main sync function.
    - Authenticates
    - Finds the COMMAND_CENTER folder
    - Fetches and saves each doc to docs/imported/
    Returns a list of saved filenames.
    """
    drive_service, docs_service = get_google_service()
    folder_id = find_folder_id(drive_service, COMMAND_CENTER_FOLDER_NAME)
    files = get_docs_in_folder(drive_service, folder_id)
    saved_files = [fetch_and_save_doc(docs_service, f) for f in files]
    print(f"✅ Synced {len(saved_files)} files:", saved_files)
    return saved_files

# If run as a script, perform sync immediately
enabled = __name__ == "__main__"
if enabled:
    sync_google_docs()
