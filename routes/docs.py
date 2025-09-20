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

import logging
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Header
from fastapi.responses import JSONResponse

from services import kb
from services.context_engine import ContextEngine
from services.docs_utils import (
    extract_doc_id,
    build_doc_registry,
    choose_canonical_path,
    write_doc_metadata,
)


logger = logging.getLogger(__name__)

try:
    from services.google_docs_sync import sync_google_docs as _sync_google_docs
    _GOOGLE_SYNC_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - optional dependency may be absent
    _sync_google_docs = None  # type: ignore[assignment]
    _GOOGLE_SYNC_IMPORT_ERROR = exc
    logger.warning("Google Docs sync disabled: %s", exc)

# Preserve historical module-level symbol for tests/monkeypatching.
sync_google_docs = _sync_google_docs

# ─── Router Setup ──────────────────────────────────────────────────────────
router = APIRouter(prefix="/docs", tags=["docs"])

# ─── Auth ‐ enforce X-Api-Key ------------------------------------------------
_AUTH_ENV_NAMES = ("API_KEY", "RELAY_API_KEY", "ADMIN_API_KEY")
_AUTH_BYPASS_LOGGED = False


def _load_admin_keys() -> List[str]:
    keys = []
    for name in _AUTH_ENV_NAMES:
        value = (os.getenv(name) or "").strip()
        if value:
            keys.append(value)
    return keys


def require_api_key(x_api_key: str | None = Header(None, alias="X-Api-Key")) -> bool:
    global _AUTH_BYPASS_LOGGED
    keys = _load_admin_keys()
    if not keys:
        if not _AUTH_BYPASS_LOGGED:
            logger.warning("X-Api-Key check bypassed (no key envs present)")
            _AUTH_BYPASS_LOGGED = True
        return True

    if not x_api_key or x_api_key not in keys:
        raise HTTPException(
            status_code=401,
            detail={"error": True, "detail": "Missing or invalid X-Api-Key"},
        )

    return True

# ─── Constants ────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_DIR: Path = PROJECT_ROOT / "docs"
CATEGORIES = ("imported", "generated")
LOCK_DIR = PROJECT_ROOT / "var" / "locks"
LOCK_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def _op_lock(name: str):
    lock_path = LOCK_DIR / f"{name}.lock"
    fh = lock_path.open("a+")
    try:
        try:
            import fcntl  # type: ignore

            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(f"{name} already in progress") from exc
        except ImportError:
            if lock_path.exists():
                raise RuntimeError(f"{name} already in progress")
            lock_path.write_text(str(time.time()), encoding="utf-8")

        yield
    finally:
        try:
            try:
                import fcntl  # type: ignore

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass
        except Exception:
            pass
        fh.close()
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass


_ASYNC_IN_FLIGHT: set[str] = set()


def _run_locked(name: str, fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    with _op_lock(name):
        return fn()


def _execute_op(
    name: str,
    *,
    wait: bool,
    background: BackgroundTasks,
    fn: Callable[[], Dict[str, Any]],
):
    if wait:
        return _run_locked(name, fn)

    if name in _ASYNC_IN_FLIGHT:
        raise RuntimeError(f"{name} already in progress")

    _ASYNC_IN_FLIGHT.add(name)

    def _background_wrapper() -> None:
        try:
            _run_locked(name, fn)
        finally:
            _ASYNC_IN_FLIGHT.discard(name)

    background.add_task(_background_wrapper)
    return JSONResponse(status_code=202, content={"accepted": True})

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
async def sync_docs(
    request: Request,
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    del request  # currently unused; keeps signature for future telemetry

    if _sync_google_docs is None:
        detail = "Google Docs sync is not available in this environment."
        if _GOOGLE_SYNC_IMPORT_ERROR is not None:
            detail = f"{detail} ({_GOOGLE_SYNC_IMPORT_ERROR})"
        raise HTTPException(status_code=503, detail=detail)

    def _job() -> Dict[str, Any]:
        saved_files = _sync_google_docs()
        kb.api_reindex()
        ContextEngine.clear_cache()
        return {"synced_docs": saved_files}

    try:
        return _execute_op(
            "docs_sync",
            wait=wait,
            background=background,
            fn=_job,
        )
    except RuntimeError as err:
        if "already in progress" in str(err):
            raise HTTPException(status_code=409, detail=str(err))
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

# ─── Manual Reindex ───────────────────────────────────────────────────────
@router.post("/refresh_kb", dependencies=[Depends(require_api_key)])
async def refresh_kb(
    request: Request,
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    del request

    def _job() -> Dict[str, Any]:
        result = kb.api_reindex()
        ContextEngine.clear_cache()
        return result

    try:
        return _execute_op(
            "kb_reindex",
            wait=wait,
            background=background,
            fn=_job,
        )
    except RuntimeError as err:
        if "already in progress" in str(err):
            raise HTTPException(status_code=409, detail=str(err))
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/full_sync", dependencies=[Depends(require_api_key)])
async def full_sync(
    request: Request,
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    del request

    if _sync_google_docs is None:
        detail = "Google Docs sync is not available in this environment."
        if _GOOGLE_SYNC_IMPORT_ERROR is not None:
            detail = f"{detail} ({_GOOGLE_SYNC_IMPORT_ERROR})"
        raise HTTPException(status_code=503, detail=detail)

    def _job() -> Dict[str, Any]:
        files = _sync_google_docs()
        index_info = kb.api_reindex()
        ContextEngine.clear_cache()
        return {"synced_docs": files, "kb": index_info}

    try:
        return _execute_op(
            "docs_full_sync",
            wait=wait,
            background=background,
            fn=_job,
        )
    except RuntimeError as err:
        if "already in progress" in str(err):
            raise HTTPException(status_code=409, detail=str(err))
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

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
async def prune_duplicates(
    request: Request,
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    del request

    def _job() -> Dict[str, Any]:
        removed: List[str] = []
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

    try:
        return _execute_op(
            "docs_prune",
            wait=wait,
            background=background,
            fn=_job,
        )
    except RuntimeError as err:
        if "already in progress" in str(err):
            raise HTTPException(status_code=409, detail=str(err))
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Prune failed: {exc}")

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
