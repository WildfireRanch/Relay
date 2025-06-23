# File: routes/index.py
# Directory: routes/
# Purpose: FastAPI endpoint to trigger code/doc indexing—secured with API Key, dev/staging only.

from fastapi import APIRouter, Depends, HTTPException, Header
import os
from services.indexer import index_directories
from datetime import datetime
from pathlib import Path

router = APIRouter(prefix="/ops", tags=["ops"])

# -- Security: Require X-API-Key header for indexing --
def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    api_key = os.environ.get("API_KEY")
    if not api_key or x_api_key != api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")

# -- Optional: Simple audit log to /data/ops_events.log --
AUDIT_LOG = Path(os.environ.get("AUDIT_LOG", "/app/data/ops_events.log"))

def log_event(msg: str):
    now = datetime.utcnow().isoformat()
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(f"{now} | {msg}\n")

@router.post("/index")
async def trigger_index(api_key: str = Depends(require_api_key), user: str = "ops"):
    """
    Secured endpoint to start indexing codebase and docs (requires X-API-Key).
    """
    log_event(f"[TRIGGER_INDEX] by {user}")
    index_directories()
    return {"status": "ok", "message": "Indexing started!"}
