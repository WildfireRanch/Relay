# routes/kb.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services import kb

router = APIRouter(prefix="/kb", tags=["knowledge-base"])

class SearchQuery(BaseModel):
    query: str
    k: int = 4

@router.post("/search")
def search_kb(q: SearchQuery):
    try:
        results = kb.search(query=q.query, k=q.k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
