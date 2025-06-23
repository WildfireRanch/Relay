# File: docs.py
# Directory: routes/
# Purpose: Secure API routes for listing, viewing, and syncing Markdown documentation.
# Notes:
#   • API‑key (or future SSO) required for every endpoint.
#   • Path‑traversal safe: requested file must resolve inside project_root/docs.
#   • Supports category filter (imported/generated/all) and result limiting.
#   • Sync endpoint is async‑ready; replace stub with real Google Docs sync.
#   • Returns 202 on sync trigger, 200 on list/view.

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from services.google_docs_sync import sync_google_docs
from services import kb

# ─── Router Setup ──────────────────────────────────────────────────────────
router = APIRouter(prefix="/docs", tags=["docs"])

# ─── Auth Stub (replace with real API‑key or SSO dependency) ───────────────

def require_api_key():
    # TODO: implement real auth (e.g. Header x-api-key validation)
    return True

# ─── Constants ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR: Path = PROJECT_ROOT / "docs"
CATEGORIES = ("imported", "generated")

# ─── Helpers ──────────────────────────────────────────────────────────────

def _safe_resolve(path: Path) -> Path:
    """Return *path* if it resolves inside BASE_DIR else raise ValueError."""
    resolved = path.resolve()
    resolved.relative_to(BASE_DIR)  # raises ValueError if outside tree
    return resolved

# ─── Routes ───────────────────────────────────────────────────────────────

@router.get("/list", dependencies=[Depends(require_api_key)])
async def list_docs(
    category: str = Query("all", pattern="^(all|imported|generated)$"),
    limit: int = Query(100, ge=1, le=500),
):
    """Return a list of Markdown docs in `/docs/<category>`.

    * **category** – `imported`, `generated`, or `all` (default).
    * **limit**    – maximum number of results (default 100).
    """
    cats = CATEGORIES if category == "all" else (category,)
    results: List[str] = []
    for sub in cats:
        for f in (BASE_DIR / sub).rglob("*.md"):
            if len(results) >= limit:
                break
            results.append(str(f.relative_to(BASE_DIR)))
        if len(results) >= limit:
            break
    return {"files": results}


@router.get("/view", dependencies=[Depends(require_api_key)])
async def view_doc(path: str):
    """Return the contents of a markdown doc given its relative *path*."""
    try:
        doc_path = _safe_resolve(BASE_DIR / path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")

    if not doc_path.exists():
        raise HTTPException(status_code=404, detail="Doc not found")

    try:
        return {"content": doc_path.read_text()}
    except Exception:
        # Avoid leaking internal paths in prod
        raise HTTPException(status_code=500, detail="Internal error")


@router.post("/sync", dependencies=[Depends(require_api_key)])
async def sync_docs():
    """Synchronize Google Docs and return saved filenames."""
    try:
        saved_files = sync_google_docs()
        try:
            kb.api_reindex()
        except Exception as reindex_error:
            # Log but don't fail the sync if reindexing hits issues
            print(f"KB reindex failed: {reindex_error}")
        return {"synced_docs": saved_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/refresh_kb", dependencies=[Depends(require_api_key)])
async def refresh_kb():
    """Rebuild the semantic KB index."""
    try:
        return kb.api_reindex()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/full_sync", dependencies=[Depends(require_api_key)])
async def full_sync():
    """Run Google Docs sync then rebuild the KB index."""
    try:
        files = sync_google_docs()
        index_info = kb.api_reindex()
        return {"synced_docs": files, "kb": index_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
