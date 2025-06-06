# File: routes/docs.py (absolute path fix for Codespaces)

from fastapi import APIRouter, HTTPException, Query
from services.logs import get_recent_logs, log_and_refresh
from services.google_docs_sync import sync_google_docs
from services.kb import embed_docs
from openai import OpenAI
from pathlib import Path
import traceback
import os

router = APIRouter(prefix="/docs", tags=["docs"])

# === Absolute path to docs directory (Codespaces-friendly) ===
DOCS_PATH = Path("/workspaces/codespaces-blank/docs")
doc_path = DOCS_PATH / "generated/relay_context.md"
doc_path.parent.mkdir(parents=True, exist_ok=True)

# === Auto-generate context summary from recent logs ===
@router.post("/update_context")
def update_context_summary():
    try:
        logs = get_recent_logs(100)
        if not logs:
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
        doc_path.write_text(f"# Relay Context (auto-generated)\n\n{summary}", encoding="utf-8")
        log_and_refresh("system", "Updated relay_context.md from session logs.")

        return {"status": "ok", "summary": summary}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# === Google Docs sync ===
@router.post("/sync_google")  # legacy alias
def legacy_sync_google():
    return sync_docs_and_update()

@router.post("/sync")
def sync_docs_and_update():
    try:
        synced = sync_google_docs()
        log_and_refresh("system", f"Synced {len(synced)} docs from Google Drive into /docs/imported")
        return {"status": "ok", "synced_docs": synced}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Embed all .md files into vector database (manual refresh) ===
@router.post("/refresh_kb")
def refresh_kb():
    try:
        embed_docs()
        log_and_refresh("system", "Re-embedded all Markdown docs into KB.")
        return {"status": "ok", "message": "Knowledge base updated."}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Combined: sync Google Docs and re-embed KB ===
@router.post("/full_sync")
def full_sync():
    try:
        synced = sync_google_docs()
        embed_docs()
        log_and_refresh("system", f"Full sync: {len(synced)} docs pulled and embedded.")
        return {"status": "ok", "synced_docs": synced, "message": "Docs pulled and KB updated."}
    except Exception as e:
        print("❌ Full sync failed:", str(e))
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === List available Markdown and text files in /docs ===
@router.get("/list")
def list_docs():
    if not DOCS_PATH.exists():
        raise HTTPException(status_code=404, detail="Docs folder missing.")
    files = [
        str(p.relative_to(DOCS_PATH))
        for p in DOCS_PATH.rglob("*")
        if p.suffix in [".md", ".txt"]
    ]
    return {"files": sorted(files)}

# === Return the contents of a single Markdown doc ===
@router.get("/view")
def view_doc(path: str = Query(..., description="Path relative to /docs")):
    full_path = DOCS_PATH / path
    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    return {"content": full_path.read_text(encoding="utf-8")}

