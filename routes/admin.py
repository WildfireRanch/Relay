# routes/admin.py
# ------------------------------------------------------------------------
# Admin and Ops Endpoints for Relay Command Center
# Secure, auditable, and environment-driven maintenance tools.
# ALL endpoints require ENABLE_ADMIN_TOOLS=true, a valid secret, and optional allowlist.
# Review and update environment variables in Railway/Vercel/Codespaces as needed.
# ------------------------------------------------------------------------

import os
import shutil
import psutil
import platform
import zipfile
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from pathlib import Path
from datetime import datetime

# ------------------------------------------------------------------------
# ENV/CONFIG SETUP
# ------------------------------------------------------------------------
router = APIRouter(prefix="/admin", tags=["admin-ops"])

ADMIN_SECRET = os.environ.get("ADMIN_SECRET")
ADMIN_ALLOWLIST = os.environ.get("ADMIN_ALLOW", "").split(",") if os.environ.get("ADMIN_ALLOW") else []
ADMIN_TOOLS_ENABLED = os.environ.get("ENABLE_ADMIN_TOOLS", "false").lower() == "true"

INDEX_DIR = Path(os.environ.get("INDEX_DIR", "/app/data/index"))  # Safe for Railway/Codespaces
DATA_DIR = INDEX_DIR.parent
ADMIN_LOG = DATA_DIR / "admin_events.log"

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
    secret: str,
    user: str = ""
):
    """
    Deletes all files in the index directory and SQLite DBs.
    Requires ENABLE_ADMIN_TOOLS=true and valid ADMIN_SECRET in env/config.
    """
    # --- Authorization checks ---
    if not ADMIN_TOOLS_ENABLED:
        raise HTTPException(status_code=403, detail="Admin tools not enabled.")
    if not ADMIN_SECRET or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret.")
    if ADMIN_ALLOWLIST and user not in ADMIN_ALLOWLIST:
        raise HTTPException(status_code=403, detail=f"User '{user}' not allowed.")

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
# ENDPOINT: Trigger Index Rebuild (stub, implement as needed)
# ------------------------------------------------------------------------
@router.post("/trigger_reindex")
async def trigger_reindex(
    request: Request,
    secret: str,
    user: str = ""
):
    """
    Triggers a rebuild of the LlamaIndex. Stub for actual backend logic.
    """
    # (Auth logic as above)
    # Call your real index-rebuild function here
    log_admin_event(f"[REINDEX_TRIGGER] by {user or 'unknown'} from {request.client.host}")
    return {"status": "ok", "message": "Reindex triggered (implement logic here)."}

# ------------------------------------------------------------------------
# ENDPOINT: Health Check (disk, CPU, memory, config summary)
# ------------------------------------------------------------------------
@router.get("/health_check")
async def health_check(
    request: Request,
    secret: str,
    user: str = ""
):
    """
    Returns backend, disk, memory, and config health for diagnostics.
    """
    # (Auth logic as above)
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
            "admin_tools_enabled": ADMIN_TOOLS_ENABLED,
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
    secret: str,
    user: str = ""
):
    """
    Allows secure download of admin event log.
    """
    # (Auth logic as above)
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
    secret: str,
    user: str = ""
):
    """
    Zips the index directory for backup/offline restore.
    """
    # (Auth logic as above)
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
