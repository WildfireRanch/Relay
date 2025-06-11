# File: kb.py
# Directory: routes/
# Purpose: API routes for knowledge base (KB) semantic search and summary endpoints.

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from services import kb

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

class SearchQuery(BaseModel):
    query: str
    k: int = 4

@router.post("/search")
async def search_kb(
    q: SearchQuery,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id")
):
    """
    Search the knowledge base for snippets matching the query.
    Accepts optional X-User-Id header to tailor results per user.
    Returns a list of matching documents with snippets.
    """
    user_id = x_user_id or "anonymous"
    try:
        # Try user-aware KB search, fallback to all docs if not supported
        try:
            results = kb.search(query=q.query, user_id=user_id, k=q.k)
        except TypeError:
            results = kb.search(query=q.query, k=q.k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))