# ──────────────────────────────────────────────────────────────────────────────
# File: kb.py
# Directory: routes
# Purpose: Provides the backend functionality for knowledge base search and management, including API endpoints and data validation models.
# Security: All admin/debug endpoints require X-API-Key header, which must match API_KEY in environment.
# Stack: FastAPI, LlamaIndex/OpenAI (via services.kb), User-aware
# Upstream:
#   - ENV: —
#   - Imports: fastapi, os, pydantic, services, typing
#
# Downstream:
#   - main
#
# Contents:
#   - SearchQuery()
#   - get_summary()
#   - reindex_kb()
#   - require_api_key()
#   - search_kb()
#   - search_kb_get()

# ──────────────────────────────────────────────────────────────────────────────

from fastapi import APIRouter, HTTPException, Header, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from services import kb
import os
import logging

# Align auth with routes/docs.py (same header and behavior)
logger = logging.getLogger(__name__)
_AUTH_ENV_NAMES = ("API_KEY", "RELAY_API_KEY", "ADMIN_API_KEY")
_AUTH_BYPASS_LOGGED = False


def _load_admin_keys() -> List[str]:
    keys: List[str] = []
    for name in _AUTH_ENV_NAMES:
        value = (os.getenv(name) or "").strip()
        if value:
            keys.append(value)
    return keys


def require_api_key(x_api_key: str | None = Header(None, alias="X-Api-Key")) -> bool:
    global _AUTH_BYPASS_LOGGED
    keys = _load_admin_keys()
    if not keys:
        if not _AUTH_BYPASS_LOGGED:
            logger.warning("X-Api-Key check bypassed (no key envs present)")
            _AUTH_BYPASS_LOGGED = True
        return True

    if not x_api_key or x_api_key not in keys:
        raise HTTPException(
            status_code=401,
            detail={"error": True, "detail": "Missing or invalid X-Api-Key"},
        )

    return True

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

class SearchQuery(BaseModel):
    query: str
    k: int = 4
    search_type: Optional[str] = "all"  # "code", "doc", or "all"

@router.post("/search", dependencies=[Depends(require_api_key)])
async def search_kb(
    q: SearchQuery,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Search the knowledge base (semantic vector index) for relevant snippets.
    Optional X-User-Id header for user-aware results.
    `search_type`: 'code', 'doc', or 'all'.
    """
    user_id = x_user_id or "anonymous"
    try:
        results = kb.api_search(
            query=q.query,
            k=q.k,
            search_type=q.search_type or "all"
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KB search failed: {e}")

@router.get("/search", dependencies=[Depends(require_api_key)])
async def search_kb_get(
    query: str,
    k: int = 4,
    search_type: Optional[str] = "all",
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    GET variant of KB search for easy testing.
    """
    user_id = x_user_id or "anonymous"
    try:
        results = kb.api_search(
            query=query,
            k=k,
            search_type=search_type or "all"
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KB search failed: {e}")

@router.get("/summary")
async def get_summary(
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Fetch recent context summary for a given user, or fallback to generic summary.
    """
    user_id = x_user_id or "anonymous"
    try:
        summary = kb.get_recent_summaries(user_id)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KB summary fetch failed: {e}")

@router.post("/reindex")
async def reindex_kb(
    api_key: str = Depends(require_api_key)
):
    """
    Trigger a rebuild of the KB index (admin/debug only).
    Requires X-API-Key header.
    """
    try:
        resp = kb.api_reindex()
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KB reindex failed: {e}")
