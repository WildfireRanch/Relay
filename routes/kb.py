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
import os, math
from pydantic import BaseModel
from typing import Optional, List
from services import kb
from services.auth import require_api_key  # ✅ shared API key validator

# ──────────────────────────────────────────────────────────────────────────────
# Enforce X-Api-Key (or Bearer) on ALL /kb/* endpoints.
# Golden path requires /kb/search to succeed "with auth".
# ──────────────────────────────────────────────────────────────────────────────
router = APIRouter(
    prefix="/kb",
    tags=["kb"],
    dependencies=[Depends(require_api_key)],
)

def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default

SEMANTIC_SCORE_THRESHOLD = _env_float("SEMANTIC_SCORE_THRESHOLD", 0.25)

def _score_of(row) -> float:
    """
    Be tolerant: accept 'score' or 'similarity'; coerce to float, clamp 0..1 when possible.
    """
    v = (row or {}).get("score", (row or {}).get("similarity"))
    try:
        x = float(v)
    except Exception:
        return -math.inf  # guarantees it will be filtered if threshold > -inf
    if math.isnan(x) or math.isinf(x):
        return -math.inf
    if 0.0 <= x <= 1.0:
        return x
    if -1.0 <= x <= 1.0:
        return max(0.0, min(1.0, 0.5 + 0.5 * x))
    # Large positives (e.g., dot product): logistic squash (clamped)
    x = min(x, 20.0)
    return 1.0 - (1.0 / (1.0 + math.exp(-x)))

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
        ) or []

        normalized = []
        for r in results:
            if not isinstance(r, dict):
                continue
            s = _score_of(r)
            if s < SEMANTIC_SCORE_THRESHOLD:
                continue
            n = dict(r)
            n["score"] = s
            normalized.append(n)
        return {"ok": True, "threshold": SEMANTIC_SCORE_THRESHOLD, "count": len(normalized), "results": normalized}
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
        ) or []

        normalized = []
        for r in results:
            if not isinstance(r, dict):
                continue
            s = _score_of(r)
            if s < SEMANTIC_SCORE_THRESHOLD:
                continue
            n = dict(r)
            n["score"] = s
            normalized.append(n)
        return {"ok": True, "threshold": SEMANTIC_SCORE_THRESHOLD, "count": len(normalized), "results": normalized}
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
