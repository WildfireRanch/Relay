# ──────────────────────────────────────────────────────────────────────────────
# File: routes/kb.py
# Purpose: KB search + admin ops — semantic-first, timeout-safe, production-grade
# Security: All endpoints require X-Api-Key via require_api_key dependency
# Contracts:
#   • POST /kb/search   body {query, k?, search_type?} → {ok, threshold, count, results[]}
#   • GET  /kb/search   ?query=&k=&search_type=        → same
#   • POST /kb/warmup   → {ok, warmed}
#   • GET  /kb/summary  → {ok?, items? | summary?} (shim in services.kb)
#   • POST /kb/reindex  → services.kb.api_reindex() passthrough
#
# Notes:
#   • Fast path uses services.semantic_retriever.search (adaptable signature).
#   • Optional fallback to services.kb.search guarded by ALLOW_KB_FALLBACK.
#   • Non-blocking timeouts return JSON 503 (never edge 504).
#   • Scores normalized to [0,1]; filtered by SEMANTIC_SCORE_THRESHOLD (env).
#   • Stable, non-throwing warmup and summary paths.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
import math
import os
import time
from typing import Any, Callable, List, Optional, Tuple

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Best-effort structured logger (safe to no-op if missing)
try:  # pragma: no cover
    from core.logging import log_event as _structured_log_event  # type: ignore
except Exception:  # pragma: no cover
    def _structured_log_event(event: str, data: dict) -> None:  # type: ignore
        return

from services import kb as kb_service
from services.auth import require_api_key

# Prefer semantic adapter when available (fast path)
try:  # pragma: no cover
    from services.semantic_retriever import search as sem_search  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    sem_search = None  # type: ignore[assignment]

# ──────────────────────────────────────────────────────────────────────────────
# Router (global auth)
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/kb", tags=["kb"], dependencies=[Depends(require_api_key)])

_LOG = logging.getLogger("relay.kb")
if not _LOG.handlers:
    _LOG.setLevel(logging.INFO)

# ──────────────────────────────────────────────────────────────────────────────
# Change: Gate temporary impl marker via env (Step A verification only)
# Why: Keep 504-debug signal without permanently changing response shape
# ──────────────────────────────────────────────────────────────────────────────
IMPL_MARKER: str = os.getenv("KB_IMPL_MARKER", "").strip()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


SEMANTIC_SCORE_THRESHOLD: float = _env_float("SEMANTIC_SCORE_THRESHOLD", 0.25)
KB_SEARCH_TIMEOUT_S: float = _env_float("KB_SEARCH_TIMEOUT_S", 30.0)
ALLOW_KB_FALLBACK: bool = os.getenv("ALLOW_KB_FALLBACK", "1") not in ("0", "false", "False")

# ──────────────────────────────────────────────────────────────────────────────
# Helpers: non-blocking timeout harness, scoring, logging
# ──────────────────────────────────────────────────────────────────────────────


async def _run_with_timeout(fn: Callable[[], Any], timeout_s: float) -> Tuple[bool, Any]:
    """
    Run a blocking function in a worker thread and race a timeout.

    Returns:
        (ok, value) on success,
        (False, "timeout") on timeout,
        (False, Exception) on error.

    Design:
        - The worker runs in a thread via anyio.to_thread.run_sync.
        - The main task awaits a memory channel receive with a move_on_after timeout.
        - We never block the event loop; the worker may complete later but we return promptly.
    """
    send, recv = anyio.create_memory_object_stream(1)

    async def _runner() -> None:
        def _work():
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                return e

        result = await anyio.to_thread.run_sync(_work)
        # send is async; dispatch from thread-safe context is not needed here
        await send.send(result)

    result: Any = None
    async with anyio.create_task_group() as tg:
        tg.start_soon(_runner)
        with anyio.move_on_after(timeout_s) as scope:
            result = await recv.receive()
        tg.cancel_scope.cancel()

    if scope.cancel_called:
        return False, "timeout"
    if isinstance(result, Exception):
        return False, result
    return True, result


def _score_of(row: dict) -> float:
    """
    Accept 'score' or 'similarity'; coerce to float; clamp into [0,1].
    - If score already in [0,1], keep it.
    - If cosine similarity in [-1,1], map to [0,1] via (x+1)/2.
    - If arbitrary positive score, squash with logistic curve and clamp.
    """
    v = (row or {}).get("score", (row or {}).get("similarity"))
    try:
        x = float(v)
    except Exception:
        return -math.inf
    if math.isnan(x) or math.isinf(x):
        return -math.inf
    if 0.0 <= x <= 1.0:
        return x
    if -1.0 <= x <= 1.0:
        return max(0.0, min(1.0, 0.5 + 0.5 * x))  # shift/scale cosine
    # Logistic squash for large positives (clamped)
    x = min(x, 20.0)
    return 1.0 / (1.0 + math.exp(-x))


def _log_search_event(event: str, **data: Any) -> None:
    try:
        _LOG.info("%s %s", event, {k: v for k, v in data.items()})
    except Exception:
        pass
    try:
        _structured_log_event(event, data)  # best-effort external logger
    except Exception:
        pass


def _corr_id(req: Optional[Request]) -> str:
    try:
        return getattr(getattr(req, "state", None), "corr_id", "") or ""
    except Exception:
        return ""


def _json_503(reason: str, **extra: Any) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "status": 503,
            "reason": reason,
            **({"impl": IMPL_MARKER} if IMPL_MARKER else {}),
            **extra,
        },
    )


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────


class SearchQuery(BaseModel):
    query: str
    # Guardrails: bound server work; matches GET default, adds upper bound for POST
    k: int = Field(10, ge=1, le=100)
    search_type: Optional[str] = "all"  # "code" | "doc" | "all"


# ──────────────────────────────────────────────────────────────────────────────
# POST /kb/search — semantic-first search (async, timeout-safe)
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/search")
async def search_kb(
    q: SearchQuery,
    request: Request,
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    user_id = x_user_id or "anonymous"
    corr_id = _corr_id(request)
    t0 = time.perf_counter()
    source = "none"
    rows: List[dict] = []

    # 1) Semantic fast path
    if sem_search is not None:
        try:
            def _sem_call():
                try:
                    return sem_search(query=q.query, k=q.k) or []
                except TypeError:
                    return sem_search(q=q.query, k=q.k) or []

            ok, res = await _run_with_timeout(_sem_call, KB_SEARCH_TIMEOUT_S)
            if ok and res:
                rows = res
                source = "semantic"
            elif not ok and res == "timeout":
                took_ms = int((time.perf_counter() - t0) * 1000)
                _log_search_event(
                    "kb.search.timeout",
                    corr_id=corr_id,
                    path="POST",
                    source="semantic",
                    timeout_s=KB_SEARCH_TIMEOUT_S,
                    took_ms=took_ms,
                    k=q.k,
                    query_len=len(q.query or ""),
                    allow_fallback=ALLOW_KB_FALLBACK,
                )
                return _json_503("semantic_timeout", timeout_s=KB_SEARCH_TIMEOUT_S)
        except Exception:
            rows = []

    # 2) Optional fallback to KB service (heavier)
    if not rows and ALLOW_KB_FALLBACK:
        try:
            def _kb_call():
                try:
                    # Prefer passing search_type if accepted by the service
                    return kb_service.search(
                        q=q.query, limit=q.k, offset=0, search_type=q.search_type
                    ) or []
                except TypeError:
                    return kb_service.search(q=q.query, limit=q.k, offset=0) or []

            ok, res = await _run_with_timeout(_kb_call, KB_SEARCH_TIMEOUT_S)
            if not ok and res == "timeout":
                took_ms = int((time.perf_counter() - t0) * 1000)
                _log_search_event(
                    "kb.search.timeout",
                    corr_id=corr_id,
                    path="POST",
                    source="fallback",
                    timeout_s=KB_SEARCH_TIMEOUT_S,
                    took_ms=took_ms,
                    k=q.k,
                    query_len=len(q.query or ""),
                    allow_fallback=ALLOW_KB_FALLBACK,
                )
                return _json_503("kb_timeout", timeout_s=KB_SEARCH_TIMEOUT_S)
            if not ok and isinstance(res, Exception):
                raise res
            rows = res or []
            source = "fallback" if rows else source
        except Exception as e:  # noqa: BLE001
            took_ms = int((time.perf_counter() - t0) * 1000)
            _log_search_event(
                "kb.search.error",
                corr_id=corr_id,
                path="POST",
                source="fallback",
                error=str(e),
                took_ms=took_ms,
                k=q.k,
                query_len=len(q.query or ""),
            )
            return _json_503("kb_error", error=str(e))

    # 3) Normalize & filter
    normalized: List[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        s = _score_of(r)
        if s < SEMANTIC_SCORE_THRESHOLD:
            continue
        n = dict(r)
        n["score"] = s
        normalized.append(n)

    took_ms = int((time.perf_counter() - t0) * 1000)
    _log_search_event(
        "kb.search.ok",
        corr_id=corr_id,
        path="POST",
        source=source,
        took_ms=took_ms,
        k=q.k,
        count=len(normalized),
        threshold=SEMANTIC_SCORE_THRESHOLD,
        timeout_s=KB_SEARCH_TIMEOUT_S,
        allow_fallback=ALLOW_KB_FALLBACK,
        query_len=len(q.query or ""),
        user_id=user_id,
    )
    return {
        "ok": True,
        "threshold": SEMANTIC_SCORE_THRESHOLD,
        "count": len(normalized),
        "results": normalized,
        **({"impl": IMPL_MARKER} if IMPL_MARKER else {}),
    }


# ──────────────────────────────────────────────────────────────────────────────
# GET /kb/search — convenience GET variant (same behavior/shape)
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/search")
async def search_kb_get(
    request: Request,
    query: str = Query(...),
    k: int = Query(10, ge=1, le=1000),
    search_type: Optional[str] = Query("all"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
):
    user_id = x_user_id or "anonymous"
    corr_id = _corr_id(request)
    t0 = time.perf_counter()
    source = "none"
    rows: List[dict] = []

    # 1) Semantic fast path
    if sem_search is not None:
        try:
            def _sem_call():
                try:
                    return sem_search(query=query, k=k) or []
                except TypeError:
                    return sem_search(q=query, k=k) or []

            ok, res = await _run_with_timeout(_sem_call, KB_SEARCH_TIMEOUT_S)
            if ok and res:
                rows = res
                source = "semantic"
            elif not ok and res == "timeout":
                took_ms = int((time.perf_counter() - t0) * 1000)
                _log_search_event(
                    "kb.search.timeout",
                    corr_id=corr_id,
                    path="GET",
                    source="semantic",
                    timeout_s=KB_SEARCH_TIMEOUT_S,
                    took_ms=took_ms,
                    k=k,
                    query_len=len(query or ""),
                    allow_fallback=ALLOW_KB_FALLBACK,
                )
                return _json_503("semantic_timeout", timeout_s=KB_SEARCH_TIMEOUT_S)
        except Exception:
            rows = []

    # 2) Optional fallback to KB service
    if not rows and ALLOW_KB_FALLBACK:
        try:
            def _kb_call():
                try:
                    return kb_service.search(
                        q=query, limit=k, offset=0, search_type=search_type
                    ) or []
                except TypeError:
                    return kb_service.search(q=query, limit=k, offset=0) or []

            ok, res = await _run_with_timeout(_kb_call, KB_SEARCH_TIMEOUT_S)
            if not ok and res == "timeout":
                took_ms = int((time.perf_counter() - t0) * 1000)
                _log_search_event(
                    "kb.search.timeout",
                    corr_id=corr_id,
                    path="GET",
                    source="fallback",
                    timeout_s=KB_SEARCH_TIMEOUT_S,
                    took_ms=took_ms,
                    k=k,
                    query_len=len(query or ""),
                    allow_fallback=ALLOW_KB_FALLBACK,
                )
                return _json_503("kb_timeout", timeout_s=KB_SEARCH_TIMEOUT_S)
            if not ok and isinstance(res, Exception):
                raise res
            rows = res or []
            source = "fallback" if rows else source
        except Exception as e:  # noqa: BLE001
            took_ms = int((time.perf_counter() - t0) * 1000)
            _log_search_event(
                "kb.search.error",
                corr_id=corr_id,
                path="GET",
                source="fallback",
                error=str(e),
                took_ms=took_ms,
                k=k,
                query_len=len(query or ""),
            )
            return _json_503("kb_error", error=str(e))

    # 3) Normalize & filter
    normalized: List[dict] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        s = _score_of(r)
        if s < SEMANTIC_SCORE_THRESHOLD:
            continue
        n = dict(r)
        n["score"] = s
        normalized.append(n)

    took_ms = int((time.perf_counter() - t0) * 1000)
    _log_search_event(
        "kb.search.ok",
        corr_id=corr_id,
        path="GET",
        source=source,
        took_ms=took_ms,
        k=k,
        count=len(normalized),
        threshold=SEMANTIC_SCORE_THRESHOLD,
        timeout_s=KB_SEARCH_TIMEOUT_S,
        allow_fallback=ALLOW_KB_FALLBACK,
        query_len=len(query or ""),
        user_id=user_id,
    )
    return {
        "ok": True,
        "threshold": SEMANTIC_SCORE_THRESHOLD,
        "count": len(normalized),
        "results": normalized,
        **({"impl": IMPL_MARKER} if IMPL_MARKER else {}),
    }


# ──────────────────────────────────────────────────────────────────────────────
# POST /kb/warmup — prime semantic + fallback paths (idempotent)
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/warmup")
async def kb_warmup():
    # ──────────────────────────────────────────────────────────────────────────
    # Change: Time-bound warmup; return structured 503 on timeout
    # Why: Align with contract (503 JSON; never 504)
    # ──────────────────────────────────────────────────────────────────────────
    try:
        # Time-bound both warmups to avoid startup stalls
        if sem_search is not None:
            def _sem():
                try:
                    return sem_search(query="warmup", k=1)
                except TypeError:
                    return sem_search(q="warmup", k=1)
            ok_sem, _ = await _run_with_timeout(_sem, timeout_s=10.0)
            if not ok_sem:
                return _json_503("warmup_semantic_timeout", timeout_s=10.0)

        def _kb():
            return kb_service.search(q="warmup", limit=1, offset=0) or []
        ok_fb, _ = await _run_with_timeout(_kb, timeout_s=10.0)
        if not ok_fb:
            return _json_503("warmup_kb_timeout", timeout_s=10.0)

        return {"ok": True, "warmed": True, **({"impl": IMPL_MARKER} if IMPL_MARKER else {})}
    except Exception as e:  # noqa: BLE001
        return _json_503("warmup_error", error=str(e))


# ──────────────────────────────────────────────────────────────────────────────
# GET /kb/summary — tolerant wrapper over services.kb shim
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/summary")
async def get_summary(x_user_id: Optional[str] = Header(None, alias="X-User-Id")):
    user_id = x_user_id or "anonymous"
    try:
        data = kb_service.get_recent_summaries(user_id=user_id)
        # Normalize shape (services.kb shim returns {ok, items, note?})
        if isinstance(data, dict) and "ok" in data:
            return data
        return {"ok": True, "items": data or []}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "items": [], "error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# POST /kb/reindex — prefer semantic path; preserve legacy fields
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/reindex")
async def reindex_kb():
    try:
        # Pass through exactly (contracts enforced at services layer)
        resp = kb_service.api_reindex()
        return resp
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"KB reindex failed: {e}")
