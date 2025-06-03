# routes/context.py
from fastapi import APIRouter, HTTPException
from services.logs import get_recent_logs, log_and_refresh
from services.google_docs_sync import sync_google_docs
from openai import OpenAI
from pathlib import Path
import os

router = APIRouter(prefix="/context", tags=["context"])

# Path to the context file generated from session logs
doc_path = Path("docs/generated/relay_context.md")
doc_path.parent.mkdir(parents=True, exist_ok=True)

@router.post("/update")
def update_context_summary():
    try:
        logs = get_recent_logs(100)
        if not logs:
            return {"status": "no logs to summarize"}

        # Prepare the text block from log entries
        text = "\n".join(f"[{l['source']}] {l['message']}" for l in logs)

        # Use OpenAI API to summarize log content
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a system summarizer for a command center log."},
                {"role": "user", "content": f"Summarize the following session log:\n\n{text}"}
            ]
        )

        summary = response.choices[0].message.content.strip()

        # Write summary to markdown file
        doc_path.write_text(f"# Relay Context (auto-generated)\n\n{summary}", encoding="utf-8")
        log_and_refresh("system", "Updated relay_context.md from session logs.")

        return {"status": "ok", "summary": summary}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Deprecated sync route for compatibility with /docs/sync_google
@router.post("/sync_google")
def legacy_sync_google():
    return sync_docs_and_update()

@router.post("/sync_docs")
def sync_docs_and_update():
    try:
        synced = sync_google_docs()
        log_and_refresh("system", f"Synced {len(synced)} docs from Google Drive into /docs/imported")
        return {"status": "ok", "synced_docs": synced}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
