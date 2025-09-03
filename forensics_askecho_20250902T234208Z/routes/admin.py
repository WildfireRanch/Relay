# ──────────────────────────────────────────────────────────────────────────────
# File: admin.py
# Directory: routes
# Purpose: # Purpose: Provides administrative functionalities like logging, indexing, and system health checks for the web service.
# Admin and Ops Endpoints for Relay Command Center
# Secure, auditable, and environment-driven maintenance tools.
# ALL endpoints require a valid API key (X-API-Key header, matches API_KEY env var).
# Review and update environment variables in Railway/Vercel/Codespaces as needed.

# Upstream:
#   - ENV: —
#   - Imports: datetime, fastapi, fastapi.responses, os, pathlib, platform, psutil, services.config, services.indexer, shutil, zipfile
#
# Downstream:
#   - main
#
# Contents:
#   - backup_index()
#   - clean_index()
#   - download_log()
#   - health_check()
#   - log_admin_event()
#   - require_api_key()
#   - trigger_reindex()

# ──────────────────────────────────────────────────────────────────────────────

import os
import shutil
import psutil
import platform
import zipfile
from fastapi import APIRouter, HTTPException, Request, status, Header, Depends
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime

from services.config import INDEX_DIR

# ------------------------------------------------------------------------
# ENV/CONFIG SETUP
# ------------------------------------------------------------------------
router = APIRouter(prefix="/admin", tags=["admin-ops"])

DATA_DIR = INDEX_DIR.parent
ADMIN_LOG = DATA_DIR / "admin_events.log"

# ------------------------------------------------------------------------
# SECURITY: Require valid API Key (X-API-Key header) for all admin ops
# ------------------------------------------------------------------------
def require_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    api_key = os.environ.get("API_KEY")
    if not api_key or x_api_key != api_key:
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")

# ------------------------------------------------------------------------
# UTIL: Audit logging—append all events and errors
# ------------------------------------------------------------------------
def log_admin_event(msg: str):
    timestamp = datetime.utcnow().isoformat()
    log_entry = f"{timestamp} | {msg}\n"
    with ADMIN_LOG.open("a", encoding="utf-8") as f:
        f.write(log_entry)

# ------------------------------------------------------------------------
# ENDPOINT: Clean LlamaIndex index and SQLite DBs
# ------------------------------------------------------------------------
@router.post("/clean_index")
async def clean_index(
    request: Request,
    user: str = "",
    api_key: str = Depends(require_api_key)
):
    """
    Deletes all files in the index directory and SQLite DBs.
    Requires valid X-API-Key header.
    """
    deleted_files = []
    # --- Index directory wipe ---
    if INDEX_DIR.exists():
        for f in INDEX_DIR.glob("*"):
            try:
                if f.is_file():
                    f.unlink()
                    deleted_files.append(str(f))
                elif f.is_dir():
                    shutil.rmtree(f)
                    deleted_files.append(str(f))
            except Exception as e:
                log_admin_event(f"[ERROR] Failed to delete {f}: {e}")
    # --- SQLite DBs wipe ---
    for sfile in DATA_DIR.glob("*.sqlite*"):
        try:
            sfile.unlink()
            deleted_files.append(str(sfile))
        except Exception as e:
            log_admin_event(f"[ERROR] Failed to delete {sfile}: {e}")

    # --- Audit log ---
    client_ip = request.client.host if request.client else "unknown"
    now = datetime.utcnow().isoformat()
    log_admin_event(f"[CLEAN_INDEX] {now} by {user or 'unknown'} from {client_ip}: Deleted {len(deleted_files)} files")

    return {
        "status": "ok",
        "message": "Index and SQLite files cleaned.",
        "deleted_files": deleted_files,
        "timestamp": now,
        "user": user,
        "ip": client_ip
    }

# ------------------------------------------------------------------------
# ENDPOINT: Trigger Index Rebuild (now fully implemented)
# ------------------------------------------------------------------------
from services.indexer import index_directories  # <-- add this import at the top if missing

@router.post("/trigger_reindex")
async def trigger_reindex(
    request: Request,
    user: str = "",
    api_key: str = Depends(require_api_key)
):
    """
    Triggers a rebuild of the LlamaIndex (semantic KB).
    Returns status/result.
    """
    try:
        index_directories()  # This will run synchronously (blocking until finished)
        log_admin_event(f"[REINDEX_TRIGGER] SUCCESS by {user or 'unknown'} from {request.client.host}")
        return {"status": "ok", "message": "Reindex complete."}
    except Exception as exc:
        log_admin_event(f"[REINDEX_TRIGGER] ERROR by {user or 'unknown'} from {request.client.host}: {exc}")
        raise HTTPException(status_code=500, detail=f"Reindex failed: {exc}")


# ------------------------------------------------------------------------
# ENDPOINT: Health Check (disk, CPU, memory, config summary)
# ------------------------------------------------------------------------
@router.get("/health_check")
async def health_check(
    request: Request,
    user: str = "",
    api_key: str = Depends(require_api_key)
):
    """
    Returns backend, disk, memory, and config health for diagnostics.
    Requires valid X-API-Key header.
    """
    health = {
        "system": platform.system(),
        "release": platform.release(),
        "cpu_percent": psutil.cpu_percent(),
        "memory": dict(psutil.virtual_memory()._asdict()),
        "disk": dict(psutil.disk_usage('/')._asdict()),
        "python_version": platform.python_version(),
        "env": {
            "index_dir": str(INDEX_DIR),
            "data_dir": str(DATA_DIR),
        }
    }
    log_admin_event(f"[HEALTH_CHECK] by {user or 'unknown'} from {request.client.host}")
    return health

# ------------------------------------------------------------------------
# ENDPOINT: Download Audit Log
# ------------------------------------------------------------------------
@router.get("/download_log")
async def download_log(
    request: Request,
    user: str = "",
    api_key: str = Depends(require_api_key)
):
    """
    Allows secure download of admin event log.
    Requires valid X-API-Key header.
    """
    if not ADMIN_LOG.exists():
        raise HTTPException(status_code=404, detail="No log file found.")
    log_admin_event(f"[DOWNLOAD_LOG] by {user or 'unknown'} from {request.client.host}")
    return FileResponse(str(ADMIN_LOG), media_type="text/plain", filename="admin_events.log")

# ------------------------------------------------------------------------
# ENDPOINT: Backup Index Directory (zip)
# ------------------------------------------------------------------------
@router.post("/backup_index")
async def backup_index(
    request: Request,
    user: str = "",
    api_key: str = Depends(require_api_key)
):
    """
    Zips the index directory for backup/offline restore.
    Requires valid X-API-Key header.
    """
    backup_path = DATA_DIR / f"index_backup_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    with zipfile.ZipFile(backup_path, "w") as zipf:
        if INDEX_DIR.exists():
            for f in INDEX_DIR.rglob("*"):
                if f.is_file():
                    zipf.write(f, f.relative_to(DATA_DIR))
    log_admin_event(f"[BACKUP_INDEX] by {user or 'unknown'} from {request.client.host}")
    return {
        "status": "ok",
        "message": f"Index directory backed up to {backup_path.name}",
        "backup_file": str(backup_path)
    }

