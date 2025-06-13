# File: search.py
# Directory: routes/
# Purpose: Secure semantic KB search endpoint (GET /kb/search)

from __future__ import annotations

import os
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from services import kb

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/kb", tags=["kb-search"])

# ────────────────────────────────────────────────
# Auth helper
# ────────────────────────────────────────────────


def require_api_key(request: Request) -> None:
    """Simple header check. OPTIONS (CORS pre-flight) bypasses auth."""
    if request.method == "OPTIONS":
        return  # allow browser pre-flight

    api_key_header = request.headers.get("x-api-key")
    api_key_env = os.getenv("API_KEY")

    if api_key_header != api_key_env:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────


@router.get(
    "/search",
    dependencies=[Depends(require_api_key)],
    response_class=JSONResponse,
    summary="Semantic KB search",
)
def search(
    query: Optional[str] = Query(
        None,
        alias="query",
        description="Search query string (preferred param name)",
    ),
    q: Optional[str] = Query(
        None,
        description="Legacy alias for query param",
    ),
    k: int = Query(5, ge=1, le=20, description="Top-K results"),
) -> List[dict]:
    """
    Proxy to `services.kb.api_search`.

    Returns plain list of objects:
    ```json
    [
      {
        "path": "...",
        "title": "...",
        "snippet": "...",
        "updated": "...",
        "similarity": 0.97
      },
      ...
    ]
    ```
    """
    term = (query or q or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="Missing query parameter")

    try:
        results = kb.api_search(term, k=k)
        return results  # FastAPI serialises the list directly
    except Exception as exc:
        logger.exception("KB search failed for %r", term)
        raise HTTPException(status_code=500, detail="KB backend error") from exc
