# services/google_docs_sync.py
import os
import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from markdownify import markdownify as md
from google.auth.transport.requests import Request  # ✅ Added missing import for token refresh

# === Config ===
SCOPES = ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/documents.readonly"]
CREDENTIALS_PATH = Path("frontend/sync/credentials.json")
TOKEN_PATH = Path("frontend/sync/token.json")
IMPORT_PATH = Path("docs/imported")
COMMAND_CENTER_FOLDER_NAME = "Command_Center"
IMPORT_PATH.mkdir(parents=True, exist_ok=True)

# === Auth ===
def get_google_service():
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
            # Use terminal-based auth flow for headless environments like Codespaces
            creds = flow.run_console()
        with open(TOKEN_PATH, 'w') as token:
            token.write(creds.to_json())
    drive_service = build('drive', 'v3', credentials=creds)
    docs_service = build('docs', 'v1', credentials=creds)
    return drive_service, docs_service

# === Google Docs Operations ===
def find_folder_id(drive_service, folder_name):
    results = drive_service.files().list(
        q=f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}'",
        spaces='drive',
        fields="files(id, name)",
    ).execute()
    folders = results.get('files', [])
    return folders[0]['id'] if folders else None

def get_docs_in_folder(drive_service, folder_id):
    query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.document'"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    return results.get('files', [])

def fetch_and_save_doc(docs_service, file):
    doc = docs_service.documents().get(documentId=file['id']).execute()
    title = file['name'].replace(" ", "_").lower()
    content = doc.get("body", {}).get("content", [])
    html = ""
    for element in content:
        if 'paragraph' in element:
            for el in element['paragraph'].get('elements', []):
                html += el.get('textRun', {}).get('content', '')
            html += "\n"
    markdown = md(html)
    out_path = IMPORT_PATH / f"{title}.md"
    out_path.write_text(markdown, encoding='utf-8')
    return out_path.name

# === Main Sync Function ===
def sync_google_docs():
    drive_service, docs_service = get_google_service()
    folder_id = find_folder_id(drive_service, COMMAND_CENTER_FOLDER_NAME)
    if not folder_id:
        raise RuntimeError(f"Folder '{COMMAND_CENTER_FOLDER_NAME}' not found in Google Drive")
    files = get_docs_in_folder(drive_service, folder_id)
    return [fetch_and_save_doc(docs_service, f) for f in files]
