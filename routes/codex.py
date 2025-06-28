# File: routes/codex.py
# Purpose: CodexAgent backend endpoints (e.g., patch application)

import os
from fastapi import APIRouter, HTTPException, Request
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
    if not validate_patch_format({"type": "patch", **payload.dict()}):
        raise HTTPException(status_code=422, detail="Invalid patch format.")

    try:
        file_path = os.path.abspath(payload.target_file)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(payload.patch)
    except Exception as e:
        log_event("codex_patch_error", {"file": payload.target_file, "error": str(e)})
        raise HTTPException(status_code=500, detail=f"Failed to apply patch: {e}")

    log_event("codex_patch_applied", {"file": payload.target_file, "user": request.headers.get("X-User-Id", "anon")})
    return {"status": "success", "file": payload.target_file}
