# routes/search.py
# Directory: routes/
# Purpose: Auth-gated semantic search proxy using services.kb.api_search
# Security: API-key required (adjust Depends as your auth layer evolves)

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from services import kb
import logging

router = APIRouter(prefix="/kb", tags=["kb-search"])
logger = logging.getLogger(__name__)

def require_api_key():       #  ← replace with your real auth
    return True

@router.get("/search", dependencies=[Depends(require_api_key)])
def search(
    q: str = Query(..., alias="query", description="Search query string"),
    k: int = Query(5, ge=1, le=20, description="Top-K results"),
):
    """
    Semantic search over code/docs (LlamaIndex backend).
    """
    logger.info("KB search: %r (k=%d)", q, k)
    try:
        results = kb.api_search(query=q, k=k)
    except Exception as e:
        logger.exception("kb.api_search failed")
        raise HTTPException(status_code=500, detail=str(e))

    payload = [
        {
            "path": r["path"],
            "title": r["title"],
            "snippet": r["snippet"],
            "similarity": r["similarity"],
        }
        for r in results
    ]
    return JSONResponse(payload)
