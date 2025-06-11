# routes/kb.py
# Directory: routes/
# Purpose: API routes for knowledge base (KB) semantic search and summary endpoints.
# Stack: FastAPI, LlamaIndex/OpenAI (via services.kb), User-aware

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from services import kb

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

class SearchQuery(BaseModel):
    query: str
    k: int = 4
    search_type: Optional[str] = "all"  # "code", "doc", or "all"

@router.post("/search")
async def search_kb(
    q: SearchQuery,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Search the knowledge base (semantic vector index) for relevant snippets matching the query.
    Optional X-User-Id header for user-aware results.
    `search_type` allows targeting 'code', 'doc', or 'all'.
    Returns a list of matching documents/snippets.
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

@router.get("/search")
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
    Fetch the recent context summary for a given user, or fallback to generic summary.
    """
    user_id = x_user_id or "anonymous"
    try:
        summary = kb.get_recent_summaries(user_id)
        return {"summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KB summary fetch failed: {e}")

@router.post("/reindex")
async def reindex_kb():
    """
    Trigger a rebuild of the KB index (admin/debug only).
    """
    try:
        resp = kb.api_reindex()
        return resp
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"KB reindex failed: {e}")
