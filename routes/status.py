# File: routes/status.py
# Directory: routes/
# Purpose: Health, environment, version, and context awareness endpoints for Relay service.
# Security: Public (no auth; consider protecting `/env` or `/summary` in production).

from fastapi import APIRouter
from pathlib import Path
import os
from subprocess import check_output, CalledProcessError
from datetime import datetime

router = APIRouter(prefix="/status", tags=["status"])

@router.get("/paths")
def get_status_paths():
    """
    Returns existence of major source code/data directories for debugging.
    """
    env_root = os.getenv("RELAY_PROJECT_ROOT")
    base = Path(env_root).resolve() if env_root else Path.cwd()

    roots = [
        "services",
        "frontend/src/app",
        "frontend/src/components",
        "routes",
        "."
    ]

    visible = {}
    for r in roots:
        path = base / r
        visible[r] = path.exists()

    return {
        "base_path": str(base),
        "resolved_paths": visible
    }

@router.get("/env")
def get_env_status():
    """
    Returns selected environment variable statuses (partially masked for safety).
    """
    keys = ["OPENAI_API_KEY", "API_KEY", "RELAY_PROJECT_ROOT", "RAILWAY_URL"]
    values = {
        k: os.getenv(k)[:5] + "..." if os.getenv(k) else None
        for k in keys
    }
    return values

@router.get("/version")
def get_version():
    """
    Returns current Git commit short hash.
    """
from subprocess import check_output, CalledProcessError, DEVNULL

@router.get("/version")
def get_version():
    """
    Returns current Git commit short hash.
    """
    try:
        commit = check_output(["git", "rev-parse", "--short", "HEAD"], stderr=DEVNULL).decode().strip()
    except Exception:
        commit = "unknown"
    return {"git_commit": commit}


@router.get("/summary")
def get_summary():
    """
    Returns a bundle of status: paths, env, and version.
    """
    return {
        "paths": get_status_paths(),
        "env": get_env_status(),
        "version": get_version()
    }

def list_context_inventory(
    base: Path, 
    roots = ["docs", "context"], 
    exts = [".md", ".txt"]
):
    """
    Helper: Returns a list of context file metadata from all roots.
    """
    inventory = []
    for root in roots:
        folder = base / root
        if not folder.exists():
            continue
        for f in folder.rglob("*"):
            if f.is_file() and f.suffix in exts:
                inventory.append({
                    "path": str(f.relative_to(base)),
                    "size_bytes": f.stat().st_size,
                    "last_modified": datetime.utcfromtimestamp(f.stat().st_mtime).isoformat() + "Z"
                })
    return inventory

@router.get("/context")
def get_context_status():
    """
    Returns details about all global context and overlays:
    - All context files with metadata (from /docs, /context)
    - Which global_context (manual or auto) is active
    - Last updated timestamps
    """
    env_root = os.getenv("RELAY_PROJECT_ROOT")
    base = Path(env_root).resolve() if env_root else Path.cwd()
    global_manual = base / "docs/generated/global_context.md"
    global_auto = base / "docs/generated/global_context.auto.md"

    def fmt_time(path):
        return datetime.utcfromtimestamp(path.stat().st_mtime).isoformat() + "Z" if path.exists() else "missing"

    files = list_context_inventory(base)
    files_sorted = sorted(files, key=lambda x: x["path"])

    return {
        "context_files": files_sorted,
        "global_context_used": "manual" if global_manual.exists() else "auto" if global_auto.exists() else "none",
        "global_context_manual_last_updated": fmt_time(global_manual),
        "global_context_auto_last_updated": fmt_time(global_auto),
        "file_count": len(files_sorted),
        "root": str(base)
    }
