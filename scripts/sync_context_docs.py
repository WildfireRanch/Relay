# File: sync_context_docs.py
# Directory: scripts
# Purpose: # Purpose: Synchronize context documentation from a Google Drive source to the local file system.
#
# Upstream:
#   - ENV: —
#   - Imports: os, pathlib, services.google
#
# Downstream:
#   - —
#
# Contents:
#   - sync_context_from_drive()









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
