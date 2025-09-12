# ──────────────────────────────────────────────────────────────────────────────
# File: docs.py
# Directory: routes/
# Purpose: Provides endpoints for managing documentation, including listing, viewing, syncing, and organizing documents.
# Notes   :
#   • API‑key (or future SSO) required for every endpoint.
#   • Path‑traversal safe: requested file must resolve inside project_root/docs.
#   • Adds /mark_priority to manually set doc tier or pin for context.
# ──────────────────────────────────────────────────────────────────────────────#
# Upstream:
#   - ENV: —
#   - Imports: __future__, fastapi, fastapi.responses, os, pathlib, services, services.context_engine, services.docs_utils, services.google_docs_sync, shutil, typing
#
# Downstream:
#   - main
#
# Contents:
#   - _safe_resolve()
#   - full_sync()
#   - list_docs()
#   - mark_priority()
#   - promote_doc()
#   - prune_duplicates()
#   - refresh_kb()
#   - require_api_key()
#   - sync_docs()
#   - view_doc()

#-----docs.py-----

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from services.google_docs_sync import sync_google_docs
from services import kb
from core.context_engine import ContextEngine  # or build_context, etc., per its usage


from services.docs_utils import (
    extract_doc_id,
    build_doc_registry,
    choose_canonical_path,
    write_doc_metadata,
)

# ─── Router Setup ──────────────────────────────────────────────────────────
router = APIRouter(prefix="/docs", tags=["docs"])

# ─── Auth Stub (replace with real auth) ────────────────────────────────────
def require_api_key():
    return True  # TODO: Replace with real API key or OAuth validation

# ─── Constants ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR: Path = PROJECT_ROOT / "docs"
CATEGORIES = ("imported", "generated")

def _safe_resolve(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASE_DIR)
    return resolved

# ─── List docs with metadata ──────────────────────────────────────────────
@router.get("/list", dependencies=[Depends(require_api_key)])
async def list_docs(
    category: str = Query("all", pattern="^(all|imported|generated)$"),
    limit: int = Query(100, ge=1, le=500),
):
    cats = CATEGORIES if category == "all" else (category,)
    results: List[dict] = []

    for sub in cats:
        for f in (BASE_DIR / sub).rglob("*.md"):
            if len(results) >= limit:
                break
            try:
                doc_id = extract_doc_id(f)
                results.append({
                    "path": str(f.relative_to(BASE_DIR)),
                    "doc_id": doc_id,
                    "tier": sub,
                    "source": "google" if "imported" in str(f) else "local",
                    "last_modified": f.stat().st_mtime,
                })
            except Exception:
                continue

    return {"files": results}

# ─── View raw markdown ────────────────────────────────────────────────────
@router.get("/view", dependencies=[Depends(require_api_key)])
async def view_doc(path: str):
    try:
        doc_path = _safe_resolve(BASE_DIR / path)
        if not doc_path.exists():
            raise HTTPException(status_code=404, detail="Doc not found")
        return {"content": doc_path.read_text()}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid path")
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")

# ─── Google Docs Sync ─────────────────────────────────────────────────────
@router.post("/sync", dependencies=[Depends(require_api_key)])
async def sync_docs():
    try:
        saved_files = sync_google_docs()
        kb.api_reindex()
        ContextEngine.clear_cache()
        return {"synced_docs": saved_files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Manual Reindex ───────────────────────────────────────────────────────
@router.post("/refresh_kb", dependencies=[Depends(require_api_key)])
async def refresh_kb():
    try:
        result = kb.api_reindex()
        ContextEngine.clear_cache()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/full_sync", dependencies=[Depends(require_api_key)])
async def full_sync():
    try:
        files = sync_google_docs()
        index_info = kb.api_reindex()
        ContextEngine.clear_cache()
        return {"synced_docs": files, "kb": index_info}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ─── Promote to canonical ─────────────────────────────────────────────────
@router.post("/promote", dependencies=[Depends(require_api_key)])
async def promote_doc(request: Request):
    data = await request.json()
    path = data.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Missing path")

    full_path = _safe_resolve(BASE_DIR / path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    doc_id = extract_doc_id(full_path)
    target_path = BASE_DIR / f"{doc_id}.md"

    try:
        shutil.copy(full_path, target_path)
        kb.api_reindex()
        ContextEngine.clear_cache()
        return {"promoted": str(target_path.relative_to(BASE_DIR))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Promote failed: {e}")

# ─── Prune Duplicates ─────────────────────────────────────────────────────
@router.post("/prune_duplicates", dependencies=[Depends(require_api_key)])
async def prune_duplicates():
    removed = []
    try:
        registry = build_doc_registry()
        for doc_id, versions in registry.items():
            if len(versions) <= 1:
                continue
            keep = choose_canonical_path(versions)
            for path in versions:
                if path != keep:
                    try:
                        os.remove(path)
                        removed.append(str(path.relative_to(BASE_DIR)))
                    except Exception as e:
                        print(f"⚠️ Failed to remove {path}: {e}")
        kb.api_reindex()
        ContextEngine.clear_cache()
        return {"removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prune failed: {e}")

# ─── Mark Priority / Tier ─────────────────────────────────────────────────
@router.post("/mark_priority", dependencies=[Depends(require_api_key)])
async def mark_priority(request: Request):
    """
    Set or update a doc's metadata: tier, pinned flag, or doc_id.
    """
    data = await request.json()
    path = data.get("path")
    tier = data.get("tier")
    pinned = data.get("pinned")

    if not path:
        raise HTTPException(status_code=400, detail="Missing path")

    full_path = _safe_resolve(BASE_DIR / path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        write_doc_metadata(full_path, {"tier": tier, "pinned": pinned})
        kb.api_reindex()
        ContextEngine.clear_cache()
        return {"updated": str(full_path.relative_to(BASE_DIR)), "tier": tier, "pinned": pinned}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metadata update failed: {e}")
