# ──────────────────────────────────────────────────────────────────────────────
# File: routes/docs.py
# Purpose: Authenticated Docs API (list, view, sync, reindex, housekeeping)
#
# Endpoints (all require X-Api-Key or Authorization: Bearer …):
#   • GET  /docs/list?category=all|imported|generated&limit=&offset=
#   • GET  /docs/view?path=<relative-path-under-imported-or-generated>
#   • POST /docs/sync?wait=true|false                # Google sync only
#   • POST /docs/full_sync?wait=true|false          # sync + reindex + cache clear
#   • POST /docs/refresh_kb?wait=true|false         # reindex + cache clear
#   • POST /docs/prune_duplicates?wait=true|false   # canonicalize duplicate doc IDs
#   • POST /docs/promote                            # promote a chosen file to canonical
#   • POST /docs/mark_priority                      # set tier/pinned metadata
#
# Guarantees
#   • Never allows path traversal: requested files must resolve under ./docs/*
#   • Long ops are lock-protected (409 on contention; 202 when wait=false)
#   • Google stack absence → 503 with actionable detail (never generic 500)
#   • ContextEngine.clear_cache() and kb.api_reindex() are wrapped to never crash
#   • Success payloads are structured and predictable (no ad-hoc shapes)
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Literal, Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

# ── Local/Service imports -----------------------------------------------------
from services import kb
from services.auth import require_api_key  # shared API key validator

# ContextEngine — cache clear is wrapped to never raise
try:
    from services.context_engine import ContextEngine
except Exception as _ctx_exc:  # pragma: no cover
    ContextEngine = None  # type: ignore[assignment]
    _CTX_IMPORT_ERROR = _ctx_exc
else:
    _CTX_IMPORT_ERROR = None

# Google sync (optional)
try:
    from services.google_docs_sync import sync_google_docs as _sync_google_docs
    _GOOGLE_SYNC_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - optional dependency may be absent
    _sync_google_docs = None  # type: ignore[assignment]
    _GOOGLE_SYNC_IMPORT_ERROR = exc

# Preserve historical symbol for tests/monkeypatching
sync_google_docs = _sync_google_docs

logger = logging.getLogger(__name__)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Paths & Constants                                                        ║
# ╚══════════════════════════════════════════════════════════════════════════╝

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_BASE = (PROJECT_ROOT / "docs").resolve()
DOCS_IMPORTED = (DOCS_BASE / "imported").resolve()
DOCS_GENERATED = (DOCS_BASE / "generated").resolve()
CATEGORIES: Tuple[str, str] = ("imported", "generated")

# Ensure base dirs exist (defensive; main.py also does this)
for _p in (DOCS_BASE, DOCS_IMPORTED, DOCS_GENERATED):
    try:
        _p.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Startup should remain resilient; /readyz surfaces writability separately
        pass

# Lock directory (shared; overridable by env)
LOCK_DIR = Path(os.getenv("LOCK_DIR") or PROJECT_ROOT / "var" / "locks")
try:
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # will be caught by _writable checks during operations
    pass


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Utilities (safe pathing, locks, wrappers)                                ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _safe_under(base: Path, rel: str) -> Path:
    """Resolve rel under base; raise 400 if it escapes base."""
    try:
        target = (base / rel).resolve()
        target.relative_to(base)
        return target
    except Exception:
        raise HTTPException(status_code=400, detail="path escapes allowed base directory")

def _iter_files(base: Path) -> Iterable[Path]:
    if not base.exists():
        return []
    return (p for p in sorted(base.rglob("*")) if p.is_file())

def _ok(content: Dict[str, Any], status: int = 200) -> JSONResponse:
    content.setdefault("ok", True)
    return JSONResponse(status_code=status, content=content)

def _err(status: int, detail: str) -> None:
    raise HTTPException(status_code=status, detail=detail)

def _safe_clear_cache() -> Dict[str, Any]:
    """Clear ContextEngine cache but never raise; report status."""
    if ContextEngine is None:
        return {"ok": True, "cleared": False, "reason": f"context_engine import failed: {_CTX_IMPORT_ERROR}"}
    try:
        res = ContextEngine.clear_cache()
        # normalize
        if isinstance(res, dict):
            return {"ok": bool(res.get("ok", True)), "cleared": res.get("cleared", True), "version": res.get("version")}
        return {"ok": True, "cleared": True}
    except Exception as e:  # pragma: no cover
        logger.warning("ContextEngine.clear_cache() failed: %s", e)
        return {"ok": True, "cleared": False, "reason": str(e)}

def _safe_kb_reindex() -> Dict[str, Any]:
    """Call kb.api_reindex() and normalize output; never raise."""
    try:
        res = kb.api_reindex()  # type: ignore[attr-defined]
    except Exception as e:  # pragma: no cover
        logger.exception("kb.api_reindex() failed: %s", e)
        return {"ok": False, "status": "error", "error": str(e)}
    if isinstance(res, dict):
        return {"ok": bool(res.get("ok", True)), **{k: v for k, v in res.items() if k != "ok"}}
    return {"ok": True, "status": "done", "result": str(res)}

@contextmanager
def _op_lock(name: str):
    """
    Cross-process advisory lock.
    - Linux: fcntl flock (non-blocking)
    - Fallback: lock file presence
    """
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
    """
    Execute an operation with locking.
    - wait=true  → run now under lock, return result
    - wait=false → queue background task (202) unless already in-flight
    - if locked/in-flight → 409
    """
    if wait:
        return _run_locked(name, fn)

    if name in _ASYNC_IN_FLIGHT:
        _err(409, f"{name} already in progress")

    _ASYNC_IN_FLIGHT.add(name)

    def _bg_wrapper() -> None:
        try:
            _run_locked(name, fn)
        finally:
            _ASYNC_IN_FLIGHT.discard(name)

    background.add_task(_bg_wrapper)
    return _ok({"accepted": True}, status=202)

    # (remove any nested / duplicated @router.get("/op_status") definitions here)
    # (keep _execute_op helper body focused solely on running ops)
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║ Router                                                                   ║
# ╚══════════════════════════════════════════════════════════════════════════╝

router = APIRouter(
    prefix="/docs",
    tags=["docs"],
    dependencies=[Depends(require_api_key)],  # enforce auth on ALL endpoints
)


# ──────────────────────────────────────────────────────────────────────────────
# Change: Define a single, module-scope /op_status with clear, non-throwing body
# Why: Duplicates + nesting broke import/registration; this is the canonical one
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/op_status")
def op_status():
    """Read-only probe for long-ops and active locks. Never raises."""
    try:
        try:
            in_flight = sorted(list(_ASYNC_IN_FLIGHT))
        except Exception:
            in_flight = []

        locks: List[str] = []
        try:
            for p in Path(str(LOCK_DIR)).glob("*.lock"):
                locks.append(p.name)
        except Exception:
            locks = []

        return _ok({"action": "op_status", "in_flight": in_flight, "locks": locks})
    except Exception as e:
        # Final guard: never raise from diagnostics
        return {"ok": False, "action": "op_status", "error": str(e), "in_flight": [], "locks": []}


# ── List documents (read-only) -----------------------------------------------
@router.get("/list")
def list_docs(
    category: Literal["all", "imported", "generated"] = Query("all"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List .md files under docs/imported and/or docs/generated.
    Returns stable shape: {ok, category, count, total, items:[{source,relpath,bytes,mtime}]}
    """
    imported = [
        {"source": "imported", "relpath": str(p.relative_to(DOCS_BASE)), "bytes": p.stat().st_size, "mtime": p.stat().st_mtime}
        for p in _iter_files(DOCS_IMPORTED) if p.suffix.lower() == ".md"
    ]
    generated = [
        {"source": "generated", "relpath": str(p.relative_to(DOCS_BASE)), "bytes": p.stat().st_size, "mtime": p.stat().st_mtime}
        for p in _iter_files(DOCS_GENERATED) if p.suffix.lower() == ".md"
    ]

    if category == "imported":
        items = imported
    elif category == "generated":
        items = generated
    else:
        items = imported + generated

    total = len(items)
    page = items[offset: offset + limit] if limit > 0 else items[offset:]
    return _ok({"action": "list", "category": category, "count": len(page), "total": total, "items": page})


# ── View a document (read-only) ----------------------------------------------
@router.get("/view")
def view_doc(path: str = Query(..., description="Relative path under 'docs/', 'imported/', or 'generated/'")):
    """
    Return file content for a single relative path.
    Accepts:
      • 'imported/foo.md' or 'generated/foo.md'
      • 'foo.md' (we'll look in generated/ first, then imported/)
      • 'imported/sub/dir/foo.md' etc.
    Always prevents path traversal.
    """
    candidates: List[Path] = []

    # 1) Directly under DOCS_BASE (handles 'imported/...' / 'generated/...' / plain 'foo.md')
    try:
        cand = _safe_under(DOCS_BASE, path)
        candidates.append(cand)
    except HTTPException:
        # If this failed due to traversal, we still try base-specific below,
        # which will raise a 400 if all attempts fail.
        pass

    # 2) If user passed 'imported/...' or 'generated/...', also try stripping the prefix
    #    and resolving under the specific base to catch edge differences in symlinks/paths.
    lowered = path.lstrip("/").lower()
    if lowered.startswith("generated/"):
        sub = path.split("/", 1)[1] if "/" in path else ""
        try:
            candidates.append(_safe_under(DOCS_GENERATED, sub))
        except HTTPException:
            pass
    elif lowered.startswith("imported/"):
        sub = path.split("/", 1)[1] if "/" in path else ""
        try:
            candidates.append(_safe_under(DOCS_IMPORTED, sub))
        except HTTPException:
            pass
    else:
        # 3) Plain filename like 'foo.md': probe generated first, then imported
        try:
            candidates.append(_safe_under(DOCS_GENERATED, path))
        except HTTPException:
            pass
        try:
            candidates.append(_safe_under(DOCS_IMPORTED, path))
        except HTTPException:
            pass

    # Deduplicate candidates while preserving order
    seen = set()
    uniq: List[Path] = []
    for p in candidates:
        key = str(p)
        if key not in seen:
            seen.add(key)
            uniq.append(p)

    for safe in uniq:
        if safe.exists() and safe.is_file():
            try:
                text = safe.read_text(encoding="utf-8", errors="replace")
            except UnicodeDecodeError:
                return _ok({"action": "view", "path": path, "binary": True, "bytes": safe.stat().st_size})
            return _ok({"action": "view", "path": path, "binary": False, "content": text})

    # If none existed, decide between 400 (traversal) vs 404 (not found)
    # The traversal case would have raised above during _safe_under;
    # if we got here, it means the path was syntactically safe but missing.
    _err(404, f"File not found under allowed bases: {path}")


# ── Google Docs Sync ----------------------------------------------------------
def _google_sync_ready() -> Tuple[bool, str]:
    """Return (ready, reason) for google sync availability."""
    if sync_google_docs is None:
        reason = "google sync module not available"
        if _GOOGLE_SYNC_IMPORT_ERROR:
            reason += f": {_GOOGLE_SYNC_IMPORT_ERROR}"
        return False, reason
    return True, ""

@router.post("/sync")
def sync_docs(
    request: Request,  # reserved for future telemetry
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    ready, reason = _google_sync_ready()
    if not ready:
        _err(503, f"Google Docs sync is not available ({reason})")

    def _job() -> Dict[str, Any]:
        files = sync_google_docs()  # type: ignore[misc]
        reindex = _safe_kb_reindex()
        cache = _safe_clear_cache()
        return {"action": "sync", "synced_docs": files, "kb": reindex, "cache": cache}

    try:
        return _execute_op("docs_sync", wait=wait, background=background, fn=_job)
    except RuntimeError as err:
        if "already in progress" in str(err):
            _err(409, str(err))
        raise
    except HTTPException as http_exc:
        # Preserve original status (e.g., 409)
        raise http_exc
    except Exception as exc:  # pragma: no cover
        _err(500, f"sync failed: {exc}")

@router.post("/full_sync")
def full_sync(
    request: Request,
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    ready, reason = _google_sync_ready()
    if not ready:
        _err(503, f"Google Docs sync is not available ({reason})")

    def _job() -> Dict[str, Any]:
        files = sync_google_docs()  # type: ignore[misc]
        reindex = _safe_kb_reindex()
        cache = _safe_clear_cache()
        return {"action": "full_sync", "synced_docs": files, "kb": reindex, "cache": cache}

    try:
        return _execute_op("docs_full_sync", wait=wait, background=background, fn=_job)
    except RuntimeError as err:
        if "already in progress" in str(err):
            _err(409, str(err))
        raise
    except Exception as exc:  # pragma: no cover
        _err(500, f"full_sync failed: {exc}")


# ── KB Reindex only -----------------------------------------------------------
@router.post("/refresh_kb")
def refresh_kb(
    request: Request,
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    def _job() -> Dict[str, Any]:
        reindex = _safe_kb_reindex()
        # ── Extract semantic counts if present (non-throwing) ────────────────
        semantic_counts = None
        try:
            sem = reindex.get("semantic") if isinstance(reindex, dict) else None
            if isinstance(sem, dict) and sem.get("ok"):
                semantic_counts = sem.get("counts")
            if semantic_counts is None and isinstance(reindex, dict) and isinstance(reindex.get("counts"), dict):
                semantic_counts = reindex.get("counts")
        except Exception:
            semantic_counts = None

        # ── Friendly source label for UI/scripts (tolerant inference) ────────
        kb_source = None
        try:
            kb_source = reindex.get("source") if isinstance(reindex, dict) else None
            if not kb_source:
                if isinstance(reindex.get("semantic"), dict) and reindex["semantic"].get("ok"):
                    kb_source = "semantic"
                elif any(k in (reindex or {}) for k in ("indexed", "model", "took_ms")):
                    kb_source = "llamaindex"
                else:
                    kb_source = "unknown"
        except Exception:
            kb_source = "unknown"
        cache = _safe_clear_cache()
        return {"action": "refresh_kb", "kb": reindex, "kb_source": kb_source, "semantic_counts": semantic_counts, "cache": cache}

    try:
        return _execute_op("kb_reindex", wait=wait, background=background, fn=_job)
    except RuntimeError as err:
        if "already in progress" in str(err):
            _err(409, str(err))
        raise
    except HTTPException as http_exc:
        raise http_exc
    except Exception as exc:  # pragma: no cover
        _err(500, f"refresh_kb failed: {exc}")


# ── Promote a specific file to canonical -------------------------------------
@router.post("/promote")
async def promote_doc(request: Request):
    """
    Promote a file to a canonical path based on its doc_id.
    - body: { path: "<relative path>" }
    """
    data = await request.json()
    path = data.get("path")
    if not path:
        _err(400, "Missing path")

    # Resolve and check
    for base in (DOCS_GENERATED, DOCS_IMPORTED):
        try:
            full_path = _safe_under(base, path)
        except HTTPException:
            continue
        if full_path.exists():
            break
    else:
        _err(404, "File not found")

    # Derive canonical name: prefer folder name or stem as ID if available
    try:
        from services.docs_utils import extract_doc_id
        doc_id = extract_doc_id(full_path)
    except Exception:
        doc_id = full_path.stem  # fallback

    target_path = (DOCS_BASE / f"{doc_id}.md").resolve()
    try:
        shutil.copy(full_path, target_path)
        reindex = _safe_kb_reindex()
        cache = _safe_clear_cache()
        return _ok({"action": "promote", "promoted": str(target_path.relative_to(DOCS_BASE)), "kb": reindex, "cache": cache})
    except Exception as e:
        _err(500, f"promote failed: {e}")


# ── Prune duplicate doc IDs ---------------------------------------------------
@router.post("/prune_duplicates")
def prune_duplicates(
    request: Request,
    background: BackgroundTasks,
    wait: bool = Query(True),
):
    """
    Remove non-canonical duplicates: keeps chosen canonical per doc_id.
    """
    def _job() -> Dict[str, Any]:
        removed: List[str] = []
        try:
            from services.docs_utils import build_doc_registry, choose_canonical_path
        except Exception as e:
            return {"action": "prune_duplicates", "ok": False, "error": f"docs_utils import failed: {e}"}

        registry = build_doc_registry()
        for doc_id, versions in registry.items():
            if len(versions) <= 1:
                continue
            keep = choose_canonical_path(versions)
            for path in versions:
                if path != keep:
                    try:
                        os.remove(path)
                        removed.append(str(Path(path).resolve().relative_to(DOCS_BASE)))
                    except Exception as e:
                        logger.warning("Failed to remove %s: %s", path, e)

        reindex = _safe_kb_reindex()
        cache = _safe_clear_cache()
        return {"action": "prune_duplicates", "removed": removed, "kb": reindex, "cache": cache}

    try:
        return _execute_op("docs_prune", wait=wait, background=background, fn=_job)
    except RuntimeError as err:
        if "already in progress" in str(err):
            _err(409, str(err))
        raise
    except HTTPException as http_exc:
        raise http_exc
    except Exception as exc:  # pragma: no cover
        _err(500, f"prune failed: {exc}")


# ── Mark priority / tier / pinned metadata -----------------------------------
@router.post("/mark_priority")
async def mark_priority(request: Request):
    """
    Update a doc's metadata (tier, pinned).
    - body: { path, tier?, pinned? }
    """
    data = await request.json()
    path = data.get("path")
    tier = data.get("tier")
    pinned = data.get("pinned")

    if not path:
        _err(400, "Missing path")

    # Resolve path safely
    for base in (DOCS_GENERATED, DOCS_IMPORTED, DOCS_BASE):
        try:
            full_path = _safe_under(base, path)
        except HTTPException:
            continue
        if full_path.exists():
            break
    else:
        _err(404, "File not found")

    try:
        from services.docs_utils import write_doc_metadata
        write_doc_metadata(full_path, {"tier": tier, "pinned": pinned})
        reindex = _safe_kb_reindex()
        cache = _safe_clear_cache()
        return _ok({"action": "mark_priority", "updated": str(full_path.relative_to(DOCS_BASE)), "tier": tier, "pinned": pinned, "kb": reindex, "cache": cache})
    except Exception as e:
        _err(500, f"metadata update failed: {e}")
