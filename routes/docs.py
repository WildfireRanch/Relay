# File: routes/docs.py
# Directory: /routes
# Purpose: Provide endpoints for log-based context, Google Docs sync,
#          and knowledge-base (KB) operations, including listing and viewing
#          Markdown/text docs in the /docs directory.

import os
import traceback
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from openai import OpenAI

from services.logs import get_recent_logs, log_and_refresh
from services.google_docs_sync import sync_google_docs
from services.kb import embed_docs

router = APIRouter(prefix="/docs", tags=["docs"])

# === Configuration ===
# Base path to docs directory. Can override via RELAY_PROJECT_ROOT env var.
ENV_ROOT = os.getenv("RELAY_PROJECT_ROOT")
DOCS_PATH = (
    Path(ENV_ROOT).resolve() / "docs"
    if ENV_ROOT
    else Path(__file__).resolve().parents[1] / "docs"
)
# Ensure the generated folder exists
GEN_PATH = DOCS_PATH / "generated"
GEN_PATH.mkdir(parents=True, exist_ok=True)
CONTEXT_DOC = GEN_PATH / "relay_context.md"

# === Debug Endpoints ===
@router.get("/debug/env")
async def debug_env():
    """
    Check presence of critical environment variables and current working directory.
    Useful for diagnosing path or config issues in different environments.
    """
    return {
        "GOOGLE_CREDS_JSON_PRESENT": bool(os.getenv("GOOGLE_CREDS_JSON")),
        "GOOGLE_TOKEN_JSON_PRESENT": bool(os.getenv("GOOGLE_TOKEN_JSON")),
        "RELAY_PROJECT_ROOT": ENV_ROOT,
        "cwd": os.getcwd(),
        "DOCS_PATH": str(DOCS_PATH),
    }

# === Log-based Context Generation ===
@router.post("/update_context")
async def update_context_summary():
    """
    Summarize recent logs into a context Markdown file (relay_context.md).
    Uses OpenAI GPT to generate a summary of the last 100 log entries.
    """
    try:
        logs = get_recent_logs(100)
        if not logs:
            return JSONResponse({"status": "no logs to summarize"}, status_code=200)

        # Format logs for summarization
        text = "\n".join(f"[{l['source']}] {l['message']}" for l in logs)

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a system summarizer for a command center log."},
                {"role": "user", "content": f"Summarize the following session log:\n\n{text}"},
            ],
        )
        summary = response.choices[0].message.content.strip()

        # Write summary to file
        CONTEXT_DOC.write_text(f"# Relay Context (auto-generated)\n\n{summary}", encoding="utf-8")
        log_and_refresh("system", "Updated relay_context.md from session logs.")

        return {"status": "ok", "summary": summary}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Google Docs Sync Endpoints ===
@router.post("/sync", summary="Sync Google Docs into /docs/imported")
async def sync_docs():
    """
    Pull all documents from Google Drive COMMAND_CENTER folder,
    convert to Markdown, and save under /docs/imported.
    """
    try:
        synced = sync_google_docs()
        log_and_refresh("system", f"Synced {len(synced)} docs from Google Drive into /docs/imported")
        return {"status": "ok", "synced_docs": synced}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# Legacy alias for backward compatibility
router.post("/sync_google")(sync_docs)

# === Knowledge Base Embedding ===
@router.post("/refresh_kb", summary="Embed Markdown docs into vector KB")
async def refresh_kb():
    """
    Re-embed all Markdown and text docs under /docs into the vector database.
    """
    try:
        embed_docs()
        log_and_refresh("system", "Re-embedded all Markdown docs into KB.")
        return {"status": "ok", "message": "Knowledge base updated."}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Combined Full Sync ===
@router.post("/full_sync", summary="Sync Google Docs and refresh KB")
async def full_sync():
    """
    Perform both Google Docs sync and KB embedding in one call.
    """
    try:
        synced = sync_google_docs()
        embed_docs()
        log_and_refresh("system", f"Full sync: {len(synced)} docs pulled and embedded.")
        return {"status": "ok", "synced_docs": synced, "message": "Docs pulled and KB updated."}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Listing and Viewing Docs ===
@router.get("/list", summary="List all .md and .txt files under /docs")
async def list_docs():
    """
    Return a sorted list of relative file paths for all Markdown and text files under /docs.
    """
    if not DOCS_PATH.exists():
        raise HTTPException(status_code=404, detail="Docs folder missing.")
    files = [
        str(p.relative_to(DOCS_PATH))
        for p in DOCS_PATH.rglob("*.*")
        if p.suffix.lower() in [".md", ".txt"]
    ]
    return {"files": sorted(files)}

@router.get("/view", summary="View contents of a specific doc")
async def view_doc(path: str = Query(..., description="Path relative to /docs")):
    """
    Return the text content of the specified Markdown or text file under /docs.
    """
    full_path = DOCS_PATH / path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    content = full_path.read_text(encoding="utf-8")
    return {"content": content}
