# File: routes/index.py
# Purpose: FastAPI endpoint to trigger code/doc indexing in dev environment

from fastapi import APIRouter
from services.indexer import index_directories

router = APIRouter()

@router.post("/index")
async def trigger_index():
    """
    Endpoint to start indexing codebase and docs.
    """
    index_directories()
    return {"status": "Indexing started!"}
