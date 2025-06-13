# routes/search.py
# Directory: routes/
# Purpose: Semantic search API for Relay
# Security: None (public for now; see known issues)
# Known Issues: No authentication or rate limiting enabled (see project log).

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from services.embeddings import search_index
import logging

router = APIRouter(prefix="/public", tags=["public-search"])

logger = logging.getLogger("search")

@router.get("/search")
def search(
    query: str = Query(..., description="Search query string"),
    top_k: int = 5,
):
    """
    Semantic search over docs/code.  
    Returns top matching file paths and snippets.
    """
    logger.info(f"Semantic search query: '{query}' (top_k={top_k})")
    results = search_index(query, top_k=top_k)
    # Strip out embedding vectors from API result for bandwidth
    payload = [
        {"file": r.get("file"), "snippet": r.get("snippet")} for r in results
    ]
    return JSONResponse(payload)
