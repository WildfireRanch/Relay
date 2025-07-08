# ──────────────────────────────────────────────────────────────────────────────
# File: context.py
# Directory: routes
# Purpose: # Purpose: Manage and synchronize documentation context between local and cloud storage, ensuring consistency and updating legacy systems.
#
# Upstream:
#   - ENV: OPENAI_API_KEY
#   - Imports: fastapi, openai, os, pathlib, services.google_docs_sync, services.logs, traceback
#
# Downstream:
#   - —
#
# Contents:
#   - ensure_stub_file()
#   - legacy_sync_google()
#   - safe_write_markdown()
#   - sync_docs_and_update()
#   - update_context_summary()

# ──────────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter, HTTPException
from services.logs import get_recent_logs, log_and_refresh
from services.google_docs_sync import sync_google_docs
from openai import OpenAI
from pathlib import Path
import os
import traceback

router = APIRouter(prefix="/context", tags=["context"])

# Paths for generated context files
RELAY_CONTEXT_PATH = Path("docs/generated/relay_context.md")
GLOBAL_CONTEXT_PATH = Path("docs/generated/global_context.md")
RELAY_CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)

def safe_write_markdown(path: Path, content: str, header: str = None):
    """Write markdown safely, fallback to a minimal file if an error occurs."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            if header:
                f.write(f"# {header}\n\n")
            f.write(content.strip() + "\n")
    except Exception as e:
        print(f"Failed to write {path}: {e}")
        # Ensure at least an empty file exists
        try:
            path.write_text("# (empty)\n", encoding="utf-8")
        except Exception:
            pass

def ensure_stub_file(path: Path, stub: str = "# (empty)\n"):
    """Ensure a minimal stub markdown file exists."""
    if not path.exists():
        try:
            path.write_text(stub, encoding="utf-8")
        except Exception as e:
            print(f"Failed to create stub {path}: {e}")

# --- Endpoint: Update relay_context.md from logs ---
@router.post("/update")
def update_context_summary():
    """Summarize recent logs to relay_context.md (markdown-safe, robust to errors)."""
    ensure_stub_file(RELAY_CONTEXT_PATH, "# Relay Context (not yet summarized)\n")
    try:
        logs = get_recent_logs(100)
        if not logs:
            safe_write_markdown(RELAY_CONTEXT_PATH, "No logs to summarize.", "Relay Context (auto-generated)")
            return {"status": "no logs to summarize"}

        text = "\n".join(f"[{l['source']}] {l['message']}" for l in logs)

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a system summarizer for a command center log."},
                {"role": "user", "content": f"Summarize the following session log:\n\n{text}"}
            ]
        )

        summary = response.choices[0].message.content.strip()
        safe_write_markdown(RELAY_CONTEXT_PATH, summary, "Relay Context (auto-generated)")
        log_and_refresh("system", "Updated relay_context.md from session logs.")
        return {"status": "ok", "summary": summary}

    except Exception as e:
        # Log the traceback and return a safe fallback
        print(f"Exception in update_context_summary: {e}\n{traceback.format_exc()}")
        safe_write_markdown(RELAY_CONTEXT_PATH, f"Error updating summary: {e}", "Relay Context (auto-generated)")
        raise HTTPException(status_code=500, detail=f"Failed to update context: {e}")

# --- Sync Google Docs and ensure stub context files ---
@router.post("/sync_docs")
def sync_docs_and_update():
    """Sync Google Docs and ensure global context markdown is safe."""
    ensure_stub_file(GLOBAL_CONTEXT_PATH, "# Global Project Context (not yet generated)\n")
    try:
        synced = sync_google_docs()
        log_and_refresh("system", f"Synced {len(synced)} docs from Google Drive into /docs/imported")
        return {"status": "ok", "synced_docs": synced}
    except Exception as e:
        print(f"Exception in sync_docs_and_update: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))

# Deprecated sync route for compatibility with /docs/sync_google
@router.post("/sync_google")
def legacy_sync_google():
    """Backward-compatible alias for sync_docs."""
    return sync_docs_and_update()
