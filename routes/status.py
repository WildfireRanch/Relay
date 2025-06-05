# File: routes/status.py

from fastapi import APIRouter
from pathlib import Path
import os
from subprocess import check_output, CalledProcessError

router = APIRouter()

@router.get("/status/paths")
def get_status_paths():
    env_root = os.getenv("RELAY_PROJECT_ROOT")
    base = Path(env_root).resolve() if env_root else Path.cwd()

    # These are the paths being checked by read_source_files()
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

@router.get("/status/env")
def get_env_status():
    keys = ["OPENAI_API_KEY", "API_KEY", "RELAY_PROJECT_ROOT", "RAILWAY_URL"]
    values = {
        k: os.getenv(k)[:5] + "..." if os.getenv(k) else None
        for k in keys
    }
    return values

@router.get("/status/version")
def get_version():
    try:
        commit = check_output(["git", "rev-parse", "--short", "HEAD"]).decode().strip()
    except (CalledProcessError, FileNotFoundError):
        commit = "unknown"
    return {"git_commit": commit}

@router.get("/status/summary")
def get_summary():
    return {
        "paths": get_status_paths(),
        "env": get_env_status(),
        "version": get_version()
    }
