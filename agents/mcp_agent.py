# ──────────────────────────────────────────────────────────────────────────────
# File: agents/mcp_agent.py
# Purpose: Orchestrate MCP (plan → context → dispatch) with lazy imports, tiered
#          retrieval via core.context_engine (GLOBAL + PROJECT_DOCS), kwargs
#          filtering to avoid TypeError, and null-safe KB meta.
# Contract: async run_mcp(...) -> stable dict; never raises.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import inspect
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Local logging is lightweight / no circular deps
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    def log_event(event: str, data: Optional[Dict[str, Any]] = None) -> None:
        pass

# Constants
MCP_DEFAULT_ROUTE = "echo"
KB_TOPK_LIMIT = 12
KB_MIN_SCORE_FLOOR = 0.0  # engine already thresholds per-tier

# ── Small utils ───────────────────────────────────────────────────────────────

def _jsonable(obj: Any) -> Any:
    try:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {str(k): _jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [_jsonable(x) for x in obj]
        if hasattr(obj, "model_dump"):
            return obj.model_dump()  # pydantic v2
        if hasattr(obj, "dict"):
            return obj.dict()  # pydantic v1
        return str(obj)
    except Exception:
        return "[unserializable]"

def _filter_kwargs(fn, **kw) -> Dict[str, Any]:
    """
    Retain only kwargs present in callable's signature (prevents TypeError).
    Accepts functions or coroutine functions.
    """
    try:
        sig = inspect.signature(fn)
        out = {}
        for k, v in kw.items():
            if k in sig.parameters or any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
                out[k] = v
        return out
    except Exception:
        return kw

def _max_score(matches: List[Dict[str, Any]]) -> Optional[float]:
    """Return max(score) across matches; None if none parseable."""
    mx: Optional[float] = None
    for m in matches or []:
        s = m.get("score")
        try:
            f = float(s) if s is not None else None
        except Exception:
            f = None
        if f is None:
            continue
        mx = f if mx is None else max(mx, f)
    return mx

def _filter_matches(matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize grounding matches and apply a final top-K cap for payload size.
    Each entry → {"path": str, "score": float}
    """
    out: List[Dict[str, Any]] = []
    for m in matches or []:
        path = (m.get("path") or "").strip()
        try:
            score = float(m.get("score")) if m.get("score") is not None else 0.0
        except Exception:
            score = 0.0
        if not path:
            continue
        if score < KB_MIN_SCORE_FLOOR:
            continue
        out.append({"path": path, "score": score})
    return out[:KB_TOPK_LIMIT]

def _shape_routed_result(raw: Any) -> Dict[str, Any]:
    """
    Normalize routed result to:
      {"response": str|{"text": str, "meta": {...}}, "route": str, "grounding": optional[list]}
    """
    if isinstance(raw, dict):
        route = raw.get("route") or MCP_DEFAULT_ROUTE
        response = raw.get("response")
        if isinstance(response, dict):
            txt = response.get("text") or raw.get("answer") or ""
            meta = response.get("meta") or {}
            return {"response": {"text": txt, "meta": meta}, "route": route}
        elif isinstance(response, str):
            return {"response": response, "route": route}
        # Fallback
        txt = raw.get("answer") or raw.get("text") or ""
        return {"response": {"text": txt, "meta": {}}, "route": route}
    elif isinstance(raw, str):
        return {"response": raw, "route": MCP_DEFAULT_ROUTE}
    return {"response": "", "route": MCP_DEFAULT_ROUTE}

# ── Lazy helpers (avoid import cycles) ────────────────────────────────────────

def _plan(query: str, files: List[str], topics: List[str], debug: bool, corr_id: str) -> Dict[str, Any]:
    """
    Invoke planner; tolerant to async/sync and unknown kwargs.
    """
    try:
        from agents import planner_agent  # type: ignore
        plan_fn = getattr(planner_agent, "plan")
    except Exception as e:
        log_event("mcp_plan_import_error", {"corr_id": corr_id, "error": str(e)})
        return {"route": MCP_DEFAULT_ROUTE, "_diag": {"plan_import_error": True, "error": str(e)}}

    call_kwargs = {
        "query": query,
        "files": files,
        "topics": topics,
        "debug": debug,
        # Pass both names; planner can ignore
        "corr_id": corr_id,
        "request_id": corr_id,
    }
    call_kwargs = _filter_kwargs(plan_fn, **call_kwargs)

    try:
        # If coroutine function or returns coroutine, run it
        res = plan_fn(**call_kwargs)
        if inspect.iscoroutine(res):
            import asyncio
            res = asyncio.get_event_loop().run_until_complete(res)  # routes already run in event loop; safe since planner is now sync. Guard anyway.
        return res or {}
    except RuntimeError:
        # In case we're already in an event loop (FastAPI), use asyncio.create_task workaround
        import asyncio
        async def _co():
            r = plan_fn(**call_kwargs)
            return await r if inspect.iscoroutine(r) else r
        res = asyncio.get_event_loop().run_until_complete(_co())
        return res or {}
    except Exception as e:
        log_event("mcp_plan_error", {"corr_id": corr_id, "error": str(e)})
        return {"route": MCP_DEFAULT_ROUTE, "_diag": {"plan_error": True, "error": str(e)}}

def _build_context(query: str, debug: bool, corr_id: str) -> Dict[str, Any]:
    try:
        from core.context_engine import (
            build_context, ContextRequest, EngineConfig, RetrievalTier,
        )
        from services.semantic_retriever import TieredSemanticRetriever
    except Exception as e:
        log_event("mcp_ctx_import_error", {"corr_id": corr_id, "error": str(e)})
        return {"context": "", "files_used": [], "matches": []}

    retrievers = {
        RetrievalTier.GLOBAL:       TieredSemanticRetriever("global"),
        RetrievalTier.PROJECT_DOCS: TieredSemanticRetriever("project_docs"),
    }
    req = ContextRequest(query=query, corr_id=corr_id)
    cfg = EngineConfig(retrievers=retrievers)

    try:
        ctx = build_context(req=req, cfg=cfg)

        # Support both object and dict shapes
        if isinstance(ctx, dict):
            context_text = str(ctx.get("context") or "")
            # prefer explicit lists if present; fall back gracefully
            used = ctx.get("used") or ctx.get("files_used") or []
            matches = ctx.get("matches") or ctx.get("grounding") or []
            files_used = []
            for r in used:
                if isinstance(r, dict):
                    files_used.append({
                        "path": (r.get("path") or r.get("file") or "").strip(),
                        "tier": (r.get("tier") or r.get("source") or "unknown"),
                        "score": r.get("score"),
                    })
            norm_matches = []
            for m in matches:
                if isinstance(m, dict):
                    norm_matches.append({
                        "path": (m.get("path") or m.get("file") or "").strip(),
                        "score": m.get("score"),
                    })
            return {"context": context_text, "files_used": files_used, "matches": norm_matches}

        # object shape (preferred)
        context_text = str(getattr(ctx, "context", "") or "")
        used = getattr(ctx, "used", []) or []
        matches = getattr(ctx, "matches", []) or []
        files_used = [{"path": getattr(r, "path", ""), "tier": getattr(getattr(r, "tier", None), "value", None) or getattr(r, "tier", None), "score": getattr(r, "score", None)} for r in used if r]
        norm_matches = [{"path": getattr(m, "path", ""), "score": getattr(m, "score", None)} for m in matches if m]
        return {"context": context_text, "files_used": files_used, "matches": norm_matches}

    except Exception as e:
        log_event("mcp_context_error", {"corr_id": corr_id, "error": str(e)})
        return {"context": "", "files_used": [], "matches": []}


def _dispatch(route: str, query: str, context: str, user_id: str, debug: bool, corr_id: str) -> Dict[str, Any]:
    """
    Dispatch to a concrete agent. Default to echo.invoke; never raise.
    """
    try:
        from agents.echo_agent import invoke as echo_invoke  # type: ignore
        text = echo_invoke(query=query, context=context, user_id=user_id, corr_id=corr_id, debug=debug)
        return {"response": text, "route": route or MCP_DEFAULT_ROUTE}
    except Exception as e:
        log_event("mcp_dispatch_error", {"corr_id": corr_id, "error": str(e), "route": route})
        return {"response": "", "route": route or MCP_DEFAULT_ROUTE}

# ── Public API ────────────────────────────────────────────────────────────────

async def run_mcp(
    *,
    query: str,
    role: Optional[str] = "planner",
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    user_id: str = "anonymous",
    debug: bool = False,
    corr_id: Optional[str] = None,
    **_: Any,   # tolerate unexpected kwargs like `context`
) -> Dict[str, Any]:
    
    """
    Orchestrates: plan → context → dispatch. Returns a stable dict; never raises.
    """
    cid = corr_id or str(uuid4())
    t0 = time.perf_counter()
    log_event("mcp_start", {"corr_id": cid, "role": role, "user": user_id, "debug": debug})

    # 1) Plan
    t_pl0 = time.perf_counter()
    plan = _plan(query=query, files=files or [], topics=topics or [], debug=debug, corr_id=cid)
    t_pl1 = time.perf_counter()
    route = (plan.get("route") or role or MCP_DEFAULT_ROUTE).strip() or MCP_DEFAULT_ROUTE

    # 2) Context (GLOBAL + PROJECT_DOCS)
    t_ctx0 = time.perf_counter()
    ctx = _build_context(query=query, debug=debug, corr_id=cid)
    context = str(ctx.get("context") or "")
    files_used = ctx.get("files_used") or []
    matches = _filter_matches(ctx.get("matches") or [])
    t_ctx1 = time.perf_counter()

    # 3) Dispatch
    t_ds0 = time.perf_counter()
    routed_raw = _dispatch(route=route, query=query, context=context, user_id=user_id, debug=debug, corr_id=cid)
    t_ds1 = time.perf_counter()
    routed_result = _shape_routed_result(routed_raw)

    # 4) Attach structured grounding (list) if missing
    if isinstance(routed_result, dict):
        if not isinstance(routed_result.get("grounding"), list):
            routed_result["grounding"] = matches  # may be []

    # 5) Meta (timings + null-safe kb stats)
    kb_hits = len(matches)
    kb_max = _max_score(matches)  # may be None
    meta: Dict[str, Any] = {
        "request_id": cid,
        "origin": plan.get("route") or route,
        "route": route,
        "timings_ms": {
            "planner_ms": int((t_pl1 - t_pl0) * 1000),
            "context_ms": int((t_ctx1 - t_ctx0) * 1000),
            "dispatch_ms": int((t_ds1 - t_ds0) * 1000),
            "total_ms": int((time.perf_counter() - t0) * 1000),
        },
        "planner_diag": plan.get("_diag") or {},
        "kb": {
            "hits": int(kb_hits),
            "max_score": (None if kb_max is None else float(kb_max)),
            "sources": matches,  # explicit for UX/inspection
        },
    }

    log_event("mcp_done", {
        "corr_id": cid,
        "route": route,
        "kb_hits": meta["kb"]["hits"],
        "kb_max_score": meta["kb"]["max_score"],
        "total_ms": meta["timings_ms"]["total_ms"],
    })

    return {
        "plan": _jsonable(plan),
        "routed_result": _jsonable(routed_result),
        "critics": None,
        "context": context,
        "files_used": files_used,
        "meta": meta,
    }
