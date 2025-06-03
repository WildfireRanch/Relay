import os
import json
from pathlib import Path
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/drive.metadata.readonly"
]

# === Load or refresh token ===
def get_creds():
    creds = None
    creds_path = Path(__file__).parent / "token.json"
    creds_file = Path(__file__).parent / "credentials.json"

    if creds_path.exists():
        creds = json.load(open(creds_path))
    if not creds or not creds.get("token"):
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(creds_path, "w") as token:
            token.write(creds.to_json())
    return creds

# === Sync all docs with label 'Relay' ===
def sync_docs():
    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)
    docs = build("docs", "v1", credentials=creds)
    base = Path(__file__).resolve().parents[2] / "docs/imported"
    base.mkdir(parents=True, exist_ok=True)

    # Get all Google Docs with 'Relay' in the name or description
    results = drive.files().list(
        q="mimeType='application/vnd.google-apps.document' and trashed=false",
        pageSize=20,
        fields="files(id, name)"
    ).execute()

    for file in results.get("files", []):
        doc_id = file["id"]
        name = file["name"]
        print(f"Syncing: {name} ({doc_id})")

        content = docs.documents().get(documentId=doc_id).execute()
        text = "".join(
            part.get("textRun", {}).get("content", "")
            for part in content.get("body", {}).get("content", [])
            if "textRun" in part
        )

        path = base / f"{name.replace(' ', '_')}.md"
        path.write_text(text)
        print(f"  ✅ Saved to: {path.relative_to(base.parent)}")

if __name__ == "__main__":
    sync_docs()
