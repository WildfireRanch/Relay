# ──────────────────────────────────────────────────────────────────────────────
# File: embeddings.py
# Directory: routes
# Purpose: # Purpose: Manage the lifecycle and API endpoints for embedding generation and updates in the system.
#
# Upstream:
#   - ENV: —
#   - Imports: fastapi, fastapi.responses, os, pathlib, pickle, services, time
#
# Downstream:
#   - —
#
# Contents:
#   - embeddings_rebuild()
#   - embeddings_status()

# ──────────────────────────────────────────────────────────────────────────────

"""
Embeddings Debug & Maintenance API for Relay
---------------------------------------------
- /embeddings/status : Check if embedding index exists, get stats
- /embeddings/rebuild : (POST) Trigger rebuild of the embedding index
"""

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse
from services import embeddings
import os
from pathlib import Path
import time

router = APIRouter()

EMBED_INDEX = embeddings.EMBED_INDEX

@router.get("/embeddings/status")
def embeddings_status():
    """
    Returns basic info about the current embedding index.
    """
    info = {
        "exists": False,
        "num_files": None,
        "last_modified": None
    }
    if os.path.exists(EMBED_INDEX):
        stat = os.stat(EMBED_INDEX)
        info["exists"] = True
        info["last_modified"] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stat.st_mtime))
        try:
            # Try to get number of files in index
            import pickle
            with open(EMBED_INDEX, "rb") as f:
                idx = pickle.load(f)
            info["num_files"] = len(idx)
        except Exception as e:
            info["num_files"] = f"Error: {e}"
    return JSONResponse(info)

@router.post("/embeddings/rebuild")
def embeddings_rebuild():
    """
    Triggers a rebuild of the embedding index.
    """
    try:
        embeddings.build_index()
        return JSONResponse({"status": "ok", "message": "Embedding index rebuilt."})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
