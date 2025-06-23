# File: services/google.py
"""Utility helpers for fetching Google Docs content."""

from typing import List, Tuple
from markdownify import markdownify as md

from . import google_docs_sync


def fetch_drive_docs() -> List[Tuple[str, str]]:
    """Return (title, markdown) for docs in the COMMAND_CENTER folder."""
    drive_service, docs_service = google_docs_sync.get_google_service()
    folder_id = google_docs_sync.find_folder_id(
        drive_service, google_docs_sync.COMMAND_CENTER_FOLDER_NAME
    )
    files = google_docs_sync.get_docs_in_folder(drive_service, folder_id)

    docs = []
    for file in files:
        doc = docs_service.documents().get(documentId=file["id"]).execute()
        elements = doc.get("body", {}).get("content", [])
        html = ""
        for element in elements:
            if "paragraph" in element:
                for part in element["paragraph"].get("elements", []):
                    html += part.get("textRun", {}).get("content", "")
                html += "\n"
        markdown = md(html)
        docs.append((file["name"], markdown))
    return docs
