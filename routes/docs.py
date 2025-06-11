# File: docs.py
# Directory: routes/
# Purpose: API routes for listing, viewing, and syncing documentation files.

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from typing import Optional
import os

router = APIRouter(prefix="/docs", tags=["docs"])

@router.get("/list")
async def list_docs():
    """
    List all markdown docs in docs/imported and docs/generated.
    """
    import pathlib
    base = pathlib.Path(__file__).resolve().parents[1] / "docs"
    results = []
    for sub in ["imported", "generated"]:
        subdir = base / sub
        if not subdir.exists():
            continue
        for f in subdir.rglob("*.md"):
            results.append(str(f.relative_to(base)))
    return {"docs": results}

@router.get("/view")
async def view_doc(path: str):
    """
    Return the contents of the given markdown doc path.
    """
    import pathlib
    base = pathlib.Path(__file__).resolve().parents[1] / "docs"
    doc_path = base / path
    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Doc not found.")
    try:
        return {"content": doc_path.read_text()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/sync")
async def sync_docs():
    """
    Dummy placeholder for Google Docs sync trigger.
    """
    # You can fill this in with your actual sync logic (call services.google_docs_sync, etc)
    # For now just return a stub
    return {"message": "Docs sync triggered (stub)."}
