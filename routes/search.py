# ──────────────────────────────────────────────────────────────────────────────
# File: routes/search.py
# Purpose: # Purpose: Provide API endpoints for handling search queries and validating API keys.
#
# Upstream:
#   - ENV: API_KEY
#   - Imports: __future__, fastapi, logging, os, services, typing
#
# Downstream:
#   - main
#
# Contents:
#   - require_api_key()
#   - search()
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import os
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

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

    if request.headers.get("x-api-key") != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")


# ────────────────────────────────────────────────
# Routes
# ────────────────────────────────────────────────


@router.get(
    "/search",
    dependencies=[Depends(require_api_key)],
    summary="Semantic KB search",
)
def search(
    query: Optional[str] = Query(None, alias="query", description="Search string"),
    q: Optional[str] = Query(None, description="Legacy alias for query"),
    k: int = Query(5, ge=1, le=20, description="Top‑K results"),
) -> List[dict]:
    """Proxy to `services.kb.api_search`. Returns a JSON‑serialisable list."""
    term = (query or q or "").strip()
    if not term:
        raise HTTPException(status_code=400, detail="Missing query parameter")

    try:
        raw = kb.api_search(term, k=k)
        safe = [
            {
                "path": r["path"],
                "title": r["title"],
                "snippet": r["snippet"],
                "updated": r["updated"],
                "similarity": float(r["similarity"]),
            }
            for r in raw
        ]
        return safe
    except Exception as exc:
        logger.exception("KB search failed for %r", term)
        raise HTTPException(status_code=500, detail="KB backend error") from exc
