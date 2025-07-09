# ──────────────────────────────────────────────────────────────────────────────
# File: codex.py
# Directory: routes
# Purpose: # Purpose: Provides API endpoints for applying patches to system configurations using FastAPI.
#
# Upstream:
#   - ENV: —
#   - Imports: core.logging, fastapi, fastapi.responses, os, pydantic, utils.patch_utils
#
# Downstream:
#   - main
#
# Contents:
#   - PatchRequest()
#   - apply_patch()

# ──────────────────────────────────────────────────────────────────────────────

import os
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from utils.patch_utils import validate_patch_format
from core.logging import log_event

router = APIRouter(prefix="/codex", tags=["codex"])

class PatchRequest(BaseModel):
    target_file: str
    patch: str
    reason: str

@router.post("/apply_patch")
async def apply_patch(payload: PatchRequest, request: Request):
    """
    Apply a code patch directly to the specified file on disk.
    """
    if not validate_patch_format({"type": "patch", **payload.dict()}):
        raise HTTPException(status_code=422, detail="Invalid patch format.")

    try:
        file_path = os.path.abspath(payload.target_file)

        # Optional: Prevent writing outside project root
        project_root = os.path.abspath(os.getcwd())
        if not file_path.startswith(project_root):
            raise HTTPException(status_code=400, detail="Refused to write outside project scope.")

        # Optional: Ensure file exists (comment out if you want to allow creation)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Target file not found: {payload.target_file}")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(payload.patch)

    except Exception as e:
        log_event("codex_patch_error", {
            "file": payload.target_file,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=f"Failed to apply patch: {e}")

    log_event("codex_patch_applied", {
        "file": payload.target_file,
        "user": request.headers.get("X-User-Id", "anon")
    })
    return JSONResponse({
        "status": "success",
        "file": payload.target_file,
        "message": "Patch written successfully."
    })
