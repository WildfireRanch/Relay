# File: agents/mcp_agent.py
# Purpose: Orchestrate MCP (plan → context → dispatch) with lazy imports to avoid
#          circular imports; emit structured grounding and kb stats; robust logging.
#
# Returned dict contract (stable; never raises):
# {
#   "plan": dict,                        # planner output (may include final_answer, route, _diag)
#   "routed_result": dict|str,           # normalized to include {"response": str|{"text":...}, "route": str, "grounding": [...]}
#   "critics": list|None,                # (reserved)
#   "context": str,                      # pretty context (optional, for debugging/traceability)
#   "files_used": list,                  # [{path, tier, score}, ...] where available
#   "meta": {
#     "request_id": str,                 # corr_id propagated by routes
#     "route": str,                      # chosen route (echo/docs/codex/…)
#     "origin": str,                     # planner-suggested route or final route
#     "timings_ms": { planner_ms, context_ms, dispatch_ms, total_ms },
#     "planner_diag": dict,              # pass-through diagnostics from planner
#     "kb": { "hits": int, "max_score": float|None, "sources": [{path, score}, ...] }
#   }
# }
#
# IMPORTANT
# - No top-level imports of other agents or core modules (prevents init-time cycles).
# - All heavy imports happen inside helper functions right before first use.
# - This file must NOT import routes.* or main.

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

# ── Logging shim (prefer core.logging; safe fallback) ────────────────────────
try:
    from core.logging import log_event  # type: ignore
except Exception:  # pragma: no cover
    import logging
    _LOG = logging.getLogger("relay.mcp_agent")
    def log_event(event: str, data: Dict[str, Any] | None = None) -> None:
        _LOG.info("event=%s data=%s", event, (data or {}))

# ── Tunables (env) ───────────────────────────────────────────────────────────
KB_MIN_SCORE_FLOOR: float = float(os.getenv("KB_MIN_SCORE_FLOOR", "0.0"))  # drop weak retrievals
KB_TOPK_LIMIT: int = int(os.getenv("KB_TOPK_LIMIT", "10"))                 # surface at most N sources
MCP_DEFAULT_ROUTE: str = os.getenv("MCP_DEFAULT_ROUTE", "echo")            # fallback route if planner fails


# ── Small utilities (pure, no external imports) ──────────────────────────────
def _max_score(matches: List[Dict[str, Any]]) -> Optional[float]:
    """Return max(score) across matches (None if empty/unparseable)."""
    mx = None
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
    Normalize grounding matches and apply min-score floor + top-k cap.
    Ensures each entry is {"path": str, "score": float}.
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
    Normalize a routed result to at least:
      {"response": str|{"text": str}, "route": str, "grounding": optional[list]}
    """
    if isinstance(raw, dict):
        route = raw.get("route") or MCP_DEFAULT_ROUTE
        response = raw.get("response")
        if isinstance(response, dict):
            txt = response.get("text") or raw.get("answer") or ""
            meta = response.get("meta") or {}
            return {"response": {"text": txt, "meta": meta}, "route": route}
        if isinstance(response, str):
            return {"response": response, "route": route}
        if isinstance(raw.get("answer"), str):
            return {"response": raw["answer"], "route": route}
        return {"response": "", "route": route}
    elif isinstance(raw, str):
        return {"response": raw, "route": MCP_DEFAULT_ROUTE}
    return {"response": "", "route": MCP_DEFAULT_ROUTE}


# ── Lazy-imported stage helpers (prevents circular imports) ──────────────────
def _plan(query: str, files: List[str], topics: List[str], debug: bool, corr_id: str) -> Dict[str, Any]:
    """
    Invoke the planner. Imported LAZILY to avoid agent↔agent cycles.
    Expected to return a dict that may include {"route": "...", "_diag": {...}, "final_answer": "..."}.
    """
    try:
        from agents.planner_agent import plan  # type: ignore  # LAZY
    except Exception as e:
        log_event("mcp_plan_import_error", {"corr_id": corr_id, "error": str(e)})
        return {"route": MCP_DEFAULT_ROUTE, "_diag": {"plan_import_error": True, "error": str(e)}}

    try:
        return plan(query=query, files=files, topics=topics, debug=debug, corr_id=corr_id) or {}
    except Exception as e:
        log_event("mcp_plan_error", {"corr_id": corr_id, "error": str(e)})
        return {"route": MCP_DEFAULT_ROUTE, "_diag": {"plan_error": True, "error": str(e)}}


def _build_context(query: str, files: List[str], topics: List[str], debug: bool, corr_id: str) -> Dict[str, Any]:
    """
    Build retrieval context and provide STRUCTURED matches.
    Returns:
      {"context": str, "files_used": [...], "matches": [{"path":..., "score":...}, ...]}
    """
    try:
        from core.context_engine import build_context  # type: ignore  # LAZY
    except Exception as e:
        log_event("mcp_ctx_import_error", {"corr_id": corr_id, "error": str(e)})
        return {"context": "", "files_used": [], "matches": []}

    try:
        ctx = build_context(query=query, files=files, topics=topics, debug=debug, corr_id=corr_id) or {}
        context = str(ctx.get("context") or "")
        files_used = ctx.get("files_used") or []
        matches = _filter_matches(ctx.get("matches") or [])
        return {"context": context, "files_used": files_used, "matches": matches}
    except Exception as e:
        log_event("mcp_context_error", {"corr_id": corr_id, "error": str(e)})
        return {"context": "", "files_used": [], "matches": []}


def _dispatch(route: str, query: str, context: str, user_id: str, debug: bool, corr_id: str) -> Dict[str, Any]:
    """
    Dispatch to a concrete agent. Default to echo; never raise.
    You can later branch on `route` (docs/codex/control/etc).
    """
    try:
        from agents.echo_agent import invoke as echo_invoke  # type: ignore  # LAZY
        text = echo_invoke(query=query, context=context, user_id=user_id, corr_id=corr_id)
        return {"response": text, "route": route or MCP_DEFAULT_ROUTE}
    except Exception as e:
        log_event("mcp_dispatch_error", {"corr_id": corr_id, "error": str(e), "route": route})
        return {"response": "", "route": route or MCP_DEFAULT_ROUTE}


# ── Public API ───────────────────────────────────────────────────────────────
async def run_mcp(
    query: str,
    role: Optional[str] = "planner",
    files: Optional[List[str]] = None,
    topics: Optional[List[str]] = None,
    user_id: str = "anonymous",
    debug: bool = False,
    corr_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Orchestrate plan → context → dispatch.
    - Uses LAZY imports inside helpers to avoid circular imports.
    - Attaches structured grounding; computes kb stats.
    - Emits detailed logs for each stage with corr_id.
    - Returns a stable dict (never raises), so routes can normalize safely.
    """
    cid = corr_id or str(uuid4())
    t0 = time.perf_counter()

    log_event("mcp_start", {"corr_id": cid, "role": role, "user": user_id, "debug": debug})

    # 1) Plan
    t_pl0 = time.perf_counter()
    plan = _plan(query=query, files=files or [], topics=topics or [], debug=debug, corr_id=cid)
    t_pl1 = time.perf_counter()

    route = plan.get("route") or role or MCP_DEFAULT_ROUTE

    # 2) Context
    t_ctx0 = time.perf_counter()
    ctx = _build_context(query=query, files=files or [], topics=topics or [], debug=debug, corr_id=cid)
    context = str(ctx.get("context") or "")
    files_used = ctx.get("files_used") or []
    matches = ctx.get("matches") or []  # already normalized + filtered + top-k
    t_ctx1 = time.perf_counter()

    # 3) Dispatch
    t_ds0 = time.perf_counter()
    routed_raw = _dispatch(route=route, query=query, context=context, user_id=user_id, debug=debug, corr_id=cid)
    t_ds1 = time.perf_counter()
    routed_result = _shape_routed_result(routed_raw)

    # 4) Attach structured grounding to result (always present as list)
    if isinstance(routed_result, dict):
        existing = routed_result.get("grounding")
        if not isinstance(existing, list) or not existing:
            routed_result["grounding"] = matches  # may be []

    # 5) Meta (timings + kb stats)
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
            "hits": len(matches),
            "max_score": _max_score(matches),
            "sources": matches,  # explicit copy for easy inspection/UX
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
        "plan": plan,
        "routed_result": routed_result,
        "critics": None,            # hook up critics when ready
        "context": context,
        "files_used": files_used,
        "meta": meta,
    }
