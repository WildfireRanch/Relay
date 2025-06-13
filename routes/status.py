# routes/status.py
# Directory: routes/
# Purpose: Health, environment, and version endpoints for Relay status and debugging.
# Security: Public (no auth; consider adding for prod if needed).

from fastapi import APIRouter
from pathlib import Path
import os
from subprocess import check_output, CalledProcessError

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
    try:
        commit = check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except (CalledProcessError, FileNotFoundError):
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

