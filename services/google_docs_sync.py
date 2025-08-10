# File: services/google_docs_sync.py
"""
Synchronize documents from a Google Drive folder into local Markdown files.

This version includes several improvements over the original:
- The Drive folder name can be set via the GOOGLE_FOLDER_NAME environment
  variable instead of being hard-coded.
- Credentials and token files are generated from base64-encoded environment
  variables (`GOOGLE_CREDS_JSON` and `GOOGLE_TOKEN_JSON`) if they don't exist.
- The Google Docs export API is used to fetch each document as HTML, which
  preserves basic formatting when converting to Markdown.
- Error handling provides clear messages when credentials are missing or a
  specified folder can't be found.
"""

import os
import base64
from pathlib import Path
from typing import List, Tuple

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from markdownify import markdownify as md

# The scopes our application requires to read files from Drive and Docs.
SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]

# Paths used to store OAuth client credentials and tokens.
CREDENTIALS_PATH = Path("/tmp/credentials.json")
TOKEN_PATH = Path("frontend/sync/token.json")

# Directory where imported Markdown files will be stored.
IMPORT_PATH = Path("docs/imported")
IMPORT_PATH.mkdir(parents=True, exist_ok=True)

# Name of the Drive folder to sync.  Can be overridden via env var.
FOLDER_NAME = os.getenv("GOOGLE_FOLDER_NAME", "COMMAND_CENTER")


def get_google_service() -> Tuple:
    """
    Authenticate with Google APIs and return Drive and Docs service clients.

    Credentials are loaded from environment variables if not already present.
    In production, interactive OAuth flows are disabled.
    """
    creds = None

    # Write client secrets if they don't exist yet.
    if not CREDENTIALS_PATH.exists():
        raw = os.getenv("GOOGLE_CREDS_JSON")
        if not raw:
            raise FileNotFoundError(
                "Missing GOOGLE_CREDS_JSON environment variable; cannot authenticate."
            )
        decoded = base64.b64decode(raw).decode()
        CREDENTIALS_PATH.write_text(decoded)

    # Write token from environment, if available and no token file exists.
    if not TOKEN_PATH.exists() and os.getenv("GOOGLE_TOKEN_JSON"):
        try:
            token_raw = os.getenv("GOOGLE_TOKEN_JSON")
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_PATH.write_text(base64.b64decode(token_raw).decode())
        except Exception as exc:
            raise RuntimeError(f"Failed to decode GOOGLE_TOKEN_JSON: {exc}") from exc

    # Load existing credentials
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or run interactive flow if necessary
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Only allow interactive auth in local development
            if os.getenv("ENV", "local") == "local":
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(CREDENTIALS_PATH), SCOPES
                )
                creds = flow.run_local_server(port=0)
                TOKEN_PATH.write_text(creds.to_json())
            else:
                raise RuntimeError(
                    "Missing valid Google credentials; set GOOGLE_TOKEN_JSON "
                    "or enable interactive login in a local environment."
                )

    # Build service clients
    drive_service = build("drive", "v3", credentials=creds)
    docs_service = build("docs", "v1", credentials=creds)
    return drive_service, docs_service


def find_folder_id(drive_service, folder_name: str) -> str:
    """
    Locate a folder on Drive by name and return its ID.

    Raises a RuntimeError with guidance if the folder is not found.
    """
    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{folder_name}' and trashed=false"
    )
    result = (
        drive_service.files()
        .list(q=query, spaces="drive", fields="files(id, name)")
        .execute()
    )
    folders = result.get("files", [])
    if not folders:
        raise RuntimeError(
            f"Folder '{folder_name}' not found in Drive. "
            "Check the GOOGLE_FOLDER_NAME environment variable."
        )
    return folders[0]["id"]


def get_docs_in_folder(drive_service, folder_id: str) -> List[dict]:
    """
    Return a list of Google Docs files contained within the specified folder.
    """
    query = (
        f"'{folder_id}' in parents "
        "and mimeType='application/vnd.google-apps.document' "
        "and trashed=false"
    )
    result = (
        drive_service.files()
        .list(q=query, fields="files(id, name)")
        .execute()
    )
    return result.get("files", [])


def fetch_and_save_doc(docs_service, file_info: dict) -> str:
    """
    Fetch a Google Doc by ID, convert it to Markdown and save it locally.

    Returns the filename of the saved Markdown file.
    """
    # Export the doc as HTML; this includes basic formatting.
    export = (
        docs_service.documents()
        .export(fileId=file_info["id"], mimeType="text/html")
        .execute()
    )
    html_content = export.decode("utf-8")
    markdown = md(html_content)

    # Use a slugified title for the output filename
    title_slug = file_info["name"].replace(" ", "_").lower()
    out_path = IMPORT_PATH / f"{title_slug}.md"
    out_path.write_text(markdown, encoding="utf-8")
    return out_path.name


def sync_google_docs() -> List[str]:
    """
    Authenticate and synchronise all Google Docs from the configured folder.

    Returns a list of filenames that were saved.
    """
    drive_service, docs_service = get_google_service()
    folder_id = find_folder_id(drive_service, FOLDER_NAME)
    doc_files = get_docs_in_folder(drive_service, folder_id)
    saved = [fetch_and_save_doc(docs_service, f) for f in doc_files]
    print(f"Synced {len(saved)} file(s) from Drive folder '{FOLDER_NAME}': {saved}")
    return saved


if __name__ == "__main__":
    sync_google_docs()
