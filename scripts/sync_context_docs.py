# File: scripts/sync_context_docs.py
# Purpose: Sync Google Docs to /context/ and /docs/imported/ based on prefix naming convention

import os
from pathlib import Path
from services.google import fetch_drive_docs  # assumed helper that returns [(title, content)]

CONTEXT_DIR = Path("./context")
DOCS_DIR = Path("./docs/imported")
CONTEXT_PREFIX = "context-"

CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

def sync_context_from_drive():
    docs = fetch_drive_docs()
    for title, content in docs:
        if title.startswith(CONTEXT_PREFIX):
            filename = title[len(CONTEXT_PREFIX):] + ".md"
            path = CONTEXT_DIR / filename
        else:
            filename = title + ".md"
            path = DOCS_DIR / filename

        path.write_text(content)
        print(f"Synced: {path.relative_to(Path.cwd())}")

if __name__ == "__main__":
    sync_context_from_drive()
