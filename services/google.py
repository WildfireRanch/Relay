# ──────────────────────────────────────────────────────────────────────────────
# File: google.py
# Directory: services
# Purpose: Provides functionality for fetching and converting Google Drive documents into markdown format.
#
# Upstream:
#   - ENV: —
#   - Imports: google_docs_sync, markdownify, typing
#
# Downstream:
#   - scripts.sync_context_docs
#
# Contents:
#   - fetch_drive_docs()
# ──────────────────────────────────────────────────────────────────────────────

"""Utility helpers for fetching Google Docs content."""

from typing import List, Tuple
from markdownify import markdownify as md

from .google_docs_sync import (
    get_google_service,
    find_folder_id,
    get_docs_in_folder,
    COMMAND_CENTER_FOLDER_NAME,
)

def fetch_drive_docs() -> List[Tuple[str, str]]:
    """Return (title, markdown) for docs in the COMMAND_CENTER folder."""
    drive_service, docs_service = get_google_service()
    folder_id = find_folder_id(
        drive_service, COMMAND_CENTER_FOLDER_NAME
    )
    files = get_docs_in_folder(drive_service, folder_id)

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
