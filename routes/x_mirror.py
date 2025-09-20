# ──────────────────────────────────────────────────────────────────────────────
# File: routes/x_mirror.py
# Purpose: Minimal authenticated echo endpoint for ops/debug
#          • POST /x_mirror/echo  (Authorization: Bearer <X_BEARER>)
# Contract:
#   - 200: returns request JSON when bearer matches env
#   - 401: invalid bearer
#   - 503: feature disabled (X_BEARER not set)
# Notes:
#   - No import-time crashes; env is read lazily.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
from fastapi import APIRouter, HTTPException, Request

def _get_bearer() -> str | None:
    # Support legacy "$shared.X_BEARER" fallback
    return os.getenv("X_BEARER") or os.getenv("$shared.X_BEARER")

router = APIRouter(prefix="/x_mirror", tags=["mirror"])

@router.post("/echo")
async def echo(req: Request):
    expected = _get_bearer()
    if not expected:
        raise HTTPException(status_code=503, detail="x_mirror disabled: missing X_BEARER")

    auth = req.headers.get("authorization", "")
    token = auth.split(" ", 1)[1] if auth.lower().startswith("bearer ") else ""
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid bearer")

    try:
        body = await req.json()
    except Exception:
        body = None
    return {"ok": True, "echo": body}
