# routes/search.py

"""
Semantic search API for Relay
-----------------------------
- Accepts 'query' as a GET param
- Returns most relevant files/snippets via embeddings service
"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from services.embeddings import search_index

router = APIRouter()

@router.get("/search")
def search(query: str = Query(..., description="Search query string"), top_k: int = 5):
    """
    Semantic search over docs/code.
    Returns top matching file paths and snippets.
    """
    results = search_index(query, top_k=top_k)
    # Strip out embedding vectors from API result for bandwidth
    payload = [
        {"file": r["file"], "snippet": r["snippet"]} for r in results
    ]
    return JSONResponse(payload)
